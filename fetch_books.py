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
    # 【优化】为书籍封面专门设计了“3D立体书架”模板，要求 AI 必须1:1复制
    prompt = f"""你是一名擅长微信流量算法的公众号主编兼高级排版设计师。根据以下书籍撰写推文。
    书籍：{json.dumps([b1, b2], ensure_ascii=False)}
    要求：
    1. 标题：32字内，采用爆款逻辑（情绪钩子/反差/认知升级）。
    2. 内容：符合微信推荐算法，短句，强痛点共鸣，600字以上。
    3. HTML排版要求（极简高级风）：
       - 必须全部使用【单引号】编写属性，严禁使用双引号和反斜杠。
       - 头图样式（可选）：<img src='WECHAT_COVER' style='width:100%; border-radius:12px; margin-bottom:30px; display:block; box-shadow:0 4px 15px rgba(0,0,0,0.05);'>
       - 【重要】书籍封面必须使用“立体书架”样式（直接复制以下整段代码，仅替换B1_COVER即可）：
         <div style='text-align:center; margin:45px 0;'>
           <div style='display:inline-block; padding-bottom:15px; border-bottom:4px solid #e8e8e8; width:220px;'>
             <img src='B1_COVER' style='width:140px; height:auto; border-radius:3px 10px 10px 3px; box-shadow:8px 12px 24px rgba(0,0,0,0.18); border-left:3px solid #f9f9f9; display:block; margin:0 auto;'>
           </div>
           <p style='font-size:12px; color:#b0b0b0; margin-top:12px; letter-spacing:2px;'>▲ 本期馆藏推荐</p>
         </div>
       - （B2书籍同理，直接复制上述代码，把B1_COVER换成B2_COVER即可）
       - 小标题样式：<h3 style='font-size:17px; color:#222; border-left:4px solid #d4af37; padding-left:12px; margin:40px 0 20px 0; letter-spacing:1px;'>
       - 正文段落样式（留白、高级灰、大行高）：<p style='font-size:15px; color:#4a4a4a; line-height:2.2; margin-bottom:20px; text-align:justify; letter-spacing:1px;'>
       - 引用/金句样式：<blockquote style='background:#fcfcfc; border-left:3px solid #e0e0e0; padding:15px 20px; color:#666; font-size:14px; margin:25px 0; line-height:1.8;'>
    4. 占位符：必须在对应位置插入 WECHAT_COVER, B1_COVER, B2_COVER。
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
        
    # 注入数据
    html = data['article_html']
    mappings = [("WECHAT_COVER", get_github_url(wc_local)), ("B1_COVER", get_github_url(p1)), ("B2_COVER", get_github_url(p2))]
    for p, u in mappings: html = robust_replace(html, p, u)
    
    # 重新组合 HTML，设定全局高级容器
    content_wrapper_style = "padding: 30px 20px; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;"
    top_gif_style = "width: 100%; display: block; margin-bottom: 25px;"
    bottom_gif_style = "width: 100%; display: block; margin-top: 40px;"
    
    full_html = (
        f"<section style='background-color: #ffffff;'>"
        f"<img src='{TOP_GIF}' style='{top_gif_style}'>"
        f"<section style='{content_wrapper_style}'>{html}</section>"
        f"<img src='{BOTTOM_GIF}' style='{bottom_gif_style}'>"
        f"</section>"
    )
    
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
