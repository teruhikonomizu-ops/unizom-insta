# カルーセル用の文字載せ。写真の上に読める文字を置き、投稿用のJPEGを書き出す。
#
# 使い方: python3 scripts/overlay_cards.py <パックのフォルダ>
# そのフォルダの cards.json を読み、各カードを 1080x1350(4:5) のJPEGにする。
#
# ⚠ InstagramのAPIはPNGを受け付けない。必ずJPEGで書き出すこと。
# ⚠ フォントはリポジトリ同梱の Noto Sans JP を使う。
#    WindowsのYu Gothicを使うと、クラウド(ubuntu)に無いので見た目が変わり、
#    はみ出し検査の結果もローカルとCIでズレる。**同じフォントを両方で使う。**
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350          # Instagramのフィード縦位置いっぱい(4:5)
MARGIN_X = 80
BOTTOM_PAD = 110

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "assets", "fonts")
FONT_BOLD = os.path.join(FONTS, "NotoSansJP-Bold.otf")
FONT_MED = os.path.join(FONTS, "NotoSansJP-Medium.otf")


def hexc(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def fit(im):
    """元画像を4:5にセンタークロップして1080x1350にする。"""
    target = W / H
    w, h = im.size
    if w / h > target:                       # 横に広い → 左右を削る
        new_w = int(h * target)
        box = ((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h)
    else:                                    # 縦に長い → 上下を削る
        new_h = int(w / target)
        box = (0, (h - new_h) // 2, w, (h - new_h) // 2 + new_h)
    return im.crop(box).resize((W, H), Image.LANCZOS)


def add_scrim(im, strength, height_ratio):
    """下から上へ黒を薄くかける。写真の情報は残しつつ白文字を読ませる。"""
    band = int(H * height_ratio)
    grad = Image.new("L", (1, band))
    for y in range(band):
        # 下端が最も濃い。二乗で効かせて上側の変化をなだらかにする。
        grad.putpixel((0, y), int(255 * strength * (y / band) ** 2))
    grad = grad.resize((W, band))
    veil = Image.new("RGB", (W, band), (0, 0, 0))
    im.paste(veil, (0, H - band), grad)
    return im


def wrap(draw, text, font, limit):
    """幅を測って折り返す。日本語は単語で切れないので1文字ずつ詰める。"""
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > limit and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def text_block(draw, card, fonts):
    """(描画する行のリスト, 合計の高さ) を返す。下端から積み上げるため先に高さが要る。"""
    limit = W - MARGIN_X * 2
    items = []
    if card.get("kicker"):
        items.append(("kicker", card["kicker"], fonts["kicker"], card.get("accent", "#D63036")))
    for line in card.get("lines", []):
        for piece in wrap(draw, line, fonts["line"], limit):
            items.append(("line", piece, fonts["line"], "#FFFFFF"))
    for sub in card.get("subs", []):
        for piece in wrap(draw, sub, fonts["sub"], limit):
            items.append(("sub", piece, fonts["sub"], "#E8E8E8"))

    total = 0
    sized = []
    for kind, text, font, color in items:
        asc, desc = font.getmetrics()
        gap = {"kicker": 1.55, "line": 1.20, "sub": 1.45}[kind]
        h = int((asc + desc) * gap)
        sized.append((kind, text, font, color, h))
        total += h
    return sized, total


def render(post_dir, card):
    src = os.path.join(post_dir, card["src"])
    with Image.open(src) as raw:
        im = fit(raw.convert("RGB"))

    im = add_scrim(im, card.get("scrim", 0.82), card.get("scrim_height", 0.58))
    draw = ImageDraw.Draw(im)

    fonts = {
        "kicker": ImageFont.truetype(FONT_BOLD, card.get("kicker_size", 40)),
        "line": ImageFont.truetype(FONT_BOLD, card.get("line_size", 104)),
        "sub": ImageFont.truetype(FONT_MED, card.get("sub_size", 40)),
    }
    sized, total = text_block(draw, card, fonts)

    y = H - BOTTOM_PAD - total
    if y < 40:
        raise SystemExit(f"文字が多すぎて収まらない: {card['out']}（必要 {total}px）")

    for kind, text, font, color, h in sized:
        if kind == "kicker":
            # 見出しの左に赤い縦棒を立てて視線を止める
            bar_h = int(h * 0.62)
            draw.rectangle(
                [MARGIN_X, y + int(h * 0.10), MARGIN_X + 8, y + int(h * 0.10) + bar_h],
                fill=hexc(card.get("accent", "#D63036")),
            )
            draw.text((MARGIN_X + 28, y), text, font=font, fill=hexc(color))
        else:
            draw.text((MARGIN_X, y), text, font=font, fill=hexc(color))
        y += h

    out = os.path.join(post_dir, card["out"])
    im.save(out, "JPEG", quality=92, optimize=True, progressive=True)
    print(f"saved {card['out']}  ({os.path.getsize(out) // 1024} KB)")


def main(post_dir):
    spec = json.load(open(os.path.join(post_dir, "cards.json"), encoding="utf-8-sig"))
    for card in spec["cards"]:
        render(post_dir, card)


if __name__ == "__main__":
    main(sys.argv[1])
