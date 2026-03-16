import os, json, random, requests, re, time
from datetime import datetime
from PIL import Image, ImageFilter

# ================= 配置 =================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
# 自动获取仓库名，确保 Raw 链接生成正确
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'duguBoss/daily-book-hub')
GITHUB_BRANCH = "main"
IMAGE_DIR = f"images/{datetime.utcnow().strftime('%Y-%m-%d')}"
os.makedirs(IMAGE_DIR, exist_ok=True)

# ================= 基础工具 =================
def get_github_url(local_path):
    """生成 GitHub Raw 直链"""
    if not local_path: return ""
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
    """带重试的书籍抓取逻辑"""
    for _ in range(5):
        try:
            if source == "gutenberg":
                res = requests.get(f"https://gutendex.com/books/?page={random.randint(1, 300)}", timeout=15).json()
                items = res.get('results', [])
            else:
                subjects = ['literature', 'classics', 'history', 'philosophy', 'fiction']
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
    """调用 Gemini 生成深度推文"""
    prompt = f"""
    你是资深书评人，擅长中英双语文学拆解。请为这两本书生成微信推文数据。
    书籍数据：{json.dumps([b1, b2], ensure_ascii=False)}
    
    【核心要求】
    1. article_title: 32字内极其吸睛、富有情绪的中文标题。
    2. article_html: 必须输出 600 字以上的高质量内容。包含：
       - 书籍中英文对照名、作者介绍。
       - 客观深度解析：背景与核心思想。
       - 中英对照的名句引用。
       - 强烈的情绪引导推荐。
    3. 排版规范：
       - 外层框架：<section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:20px;line-height:1.8;color:#333;text-align:justify;'>{{CONTENT}}</section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>
       - 内容块卡片：<div style='background-color:#f9f9f9;padding:20px;border-radius:10px;margin-bottom:20px;'>...</div>
       - 图片插槽（**必须准确使用以下字符**）：
         微信大头图插槽：{{WECHAT_COVER}}
         书1封面插槽：{{B1_COVER}}
         书2封面插槽：{{B2_COVER}}
       - 图片标签样式：<img src='{{占位符}}' style='width:100%;border-radius:10px;margin:15px 0;'>
    
    必须且仅输出标准 JSON 格式，不要包含 ```json 等任何 Markdown。
    """
    res = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", 
                        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}})
    
    raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
    clean_json = re.sub(r'```json\s?|```', '', raw_text).strip()
    return json.loads(clean_json)

def robust_replace(html, placeholder, real_url):
    """强力替换函数：处理各种大括号变体及大小写"""
    # 匹配模式包括： {{PLACEHOLDER}}, {PLACEHOLDER}, PLACEHOLDER (不区分大小写)
    pattern = re.compile(r'\{{1,2\}' + re.escape(placeholder) + r'\}{1,2\}', re.IGNORECASE)
    # 如果正则没匹配到，最后再尝试一次直接替换
    if not pattern.search(html):
        return html.replace(placeholder, real_url)
    return pattern.sub(real_url, html)

# ================= 主流程 =================
def main():
    history = json.load(open('history.json')) if os.path.exists('history.json') else []
    b1, b2 = get_book(history, "gutenberg"), get_book(history, "openlibrary")
    if not b1 or not b2: exit("无法获取书籍数据，请重试")
    
    # 1. 生成内容
    data = generate_content(b1, b2)
    
    # 2. 图片处理
    p1_local = download(b1['cover'], f"{b1['id']}.jpg")
    p2_local = download(b2['cover'], f"{b2['id']}.jpg")
    
    # 合成 21:9 模糊头图
    wc_local = f"{IMAGE_DIR}/wechat_cover.jpg"
    with Image.open(p2_local) as img:
        bg = img.convert("RGB").resize((840, 360)).filter(ImageFilter.GaussianBlur(15)).point(lambda p: p * 0.6)
        fg = img.resize((200, 300))
        bg.paste(fg, (320, 30))
        bg.save(wc_local, "JPEG")
        
    # 3. 准备 GitHub 链接
    wc_url = get_github_url(wc_local)
    b1_url = get_github_url(p1_local)
    b2_url = get_github_url(p2_local)
    
    # 4. 【核心修复】执行强力替换占位符
    html = data.get('article_html', "")
    html = robust_replace(html, "WECHAT_COVER", wc_url)
    html = robust_replace(html, "B1_COVER", b1_url)
    html = robust_replace(html, "B2_COVER", b2_url)
    
    # 5. 保存结果
    final_data = {
        "article_title": data.get('article_title', "深度阅读推荐"),
        "article_html": html,
        "covers": [wc_url, b1_url, b2_url],
        "date": datetime.utcnow().strftime('%Y-%m-%d')
    }
    
    with open('daliy-read.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=4)
        print(f"✔ 成功生成：{final_data['article_title']}")
    
    # 6. 更新历史
    json.dump(history + [b1['id'], b2['id']], open('history.json', 'w'))

if __name__ == "__main__": 
    main()
