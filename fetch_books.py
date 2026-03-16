import os, json, random, requests, re, time
from datetime import datetime
from PIL import Image, ImageFilter

# ================= 配置 =================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
# 请确保你的仓库名和分支名配置正确
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'duguBoss/daily-book-hub')
GITHUB_BRANCH = "main"
IMAGE_DIR = f"images/{datetime.utcnow().strftime('%Y-%m-%d')}"
os.makedirs(IMAGE_DIR, exist_ok=True)

# ================= 辅助函数 =================
def get_github_url(local_path):
    """
    直接返回 GitHub Raw 链接，这是微信公众号识别度最高的直链
    """
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"

def download(url, name):
    p = f"{IMAGE_DIR}/{name}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=20)
        res.raise_for_status()
        with open(p, 'wb') as f: f.write(res.content)
        return p
    except Exception as e:
        print(f"下载失败 {url}: {e}")
        return None

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
    prompt = f"""
    你是书评专家。根据以下两本书：{json.dumps([b1, b2])}，撰写一篇优美的微信推文。
    要求：
    1. 标题：32字内，富有情绪感与阅读诱惑力。
    2. 内容：两本书总计撰写 600 字以上。包含：
       - 中文译名 / 原名
       - 深度导读：客观讲述背景+思想内核+中英文对照名句。
       - 情绪引导：邀请读者阅读的走心文字。
    3. HTML排版 (必须严格执行)：
       - 外层必须包裹：<section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:20px;line-height:1.8;color:#333;text-align:justify;'>{{CONTENT}}</section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>
       - {{CONTENT}} 内部使用白色卡片：<div style='background:#f9f9f9;padding:20px;border-radius:10px;'>{{BODY}}</div>
       - 图片必须插入：<img src='{{WECHAT_COVER}}' style='width:100%;border-radius:10px;margin:15px 0;'><img src='{{B1_COVER}}' style='width:100%;border-radius:10px;margin:15px 0;'><img src='{{B2_COVER}}' style='width:100%;border-radius:10px;margin:15px 0;'>
    4. 输出纯JSON，不要Markdown。
    """
    res = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", 
                        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}})
    
    content = res.json()['candidates'][0]['content']['parts'][0]['text']
    content = re.sub(r'```json\s?', '', content).replace('```', '').strip()
    return json.loads(content)

# ================= 主流程 =================
def main():
    history = json.load(open('history.json')) if os.path.exists('history.json') else []
    b1, b2 = get_book(history, "gutenberg"), get_book(history, "openlibrary")
    if not b1 or not b2: exit("数据获取失败")
    
    data = generate_content(b1, b2)
    
    # 下载封面
    p1 = download(b1['cover'], f"{b1['id']}.jpg")
    p2 = download(b2['cover'], f"{b2['id']}.jpg")
    
    # 生成 21:9 头图
    wc_path = f"{IMAGE_DIR}/wechat_cover.jpg"
    with Image.open(p2) as img:
        bg = img.convert("RGB").resize((840, 360)).filter(ImageFilter.GaussianBlur(15)).point(lambda p: p * 0.6)
        fg = img.resize((200, 300))
        bg.paste(fg, (320, 30))
        bg.save(wc_path, "JPEG")
        
    # 获取 GitHub 直链
    wc_url = get_github_url(wc_path)
    b1_url = get_github_url(p1)
    b2_url = get_github_url(p2)
    
    # 替换占位符
    html = data['article_html'].replace('{{WECHAT_COVER}}', wc_url) \
                               .replace('{{B1_COVER}}', b1_url) \
                               .replace('{{B2_COVER}}', b2_url)
    
    # 保存结果
    with open('daliy-read.json', 'w', encoding='utf-8') as f:
        json.dump({"article_title": data['article_title'], "article_html": html, "covers": [wc_url, b1_url, b2_url]}, f, ensure_ascii=False, indent=4)
    
    json.dump(history + [b1['id'], b2['id']], open('history.json', 'w'))

if __name__ == "__main__": main()
