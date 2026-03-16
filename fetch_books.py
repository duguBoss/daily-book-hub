import os
import json
import random
import requests
import re
import time
from datetime import datetime
from urllib.parse import quote
from PIL import Image  # 引入 Pillow 图像处理库

# ================= 配置区 =================
HISTORY_FILE = 'history.json'
OUTPUT_FILE = 'daliy-read.json'
TODAY_STR = datetime.utcnow().strftime('%Y-%m-%d')
IMAGE_DIR = f"images/{TODAY_STR}"

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'your-username/your-repo')
GITHUB_BRANCH = "main"

if not GEMINI_API_KEY:
    raise ValueError("未找到 GEMINI_API_KEY 环境变量！")

os.makedirs(IMAGE_DIR, exist_ok=True)

# ================= 强力无水印绘图模块 =================

def generate_and_download_image(prompt_text, final_width, final_height, filename, max_retries=5):
    """
    完全符合官方文档的生成器 + Pillow 物理去水印
    """
    # 1. 净化 Prompt：只保留英文字母、数字和基本标点，防止特殊字符破坏 URL
    clean_prompt = re.sub(r'[^a-zA-Z0-9\s,.-]', '', prompt_text)
    # 限制长度并转换空格为 %20 (使用 quote 函数)
    encoded_prompt = quote(clean_prompt[:200].strip())
    
    # 2. 核心去水印策略：故意多请求 50 像素的高度，用于容纳官方水印
    watermark_height = 50
    request_height = final_height + watermark_height
    
    local_path = f"{IMAGE_DIR}/{filename}"

    for attempt in range(1, max_retries + 1):
        # 遵循文档：使用 seed 保证不被错误缓存锁死，明确指定 model=flux
        seed = random.randint(1, 999999)
        # 严禁使用 nologo=true (因为没有账号会导致 500 报错)
        api_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={final_width}&height={request_height}&seed={seed}&model=flux"

        try:
            print(f"[\u23f3 生成中] 正在呼叫 API (尝试 {attempt}/{max_retries} | Seed: {seed}): {filename}")
            
            res = requests.get(api_url, timeout=60)
            if res.status_code == 429:
                raise Exception("触发 429 频率限制")
            res.raise_for_status()
            
            if 'image' not in res.headers.get('Content-Type', ''):
                raise ValueError("API 返回内容非图片")

            # 将带有水印的原始大图暂存
            temp_path = local_path + ".temp.jpg"
            with open(temp_path, 'wb') as f:
                f.write(res.content)
            
            # ====================================================
            # 3. 物理切除水印 (Pillow 裁剪)
            # ====================================================
            with Image.open(temp_path) as img:
                # 获取实际生成的宽高
                w, h = img.size
                # 定义裁剪框 (左, 上, 右, 下)，直接砍掉底部 50 像素
                crop_box = (0, 0, w, h - watermark_height)
                clean_img = img.crop(crop_box)
                
                # 如果实际尺寸与我们需要的不完全一致，强制缩放到最终尺寸
                if clean_img.size != (final_width, final_height):
                    clean_img = clean_img.resize((final_width, final_height), Image.Resampling.LANCZOS)
                
                # 保存最终纯净版图片
                clean_img.save(local_path, "JPEG", quality=95)
            
            # 删除暂存图
            os.remove(temp_path)
            
            print(f"[\u2714\ufe0f 成功] 图片已完成物理去水印并保存: {local_path}")
            return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"
            
        except Exception as e:
            print(f"[\u274c 失败] 绘图请求异常: {e}")
            if attempt < max_retries:
                time.sleep(attempt * 5)
            else:
                raise Exception(f"[\ud83d\udea8 致命错误] 图片 {filename} 彻底失败！")

def download_real_cover(img_url, filename, max_retries=3):
    local_path = f"{IMAGE_DIR}/{filename}"
    if not img_url: return ""
    for attempt in range(1, max_retries + 1):
        try:
            print(f"正在下载原著封面: {filename}")
            res = requests.get(img_url, timeout=20)
            res.raise_for_status()
            with open(local_path, 'wb') as f:
                f.write(res.content)
            return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"
        except Exception as e:
            time.sleep(3)
    return img_url

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
            res = requests.get(f"https://gutendex.com/books/?page={random.randint(1, 200)}", timeout=10).json()
            books = res.get('results',[])
            random.shuffle(books)
            for book in books:
                book_id = f"gutenberg_{book['id']}"
                if book_id not in history:
                    return {
                        "id": book_id,
                        "title": book.get('title', 'Unknown'),
                        "author": ", ".join([a['name'] for a in book.get('authors',[])]),
                        "cover": book.get('formats', {}).get('image/jpeg', ''),
                        "url": f"https://www.gutenberg.org/ebooks/{book['id']}"
                    }
        except Exception: pass

