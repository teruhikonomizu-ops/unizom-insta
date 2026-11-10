"""投稿パックを1つ受け取ってInstagramに公開する。

使い方:
    python3 scripts/publish_post.py <パック名> [--dry-run]

パックは docs/media/<パック名>/ に置く（GitHub Pagesで公開される場所）:
    caption.txt   … キャプション本文。末尾にハッシュタグを入れてよい
    1.jpg 2.jpg … … 画像。連番順に並ぶ。JPEGのみ（InstagramはPNGを受け付けない）
    1.mp4        … リールにする場合。画像とは併用しない

--dry-run はコンテナ作成までで止まる。**投稿されない。**
画像が公開URLから取れるか・権限が足りているかを、投稿せずに確かめられる。
"""

import argparse
import datetime
import json
import pathlib
import sys

import ig_api

PAGES_BASE = "https://teruhikonomizu-ops.github.io/unizom-insta/media"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGE_EXTS = {".jpg", ".jpeg"}
VIDEO_EXTS = {".mp4"}
JST = datetime.timezone(datetime.timedelta(hours=9))


def sale_deadline(pack, now=None):
    """セールのお知らせのパックが、出してよい期限を過ぎていないか（2026-11-10 総点検 中19）。
    戻り値＝(期限切れか, 説明)。セールのお知らせでなければ (False, "")。
    sale.json は sale_check.py が置く。publish_until が無い前のパックは投稿日のうちだけ"""
    f = REPO_ROOT / "docs" / "media" / pack / "sale.json"
    if not f.is_file():
        return False, ""
    now = now or datetime.datetime.now(JST)
    try:
        sale = json.loads(f.read_text(encoding="utf-8-sig"))
        if not sale.get("sales"):
            return False, ""
        until = sale.get("publish_until")
        if until:
            limit = datetime.datetime.fromisoformat(until)
        else:
            limit = datetime.datetime.combine(datetime.date.fromisoformat(sale["post_date"]), datetime.time(23, 59))
        if limit.tzinfo is None:
            limit = limit.replace(tzinfo=JST)
        names = "／".join("{0}（{1}）".format(s.get("name"), s.get("when")) for s in sale["sales"])
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return True, f"sale.json が読めない（{type(e).__name__}）＝セールのお知らせの期限を確かめられない"
    limit = limit.astimezone(JST)
    label = f"{limit.month}/{limit.day} {limit:%H:%M}"
    if now > limit:
        return True, f"セールのお知らせ（{names}）を出してよい期限 {label} を過ぎている"
    return False, f"セールのお知らせ（{names}）＝出してよいのは {label} まで"


def load_pack(pack):
    """パックの中身を読み、(キャプション, メディアのパス一覧) を返す。"""
    d = REPO_ROOT / "docs" / "media" / pack
    if not d.is_dir():
        raise SystemExit(f"パックが無い: {d}")
    if pack.startswith("_"):
        # GitHub PagesのJekyllは _ 始まりを無視する。.nojekyll を置いてあるので
        # 今は動くが、事故のもとなので名前の時点で弾く。
        raise SystemExit("パック名を _ で始めない（GitHub Pagesの罠）")

    caption_file = d / "caption.txt"
    if not caption_file.is_file():
        raise SystemExit(f"caption.txt が無い: {caption_file}")
    # utf-8-sig: メモ帳などで編集されてBOMが付いても先頭に化けた文字が残らないようにする
    caption = caption_file.read_text(encoding="utf-8-sig").strip()
    if not caption:
        raise SystemExit("caption.txt が空")
    if len(caption) > 2200:
        raise SystemExit(f"キャプションが長すぎる（{len(caption)}文字 / 上限2200）")

    media = sorted(
        (p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS),
        key=lambda p: p.name,
    )
    if not media:
        raise SystemExit(f"画像も動画も無い: {d}")

    videos = [p for p in media if p.suffix.lower() in VIDEO_EXTS]
    images = [p for p in media if p.suffix.lower() in IMAGE_EXTS]
    if videos and images:
        raise SystemExit("画像と動画は混ぜない（リールにするなら .mp4 だけ置く）")
    if len(videos) > 1:
        raise SystemExit("リールは1本だけ")
    if len(images) > 10:
        raise SystemExit(f"カルーセルは10枚まで（今 {len(images)}枚）")

    # PNGを置き忘れていないか。無言で落とさず知らせる。
    strays = [p.name for p in d.iterdir() if p.suffix.lower() == ".png"]
    if strays:
        print(f"注意: PNGは投稿できないので無視した -> {strays}", file=sys.stderr)

    return caption, media


