import os, json, random, requests, re, time, shutil
from datetime import datetime
from PIL import Image, ImageFilter

# ================= 配置 =================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'duguBoss/daily-book-hub')
GITHUB_BRANCH = "main"
TODAY_DATE = datetime.utcnow()
IMAGE_DIR = f"images/{TODAY_DATE.strftime('%Y-%m-%d')}"

TOP_GIF = "https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif"
BOTTOM_GIF = "https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif"

# ================= 工具函数 =================
def minify_html(html):
    """极致压缩：移除所有换行、多余空格，仅保留标签间结构"""
    html = re.sub(r'[\r\n\t]+', '', html)  # 移除换行/制表符
    html = re.sub(r'>\s+<', '><', html)    # 移除标签间空格
    html = re.sub(r'\s{2,}', ' ', html)    # 合并多余空格
    return html.strip()

def clear_images_weekly():
    if TODAY_DATE.weekday() == 0:
        if os.path.exists('images'):
            try: shutil.rmtree('images')
            except: pass
    os.makedirs(IMAGE_DIR, exist_ok=True)

def get_github_url(local_path):
    if not local_path: return ""
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"

def download(url, name):
    p = f"{IMAGE_DIR}/{name}"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        res.raise_for_status()
        with open(p, 'wb') as f: f.write(res.content)
        return p
    except: return None

def get_book(history, source):
    for _ in range(5):
        try:
            if source == "gutenberg":
                res = requests.get(f"https://gutendex.com/books/?page={random.randint(1, 500)}", timeout=15).json()
                items = res.get('results', [])
            else:
                subjects = ['fiction', 'classics', 'philosophy', 'history', 'art', 'science']
                url = f"https://openlibrary.org/search.json?subject={random.choice(subjects)}&limit=20"
                res = requests.get(url, timeout=15).json()
                items = res.get('docs', [])
            random.shuffle(items)
            for item in items:
                b_id = str(item.get('id')) if source == "gutenberg" else item.get('key', '').split('/')[-1]
                cover = item.get('formats', {}).get('image/jpeg') if source == "gutenberg" else f"https://covers.openlibrary.org/b/id/{item.get('cover_i')}-L.jpg"
                if cover and f"{source}_{b_id}" not in history:
                    title = item.get('title', 'Unknown').replace('[','').replace(']','')
                    author_list = item.get('authors' if source == "gutenberg" else 'author_name', ['Unknown'])
                    author = (author_list[0]['name'] if source == "gutenberg" else author_list[0]).replace('[','').replace(']','')
                    return {"id": f"{source}_{b_id}", "title": title, "author": author, "cover": cover}
        except: time.sleep(2)
    return None

def generate_content(b1, b2):
    prompt = f"""你是一个百万粉丝读书博主，根据以下书籍信息撰写推文。
    书籍1：{json.dumps(b1, ensure_ascii=False)}，书籍2：{json.dumps(b2, ensure_ascii=False)}
    策略：
    1. 正文必须优美、地道中文，600字以上。
    2. 禁令：严禁使用 [] 或 {{}} 包裹图片地址或正文，直接写文字。
    3. 占位符：在HTML标签中预留 WECHAT_COVER, B1_COVER, B2_COVER。
    输出：JSON对象 {{"article_title": "...", "content_html": "..."}}"""
    
    res = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", 
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}
    )
    data = json.loads(re.sub(r'```json\s?|```', '', res.json()['candidates'][0]['content']['parts'][0]['text']))
    return data if not isinstance(data, list) else data[0]

def robust_replace(html, placeholder, real_url):
    pattern = re.compile(r'[\{\[\(]{0,3}' + re.escape(placeholder) + r'[\}\]\)]{0,3}', re.IGNORECASE)
    return pattern.sub(real_url, html)

# ================= 主流程 =================
def main():
    clear_images_weekly()
    history = json.load(open('history.json')) if os.path.exists('history.json') else []
    b1, b2 = get_book(history, "gutenberg"), get_book(history, "openlibrary")
    if not b1 or not b2: exit("书籍抓取失败")
    
    data = generate_content(b1, b2)
    p1_local, p2_local = download(b1['cover'], f"{b1['id']}.jpg"), download(b2['cover'], f"{b2['id']}.jpg")
    
    wc_local = f"{IMAGE_DIR}/wechat_cover.jpg"
    with Image.open(p2_local) as img:
        img = img.convert("RGB")
        bg = img.resize((840, 360)).filter(ImageFilter.GaussianBlur(25)).point(lambda p: p * 0.5)
        fg = img.resize((280, 280), Image.Resampling.LANCZOS)
        bg.paste(fg, (280, 40))
        bg.save(wc_local, "JPEG", quality=90)
        
    wc_url, b1_url, b2_url = get_github_url(wc_local), get_github_url(p1_local), get_github_url(p2_local)
    
    # 注入并压缩
    content_body = data.get('content_html', "")
    for p, u in [("WECHAT_COVER", wc_url), ("B1_COVER", b1_url), ("B2_COVER", b2_url)]:
        content_body = robust_replace(content_body, p, u)
    
    content_body = minify_html(content_body.replace('[', '').replace(']', ''))
    final_html = f"<section style='margin:0;padding:0;background-color:#fff;'><img src='{TOP_GIF}' style='width:100%;display:block;'><section style='padding:0;'>{content_body}</section><img src='{BOTTOM_GIF}' style='width:100%;display:block;'></section>"
    
    with open('daliy-read.json', 'w', encoding='utf-8') as f:
        json.dump({"article_title": data.get('article_title', "深度阅读"), "article_html": final_html, "date": TODAY_DATE.strftime('%Y-%m-%d')}, f, ensure_ascii=False)
    
    json.dump(history + [b1['id'], b2['id']], open('history.json', 'w'))

if __name__ == "__main__": main()
