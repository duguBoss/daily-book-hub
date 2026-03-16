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

# 环境变量获取
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'your-username/your-repo')
GITHUB_BRANCH = "main"

if not GEMINI_API_KEY:
    raise ValueError("未找到 GEMINI_API_KEY 环境变量！")

os.makedirs(IMAGE_DIR, exist_ok=True)

# ================= 封面下载与处理模块 =================

def download_image(img_url, filename, max_retries=3):
    """
    下载书籍原版封面到本地
    """
    local_path = f"{IMAGE_DIR}/{filename}"
    if not img_url: 
        return ""
        
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[\u23ec 下载中] 正在获取大尺寸原著封面: {filename}")
            res = requests.get(img_url, timeout=20)
            res.raise_for_status()
            with open(local_path, 'wb') as f:
                f.write(res.content)
            
            # 校验图片是否完整
            with Image.open(local_path) as img:
                img.verify()
                
            print(f"[\u2714\ufe0f 成功] 封面已保存: {local_path}")
            return local_path
        except Exception as e:
            print(f"[\u274c 失败] 尝试 {attempt}/{max_retries} 下载失败: {e}")
            time.sleep(3)
    
    raise Exception(f"图片下载彻底失败: {img_url}")

def create_wechat_cover(source_path, filename, target_width=840, target_height=360):
    """
    使用 Pillow 将竖版书籍封面转化为 21:9 的微信推文封面
    算法：生成高斯模糊放大的背景 + 前景封面原比例居中
    """
    local_path = f"{IMAGE_DIR}/{filename}"
    print(f"[\u2699\ufe0f 处理中] 正在生成 21:9 微信公众号头图...")
    
    try:
        with Image.open(source_path) as img:
            img = img.convert("RGB")
            img_ratio = img.width / img.height
            target_ratio = target_width / target_height
            
            # 1. 制作背景 (等比放大填满目标框，并进行重度高斯模糊)
            if img_ratio > target_ratio:
                new_h = target_height
                new_w = int(new_h * img_ratio)
            else:
                new_w = target_width
                new_h = int(new_w / img_ratio)
                
            bg_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # 居中裁剪背景
            left = (bg_img.width - target_width) / 2
            top = (bg_img.height - target_height) / 2
            bg_img = bg_img.crop((left, top, left + target_width, top + target_height))
            
            # 施加高斯模糊和亮度压暗处理 (营造高级感)
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=25))
            bg_img = bg_img.point(lambda p: p * 0.7) # 将背景亮度调暗30%
            
            # 2. 制作前景 (将原封面等比缩放至目标高度)
            fg_h = target_height - 40  # 上下留白 20px
            fg_w = int(fg_h * img_ratio)
            fg_img = img.resize((fg_w, fg_h), Image.Resampling.LANCZOS)
            
            # 3. 合并图片 (前景居中粘贴到背景上)
            paste_x = (target_width - fg_w) // 2
            paste_y = 20
            bg_img.paste(fg_img, (paste_x, paste_y))
            
            bg_img.save(local_path, "JPEG", quality=90)
            
            print(f"[\u2714\ufe0f 成功] 微信头图合成完毕: {local_path}")
            return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"
    except Exception as e:
        print(f"[\u274c 失败] 微信头图处理失败: {e}")
        return ""

# ================= 数据抓取模块 =================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    return[]

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f: json.dump(history, f, ensure_ascii=False, indent=2)

def get_gutenberg_book(history):
    while True:
        try:
            # 随机获取一页
            res = requests.get(f"https://gutendex.com/books/?page={random.randint(1, 150)}", timeout=10).json()
            books = res.get('results',[])
            random.shuffle(books)
            for book in books:
                book_id = f"gutenberg_{book['id']}"
                cover_url = book.get('formats', {}).get('image/jpeg', '')
                if book_id not in history and cover_url:
                    return {
                        "id": book_id,
                        "title": book.get('title', 'Unknown'),
                        "author": ", ".join([a['name'] for a in book.get('authors',[])]),
                        "cover": cover_url,
                        "url": f"https://www.gutenberg.org/ebooks/{book['id']}"
                    }
        except Exception: 
            pass

