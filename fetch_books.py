import os
import json
import random
import requests
import re
import time
from datetime import datetime
from urllib.parse import quote

# ================= 配置区 =================
HISTORY_FILE = 'history.json'
OUTPUT_FILE = 'daliy-read.json'
# 获取当前日期作为图片文件夹名
TODAY_STR = datetime.utcnow().strftime('%Y-%m-%d')
IMAGE_DIR = f"images/{TODAY_STR}"

# 环境变量获取
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'your-username/your-repo')
GITHUB_BRANCH = "main"

if not GEMINI_API_KEY:
    raise ValueError("未找到 GEMINI_API_KEY 环境变量！")

# 创建今日图片文件夹
os.makedirs(IMAGE_DIR, exist_ok=True)

# ================= 强力重试下载与生成模块 =================

def generate_and_download_image(prompt_text, width, height, filename, max_retries=8):
    """
    终极防御版生图模块：带随机种子突破缓存锁、指定 flux 模型、防 500 崩溃
    """
    if len(prompt_text) > 300:
        prompt_text = prompt_text[:300]
        
    encoded_prompt = quote(prompt_text)
    local_path = f"{IMAGE_DIR}/{filename}"

    for attempt in range(1, max_retries + 1):
        # 【核心修复1】每次重试生成一个完全随机的 seed。
        # 作用：打破 CDN 缓存死锁，如果上一次遇到了 500/超时，这次请求会被强制分配给全新的 GPU 节点计算。
        seed = random.randint(1, 9999999)
        
        # 【核心修复2】明确指定稳定的模型 (model=flux)，去掉可能引发冲突的 enhance=false
        api_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true&seed={seed}&model=flux"

        try:
            print(f"[\u23f3 生成中] 正在呼叫 AI 绘图 (第 {attempt}/{max_retries} 次 | 随机种子: {seed}): {filename}")
            
            # 超时时间设为 60 秒
            res = requests.get(api_url, timeout=60)
            
            if res.status_code == 429:
                raise Exception("触发 429 Too Many Requests 限流防御机制")
            
            res.raise_for_status()
            
            # 严格校验：返回的是否真的是图片格式
            content_type = res.headers.get('Content-Type', '')
            if 'image' not in content_type:
                raise ValueError(f"API 返回的不是图片，而是: {content_type}")

            # 保存图片
            with open(local_path, 'wb') as f:
                f.write(res.content)
            
            print(f"[\u2714\ufe0f 成功] 图片已无水印保存: {local_path}")
            
            # 组装 GitHub Raw 的公共访问链接
            return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"
            
        except Exception as e:
            print(f"[\u274c 失败] 绘图请求异常 {filename}: {e}")
            if attempt < max_retries:
                sleep_time = attempt * 5  
                print(f"[\u26a0\ufe0f 保护机制] 程序休眠 {sleep_time} 秒后更换 Seed 重试...")
                time.sleep(sleep_time)
            else:
                raise Exception(f"[\ud83d\udea8 致命错误] 图片 {filename} 经过 {max_retries} 次重试依旧失败！")

def download_real_cover(img_url, filename, max_retries=3):
    """用于下载原著封面的函数"""
    local_path = f"{IMAGE_DIR}/{filename}"
    if not img_url:
        return ""
    for attempt in range(1, max_retries + 1):
        try:
            print(f"正在下载原著封面 (第 {attempt}/{max_retries} 次): {filename}")
            res = requests.get(img_url, timeout=20)
            res.raise_for_status()
            with open(local_path, 'wb') as f:
                f.write(res.content)
            return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"
        except Exception as e:
            print(f"封面下载失败: {e}")
            time.sleep(3)
    return img_url

# ================= 数据抓取模块 =================

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return[]

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_gutenberg_book(history):
    print("正在从 Project Gutenberg 获取书籍...")
    while True:
        page = random.randint(1, 200)
        try:
            res = requests.get(f"https://gutendex.com/books/?page={page}", timeout=10).json()
            books = res.get('results',[])
            random.shuffle(books)
            for book in books:
                book_id = f"gutenberg_{book['id']}"
                if book_id not in history:
                    return {
                        "id": book_id,
                        "title": book.get('title', 'Unknown Title'),
                        "author": ", ".join([a['name'] for a in book.get('authors',[])]),
                        "cover": book.get('formats', {}).get('image/jpeg', ''),
                        "url": f"https://www.gutenberg.org/ebooks/{book['id']}"
                    }
        except Exception as e:
            pass

