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


def fit(im, text_top=None):
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
        x = 0
        if text_top is not None:
            # 文字ブロックの実際の上端より上に収める（2026-10-30: 白地の横長写真が文字の下まで伸び、
            # 「Amazon×楽天」の白文字が白地に重なって読めなかった）
            top_room = text_top - 30
            if fh > top_room - 60:
                fh = max(200, top_room - 60)
                fw = int(w * fh / h)
                fg = im.resize((fw, fh), Image.LANCZOS)
                x = (W - (RIGHT_SAFE // 2 if RIGHT_SAFE else 0) - fw) // 2
        y = max(60, (top_room - fh) // 2 + 40)
        bg.paste(fg, (x, y))
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

# ---- 白い枠の型（フィードの白地の商品写真用・2026-11-06追加） ----
# 縁の明るさ（0〜255）がこれ以上なら「白地・スタジオ地の写真」とみなす。
# 実測: 白地の商品写真 200〜255／風景写真（stock/images）最大168（iso-sunrise）。
LIGHT_EDGE = 200
BG_DARK = (17, 17, 17)


def is_light_photo(src):
    from PIL import ImageStat
    with Image.open(src) as raw:
        g = raw.convert("L")
        w, h = g.size
        b = max(4, min(w, h) // 40)
        strips = [g.crop((0, 0, w, b)), g.crop((0, h - b, w, h)), g.crop((0, 0, b, h)), g.crop((w - b, 0, w, h))]
        return sum(ImageStat.Stat(s).mean[0] for s in strips) / 4 >= LIGHT_EDGE


def _trim_photo(src, box_w, box_h, pad=28):
    """白い余白を詰めて枠に収める。地が白でない写真は角を丸めて、はめ込み写真に見せる。"""
    from PIL import ImageOps
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGBA")
    mask = im.convert("L").point(lambda v: 255 if v < 245 else 0)
    bbox = mask.getbbox()
    if bbox:
        m = 20
        im = im.crop((max(0, bbox[0] - m), max(0, bbox[1] - m),
                      min(im.width, bbox[2] + m), min(im.height, bbox[3] + m)))
    s = min((box_w - pad * 2) / im.width, (box_h - pad * 2) / im.height)
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    if im.width > 2 and im.height > 2 and im.convert("L").getpixel((2, 2)) < 240:
        rm = Image.new("L", im.size, 0)
        ImageDraw.Draw(rm).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=24, fill=255)
        im.putalpha(rm)
    return im


def render_panel(post_dir, card, src):
    accent = hexc(card.get("accent", "#D63036"))
    im = Image.new("RGB", (W, H), BG_DARK)
    band = Image.new("RGBA", (W * 2, 70), accent + (255,)).rotate(-28, expand=True)
    im.paste(band, (-200, -560), band)       # 右上の斜めの赤い帯
    d = ImageDraw.Draw(im)
    limit = W - MARGIN_X * 2

    y = 70
    if card.get("kicker"):
        f = ImageFont.truetype(FONT_BOLD, card.get("kicker_size", 38))
        asc, desc = f.getmetrics()
        tw = d.textlength(card["kicker"], font=f)
        d.rounded_rectangle([MARGIN_X, y, MARGIN_X + tw + 44, y + asc + desc + 12], radius=10, fill=accent)
        d.text((MARGIN_X + 22, y + 4), card["kicker"], font=f, fill=(255, 255, 255))
        y += asc + desc + 36

    # 見出し: 各行が1行に収まるまで縮める（下限72px）。それでも長い時だけ折り返す
    size = min(card.get("line_size", 104), 104)
    lf = ImageFont.truetype(FONT_BOLD, size)
    while size > 72 and any(not _fits(d, ln, lf, limit) for ln in card.get("lines", [])):
        size -= 4
        lf = ImageFont.truetype(FONT_BOLD, size)
    asc, desc = lf.getmetrics()
    for line in card.get("lines", []):
        for piece in wrap(d, line, lf, limit):
            d.text((MARGIN_X - 4, y), piece, font=lf, fill=(255, 255, 255))
            y += int((asc + desc) * 1.12)
    head_bottom = y + 20

    # 説明: 下から積む（1行目は白の太字、2行目以降は明るいグレー）
    subs = []
    for k, sub in enumerate(card.get("subs", [])):
        sf = ImageFont.truetype(FONT_BOLD if k == 0 else FONT_MED, card.get("sub_size", 44 if k == 0 else 36))
        for piece in wrap(d, sub, sf, limit):
            subs.append((piece, sf, (255, 255, 255) if k == 0 else (205, 205, 205)))
    subs_h = sum(int(sum(f.getmetrics()) * 1.45) for _, f, _ in subs)
    sub_top = H - 80 - subs_h

    panel_top, panel_bottom = head_bottom + 10, sub_top - 36
    if panel_bottom - panel_top < 380:
        # 止めずに従来の型（写真に文字を載せる）へ戻す＝金曜の自動作成を落とさない
        print(f"白い枠の型は文字が多すぎて枠が取れない（{panel_bottom - panel_top}px）→従来の型で作る: {card['out']}")
        return False
    d.rounded_rectangle([MARGIN_X, panel_top, W - MARGIN_X, panel_bottom], radius=36, fill=(255, 255, 255))
    ph = _trim_photo(src, W - MARGIN_X * 2, panel_bottom - panel_top)
    im.paste(ph, ((W - ph.width) // 2, panel_top + (panel_bottom - panel_top - ph.height) // 2), ph)
    d = ImageDraw.Draw(im)

    y = sub_top
    for piece, f, color in subs:
        tw = d.textlength(piece, font=f)
        d.text(((W - tw) / 2, y), piece, font=f, fill=color)
        y += int(sum(f.getmetrics()) * 1.45)

    out = os.path.join(post_dir, card["out"])
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    im.save(out, "JPEG", quality=92, optimize=True, progressive=True)
    print(f"saved {card['out']}  ({os.path.getsize(out) // 1024} KB) [白い枠の型]")


def render(post_dir, card):
    src = os.path.join(post_dir, card["src"])
    is_video = src.lower().endswith(VIDEO_EXTS)
    if is_video:
        # 動画は ffmpeg 側で敷く。ここでは「暗いグラデーション＋文字」だけの透明レイヤーを作る
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    else:
        im = None

    reel = RIGHT_SAFE > 0
    if not is_video and not reel and card.get("style", "auto") != "overlay":
        # 白地の商品写真は、写真の上に白文字を載せると読めない（2026-11-06 のみさん指摘
        # 「白背景の文字も見にくい」）。黒地＋赤の帯の上に、白い枠に入れた写真と文字を分けて置く。
        try:
            if card.get("style") == "panel" or is_light_photo(src):
                if render_panel(post_dir, card, src) is not False:
                    return
        except Exception as e:  # 白い枠の型で何が起きても従来の型へ戻す＝金曜の自動作成を落とさない
            print(f"白い枠の型で失敗（{type(e).__name__}: {e}）→従来の型で作る: {card['out']}")
    draw = ImageDraw.Draw(Image.new("RGB", (W, H)))   # 先に文字の高さを測るための仮の画用紙
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

    if im is None:
        with Image.open(src) as raw:
            im = fit(raw.convert("RGB"), text_top=H - BOTTOM_PAD - total)
    im = add_scrim(im, card.get("scrim", 0.82), card.get("scrim_height", 0.58))
    draw = ImageDraw.Draw(im)

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
