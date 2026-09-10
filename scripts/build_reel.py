"""カード画像（9:16）を並べて、リール用の動画 1.mp4 を組み立てる（2026-09-11 新設）。

なぜこれが要るか:
  リールだけがフォロワー以外にも配信される（フォロワーを増やす主エンジン）。
  ところが動画を作れる Higgsfield は無人実行できない（ブラウザ認証のみ）。
  そこで「写真にゆっくり寄る／引く動き（ケンバーンズ）＋文字カード」を ffmpeg で機械的に
  組み立て、無人でもリールを毎週出せるようにした。

使い方: python3 scripts/build_reel.py <パックのフォルダ>
  そのフォルダの cards.json（"format": "reel"）を読み、cards/1.jpg 2.jpg … を順に
  1080x1920・30fps・H.264/AAC の 1.mp4 にする。publish_post.py はこれをリールとして投稿する。
  src が動画（商品の動画カット）のカードは、cards/N.png（透明の文字レイヤー）を重ねて使う。

音:
  stock/bgm/ に .mp3 か .m4a があれば、パック名から決まる1本をBGMにして末尾でフェードアウトする。
  無ければ無音のAACトラックを付ける（音声トラックが無いとMeta側で弾かれることがあるため）。
  流行音源は追わない（2026-08-13 のみさん決定。MetaはAPIに音楽ライブラリを開放していない）。

出来上がりの目安: 1枚 3〜6秒、全体 15〜35秒。
"""

import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
BGM_DIR = REPO / "stock" / "bgm"
FPS = 30
W, H = 1080, 1920
ZOOM = 0.12          # 12% だけ寄る／引く。大きくすると写真が粗く見える
FADE = 0.35          # カード間の暗転の長さ（秒）


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("ffmpeg が見つからない（winget install Gyan.FFmpeg）")
    return exe


def ffprobe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def seconds_for(card, is_cover):
    """読み終えられる長さにする。文字が多いほど長く、ただし 3〜6 秒に収める。"""
    if "seconds" in card:
        return float(card["seconds"])
    if is_cover:
        return 3.2
    chars = sum(len(x) for x in card.get("lines", [])) + sum(len(x) for x in card.get("subs", []))
    return max(3.0, min(6.0, 2.6 + 0.07 * chars))


def video_segment(exe, clip, layer, out, sec, start=0.0):
    """商品の動画カットを1枚分にする（2026-09-11追加）。

    16:9 のカットは、ぼかして暗くした同じ映像を背景に敷き、その上に元の映像を欠けないように置く。
    9:16 のカットはそのまま全面に。最後に文字の透明レイヤー（cards/N.png）を重ねる。音は使わない。
    """
    frames = int(round(sec * FPS))
    vf = (
        f"[0:v]trim=start={start}:duration={sec},setpts=PTS-STARTPTS,split=2[a][b];"
        f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"boxblur=30:5,eq=brightness=-0.25[bg];"
        f"[b]scale={W}:-2:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:'if(lt(h,{H}),{int(H * 0.36)}-h/2,0)'[base];"
        f"[base][1:v]overlay=0:0,"
        f"fade=t=in:st=0:d={FADE},fade=t=out:st={max(0.0, sec - FADE):.2f}:d={FADE},"
        f"fps={FPS},format=yuv420p[v]"
    )
    subprocess.run(
        [exe, "-y", "-loglevel", "error", "-i", str(clip), "-i", str(layer),
         "-filter_complex", vf, "-map", "[v]", "-t", f"{sec:.2f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an", str(out)],
        check=True,
    )