def get_openlibrary_book(history):
    subjects = ['literature', 'fiction', 'history', 'science', 'mystery']
    while True:
        try:
            res = requests.get(f"https://openlibrary.org/search.json?subject={random.choice(subjects)}&limit=20&offset={random.randint(0, 300)}", timeout=10).json()
            docs = res.get('docs',[])
            random.shuffle(docs)
            for doc in docs:
                key = doc.get('key', '')
                book_id = f"openlibrary_{key.replace('/works/', '')}"
                if book_id not in history and doc.get('cover_i'):
                    return {
                        "id": book_id,
                        "title": doc.get('title', 'Unknown'),
                        "author": ", ".join(doc.get('author_name', ['Unknown'])),
                        "cover": f"https://covers.openlibrary.org/b/id/{doc.get('cover_i')}-L.jpg",
                        "url": f"https://openlibrary.org{key}"
                    }
        except Exception: pass

# ================= 文案排版生成 =================

def generate_wechat_content(books_data):
    print("正在调用 Gemini API...")
    prompt = """
    你是一个顶级的微信公众号内容总监。我将提供两本外文书籍数据（JSON格式）。
    
    【核心要求】
    1. 生成阅读欲望极强的文章标题（32字内）。
    2. 生成两本书的文案，每本包含【客观讲解】和【情绪引导】，两本书文案总字数达600字左右。
    3. 【极为重要：配图Prompt限制】：为你构思的每张图片写纯英文 Prompt，**必须极简短，只能使用简单的英文单词组合（最多15个单词），千万不要出现特殊标点**。
       - wechat_cover_prompt: 用于生成21:9头图。
       - book1_illustration_prompt / book2_illustration_prompt: 16:9内文插图。

    4. 【HTML高级排版】：
       - 必须使用外部容器：
         <section style='margin:0;padding:0;background-color:#f7f8fa;font-family: system-ui, -apple-system, sans-serif;'>
            <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'>
            <section style='padding:20px 15px;'>{content_html}{tags_html}</section>
            <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'>
         </section>
       - 图片严格使用这5个占位符（外层加优美的 img 样式）：
         {{WECHAT_COVER_URL}}
         {{BOOK1_COVER_URL}}
         {{BOOK1_ILLUSTRATION_URL}}
         {{BOOK2_COVER_URL}}
         {{BOOK2_ILLUSTRATION_URL}}

    【输出格式】必须纯 JSON 格式：
    {
      "article_title": "...",
      "wechat_cover_prompt": "english...",
      "book1_illustration_prompt": "english...",
      "book2_illustration_prompt": "english...",
      "article_html": "..."
    }
    """
    payload = {"contents": [{"parts":[{"text": prompt + "\n数据：\n" + json.dumps(books_data, ensure_ascii=False)}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    
    res = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", headers=headers, json=payload)
    res.raise_for_status()
    
    text = res.json()['candidates'][0]['content']['parts'][0]['text']
    text = re.sub(r'^```json\s*', '', text).strip()
    return json.loads(re.sub(r'\s*```$', '', text).strip())

# ================= 主流程 =================

def main():
    history = load_history()
    b1, b2 = get_gutenberg_book(history), get_openlibrary_book(history)
    gemini_data = generate_wechat_content([b1, b2])
    
    print("\n--- 开始调用 AI 绘图 API 并执行物理裁切去水印 ---")
    
    # 头图 21:9，最终需要 840x360
    wechat_cover_url = generate_and_download_image(gemini_data['wechat_cover_prompt'], 840, 360, "wechat_cover.jpg")
    time.sleep(3) 
    
    # 内页图 16:9，最终需要 800x450
    b1_ill_url = generate_and_download_image(gemini_data['book1_illustration_prompt'], 800, 450, f"{b1['id']}_illustration.jpg")
    time.sleep(3)
    b2_ill_url = generate_and_download_image(gemini_data['book2_illustration_prompt'], 800, 450, f"{b2['id']}_illustration.jpg")
    time.sleep(3)

    b1_cover_url = download_real_cover(b1['cover'], f"{b1['id']}_cover.jpg")
    b2_cover_url = download_real_cover(b2['cover'], f"{b2['id']}_cover.jpg")

    urls_map = {
        "{{WECHAT_COVER_URL}}": wechat_cover_url,
        "{{BOOK1_COVER_URL}}": b1_cover_url,
        "{{BOOK1_ILLUSTRATION_URL}}": b1_ill_url,
        "{{BOOK2_COVER_URL}}": b2_cover_url,
        "{{BOOK2_ILLUSTRATION_URL}}": b2_ill_url
    }

    final_html = gemini_data['article_html']
    for placeholder, url in urls_map.items():
        final_html = final_html.replace(placeholder, url)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump({"article_title": gemini_data['article_title'], "article_html": final_html, "date": TODAY_STR}, f, ensure_ascii=False, indent=4)
        print(f"\n✔ 每日推送数据已成功保存至 {OUTPUT_FILE}")
    
    history.extend([b1['id'], b2['id']])
    save_history(history)

if __name__ == "__main__":
    main()
