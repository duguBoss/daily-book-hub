import os, json, random, requests, re, time
from datetime import datetime
from PIL import Image, ImageFilter

# ================= 配置 =================
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'duguBoss/daily-book-hub')
GITHUB_BRANCH = "main"
IMAGE_DIR = f"images/{datetime.utcnow().strftime('%Y-%m-%d')}"
os.makedirs(IMAGE_DIR, exist_ok=True)

def get_cdn_url(local_path):
    return f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@{GITHUB_BRANCH}/{local_path}"

def process_and_upload(b1, b2):
    # 下载封面
    def download(url, name):
        p = f"{IMAGE_DIR}/{name}"
        with open(p, 'wb') as f: f.write(requests.get(url, timeout=20).content)
        return p
    
    p1, p2 = download(b1['cover'], f"{b1['id']}.jpg"), download(b2['cover'], f"{b2['id']}.jpg")
    
    # 合成 21:9 头图
    wc_path = f"{IMAGE_DIR}/wechat_cover.jpg"
    with Image.open(p2) as img: # 以第二本书封面为底做模糊
        bg = img.convert("RGB").resize((840, 360), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(15)).point(lambda p: p * 0.6)
        fg = img.resize((200, 300), Image.Resampling.LANCZOS)
        bg.paste(fg, (320, 30))
        bg.save(wc_path, "JPEG")
    return get_cdn_url(wc_path), get_cdn_url(p1), get_cdn_url(p2)

def generate_content(b1, b2):
    prompt = f"""
    你是资深出版策划人。请为这两本书撰写一篇高质量微信公众号推文。
    书籍数据：{json.dumps([b1, b2])}
    
    要求：
    1. 标题：32字内，富有情绪感与阅读诱惑力。
    2. 内容：每本书撰写 300 字以上（两本共 600+ 字）。包含：
       - 中文译名 / 原名 (Title / Original Title)
       - 作者 (Author)
       - 深度导读：客观讲述背景+思想内核，辅以中英文对照的精辟引用（引用部分需提供中英对照）。
       - 情绪引导：用极具感染力的文字邀请读者阅读。
    3. HTML排版：
       - 使用如下固定模板框架：
       <section style='margin:0;padding:0;background-color:#fff;'><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/0?wx_fmt=gif' style='width:100%;display:block;'><section style='padding:20px;line-height:1.8;color:#333;text-align:justify;letter-spacing:0.5px;'>{{CONTENT}}</section><img src='https://mmbiz.qpic.cn/mmbiz_gif/3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/0?wx_fmt=gif' style='width:100%;display:block;'></section>
       - 卡片样式：背景#f9f9f9，圆角10px，内边距20px。
       - 图片标签直接放入：<img src='{{URL}}' style='width:100%;border-radius:6px;margin:15px 0;'>
    """
    res = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent", 
                        headers={"x-goog-api-key": os.environ.get('GEMINI_API_KEY'), "Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}})
    return json.loads(res.json()['candidates'][0]['content']['parts'][0]['text'])

def main():
    # 逻辑：抓取 -> 生成内容 -> 合成图片 -> 替换HTML -> 保存
    # (此处省略get_book抓取逻辑，复用你之前的)
    # ... 
    data = generate_content(b1, b2)
    wc, c1, c2 = process_and_upload(b1, b2)
    
    html = data['article_html'].replace('{{WECHAT_COVER}}', wc).replace('{{B1_COVER}}', c1).replace('{{B2_COVER}}', c2)
    
    result = {
        "article_title": data['article_title'],
        "article_html": html,
        "covers": [wc, c1, c2]
    }
    with open('daliy-read.json', 'w', encoding='utf-8') as f: json.dump(result, f, ensure_ascii=False, indent=4)

if __name__ == "__main__": main()
