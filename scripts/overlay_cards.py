# カルーセル／リール用の文字載せ。写真の上に読める文字を置き、投稿用のJPEGを書き出す。
#
# 使い方: python3 scripts/overlay_cards.py <パックのフォルダ>
# そのフォルダの cards.json を読み、各カードを 1080x1350(4:5) のJPEGにする。
# cards.json に "format": "reel" があれば 1080x1920(9:16) で書き出す（2026-09-11追加）。
#   リールは画面の下（キャプション・ボタン）と右端（いいね等のアイコン）がUIに隠れるので、
#   文字は下端から 420px 以上・右端から 190px 以上あける。動画にするのは build_reel.py。
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
RIGHT_SAFE = 0             # 右側に文字を寄せない幅（リールだけ使う）


def set_format(fmt):
    """"reel" なら 9:16 の寸法と安全域に切り替える。"""
    global W, H, MARGIN_X, BOTTOM_PAD, RIGHT_SAFE
    if fmt == "reel":
        W, H = 1080, 1920
        MARGIN_X = 90
        BOTTOM_PAD = 420       # 下端1500px より上に収める（UIに隠れない）
        RIGHT_SAFE = 190       # 右のアイコン列を避ける
    else:
        W, H = 1080, 1350
        MARGIN_X = 80
        BOTTOM_PAD = 110
        RIGHT_SAFE = 0

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "assets", "fonts")
FONT_BOLD = os.path.join(FONTS, "NotoSansJP-Bold.otf")
FONT_MED = os.path.join(FONTS, "NotoSansJP-Medium.otf")


def hexc(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def fit(im):
    """元画像をキャンバスに収める。

    風景写真（縦横比が近い）はセンタークロップ。
    商品写真（正方形・16:9 など縦横比が大きく違う）は切ると商品が欠けるので、
    ぼかして暗くした同じ写真を背景に敷き、その上に元の写真を欠けないように置く（2026-09-11追加）。
    リールでは文字が下に来るので、写真はやや上寄せにする。
    """
    target = W / H
    w, h = im.size
    if (w / h) / target > 1.25:            # キャンバスよりずっと横長 → 欠けないように収める
        from PIL import ImageFilter, ImageEnhance
        bg = im.copy()
        # 背景: 全面を覆うまで拡大してクロップ → ぼかし → 暗く
        if w / h > target:
            bh = h; bw = int(h * target)
        else:
            bw = w; bh = int(w / target)
        bg = bg.crop(((w - bw) // 2, (h - bh) // 2, (w - bw) // 2 + bw, (h - bh) // 2 + bh))
        bg = bg.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
        bg = ImageEnhance.Brightness(bg).enhance(0.45)
        # 前景: 横幅いっぱいに縮めて、上寄せに置く（下は文字の場所）
        fw = W - (RIGHT_SAFE // 2 if RIGHT_SAFE else 0)
        fh = int(h * fw / w)
        fg = im.resize((fw, fh), Image.LANCZOS)
        top_room = H - BOTTOM_PAD - 260          # 文字ブロックの上端のだいたいの位置
        y = max(60, (top_room - fh) // 2 + 40)
        bg.paste(fg, (0, y))
        return bg
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
    if im.mode == "RGBA":
        veil = Image.new("RGBA", (W, band), (0, 0, 0, 255))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        veil.putalpha(grad)
        layer.paste(veil, (0, H - band))
        return Image.alpha_composite(im, layer)
    veil = Image.new("RGB", (W, band), (0, 0, 0))
    im.paste(veil, (0, H - band), grad)
    return im


NO_LINE_START = "、。，．・ー〜」』）】ぁぃぅぇぉっゃゅょ"  # 行頭に来ると見苦しい文字


def _fits(draw, text, font, limit):
    return draw.textlength(text, font=font) <= limit


def wrap(draw, text, font, limit):
    """幅を測って折り返す。日本語は単語で切れないので1文字ずつ詰める。

    2026-09-11: 末尾が1〜2文字だけ次の行に落ちる（例「鮎・磯釣りはもちろ／ん」）のを防ぐ。
    折り返しが起きた時は、各行がなるべく同じ長さになるよう均等に割り直す
    （行頭が「、」「ー」などにならないよう1文字ずらす）。
    """
    lines, cur = [], ""
    for ch in text:
        if not _fits(draw, cur + ch, font, limit) and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    if len(lines) < 2:
        return lines

    # 均等割り: 行数はそのまま、1行あたりの文字数を揃える
    n = len(lines)
    per = -(-len(text) // n)  # 切り上げ
    out, pos = [], 0
    for i in range(n):
        end = len(text) if i == n - 1 else pos + per
        # 次の行頭が禁則文字なら、その1文字を今の行に含める
        while end < len(text) and text[end] in NO_LINE_START:
            end += 1
        out.append(text[pos:end])
        pos = end
        if pos >= len(text):
            break
    out = [x for x in out if x]
    # 均等割りの結果が幅に収まらない時だけ元の詰め方に戻す
    if all(_fits(draw, x, font, limit) for x in out):
        return out
    return lines


def text_block(draw, card, fonts):
    """(描画する行のリスト, 合計の高さ) を返す。下端から積み上げるため先に高さが要る。"""
    limit = W - MARGIN_X * 2 - RIGHT_SAFE
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


VIDEO_EXTS = (".mp4", ".mov")


def render(post_dir, card):
    src = os.path.join(post_dir, card["src"])
    is_video = src.lower().endswith(VIDEO_EXTS)
    if is_video:
        # 動画は ffmpeg 側で敷く。ここでは「暗いグラデーション＋文字」だけの透明レイヤーを作る
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    else:
        with Image.open(src) as raw:
            im = fit(raw.convert("RGB"))

    im = add_scrim(im, card.get("scrim", 0.82), card.get("scrim_height", 0.58))
    draw = ImageDraw.Draw(im)

    reel = RIGHT_SAFE > 0
    fonts = {
        "kicker": ImageFont.truetype(FONT_BOLD, card.get("kicker_size", 48 if reel else 40)),
        "line": ImageFont.truetype(FONT_BOLD, card.get("line_size", 104)),
        "sub": ImageFont.truetype(FONT_MED, card.get("sub_size", 46 if reel else 40)),
    }
    if reel:
        # リールは横幅が狭く、見出しが「折りたた／める長靴」のような所で折れる。
        # 各行が1行に収まるまで見出しを縮める（下限76px＝9文字が収まる大きさ）。
        limit = W - MARGIN_X * 2 - RIGHT_SAFE
        size = card.get("line_size", 104)
        while size > 76 and any(
            not _fits(draw, ln, fonts["line"], limit) for ln in card.get("lines", [])
        ):
            size -= 4
            fonts["line"] = ImageFont.truetype(FONT_BOLD, size)
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
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if is_video:
        im.save(out, "PNG")                       # 透明レイヤー（cards/N.png）
    else:
        im.save(out, "JPEG", quality=92, optimize=True, progressive=True)
    print(f"saved {card['out']}  ({os.path.getsize(out) // 1024} KB)")


def main(post_dir):
    spec = json.load(open(os.path.join(post_dir, "cards.json"), encoding="utf-8-sig"))
    set_format(spec.get("format", "feed"))
    for card in spec["cards"]:
        render(post_dir, card)


if __name__ == "__main__":
    main(sys.argv[1])
