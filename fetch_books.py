import json
import os
import random
import re
import shutil
import time
from datetime import datetime, timedelta, timezone

import requests
from PIL import Image, ImageFilter

# ================= Configuration =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "duguBoss/daily-book-hub")
GITHUB_BRANCH = "main"
BEIJING_TZ = timezone(timedelta(hours=8))
TODAY_DATE = datetime.now(BEIJING_TZ)
IMAGE_DIR = f"images/{TODAY_DATE.strftime('%Y-%m-%d')}"
MAX_SOURCE_FETCH_RETRIES = 8
MAX_PAIR_RETRIES = 6
HISTORY_PATH = "history.json"
GEMINI_MODELS = [
    model.strip()
    for model in os.environ.get(
        "GEMINI_MODELS",
        "gemini-3-flash-preview,gemini-2.5-flash,gemini-2.0-flash",
    ).split(",")
    if model.strip()
]
GEMINI_MODEL_RETRIES = 3

TOP_GIF = "https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif"
BOTTOM_GIF = "https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif"
WECHAT_SIDE_SPACING_PX = 0


# ================= Utilities =================
def minify_html(html):
    html = html.replace('"', "'")
    html = html.replace("\\", "")
    html = re.sub(r"[\r\n\t]+", "", html)
    html = re.sub(r">\s+<", "><", html)
    html = re.sub(r"\s{2,}", " ", html)
    return html.strip()


def normalize_text(text):
    value = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", value).strip()


def get_book_signature(title, authors):
    author = authors[0] if authors else ""
    return normalize_text(f"{title} {author}")


def clear_images_weekly():
    if TODAY_DATE.weekday() == 0 and os.path.exists("images"):
        shutil.rmtree("images")
    os.makedirs(IMAGE_DIR, exist_ok=True)


def get_github_url(local_path):
    if not local_path:
        return ""
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"


def download(url, name):
    target_path = f"{IMAGE_DIR}/{name}"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        res.raise_for_status()
        with open(target_path, "wb") as file:
            file.write(res.content)
        return target_path
    except Exception:
        return None


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return {"books": [], "signatures": [], "daily_pairs": []}

    with open(HISTORY_PATH, "r", encoding="utf-8") as file:
        raw_data = json.load(file)

    # Backward compatible: previous format was a flat ID list.
    if isinstance(raw_data, list):
        unique_ids = list(dict.fromkeys(item for item in raw_data if isinstance(item, str) and item))
        return {"books": unique_ids, "signatures": [], "daily_pairs": []}

    if not isinstance(raw_data, dict):
        return {"books": [], "signatures": [], "daily_pairs": []}

    books = raw_data.get("books", [])
    signatures = raw_data.get("signatures", [])
    daily_pairs = raw_data.get("daily_pairs", [])

    books = list(dict.fromkeys(item for item in books if isinstance(item, str) and item))
    signatures = list(dict.fromkeys(item for item in signatures if isinstance(item, str) and item))
    daily_pairs = [item for item in daily_pairs if isinstance(item, dict)]

    return {"books": books, "signatures": signatures, "daily_pairs": daily_pairs}