def get_openlibrary_book(history):
    print("正在从 Open Library 获取书籍...")
    subjects =['literature', 'fiction', 'history', 'science', 'mystery', 'philosophy']
    subject = random.choice(subjects)
    while True:
        offset = random.randint(0, 300)
        url = f"https://openlibrary.org/search.json?subject={subject}&limit=20&offset={offset}"
        try:
            res = requests.get(url, timeout=10).json()
            docs = res.get('docs',[])
            random.shuffle(docs)
            for doc in docs:
                key = doc.get('key', '')
                book_id = f"openlibrary_{key.replace('/works/', '')}"
                if book_id not in history and doc.get('cover_i'):
                    return {
                        "id": book_id,
                        "title": doc.get('title', 'Unknown Title'),
                        "author": ", ".join(doc.get('author_name', ['Unknown'])),
                        "cover": f"https://covers.openlibrary.org/b/id/{doc.get('cover_i')}-L.jpg",
                        "url": f"https://openlibrary.org{key}"
                    }
        except Exception as e:
            pass

# ================= 文案排版生成 =================

def generate_wechat_content(books_data):
    print("正在调用 Gemini API 进行文案与排版创作...")
    
    prompt = """
    你是一个顶级的微信公众号内容总监、资深书评人和 UI 排版专家。我将提供两本外文书籍的数据（JSON格式）。
    
    【核心要求】
    1. 生成一个充满阅读欲望的文章标题（32字内，带有悬念和情绪）。
    2. 生成两本书的文案，每本包含【客观讲解】和【情绪引导】，两本书文案总字数必须极其丰富，达600字左右。
    3. 【极为重要：配图Prompt限制】：为你构思的每张图片写纯英文 Prompt，**必须极简短，限制在30个单词以内**，只描述核心画面、光影和风格，以防止AI绘图引擎崩溃。
       - wechat_cover_prompt: 总结两本书的氛围，用于生成21:9的极美头图。
       - book1_illustration_prompt / book2_illustration_prompt: 匹配原书内容的16:9插图。

    4. 【HTML高级排版】：
       - 必须使用外部容器：
         <section style='margin:0;padding:0;background-color:#f7f8fa;font-family: system-ui, -apple-system, sans-serif;'>
            <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'>
            <section style='padding:20px 15px;'>{content_html}{tags_html}</section>
            <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'>
         </section>
       - {content_html} 请设计成极美的高级白色卡片（border-radius:12px; box-shadow:0 4px 16px rgba(0,0,0,0.06)），带排版留白。
       - 图片必须严格使用这5个占位符（外层加优美的 img 样式，居中，带微小圆角）：
         {{WECHAT_COVER_URL}}
         {{BOOK1_COVER_URL}}
         {{BOOK1_ILLUSTRATION_URL}}
         {{BOOK2_COVER_URL}}
         {{BOOK2_ILLUSTRATION_URL}}

    【输出格式】
    必须纯 JSON 格式（绝对不能带有 Markdown 的 ```json）：
    {
      "article_title": "...",
      "wechat_cover_prompt": "english...",
      "book1_illustration_prompt": "english...",
      "book2_illustration_prompt": "english...",
      "article_html": "..."
    }
    """

    payload = {
        "contents": [{"parts":[{"text": prompt + "\n\n抓取数据：\n" + json.dumps(books_data, ensure_ascii=False)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}
    }
    
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    response = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", headers=headers, json=payload)
    response.raise_for_status()
    
    response_text = response.json()['candidates'][0]['content']['parts'][0]['text']
    response_text = re.sub(r'^```json\s*', '', response_text).strip()
    response_text = re.sub(r'\s*```$', '', response_text).strip()

    return json.loads(response_text)

# ================= 主流程 =================

def main():
    history = load_history()
    
    b1 = get_gutenberg_book(history)
    b2 = get_openlibrary_book(history)
    gemini_data = generate_wechat_content([b1, b2])
    
    print("\n--- 开始调用 AI 绘图 API 并下载至本地 (包含限流及缓存突破保护) ---")
    
    # 获取微信头图 21:9
    wechat_cover_url = generate_and_download_image(gemini_data['wechat_cover_prompt'], 840, 360, "wechat_cover.jpg")
    
    # 每次请求间依然强制休眠 5 秒，解决 429 Too Many Requests
    time.sleep(5) 
    
    # 获取第一本书内页图 16:9
    b1_ill_url = generate_and_download_image(gemini_data['book1_illustration_prompt'], 800, 450, f"{b1['id']}_illustration.jpg")
    time.sleep(5)
    
    # 获取第二本书内页图 16:9
    b2_ill_url = generate_and_download_image(gemini_data['book2_illustration_prompt'], 800, 450, f"{b2['id']}_illustration.jpg")
    time.sleep(5)

    # 下载真实封面
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
    for placeholder, github_url in urls_map.items():
        final_html = final_html.replace(placeholder, github_url)

    final_output = {
        "article_title": gemini_data['article_title'],
        "article_html": final_html,
        "date": TODAY_STR
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=4)
        print(f"\n✔ 每日推送数据已成功保存至 {OUTPUT_FILE}")
    
    history.extend([b1['id'], b2['id']])
    save_history(history)

if __name__ == "__main__":
    main()
