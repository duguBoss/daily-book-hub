import os, json, random, requests, re, time, shutil
from datetime import datetime
from PIL import Image, ImageFilter

# ================= 配置 =================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'duguBoss/daily-book-hub')
GITHUB_BRANCH = "main"
TODAY_DATE = datetime.utcnow()
IMAGE_DIR = f"images/{TODAY_DATE.strftime('%Y-%m-%d')}"

TOP_GIF = "https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif"
BOTTOM_GIF = "https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif"

# ================= 工具函数 =================
def minify_html(html):
    """极致压缩：使用单引号，移除转义，压缩为空行，适配微信算法"""
    html = html.replace('"', "'")             # 强制使用单引号
    html = html.replace('\\', '')             # 移除所有转义反斜杠
    html = re.sub(r'[\r\n\t]+', '', html)     # 移除换行与制表符
    html = re.sub(r'>\s+<', '><', html)       # 移除标签间空格
    html = re.sub(r'\s{2,}', ' ', html)       # 合并多余空格
    return html.strip()

def clear_images_weekly():
    if TODAY_DATE.weekday() == 0 and os.path.exists('images'):
        shutil.rmtree('images')
    os.makedirs(IMAGE_DIR, exist_ok=True)

def get_github_url(local_path):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{local_path}" if local_path else ""

def download(url, name):
    p = f"{IMAGE_DIR}/{name}"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        with open(p, 'wb') as f: f.write(res.content)
        return p
    except: return None

def get_book(history, source):
    for _ in range(5):
        try:
            if source == "gutenberg":
                res = requests.get(f"https://gutendex.com/books/?page={random.randint(1, 500)}", timeout=15).json()
                items = res.get('results', [])
            else:
                url = f"https://openlibrary.org/search.json?subject=literature&limit=20&offset={random.randint(0, 500)}"
                items = requests.get(url, timeout=15).json().get('docs', [])
            random.shuffle(items)
            for item in items:
                b_id = str(item.get('id')) if source == "gutenberg" else item.get('key', '').split('/')[-1]
                cover = item.get('formats', {}).get('image/jpeg') if source == "gutenberg" else f"https://covers.openlibrary.org/b/id/{item.get('cover_i')}-L.jpg"
                if cover and f"{source}_{b_id}" not in history:
                    return {"id": f"{source}_{b_id}", "title": item.get('title', 'Unknown'), "cover": cover}
        except: time.sleep(2)
    return None

def generate_content(b1, b2):
    prompt = f"""你是一名擅长微信流量算法的公众号主编。根据以下书籍撰写推文。
    书籍：{json.dumps([b1, b2], ensure_ascii=False)}
    要求：
    1. 标题：32字内，采用爆款逻辑（情绪钩子/反差/认知升级）。
    2. 内容：符合微信推荐算法，短句，强痛点共鸣，600字以上。
    3. HTML：使用单引号属性，预留占位符 WECHAT_COVER, B1_COVER, B2_COVER。
    4. 禁令：严禁使用双引号，严禁使用反斜杠。
    输出格式：JSON {{"article_title": "...", "article_html": "..."}}"""
    
    res = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", 
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}})
    return json.loads(re.sub(r'```json\s?|```', '', res.json()['candidates'][0]['content']['parts'][0]['text']))

def robust_replace(html, placeholder, real_url):
    return re.sub(r'[\{\[\(]{0,3}' + re.escape(placeholder) + r'[\}\]\)]{0,3}', real_url, html).replace(placeholder, real_url)

# ================= 主流程 =================
def main():
    clear_images_weekly()
    history = json.load(open('history.json')) if os.path.exists('history.json') else []
    b1, b2 = get_book(history, "gutenberg"), get_book(history, "openlibrary")
    if not b1 or not b2: exit("书籍抓取失败")
    
    data = generate_content(b1, b2)
    p1, p2 = download(b1['cover'], f"{b1['id']}.jpg"), download(b2['cover'], f"{b2['id']}.jpg")
    
    # 合成头图
    wc_local = f"{IMAGE_DIR}/wechat_cover.jpg"
    with Image.open(p2) as img:
        bg = img.convert("RGB").resize((840, 360)).filter(ImageFilter.GaussianBlur(25)).point(lambda p: p * 0.5)
        fg = img.resize((280, 280), Image.Resampling.LANCZOS)
        bg.paste(fg, (280, 40))
        bg.save(wc_local, "JPEG", quality=90)
        
    # 注入数据并压缩
    html = data['article_html']
    mappings = [("WECHAT_COVER", get_github_url(wc_local)), ("B1_COVER", get_github_url(p1)), ("B2_COVER", get_github_url(p2))]
    for p, u in mappings: html = robust_replace(html, p, u)
    
    # 组合整体 HTML 并压缩
    full_html = f"<section><img src='{TOP_GIF}' style='width:100%;display:block;'>{html}<img src='{BOTTOM_GIF}' style='width:100%;display:block;'></section>"
    
    final_output = {
        "article_title": data['article_title'],
        "article_html": minify_html(full_html.replace('[', '').replace(']', '')),
        "covers": [u for p, u in mappings],
        "date": TODAY_DATE.strftime('%Y-%m-%d')
    }
    
    with open('daliy-read.json', 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, separators=(',', ':'))
    
    json.dump(history + [b1['id'], b2['id']], open('history.json', 'w'))

if __name__ == "__main__": main()