def save_history(history_state, b1, b2):
    books = list(dict.fromkeys(history_state.get("books", []) + [b1["id"], b2["id"]]))
    signatures = list(dict.fromkeys(history_state.get("signatures", []) + [b1["signature"], b2["signature"]]))
    today_pair = {
        "date": TODAY_DATE.strftime("%Y-%m-%d"),
        "books": [b1["id"], b2["id"]],
        "signatures": [b1["signature"], b2["signature"]],
    }
    daily_pairs = history_state.get("daily_pairs", [])
    daily_pairs = [item for item in daily_pairs if item.get("date") != today_pair["date"]]
    daily_pairs.append(today_pair)
    daily_pairs = daily_pairs[-90:]

    payload = {"books": books[-1200:], "signatures": signatures[-1200:], "daily_pairs": daily_pairs}
    with open(HISTORY_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def fetch_source_items(source):
    if source == "gutenberg":
        url = f"https://gutendex.com/books/?page={random.randint(1, 500)}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json().get("results", [])

    url = f"https://openlibrary.org/search.json?subject=literature&limit=20&offset={random.randint(0, 500)}"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json().get("docs", [])


def parse_book_item(source, item):
    if source == "gutenberg":
        book_id = item.get("id")
        if not book_id:
            return None
        authors = [author.get("name", "") for author in item.get("authors", []) if isinstance(author, dict)]
        cover = item.get("formats", {}).get("image/jpeg")
        book_id = f"gutenberg_{book_id}"
        title = (item.get("title") or "").strip() or "Unknown"
    else:
        key = (item.get("key") or "").strip()
        if not key:
            return None
        doc_id = key.split("/")[-1]
        cover_i = item.get("cover_i")
        if not cover_i:
            return None
        authors = item.get("author_name") or []
        if not isinstance(authors, list):
            authors = []
        cover = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg"
        book_id = f"openlibrary_{doc_id}"
        title = (item.get("title") or "").strip() or "Unknown"

    if not cover:
        return None

    signature = get_book_signature(title, authors)
    if not signature:
        return None

    return {
        "id": book_id,
        "title": title,
        "authors": [a.strip() for a in authors if isinstance(a, str) and a.strip()],
        "cover": cover,
        "signature": signature,
    }


def get_book(history_ids, history_signatures, source, exclude_ids=None, exclude_signatures=None):
    exclude_ids = exclude_ids or set()
    exclude_signatures = exclude_signatures or set()

    for _ in range(MAX_SOURCE_FETCH_RETRIES):
        try:
            items = fetch_source_items(source)
            random.shuffle(items)
            for item in items:
                book = parse_book_item(source, item)
                if not book:
                    continue
                if book["id"] in history_ids or book["id"] in exclude_ids:
                    continue
                if book["signature"] in history_signatures or book["signature"] in exclude_signatures:
                    continue
                return book
        except Exception:
            time.sleep(2)
    return None


def pick_daily_books(history_state):
    history_ids = set(history_state.get("books", []))
    history_signatures = set(history_state.get("signatures", []))

    for _ in range(MAX_PAIR_RETRIES):
        first_book = get_book(history_ids, history_signatures, "gutenberg")
        if not first_book:
            continue

        second_book = get_book(
            history_ids,
            history_signatures,
            "openlibrary",
            exclude_ids={first_book["id"]},
            exclude_signatures={first_book["signature"]},
        )

        if not second_book:
            continue
        if first_book["signature"] == second_book["signature"]:
            continue
        return first_book, second_book

    return None, None


def parse_model_json(text):
    cleaned = re.sub(r"```json\s*|```", "", (text or "")).strip()
    if not cleaned:
        raise ValueError("Model returned empty text.")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"Model output is not valid JSON. Output preview: {cleaned[:300]}")
        return json.loads(cleaned[start : end + 1])


def extract_gemini_text(payload):
    if not isinstance(payload, dict):
        raise ValueError("Gemini response payload is not a JSON object.")

    if isinstance(payload.get("error"), dict):
        error = payload["error"]
        code = error.get("code", "unknown")
        message = error.get("message", "unknown error")
        status = error.get("status", "UNKNOWN")
        raise RuntimeError(f"Gemini API error ({code}/{status}): {message}")

    candidates = payload.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text

    prompt_feedback = payload.get("promptFeedback")
    finish_reasons = [c.get("finishReason") for c in candidates if isinstance(c, dict)]
    raise RuntimeError(
        f"Gemini returned no usable candidates. finishReasons={finish_reasons}, promptFeedback={prompt_feedback}"
    )


def request_gemini(prompt, model_name):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    response = requests.post(
        url,
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=45,
    )

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text[:500]}

    if response.status_code >= 400:
        message = payload.get("error", {}).get("message", str(payload))
        raise RuntimeError(f"Gemini HTTP {response.status_code} with model {model_name}: {message}")

    return payload


