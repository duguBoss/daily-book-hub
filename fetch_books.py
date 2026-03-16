import os
import json
import random
import requests
import re
import time
from datetime import datetime
from PIL import Image, ImageFilter

# ================= 配置区 =================
HISTORY_FILE = 'history.json'
OUTPUT_FILE = 'daliy-read.json'
TODAY_STR = datetime.utcnow().strftime('%Y-%m-%d')
IMAGE_DIR = f"images/{TODAY_STR}"

# 环境变量
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'duguBoss/daily-book-hub') # 已根据你的链接设定
GITHUB_BRANCH = "main"

if not GEMINI_API_KEY:
    raise ValueError("未找到 GEMINI_API_KEY 环境变量！")

os.makedirs(IMAGE_DIR, exist_ok=True)

# ================= 工具函数 =================

def get_cdn_url(local_path):
    """返回 jsDelivr CDN 加速链接，确保微信图片加载速度和稳定性"""
    # 格式: https://cdn.jsdelivr.net/gh/user/repo@branch/path
    return f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@{GITHUB_BRANCH}/{local_path}"

def download_image(img_url, filename):
    """下载原版封面并保存"""
    local_path = f"{IMAGE_DIR}/{filename}"
    res = requests.get(img_url, timeout=20)
    res.raise_for_status()
    with open(local_path, 'wb') as f:
        f.write(res.content)
    return local_path

def create_wechat_cover(source_path, filename):
    """合成 21:9 微信头图"""
    local_path = f"{IMAGE_DIR}/{filename}"
    target_width, target_height = 840, 360
    with Image.open(source_path) as img:
        img = img.convert("RGB")
        img_ratio = img.width / img.height
        
        # 1. 模糊背景
        bg_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=25))
        bg_img = bg_img.point(lambda p: p * 0.7) 
        
        # 2. 前景居中
        fg_h = target_height - 60
        fg_w = int(fg_h * img_ratio)
        fg_img = img.resize((fg_w, fg_h), Image.Resampling.LANCZOS)
        
        bg_img.paste(fg_img, ((target_width - fg_w) // 2, 30))
        bg_img.save(local_path, "JPEG", quality=90)
    return local_path

# ================= 抓取与生成 =================

def get_book(history, source):
    while True:
        try:
            if source == "gutenberg":
                res = requests.get(f"https://gutendex.com/books/?page={random.randint(1, 150)}", timeout=10).json()
                items = res.get('results', [])
            else:
                res = requests.get(f"https://openlibrary.org/search.json?subject=literature&limit=20&offset={random.randint(0, 300)}", timeout=10).json()
                items = res.get('docs', [])
            
            random.shuffle(items)
            for item in items:
                b_id = item.get('id') if source == "gutenberg" else item.get('key').split('/')[-1]
                full_id = f"{source}_{b_id}"
                cover = item.get('formats', {}).get('image/jpeg') if source == "gutenberg" else f"https://covers.openlibrary.org/b/id/{item.get('cover_i')}-L.jpg"
                
                if full_id not in history and cover:
                    return {"id": full_id, "title": item.get('title'), "author": str(item.get('authors' if source == "gutenberg" else 'author_name', 'Unknown')), "cover": cover}
        except: time.sleep(1)

def generate_html_content(books):
    prompt = f"""
    你是书评专家。请根据以下两本书：{json.dumps(books)}，撰写一篇优美的微信推文。
    要求：
    1. 生成一个32字内的情绪阅读欲望标题。
    2. HTML内容必须严格使用以下外层容器：
       <section style='margin:0;padding:0;background-color:#f7f8fa;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:20px 15px;'>{{CONTENT}}</section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>
    3. {{CONTENT}} 内部使用白色卡片排版，必须包含占位符：{{WECHAT_COVER}}，{{B1_COVER}}，{{B2_COVER}}。
    4. 输出纯JSON格式，包含 "article_title" 和 "article_html"。
    """
    res = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", 
                        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}})
    return json.loads(res.json()['candidates'][0]['content']['parts'][0]['text'])

def main():
    history = json.load(open(HISTORY_FILE)) if os.path.exists(HISTORY_FILE) else []
    b1 = get_book(history, "gutenberg")
    b2 = get_book(history, "openlibrary")
    
    data = generate_html_content([b1, b2])
    
    # 下载并处理
    b1_path = download_image(b1['cover'], f"{b1['id']}.jpg")
    b2_path = download_image(b2['cover'], f"{b2['id']}.jpg")
    wc_path = create_wechat_cover(b2_path, "wechat_cover.jpg")
    
    # 替换链接
    final_html = data['article_html'].replace('{{WECHAT_COVER}}', get_cdn_url(wc_path)) \
                                     .replace('{{B1_COVER}}', get_cdn_url(b1_path)) \
                                     .replace('{{B2_COVER}}', get_cdn_url(b2_path))
    
    # 保存结果
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            "article_title": data['article_title'],
            "article_html": final_html,
            "covers": [get_cdn_url(wc_path), get_cdn_url(b1_path), get_cdn_url(b2_path)],
            "date": TODAY_STR
        }, f, ensure_ascii=False, indent=4)
        
    json.dump(history + [b1['id'], b2['id']], open(HISTORY_FILE, 'w'))

if __name__ == "__main__":
    main()
