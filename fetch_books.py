import os
import json
import random
import requests
import re

# 配置文件路径
HISTORY_FILE = 'history.json'
OUTPUT_FILE = 'daliy-read.json'

# 从环境变量获取 Gemini API Key
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("未找到 GEMINI_API_KEY 环境变量！")

def load_history():
    """加载历史记录用于去重"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return[]

def save_history(history):
    """保存历史记录"""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_gutenberg_book(history):
    """从 Gutendex 随机获取一本不重复的书"""
    print("正在从 Project Gutenberg 获取书籍...")
    while True:
        # 随机抽取前 200 页中的一页 (每页32本，覆盖最受欢迎的6000本书)
        page = random.randint(1, 200)
        try:
            res = requests.get(f"https://gutendex.com/books/?page={page}", timeout=10).json()
            books = res.get('results',[])
            random.shuffle(books)
            
            for book in books:
                book_id = f"gutenberg_{book['id']}"
                if book_id not in history:
                    # 提取需要的信息
                    title = book.get('title', 'Unknown Title')
                    authors = [a['name'] for a in book.get('authors',[])]
                    author = ", ".join(authors) if authors else "Unknown"
                    cover = book.get('formats', {}).get('image/jpeg', '')
                    url = f"https://www.gutenberg.org/ebooks/{book['id']}"
                    subjects = book.get('subjects',[])
                    intro = f"Subjects: {', '.join(subjects)}" if subjects else "A classic literature book."
                    
                    return {
                        "id": book_id,
                        "source": "Project Gutenberg",
                        "title": title,
                        "author": author,
                        "cover": cover,
                        "description": intro,
                        "url": url
                    }
        except Exception as e:
            print(f"Gutenberg API 请求错误: {e}")

def get_openlibrary_book(history):
    """从 Open Library 随机获取一本不重复的书"""
    print("正在从 Open Library 获取书籍...")
    subjects =['literature', 'fiction', 'history', 'science', 'mystery', 'fantasy', 'romance']
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
                # 确保有封面且未被抓取过
                if book_id not in history and doc.get('cover_i'):
                    title = doc.get('title', 'Unknown Title')
                    authors = doc.get('author_name', ['Unknown'])
                    author = ", ".join(authors)
                    cover_id = doc.get('cover_i')
                    cover = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                    book_url = f"https://openlibrary.org{key}"
                    
                    # 尝试获取书籍首句或生成简短描述
                    first_sentence = doc.get('first_sentence', [''])[0]
                    intro = first_sentence if first_sentence else f"A widely read book in {subject}. First published in {doc.get('first_publish_year', 'unknown')}."

                    return {
                        "id": book_id,
                        "source": "Open Library",
                        "title": title,
                        "author": author,
                        "cover": cover,
                        "description": intro,
                        "url": book_url
                    }
        except Exception as e:
            print(f"OpenLibrary API 请求错误: {e}")

def generate_wechat_content(books_data):
    """调用 Gemini API 翻译并生成排版 HTML"""
    print("正在调用 Gemini API 进行翻译和 HTML 排版...")
    
    prompt = """
    你是一个专业的微信公众号排版专家和翻译。我将提供两本英文书籍的数据（JSON格式）。
    请完成以下任务：
    1. 将书籍的标题、作者、简介翻译成通顺的中文。如果原简介太单调，请根据书名和作者发挥创意，为它写一段约80-100字的中文精彩推荐语。
    2. 生成一个吸引人的微信公众号文章标题（需体现这两本书或阅读主题）。
    3. 生成微信公众号的HTML。**你必须严格按照我给的外部容器模板，并将书本内容替换到 {content_html} 处，将标签替换到 {tags_html} 处。**
    4. 在生成 {content_html} 时，请使用微信支持的 <section> 标签和行内样式 (inline CSS)，做到排版美观（例如居中、阴影、留白、字体颜色等）。包含：中文书名、原作者、封面图(img标签)、中文推荐语、以及“阅读原著”的链接。

    这是你必须使用的最外层模板：
    <section style='margin:0;padding:0;background-color:#fff;'>
        <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'>
        <section style='padding:0;'>{content_html}{tags_html}</section>
        <img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'>
    </section>

    【强制要求】
    你的输出必须是合法的纯 JSON 格式（不要使用 ```json 包裹文本）。JSON 包含两个字段：
    - "article_title": "生成的文章标题"
    - "article_html": "生成的完整HTML代码"
    """

    payload = {
        "contents": [
            {
                "parts":[
                    {"text": prompt + "\n\n以下是今天抓取的书籍数据：\n" + json.dumps(books_data, ensure_ascii=False)}
                ]
            }
        ]
    }

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"
    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Gemini API 错误: {response.text}")

    result_json = response.json()
    response_text = result_json['candidates'][0]['content']['parts'][0]['text']

    # 尝试清理可能附带的 markdown json 标记
    response_text = re.sub(r'^```json\s*', '', response_text)
    response_text = re.sub(r'\s*```$', '', response_text)

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        print("Gemini 返回的不是标准 JSON 格式！原始内容：", response_text)
        # 兜底处理
        return {
            "article_title": "每日阅读推荐",
            "article_html": "解析生成内容失败，请检查模型输出。"
        }

def main():
    history = load_history()
    
    # 1. 抓取书籍
    gutenberg_book = get_gutenberg_book(history)
    openlibrary_book = get_openlibrary_book(history)
    books_data =[gutenberg_book, openlibrary_book]
    
    # 2. 调用 Gemini 处理内容
    wechat_content = generate_wechat_content(books_data)
    
    # 3. 保存今天的结果（日更新，不记录此文件的历史）
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(wechat_content, f, ensure_ascii=False, indent=4)
        print(f"每日推送数据已成功保存至 {OUTPUT_FILE}")
    
    # 4. 更新历史记录（用于去重）
    history.append(gutenberg_book['id'])
    history.append(openlibrary_book['id'])
    save_history(history)
    print("历史记录已更新。")

if __name__ == "__main__":
    main()