def generate_content(b1, b2):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    prompt = f"""
You are a WeChat growth editor. Write a high-quality book recommendation article that is more likely
to perform well in WeChat recommendation distribution (high readability, useful information, and healthy interaction).
Book inputs: {json.dumps([b1, b2], ensure_ascii=False)}

Language:
1) Output in Simplified Chinese.
2) Keep tone practical and trustworthy, avoid clickbait hype words.

Content strategy:
1) Title within 16 Chinese characters, focus on reader benefit.
2) First 120 Chinese characters: pain point + clear value promise.
3) Two book sections. Each section must include:
   - Why this book matters now (real user scenario)
   - One core insight (specific, not empty phrases)
   - One actionable suggestion (can be done today)
4) End with one concrete interaction question and a soft CTA for save/like/share.
5) Total body length 700-900 Chinese characters, short paragraphs (max 3 lines per paragraph).

HTML requirements:
1) Return JSON only, no markdown code block.
2) article_html must be directly usable in WeChat official-account rich text.
3) Use single quotes for all HTML attributes. Avoid double quotes and backslashes.
4) Must include placeholders: WECHAT_COVER, B1_COVER, B2_COVER.
5) Do NOT set left/right outer margin or left/right outer padding; keep horizontal spacing 0 and let WeChat handle side spacing.
6) Must include this exact cover card block for each book (replace image src only):
   <div style='text-align:center; margin:45px 0;'>
     <div style='display:inline-block; padding-bottom:15px; border-bottom:4px solid #e8e8e8; width:220px;'>
       <img src='B1_COVER' style='width:140px; height:auto; border-radius:3px 10px 10px 3px; box-shadow:8px 12px 24px rgba(0,0,0,0.18); border-left:3px solid #f9f9f9; display:block; margin:0 auto;'>
     </div>
     <p style='font-size:12px; color:#b0b0b0; margin-top:12px; letter-spacing:2px;'>This Issue Pick</p>
   </div>
7) Suggested subtitle style:
   <h3 style='font-size:17px; color:#222; border-left:4px solid #07c160; padding-left:12px; margin:40px 0 20px 0; letter-spacing:1px;'>
8) Suggested paragraph style:
   <p style='font-size:15px; color:#333; line-height:2.1; margin-bottom:20px; text-align:justify; letter-spacing:0.5px;'>
9) Suggested quote style:
   <blockquote style='background:#f7f9fa; border-left:3px solid #07c160; padding:15px 20px; color:#555; font-size:14px; margin:25px 0; line-height:1.8;'>

Output format: JSON {{"article_title":"...","article_html":"..."}}
"""
    last_error = None
    for model_name in GEMINI_MODELS:
        for attempt in range(1, GEMINI_MODEL_RETRIES + 1):
            try:
                payload = request_gemini(prompt, model_name)
                text = extract_gemini_text(payload)
                data = parse_model_json(text)
                if not data.get("article_title") or not data.get("article_html"):
                    raise ValueError("Model JSON missing article_title/article_html.")
                return data
            except Exception as exc:
                last_error = exc
                if attempt < GEMINI_MODEL_RETRIES:
                    time.sleep(1.5 * attempt)

    raise RuntimeError(f"Failed to generate content via Gemini after retries. Last error: {last_error}")


def robust_replace(html, placeholder, real_url):
    return re.sub(r"[\{\[\(]{0,3}" + re.escape(placeholder) + r"[\}\]\)]{0,3}", real_url, html).replace(
        placeholder,
        real_url,
    )


# ================= Main =================
def main():
    clear_images_weekly()
    history_state = load_history()
    b1, b2 = pick_daily_books(history_state)
    if not b1 or not b2:
        raise RuntimeError("Failed to fetch two unique books after retries.")

    data = generate_content(b1, b2)
    p1 = download(b1["cover"], f"{b1['id']}.jpg")
    p2 = download(b2["cover"], f"{b2['id']}.jpg")
    if not p1 or not p2:
        raise RuntimeError("Failed to download book cover images.")

    wc_local = f"{IMAGE_DIR}/wechat_cover.jpg"
    with Image.open(p2) as img:
        bg = img.convert("RGB").resize((840, 360)).filter(ImageFilter.GaussianBlur(25)).point(lambda p: p * 0.5)
        fg = img.resize((280, 280), Image.Resampling.LANCZOS)
        bg.paste(fg, (280, 40))
        bg.save(wc_local, "JPEG", quality=90)

    html = data["article_html"]
    mappings = [
        ("WECHAT_COVER", get_github_url(wc_local)),
        ("B1_COVER", get_github_url(p1)),
        ("B2_COVER", get_github_url(p2)),
    ]
    for placeholder, url in mappings:
        html = robust_replace(html, placeholder, url)

    content_wrapper_style = (
        f"padding:30px {WECHAT_SIDE_SPACING_PX}px;background-color:#ffffff;"
        "font-family:-apple-system,BlinkMacSystemFont,Helvetica Neue,PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif;"
    )
    top_gif_style = "width:100%;display:block;margin-bottom:25px;"
    bottom_gif_style = "width:100%;display:block;margin-top:40px;"

    full_html = (
        f"<section data-side-spacing='{WECHAT_SIDE_SPACING_PX}' style='background-color:#ffffff;margin:0;padding:0;'>"
        f"<img src='{TOP_GIF}' style='{top_gif_style}'>"
        f"<section style='{content_wrapper_style}'>{html}</section>"
        f"<img src='{BOTTOM_GIF}' style='{bottom_gif_style}'>"
        "</section>"
    )

    final_output = {
        "article_title": data["article_title"],
        "article_html": minify_html(full_html.replace("[", "").replace("]", "")),
        "covers": [url for _, url in mappings],
        "date": TODAY_DATE.strftime("%Y-%m-%d"),
    }

    with open("daliy-read.json", "w", encoding="utf-8") as file:
        json.dump(final_output, file, ensure_ascii=False, separators=(",", ":"))

    save_history(history_state, b1, b2)


if __name__ == "__main__":
    main()
