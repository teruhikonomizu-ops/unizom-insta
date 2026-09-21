"""2026-09-22 セール告知の1枚（4:5・1080x1350）。手作りの回なので、このパック専用の組み立て。"""
import pathlib
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = pathlib.Path(__file__).resolve().parent
FONTS = HERE.parents[2] / "assets" / "fonts"
B = str(FONTS / "NotoSansJP-Bold.otf"); M = str(FONTS / "NotoSansJP-Medium.otf")
W, H = 1080, 1350
RED = (226, 40, 48); YEL = (255, 214, 64); WHITE = (255, 255, 255)

# 背景: 黒〜深い赤の斜めグラデ＋斜線（セールの札の雰囲気）
bg = Image.new("RGB", (W, H), (14, 14, 18))
px = bg.load()
for y in range(H):
    for x in range(W):
        t = max(0.0, min(1.0, (x * 0.45 + y) / (W * 0.45 + H)))
        px[x, y] = (int(16 + 150 * t * t), int(14 + 8 * t), int(18 + 12 * t))
d = ImageDraw.Draw(bg, "RGBA")
for i in range(-H, W, 90):
    d.line([(i, H), (i + H, 0)], fill=(255, 255, 255, 10), width=26)

def f(p, s): return ImageFont.truetype(p, s)
def center(text, y, font, fill, stroke=0):
    w = d.textlength(text, font=font)
    d.text(((W - w) / 2, y), text, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))

# 上: 帯＋見出し
d.rectangle([0, 0, W, 16], fill=RED)
center("unizom からのお知らせ", 58, f(B, 38), YEL)
center("セール開催中", 116, f(B, 148), WHITE)

# モール2段
def mall(y, name, sub, note):
    d.rounded_rectangle([70, y, W - 70, y + 118], radius=18, fill=(255, 255, 255, 235))
    d.rounded_rectangle([70, y, 96, y + 118], radius=0, fill=RED)
    d.text((126, y + 12), name, font=f(B, 46), fill=(20, 20, 24))
    d.text((126, y + 72), sub, font=f(M, 30), fill=(70, 70, 78))
    nw = d.textlength(note, font=f(B, 32))
    d.rounded_rectangle([W - 110 - nw - 28, y + 34, W - 96, y + 86], radius=26, fill=RED)
    d.text((W - 110 - nw - 14, y + 38), note, font=f(B, 32), fill=WHITE)
mall(330, "楽天市場", "お買い物マラソン", "9/24(木) 01:59まで")
mall(470, "Amazon", "ファッションタイムセール祭り", "9/28(月)まで")

# 商品カード2枚
def product(path, box, label):
    x0, y0, x1, y1 = box
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0 + 8, y0 + 14, x1 + 8, y1 + 14], radius=28, fill=(0, 0, 0, 150))
    bg.paste(sh.filter(ImageFilter.GaussianBlur(14)), (0, 0), sh.filter(ImageFilter.GaussianBlur(14)))
    dd = ImageDraw.Draw(bg, "RGBA")
    dd.rounded_rectangle(box, radius=28, fill=WHITE)
    im = Image.open(path).convert("RGB")
    side = min(x1 - x0, y1 - y0 - 84) - 24
    im = im.resize((side, side), Image.LANCZOS)
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, side, side], radius=18, fill=255)
    bg.paste(im, (x0 + (x1 - x0 - side) // 2, y0 + 12), mask)
    ft = f(B, 36); tw = dd.textlength(label, font=ft)
    dd.text((x0 + (x1 - x0 - tw) / 2, y1 - 68), label, font=ft, fill=(20, 20, 24))

top = 690
d.rounded_rectangle([70, top - 66, 70 + 420, top - 14], radius=26, fill=YEL)
d.text((96, top - 64), "新商品も 好評発売中", font=f(B, 36), fill=(20, 20, 24))
product(HERE / "raw" / "bag.jpg", (70, top, 525, top + 540), "防水リュック")
product(HERE / "raw" / "insole.jpg", (555, top, 1010, top + 540), "長靴専用インソール")
d = ImageDraw.Draw(bg, "RGBA")
center("詳しくはプロフィールのリンクから", 1268, f(M, 34), WHITE)
d.rectangle([0, H - 16, W, H], fill=RED)
bg.save(HERE / "1.jpg", quality=92)
print("saved", HERE / "1.jpg")
