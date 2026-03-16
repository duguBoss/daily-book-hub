import os, json, random, requests, re, time
from datetime import datetime
from PIL import Image, ImageFilter

# ================= 配置 =================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'duguBoss/daily-book-hub')
GITHUB_BRANCH = "main"
IMAGE_DIR = f"images/{datetime.utcnow().strftime('%Y-%m-%d')}"
os.makedirs(IMAGE_DIR, exist_ok=True)

# ================= 基础工具 =================
def get_github_url(local_path):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"

def download(url, name):
    p = f"{IMAGE_DIR}/{name}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=20)
        res.raise_for_status()
        with open(p, 'wb') as f: f.write(res.content)
        return p
    except: return None

def get_book(history, source):
    # 增加重试机制，防止网络抖动导致的抓取失败
    for _ in range(5):
        try:
            if source == "gutenberg":
                res = requests.get(f"https://gutendex.com/books/?page={random.randint(1, 200)}", timeout=15).json()
                items = res.get('results', [])
            else:
                subjects = ['literature', 'fiction', 'history', 'science', 'mystery', 'art']
                url = f"https://openlibrary.org/search.json?subject={random.choice(subjects)}&limit=20&offset={random.randint(0, 500)}"
                res = requests.get(url, timeout=15).json()
                items = res.get('docs', [])
            
            random.shuffle(items)
            for item in items:
                b_id = str(item.get('id')) if source == "gutenberg" else item.get('key', '').split('/')[-1]
                cover = item.get('formats', {}).get('image/jpeg') if source == "gutenberg" else f"https://covers.openlibrary.org/b/id/{item.get('cover_i')}-L.jpg"
                if cover and f"{source}_{b_id}" not in history:
                    return {"id": f"{source}_{b_id}", "title": item.get('title', 'Unknown'), "author": str(item.get('authors' if source == "gutenberg" else 'author_name', 'Unknown')), "cover": cover}
        except: time.sleep(2)
    return None

def generate_content(b1, b2):
    prompt = f"""
    你是书评专家。根据以下两本书生成微信推文：{json.dumps([b1, b2])}
    
    输出要求：
    1. 必须输出标准 JSON，不要 Markdown，不要 ```json。
    2. article_title: 32字内富有情绪诱惑力的标题。
    3. article_html: 完整的HTML代码。
       模板框架：<section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:20px;line-height:1.8;color:#333;text-align:justify;'>{{CONTENT}}</section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>
       {{CONTENT}} 内部使用带阴影的白色卡片，包含每本书的背景讲述、中英文对照、情绪引导，总计600字以上。
       文中必须插入图片占位符：
       <img src='{{WECHAT_COVER}}' style='width:100%;border-radius:10px;margin:15px 0;'>
       <img src='{{B1_COVER}}' style='width:100%;border-radius:10px;margin:15px 0;'>
       <img src='{{B2_COVER}}' style='width:100%;border-radius:10px;margin:15px 0;'>
    """
    res = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", 
                        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}})
    
    data = json.loads(res.json()['candidates'][0]['content']['parts'][0]['text'].replace('```json', '').replace('```', '').strip())
    if "article_title" not in data: data["article_title"] = "灵魂书单：穿越文明的深度阅读"
    if "article_html" not in data: data["article_html"] = "<p>内容生成失败</p>"
    return data

# ================= 主流程 =================
def main():
    history = json.load(open('history.json')) if os.path.exists('history.json') else []
    b1, b2 = get_book(history, "gutenberg"), get_book(history, "openlibrary")
    if not b1 or not b2: exit("无法抓取到书籍数据，请检查网络")
    
    data = generate_content(b1, b2)
    
    # 图片下载
    p1, p2 = download(b1['cover'], f"{b1['id']}.jpg"), download(b2['cover'], f"{b2['id']}.jpg")
    
    # 21:9 头图合成
    wc_path = f"{IMAGE_DIR}/wechat_cover.jpg"
    with Image.open(p2) as img:
        bg = img.convert("RGB").resize((840, 360)).filter(ImageFilter.GaussianBlur(15)).point(lambda p: p * 0.6)
        fg = img.resize((200, 300))
        bg.paste(fg, (320, 30))
        bg.save(wc_path, "JPEG")
        
    # 最终替换
    html = data['article_html'].replace('{{WECHAT_COVER}}', get_github_url(wc_path)) \
                               .replace('{{B1_COVER}}', get_github_url(p1)) \
                               .replace('{{B2_COVER}}', get_github_url(p2))
    
    # 保存
    with open('daliy-read.json', 'w', encoding='utf-8') as f:
        json.dump({"article_title": data['article_title'], "article_html": html, "covers": [get_github_url(wc_path), get_github_url(p1), get_github_url(p2)]}, f, ensure_ascii=False, indent=4)
    
    json.dump(history + [b1['id'], b2['id']], open('history.json', 'w'))

if __name__ == "__main__": main()
