import os, json, random, requests, re, time
from datetime import datetime
from PIL import Image, ImageFilter

# ================= 配置 =================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'duguBoss/daily-book-hub')
GITHUB_BRANCH = "main"
IMAGE_DIR = f"images/{datetime.utcnow().strftime('%Y-%m-%d')}"
os.makedirs(IMAGE_DIR, exist_ok=True)

# ================= 辅助函数 =================
def get_github_url(local_path):
    # 使用 GitHub Raw 直链，确保图片可直接加载
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
    try:
        if source == "gutenberg":
            res = requests.get(f"https://gutendex.com/books/?page={random.randint(1, 100)}", timeout=10).json()
            items = res['results']
        else:
            res = requests.get(f"https://openlibrary.org/search.json?subject=literature&limit=20&offset={random.randint(0, 200)}", timeout=10).json()
            items = res['docs']
        
        for item in items:
            b_id = item.get('id') if source == "gutenberg" else item.get('key', '').split('/')[-1]
            cover = item.get('formats', {}).get('image/jpeg') if source == "gutenberg" else f"https://covers.openlibrary.org/b/id/{item.get('cover_i')}-L.jpg"
            if cover and f"{source}_{b_id}" not in history:
                return {"id": f"{source}_{b_id}", "title": item['title'], "author": str(item.get('authors' if source == "gutenberg" else 'author_name', 'Unknown')), "cover": cover}
    except: return None

def generate_content(b1, b2):
    # 强制要求返回 JSON 结构
    prompt = f"""
    你是书评专家。根据以下两本书生成微信推文：{json.dumps([b1, b2])}
    
    必须且仅输出以下 JSON 结构：
    {{
      "article_title": "一个富有情绪阅读诱惑力的32字标题",
      "article_html": "完整的HTML内容，包含{{WECHAT_COVER}}, {{B1_COVER}}, {{B2_COVER}}占位符"
    }}
    不要Markdown标记。
    """
    res = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", 
                        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}})
    
    raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
    # 彻底清洗可能存在的 Markdown 字符
    clean_text = re.sub(r'^```json\s*', '', raw_text).replace('```', '').strip()
    data = json.loads(clean_text)
    
    # 强力校验：如果 Gemini 没给字段，赋予默认值防止崩溃
    if "article_title" not in data: data["article_title"] = "每日深度阅读：带你走进文学的自由史诗"
    if "article_html" not in data: data["article_html"] = "<p>内容生成失败，请稍后再试。</p>"
    
    return data

def main():
    history = json.load(open('history.json')) if os.path.exists('history.json') else []
    b1, b2 = get_book(history, "gutenberg"), get_book(history, "openlibrary")
    if not b1 or not b2: exit("数据获取失败")
    
    data = generate_content(b1, b2)
    
    p1 = download(b1['cover'], f"{b1['id']}.jpg")
    p2 = download(b2['cover'], f"{b2['id']}.jpg")
    
    wc_path = f"{IMAGE_DIR}/wechat_cover.jpg"
    with Image.open(p2) as img:
        bg = img.convert("RGB").resize((840, 360)).filter(ImageFilter.GaussianBlur(15)).point(lambda p: p * 0.6)
        fg = img.resize((200, 300))
        bg.paste(fg, (320, 30))
        bg.save(wc_path, "JPEG")
        
    # 替换占位符
    html = data['article_html'].replace('{{WECHAT_COVER}}', get_github_url(wc_path)) \
                               .replace('{{B1_COVER}}', get_github_url(p1)) \
                               .replace('{{B2_COVER}}', get_github_url(p2))
    
    # 最终保存
    with open('daliy-read.json', 'w', encoding='utf-8') as f:
        json.dump({"article_title": data['article_title'], "article_html": html, "covers": [get_github_url(wc_path), get_github_url(p1), get_github_url(p2)]}, f, ensure_ascii=False, indent=4)
    
    json.dump(history + [b1['id'], b2['id']], open('history.json', 'w'))

if __name__ == "__main__": main()
