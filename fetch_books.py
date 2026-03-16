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
    """生成 GitHub Raw 直链"""
    if not local_path: return ""
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}"

def download(url, name):
    p = f"{IMAGE_DIR}/{name}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
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
                res = requests.get(f"https://gutendex.com/books/?page={random.randint(1, 500)}", timeout=15).json()
                items = res.get('results', [])
            else:
                subjects = ['literature', 'classics', 'philosophy', 'history', 'fiction', 'art']
                url = f"https://openlibrary.org/search.json?subject={random.choice(subjects)}&limit=20&offset={random.randint(0, 500)}"
                res = requests.get(url, timeout=15).json()
                items = res.get('docs', [])
            
            random.shuffle(items)
            for item in items:
                b_id = str(item.get('id')) if source == "gutenberg" else item.get('key', '').split('/')[-1]
                cover = item.get('formats', {}).get('image/jpeg') if source == "gutenberg" else f"https://covers.openlibrary.org/b/id/{item.get('cover_i')}-L.jpg"
                if cover and f"{source}_{b_id}" not in history:
                    return {
                        "id": f"{source}_{b_id}", 
                        "title": item.get('title', 'Unknown'), 
                        "author": str(item.get('authors' if source == "gutenberg" else 'author_name', ['Unknown'])), 
                        "cover": cover
                    }
        except: time.sleep(2)
    return None

def generate_content(b1, b2):
    """调用 Gemini 生成内容，并增加防御性解析"""
    prompt = f"""
    你是一个拥有百万粉丝的爆文读书博主。请根据以下书籍数据撰写一篇深度推文。
    书籍数据：{json.dumps([b1, b2], ensure_ascii=False)}
    
    【写作要求】
    1. 标题：32字内，极具情绪张力和点击欲望。
    2. 正文：**必须全部使用优美、地道的中文撰写**。两本书介绍加起来必须超过 600 字。
    3. 结构：书名与作者采用 [中文译名 (英文原著)] 格式，内容需包含深度背景分析、核心认知拆解及情绪化推荐语。
    4. 算法偏好：多用金句，语言有节奏感，能直击现代人精神痛点。

    【排版规范】
    - 根节点必须是固定 section：<section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:20px;line-height:1.8;color:#333;text-align:justify;'>{{CONTENT}}</section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>
    - 必须准确使用插槽：{{WECHAT_COVER}}、{{B1_COVER}}、{{B2_COVER}}。

    【注意】
    你必须且只能返回一个标准的 JSON 对象。**严禁返回 JSON 数组/列表**。
    格式：{{"article_title": "...", "article_html": "..."}}
    """

    res = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", 
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}], 
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}
        }
    )
    
    raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
    clean_json = re.sub(r'```json\s?|```', '', raw_text).strip()
    data = json.loads(clean_json)

    # 【防御性修复】如果模型不听话返回了列表，取第一个元素
    if isinstance(data, list):
        data = data[0]
    
    return data

def robust_replace(html, placeholder, real_url):
    """强力占位符替换"""
    pattern = re.compile(r'\{{1,2\}' + re.escape(placeholder) + r'\}{1,2\}', re.IGNORECASE)
    if not pattern.search(html):
        return html.replace(placeholder, real_url)
    return pattern.sub(real_url, html)

# ================= 主流程 =================
def main():
    history = json.load(open('history.json')) if os.path.exists('history.json') else []
    
    # 抓取书籍
    b1 = get_book(history, "gutenberg")
    b2 = get_book(history, "openlibrary")
    if not b1 or not b2: exit("无法获取书籍数据")
    
    # 1. AI 创作内容
    data = generate_content(b1, b2)
    
    # 2. 图片处理
    p1_local = download(b1['cover'], f"{b1['id']}.jpg")
    p2_local = download(b2['cover'], f"{b2['id']}.jpg")
    
    # 物理合成微信大头图
    wc_local = f"{IMAGE_DIR}/wechat_cover.jpg"
    with Image.open(p2_local) as img:
        img = img.convert("RGB")
        bg = img.resize((840, 360)).filter(ImageFilter.GaussianBlur(20)).point(lambda p: p * 0.6)
        fg_h = 300
        fg_w = int(fg_h * (img.width / img.height))
        fg = img.resize((fg_w, fg_h), Image.Resampling.LANCZOS)
        bg.paste(fg, ((840 - fg_w) // 2, 30))
        bg.save(wc_local, "JPEG", quality=90)
        
    # 3. 获取地址
    wc_url = get_github_url(wc_local)
    b1_url = get_github_url(p1_local)
    b2_url = get_github_url(p2_local)
    
    # 4. 缝合内容 (修复了之前的 data.get 报错)
    html_content = data.get('article_html', "")
    html_content = robust_replace(html_content, "WECHAT_COVER", wc_url)
    html_content = robust_replace(html_content, "B1_COVER", b1_url)
    html_content = robust_replace(html_content, "B2_COVER", b2_url)
    
    # 5. 保存 JSON
    final_output = {
        "article_title": data.get('article_title', "深度阅读：治愈内心的不二法门"),
        "article_html": html_content,
        "covers": [wc_url, b1_url, b2_url],
        "date": datetime.utcnow().strftime('%Y-%m-%d')
    }
    
    with open('daliy-read.json', 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=4)
        print(f"✔ 成功生成文章：{final_output['article_title']}")
    
    # 6. 保存历史
    json.dump(history + [b1['id'], b2['id']], open('history.json', 'w'))

if __name__ == "__main__": 
    main()