def get_openlibrary_book(history):
    subjects = ['literature', 'fiction', 'history', 'science', 'mystery', 'philosophy', 'art']
    while True:
        try:
            res = requests.get(f"https://openlibrary.org/search.json?subject={random.choice(subjects)}&limit=20&offset={random.randint(0, 300)}", timeout=10).json()
            docs = res.get('docs',[])
            random.shuffle(docs)
            for doc in docs:
                key = doc.get('key', '')
                book_id = f"openlibrary_{key.replace('/works/', '')}"
                # 确保有封面ID
                if book_id not in history and doc.get('cover_i'):
                    return {
                        "id": book_id,
                        "title": doc.get('title', 'Unknown'),
                        "author": ", ".join(doc.get('author_name',['Unknown'])),
                        # 注意：-L 表示拉取最大尺寸(Large)的高清封面
                        "cover": f"https://covers.openlibrary.org/b/id/{doc.get('cover_i')}-L.jpg",
                        "url": f"https://openlibrary.org{key}"
                    }
        except Exception: 
            pass

# ================= 文案排版生成 =================

def generate_wechat_content(books_data):
    print("正在调用 Gemini API 生成文案与排版...")
    prompt = """
    你是一个顶级的微信公众号内容总监。我将提供两本世界经典书籍的数据（JSON格式）。
    
    【核心要求】
    1. 生成阅读欲望极强的文章标题（32字内，有悬念、直击人心）。
    2. 生成这两本书的深度图文推荐，每本必须包含【客观讲解】和【情绪引导】，两本书文案总字数达600字左右，排版优美，文笔细腻。

    3. 【HTML高级排版（严格使用占位符）】：
       - 必须使用外部容器：
         <section style='margin:0;padding:0;background-color:#f7f8fa;font-family: system-ui, -apple-system, sans-serif;'>
            <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'>
            <section style='padding:20px 15px;'>{content_html}{tags_html}</section>
            <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'>
         </section>
       - {content_html} 请设计成极美的高级白色卡片（border-radius:12px; box-shadow:0 4px 16px rgba(0,0,0,0.06)），深灰色字体，留白充足。
       - **图片严格使用这 3 个占位符**（请在代码外层加优美的 img 样式，居中，带微小圆角，带淡阴影）：
         顶部微信文章大封面: {{WECHAT_COVER_URL}}
         第一本书的原版封面: {{BOOK1_COVER_URL}}
         第二本书的原版封面: {{BOOK2_COVER_URL}}

    【输出格式】必须是合法的纯 JSON 格式（绝对不能含有 Markdown 的 ```json）：
    {
      "article_title": "...",
      "article_html": "..."
    }
    """
    payload = {
        "contents": [{"parts":[{"text": prompt + "\n抓取数据：\n" + json.dumps(books_data, ensure_ascii=False)}]}], 
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}
    }
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    
    res = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", headers=headers, json=payload)
    res.raise_for_status()
    
    text = res.json()['candidates'][0]['content']['parts'][0]['text']
    text = re.sub(r'^```json\s*', '', text).strip()
    return json.loads(re.sub(r'\s*```$', '', text).strip())

# ================= 主流程 =================

def main():
    history = load_history()
    
    # 1. 获取书籍数据
    b1 = get_gutenberg_book(history)
    b2 = get_openlibrary_book(history)
    
    # 2. 调用 Gemini (仅生成文案和HTML框架，不再生成Prompt)
    gemini_data = generate_wechat_content([b1, b2])
    
    print("\n--- 开始下载原版大封面并处理 ---")
    
    # 3. 下载大尺寸原著封面
    b1_local_path = download_image(b1['cover'], f"{b1['id']}_cover.jpg")
    b2_local_path = download_image(b2['cover'], f"{b2['id']}_cover.jpg")
    
    # 转换为 GitHub 直链
    b1_cover_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{b1_local_path}"
    b2_cover_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{b2_local_path}"

    # 4. 提取其中一张高质量封面 (推荐 OpenLibrary 的大图) 制作 21:9 微信文章头图
    wechat_cover_url = create_wechat_cover(b2_local_path, "wechat_cover.jpg")

    # 5. 替换 HTML 占位符
    urls_map = {
        "{{WECHAT_COVER_URL}}": wechat_cover_url,
        "{{BOOK1_COVER_URL}}": b1_cover_url,
        "{{BOOK2_COVER_URL}}": b2_cover_url
    }

    final_html = gemini_data['article_html']
    for placeholder, url in urls_map.items():
        final_html = final_html.replace(placeholder, url)

    # 6. 保存输出
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            "article_title": gemini_data['article_title'], 
            "article_html": final_html, 
            "date": TODAY_STR
        }, f, ensure_ascii=False, indent=4)
        print(f"\n✔ 每日推送数据已成功保存至 {OUTPUT_FILE}")
    
    # 7. 更新历史
    history.extend([b1['id'], b2['id']])
    save_history(history)

if __name__ == "__main__":
    main()