def url_for(pack, path):
    return f"{PAGES_BASE}/{pack}/{path.name}"


def build_container(pack, caption, media):
    """メディアの構成に応じてコンテナを作り、公開できるIDを返す。"""
    first = media[0]

    if first.suffix.lower() in VIDEO_EXTS:
        # 🔴 動画は REELS しか選べない（2026-08-13にAPIで実測）。
        # media_type=VIDEO を投げると Meta がこう返す:
        #   「The VIDEO value for media_type is deprecated.
        #     Use the REELS media type to publish a video to your Instagram feed.」
        # 公式ドキュメントのページには VIDEO が残っているが**古い**。APIの返答が正。
        # → 「フィード動画として出す」という選択肢は存在しない。作り直さないこと。
        # → リールは9:16が前提なので、動画は 1080x1920 で用意する。
        print(f"リールとして作成: {first.name}")
        cid = ig_api.create_container(
            media_type="REELS", video_url=url_for(pack, first), caption=caption
        )
        ig_api.wait_ready(cid)
        return cid

    if len(media) == 1:
        print(f"単写真として作成: {first.name}")
        cid = ig_api.create_container(image_url=url_for(pack, first), caption=caption)
        ig_api.wait_ready(cid)
        return cid

    print(f"カルーセルとして作成: {[p.name for p in media]}")
    children = []
    for p in media:
        child = ig_api.create_container(image_url=url_for(pack, p), is_carousel_item="true")
        children.append(child)
    for child in children:
        ig_api.wait_ready(child)
    cid = ig_api.create_container(
        media_type="CAROUSEL", children=",".join(children), caption=caption
    )
    ig_api.wait_ready(cid)
    return cid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pack", help="docs/media/ 配下のフォルダ名")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="コンテナ作成までで止める（投稿しない）",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="セールのお知らせの期限切れでも投稿する（のみさんが期間を確かめた時だけ）",
    )
    args = ap.parse_args()

    caption, media = load_pack(args.pack)
    print(f"パック: {args.pack}")
    print(f"メディア: {[p.name for p in media]}")
    print(f"キャプション: {len(caption)}文字")

    expired, note = sale_deadline(args.pack)
    if note:
        print(("注意: " if expired else "") + note)
    if expired and not args.dry_run and not args.force:
        raise SystemExit(f"NG: {note}。投稿しなかった（期間を確かめた上で出す時だけ --force）")

    used = ig_api.publish_limit()
    print(f"直近24時間の投稿数: {used} / 100")

    cid = build_container(args.pack, caption, media)
    print(f"コンテナ作成OK: {cid}")

    if args.dry_run:
        print("--dry-run のため、ここで停止した。投稿はしていない。")
        print("（画像の公開URL取得・認証・投稿権限まで通ったことが確認できた）")
        return

    media_id = ig_api.publish(cid)
    print(f"投稿した: media_id={media_id}")
    link = ig_api.permalink(media_id)
    if link:
        print(f"公開URL: {link}")


if __name__ == "__main__":
    try:
        main()
    except ig_api.IgError as e:
        print(f"NG: {e}", file=sys.stderr)
        sys.exit(1)