def segment(exe, img, out, sec, zoom_in):
    """1枚の写真を、ゆっくり寄る（または引く）動きの短い動画にする。"""
    frames = int(round(sec * FPS))
    # 先に 1.5 倍へ拡大してから zoompan に渡すと、ズームのガタつきが目立たない
    if zoom_in:
        z = f"min(1+{ZOOM}*on/{frames},{1 + ZOOM})"
    else:
        z = f"max({1 + ZOOM}-{ZOOM}*on/{frames},1)"
    vf = (
        f"scale={W * 3 // 2}:{H * 3 // 2},"
        f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s={W}x{H}:fps={FPS},"
        f"fade=t=in:st=0:d={FADE},fade=t=out:st={max(0.0, sec - FADE):.2f}:d={FADE},"
        f"format=yuv420p"
    )
    subprocess.run(
        [exe, "-y", "-loglevel", "error", "-loop", "1", "-i", str(img),
         "-vf", vf, "-t", f"{sec:.2f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an", str(out)],
        check=True,
    )


def pick_bgm(pack_name):
    """stock/bgm から1本。同じパック名なら同じ曲（作り直しても音が変わらない）。"""
    if not BGM_DIR.is_dir():
        return None
    files = sorted(p for p in BGM_DIR.iterdir() if p.suffix.lower() in (".mp3", ".m4a", ".wav"))
    if not files:
        return None
    i = int(hashlib.md5(pack_name.encode("utf-8")).hexdigest(), 16) % len(files)
    return files[i]


def main(pack_dir):
    pack = pathlib.Path(pack_dir).resolve()
    spec = json.loads((pack / "cards.json").read_text(encoding="utf-8-sig"))
    if spec.get("format") != "reel":
        raise SystemExit("cards.json の format が reel ではない（overlay_cards.py を 9:16 で通していない）")
    cards = spec["cards"]
    if not 2 <= len(cards) <= 8:
        raise SystemExit(f"リールのカードは2〜8枚（今 {len(cards)}枚）")

    exe = ffmpeg()
    work = pack / "_reel_work"
    work.mkdir(exist_ok=True)

    parts, total = [], 0.0
    for i, card in enumerate(cards):
        img = pack / card["out"]
        if not img.is_file():
            raise SystemExit(f"カード画像が無い: {img}")
        seg = work / f"seg{i + 1}.mp4"
        src = pack / card["src"]
        if src.suffix.lower() in (".mp4", ".mov"):
            # 動画カット: 長さはカットの尺に合わせる（最大6秒）
            clip_len = ffprobe_duration(src) - float(card.get("start", 0))
            sec = min(max(2.5, clip_len - 0.1), seconds_for(card, is_cover=(i == 0)) + 1.0, 6.0)
            video_segment(exe, src, img, seg, sec, start=float(card.get("start", 0)))
            print(f"  {i + 1}枚目: {sec:.1f}秒 (動画 {src.name})")
        else:
            sec = seconds_for(card, is_cover=(i == 0))
            segment(exe, img, seg, sec, zoom_in=(i % 2 == 0))
            print(f"  {i + 1}枚目: {sec:.1f}秒 ({'寄る' if i % 2 == 0 else '引く'})")
        parts.append(seg)
        total += sec

    if not 5 <= total <= 90:
        raise SystemExit(f"長さが範囲外: {total:.1f}秒（5〜90秒）")

    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    silent = work / "video_only.mp4"
    subprocess.run(
        [exe, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(silent)],
        check=True,
    )

    out = pack / "1.mp4"
    bgm = pick_bgm(pack.name)
    if bgm:
        print(f"  BGM: {bgm.name}")
        af = f"volume=0.9,afade=t=in:st=0:d=1,afade=t=out:st={max(0.0, total - 2):.2f}:d=2"
        audio_in = ["-stream_loop", "-1", "-i", str(bgm)]
    else:
        print("  BGM: 無し（無音トラックを付ける）")
        af = "anull"
        audio_in = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    subprocess.run(
        [exe, "-y", "-loglevel", "error", "-i", str(silent), *audio_in,
         "-map", "0:v:0", "-map", "1:a:0", "-af", af, "-shortest",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
         "-movflags", "+faststart", str(out)],
        check=True,
    )
    shutil.rmtree(work)

    got = ffprobe_duration(out)
    print(f"完成: {out.name}  {got:.1f}秒  {out.stat().st_size // 1024} KB")
    if abs(got - total) > 1.0:
        raise SystemExit(f"長さが合わない（予定 {total:.1f}秒 / 実測 {got:.1f}秒）")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
