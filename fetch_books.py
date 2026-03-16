import os
import json
import random
import requests
import re
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
# GitHub Actions 会自动注入 GITHUB_REPOSITORY (格式: username/repo)
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'your-username/your-repo')
# 默认分支通常为 main
GITHUB_BRANCH = "main"

if not GEMINI_API_KEY:
    raise ValueError("未找到 GEMINI_API_KEY 环境变量！")

# 创建今日图片文件夹
os.makedirs(IMAGE_DIR, exist_ok=True)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return[]

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def download_image(img_url, filename):
    """下载图片到本地，并返回 GitHub 的公网访问 URL"""
    local_path = f"{IMAGE_DIR}/{filename}"
    try:
        print(f"正在下载图片 -> {local_path} ...")
        res = requests.get(img_url, timeout=15)
        res.raise_for_status()
        with open(local_path, 'wb') as f:
            f.write(res.content)
        
        # 组装 GitHub Raw 的公共访问链接
        # 也可以替换为 jsDelivr CDN: f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@{GITHUB_BRANCH}/{local_path}"
        github_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"
        return github_url
    except Exception as e:
        print(f"图片下载失败 {img_url}: {e}")
        # 如果下载失败，降级使用原图链接
        return img_url

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
            print(f"Gutenberg API 请求错误: {e}")

def get_openlibrary_book(history):
    print("正在从 Open Library 获取书籍...")
    subjects =['literature', 'fiction', 'history', 'science', 'mystery']
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
            print(f"OpenLibrary API 请求错误: {e}")

def generate_wechat_content(books_data):
    print("正在调用 Gemini API 进行文案与排版创作...")
    
    prompt = """
    你是一个顶级的微信公众号内容总监、资深书评人和 UI 排版专家。我将提供两本外文原版书籍的数据（JSON格式）。
    请严格按照以下要求完成任务：

    1. 【文章标题生成】：
       - 情绪阅读欲望方向，绝对在32个字符以内。
       - 体现这是一篇读书/推荐书籍的文章（如“熬夜想读”、“治愈精神内耗”等），有悬念，激发点击欲。

    2. 【文案撰写（核心重点，总字数必须约600字左右）】：
       每本书包含：
       - 【客观讲解】：深度剖析核心剧情、思想内核或文学价值。
       - 【情绪引导】：直击读者内心的痛点，营造“哪怕只读一章，也会有所启发”的冲动氛围。

    3. 【配图 Prompt 构思（纯英文）】：
       - 构思一张微信公众号头图（21:9）：总结这两本书的主题氛围，写一段极具美感的英文画面描述。
       - 为每本书单独构思一张内文插图（16:9）：符合该书意境的英文画面描述。

    4. 【HTML高级排版（强制使用占位符）】：
       - 你必须使用以下外部容器模板，替换 {content_html} 和 {tags_html}：
         <section style='margin:0;padding:0;background-color:#f7f8fa;font-family: system-ui, -apple-system, sans-serif;'>
            <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'>
            <section style='padding:20px 15px;'>{content_html}{tags_html}</section>
            <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'>
         </section>
       - {content_html} 必须使用极度精致的纯白卡片式布局（border-radius:12px; box-shadow:0 4px 16px rgba(0,0,0,0.06)），深灰色字体，行高1.8。
       - **在 HTML 中，涉及图片的地方必须严格使用以下占位符（千万不要自己生成链接）**：
         文章最开头的21:9头图: {{WECHAT_COVER_URL}}
         第一本书的原版封面: {{BOOK1_COVER_URL}}
         第一本书的意境配图: {{BOOK1_ILLUSTRATION_URL}}
         第二本书的原版封面: {{BOOK2_COVER_URL}}
         第二本书的意境配图: {{BOOK2_ILLUSTRATION_URL}}
       - 占位符外部请包裹好精美的 img 标签及阴影样式。例如： `<img src='{{WECHAT_COVER_URL}}' style='width:100%; border-radius:8px; display:block; margin-bottom:15px;'>`

    【强制JSON输出格式】
    必须且仅包含以下字段的 JSON（严禁Markdown包裹）：
    {
      "article_title": "...",
      "wechat_cover_prompt": "纯英文",
      "book1_illustration_prompt": "纯英文",
      "book2_illustration_prompt": "纯英文",
      "article_html": "包含占位符的高级排版HTML..."
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

def main():
    history = load_history()
    
    # 1. 抓取书籍数据
    b1 = get_gutenberg_book(history)
    b2 = get_openlibrary_book(history)
    
    # 2. Gemini 生成结构化数据 (包含 HTML 排版和配图 Prompts)
    gemini_data = generate_wechat_content([b1, b2])
    
    # 3. 构建 Pollinations AI 生成图片的 URL
    # 头图 21:9 -> 840x360
    wechat_cover_gen_url = f"https://image.pollinations.ai/prompt/{quote(gemini_data['wechat_cover_prompt'])}?width=840&height=360&nologo=true"
    # 内文图 16:9 -> 800x450
    b1_ill_gen_url = f"https://image.pollinations.ai/prompt/{quote(gemini_data['book1_illustration_prompt'])}?width=800&height=450&nologo=true"
    b2_ill_gen_url = f"https://image.pollinations.ai/prompt/{quote(gemini_data['book2_illustration_prompt'])}?width=800&height=450&nologo=true"

    # 4. 下载所有图片到本地目录，并获取 GitHub Raw 公开链接
    print(f"\n--- 开始下载图片至 {IMAGE_DIR} ---")
    urls_map = {
        "{{WECHAT_COVER_URL}}": download_image(wechat_cover_gen_url, "wechat_cover.jpg"),
        "{{BOOK1_COVER_URL}}": download_image(b1['cover'], f"{b1['id']}_cover.jpg"),
        "{{BOOK1_ILLUSTRATION_URL}}": download_image(b1_ill_gen_url, f"{b1['id']}_illustration.jpg"),
        "{{BOOK2_COVER_URL}}": download_image(b2['cover'], f"{b2['id']}_cover.jpg"),
        "{{BOOK2_ILLUSTRATION_URL}}": download_image(b2_ill_gen_url, f"{b2['id']}_illustration.jpg")
    }

    # 5. 替换 HTML 中的占位符
    final_html = gemini_data['article_html']
    for placeholder, github_url in urls_map.items():
        final_html = final_html.replace(placeholder, github_url)

    # 6. 整理最终的输出 JSON
    final_output = {
        "article_title": gemini_data['article_title'],
        "article_html": final_html,
        "date": TODAY_STR
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=4)
        print(f"\n✔ 每日推送数据已成功保存至 {OUTPUT_FILE}")
    
    # 7. 写入去重历史
    history.extend([b1['id'], b2['id']])
    save_history(history)

if __name__ == "__main__":
    main()
