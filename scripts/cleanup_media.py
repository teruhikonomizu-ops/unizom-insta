"""投稿済みパックの画像・動画を GitHub Pages から片付ける（2026-10-11 新設・のみさん指示）。

なぜ:
  docs/media/<パック名>/ の画像・動画は GitHub Pages で公開URLにして Meta が取りに来る。
  Instagram は投稿した時点で自分の側に写しを持つので、投稿後はここに置いておく必要が無い。
  一方 Pages の公開サイトは 1GB までという上限があり（GitHub公式）、何もしないと
  2027年の夏〜秋ごろに届く見込み＝届くと Pages が作れず、投稿そのものが止まる。

何をするか（毎週月曜 03:30 JST・cleanup.yml から）:
  1. publish ワークフローの成功ログから「パック: X」「投稿した: media_id=Y」を読み、
     投稿済みの印 docs/media/X/posted.json を書く（ログは90日で消えるので印に写しておく）
  2. 印があり、投稿から GRACE_DAYS 日たったパックの画像・動画（と raw/）を消す。
     caption.txt・cards.json・posted.json などの文字ファイルは残す（フォルダも残る＝
     weekly.yml の「その日のパックは用意済み」の判定は今まで通り効く）
  3. 結果を _片付け結果.txt に1行で書く（1行目 [成功]／[警戒]／[失敗]）

触らないもの:
  - 投稿済みと確かめられないパック（未投稿・手で投稿した物・テスト用）は一切消さない
  - stock/（使い回す素材の貯金）は対象外
  消した物は git の履歴に残っているので、必要になれば取り戻せる。

使い方:
  python3 scripts/cleanup_media.py --dry-run   # 消さずに一覧だけ出す（手元でもクラウドでも可）
  python3 scripts/cleanup_media.py             # 実際に片付ける（クラウドの cleanup.yml が使う）
  python3 scripts/cleanup_media.py --selftest  # 判定部分を壊したデータで試す
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "docs" / "media"
RESULT = ROOT / "_片付け結果.txt"
REPO = os.environ.get("GITHUB_REPOSITORY", "teruhikonomizu-ops/unizom-insta")
JST = timezone(timedelta(hours=9))

GRACE_DAYS = 14           # 投稿からこの日数は残す（すぐ差し替えたくなった時のため）
LOG_DAYS = 85             # Actions のログは90日で消える。少し手前までだけ読みに行く
WARN_DOCS_MB = 700        # 公開サイトの上限 1GB に対する早めの警告
WARN_REPO_MB = 900        # リポジトリの推奨 1GB に対する早めの警告
MEDIA_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".m4v", ".mp3", ".wav", ".m4a"}
PACK_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]*$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m|\^\[\[[0-9;]*m")


# ---------- 判定（--selftest で試す部分） ----------

def parse_log(text: str) -> dict:
    """publish の実行ログ1本から {pack, media_id, permalink, kind} を取り出す。
    kind: posted（投稿した）／dry（確認だけ）／unknown（どちらの印も無い＝書式が変わった疑い）"""
    pack = media_id = permalink = None
    dry = False
    for raw in text.splitlines():
        line = ANSI_RE.sub("", raw)
        # 「python3 scripts/publish_post.py ...」の行（コマンドの表示）は本文ではないので見ない
        m = re.search(r"(?:^|\s)パック: (\S+)\s*$", line)
        if m and not pack:
            pack = m.group(1)
        m = re.search(r"投稿した: media_id=(\d+)", line)
        if m:
            media_id = m.group(1)
        m = re.search(r"公開URL: (https://www\.instagram\.com/\S+)", line)
        if m:
            permalink = m.group(1)
        if "--dry-run のため、ここで停止した" in line:
            dry = True
    if media_id:
        kind = "posted"
    elif dry:
        kind = "dry"
    else:
        kind = "unknown"
    return {"pack": pack, "media_id": media_id, "permalink": permalink, "kind": kind}


def due_for_cleanup(posted: dict, now: datetime) -> bool:
    """投稿済みの印から、片付けてよい時期か判定する"""
    if posted.get("片付け"):
        return False
    times = [p.get("posted_at") for p in posted.get("posts", []) if p.get("posted_at")]
    if not times:
        return False
    last = max(datetime.fromisoformat(t.replace("Z", "+00:00")) for t in times)
    return now - last >= timedelta(days=GRACE_DAYS)


def media_files(pack_dir: Path) -> list[Path]:
    """消す対象（画像・動画・音声と、作業用の raw/ など下の階層）。文字ファイルは残す"""
    out = []
    for p in sorted(pack_dir.iterdir()):
        if p.is_dir():
            out.append(p)
        elif p.suffix.lower() in MEDIA_EXT:
            out.append(p)
    return out


def judge(stats: dict) -> tuple[str, list[str]]:
    """結果の1行目（[成功]／[警戒]／[失敗]）と理由を決める"""
    reasons = []
    if stats["log_errors"]:
        reasons.append(f"ログが読めなかった実行が{stats['log_errors']}件（権限か GitHub の不調）")
    if stats["unknown_runs"]:
        reasons.append(f"投稿したか空打ちか判別できないログが{stats['unknown_runs']}件（ログの書式が変わった疑い）")
    if stats["recent_success_runs"] and stats["known_posted"] == 0:
        reasons.append("成功した投稿の実行があるのに、投稿済みが1件も見つからない（読み取りが壊れている）")
    if stats["media_dirs"] == 0:
        reasons.append("docs/media が空か見つからない（場所が変わった疑い）")
    if reasons:
        return "[失敗]", reasons
    warn = []
    if stats["docs_mb"] > WARN_DOCS_MB:
        warn.append(f"公開サイトが {stats['docs_mb']:.0f}MB（上限1GB・{WARN_DOCS_MB}MBで警告）")
    if stats["repo_mb"] is not None and stats["repo_mb"] > WARN_REPO_MB:
        warn.append(f"リポジトリが {stats['repo_mb']:.0f}MB（推奨1GB・{WARN_REPO_MB}MBで警告）")
    if warn:
        return "[警戒]", warn
    return "[成功]", []


# ---------- GitHub とのやり取り ----------

def gh(*args: str) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return r.stdout


def list_publish_runs() -> list[dict]:
    out = gh("api", "--paginate",
             f"repos/{REPO}/actions/workflows/publish.yml/runs?status=success&per_page=100",
             "--jq", ".workflow_runs[] | {id, created_at}")
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def repo_size_mb() -> float | None:
    try:
        return int(gh("api", f"repos/{REPO}", "--jq", ".size").strip()) / 1024
    except Exception:
        return None


def dir_mb(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1048576


# ---------- 本体 ----------

def load_posted(pack_dir: Path) -> dict:
    f = pack_dir / "posted.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"pack": pack_dir.name, "posts": []}


def save_posted(pack_dir: Path, data: dict) -> None:
    (pack_dir / "posted.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(dry: bool) -> int:
    now = datetime.now(timezone.utc)
    stats = {"log_errors": 0, "unknown_runs": 0, "recent_success_runs": 0,
             "known_posted": 0, "media_dirs": 0, "docs_mb": 0.0, "repo_mb": None}
    notes: list[str] = []

    packs = {p.name: p for p in MEDIA.iterdir() if p.is_dir() and PACK_RE.match(p.name)} if MEDIA.is_dir() else {}
    stats["media_dirs"] = len(packs)
    posted = {name: load_posted(d) for name, d in packs.items()}
    known_runs = {p.get("run_id") for v in posted.values() for p in v.get("posts", [])}

    # 1. 投稿ログから「投稿済み」の印を作る
    try:
        runs = list_publish_runs()
    except Exception as e:
        runs = []
        stats["log_errors"] += 1
        notes.append(f"実行一覧が取れない: {e}")
    for r in runs:
        created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        if now - created > timedelta(days=LOG_DAYS):
            continue
        stats["recent_success_runs"] += 1
        if r["id"] in known_runs:
            continue
        try:
            info = parse_log(gh("run", "view", str(r["id"]), "-R", REPO, "--log"))
        except Exception as e:
            stats["log_errors"] += 1
            notes.append(f"run {r['id']} のログが読めない: {e}")
            continue
        if info["kind"] == "unknown":
            stats["unknown_runs"] += 1
            notes.append(f"run {r['id']}: 投稿か空打ちか判別できない（パック={info['pack']}）")
            continue
        if info["kind"] != "posted":
            continue
        name = info["pack"]
        if name not in packs:
            notes.append(f"run {r['id']}: 投稿済みのパック {name} のフォルダが無い（手で消された？）")
            continue
        posted[name]["posts"].append({
            "media_id": info["media_id"], "permalink": info["permalink"],
            "posted_at": r["created_at"], "run_id": r["id"],
        })
        posted[name]["_changed"] = True

    stats["known_posted"] = sum(1 for v in posted.values() if v.get("posts"))

    # 2. 時期が来たパックを片付ける
    cleaned, freed = [], 0.0
    for name in sorted(packs):
        v = posted[name]
        if not v.get("posts") or not due_for_cleanup(v, now):
            continue
        targets = media_files(packs[name])
        if not targets:
            continue
        mb = sum(dir_mb(t) if t.is_dir() else t.stat().st_size / 1048576 for t in targets)
        cleaned.append(f"{name}（{len(targets)}点・{mb:.1f}MB）")
        freed += mb
        if dry:
            continue
        for t in targets:
            # 念のため docs/media/<パック>/ の外は絶対に消さない
            if packs[name].resolve() not in t.resolve().parents:
                raise RuntimeError(f"範囲外のパスを消そうとした: {t}")
            if t.is_dir():
                shutil.rmtree(t)
            else:
                t.unlink()
        v["片付け"] = {"日時": now.astimezone(JST).strftime("%Y-%m-%d %H:%M"),
                      "消した物": [t.name for t in targets], "MB": round(mb, 1)}
        v["_changed"] = True

    if not dry:
        for name, v in posted.items():
            if v.pop("_changed", False):
                save_posted(packs[name], v)

    # 3. 結果
    stats["docs_mb"] = dir_mb(ROOT / "docs") - (0 if not dry else freed)
    stats["repo_mb"] = repo_size_mb()
    head, reasons = judge(stats)
    stamp = now.astimezone(JST).strftime("%Y-%m-%d %H:%M")
    repo_txt = f"{stats['repo_mb']:.0f}MB" if stats["repo_mb"] is not None else "不明"
    first = (f"{head} {stamp} 片付け{len(cleaned)}件（{freed:.1f}MB）"
             f"・公開サイト {stats['docs_mb']:.0f}MB／上限1GB・リポジトリ {repo_txt}／推奨1GB"
             f"・投稿済みと確認 {stats['known_posted']}件")
    lines = [first] + [f"理由: {r}" for r in reasons] + [f"片付けた: {c}" for c in cleaned] + [f"メモ: {n}" for n in notes]
    lines.append(f"規則: 投稿から{GRACE_DAYS}日たったパックの画像・動画だけを消す（文字ファイルは残す・未投稿は触らない・消した物は git の履歴から戻せる）")
    text = "\n".join(lines) + "\n"
    print(("（確認だけ・何も消していない）\n" if dry else "") + text)
    if not dry:
        RESULT.write_text(text, encoding="utf-8")
    return 0


def selftest() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("OK  " if cond else "NG  ") + name)
        ok &= bool(cond)

    posted_log = ("publish\t投稿\t2026-10-05T23:34:50Z パック: 2026-10-06-reel\n"
                  "publish\t投稿\t2026-10-05T23:34:50Z 投稿した: media_id=18639149224016956\n"
                  "publish\t投稿\t2026-10-05T23:34:50Z 公開URL: https://www.instagram.com/reel/DeIZnOtgP5h/\n")
    r = parse_log(posted_log)
    check("投稿ログを読める", r == {"pack": "2026-10-06-reel", "media_id": "18639149224016956",
                                "permalink": "https://www.instagram.com/reel/DeIZnOtgP5h/", "kind": "posted"})
    r = parse_log("x\t投稿\tT パック: probe\nx\t投稿\tT --dry-run のため、ここで停止した。投稿はしていない。\n")
    check("空打ちを投稿と取り違えない", r["kind"] == "dry")
    r = parse_log("x\t投稿\tT Pack: 2026-10-06-reel\nx\t投稿\tT posted id=1\n")
    check("書式が変わったら unknown になる", r["kind"] == "unknown")

    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    check("13日前の投稿は残す", not due_for_cleanup({"posts": [{"posted_at": "2026-10-07T00:00:00Z"}]}, now))
    check("14日前の投稿は片付ける", due_for_cleanup({"posts": [{"posted_at": "2026-10-06T00:00:00Z"}]}, now))
    check("印の無いパックは片付けない", not due_for_cleanup({"posts": []}, now))
    check("片付け済みは二度やらない", not due_for_cleanup({"posts": [{"posted_at": "2026-09-01T00:00:00Z"}], "片付け": {"日時": "x"}}, now))

    base = {"log_errors": 0, "unknown_runs": 0, "recent_success_runs": 10, "known_posted": 8,
            "media_dirs": 20, "docs_mb": 140.0, "repo_mb": 260.0}
    check("普段は [成功]", judge(base)[0] == "[成功]")
    check("投稿が読めないと [失敗]", judge({**base, "known_posted": 0})[0] == "[失敗]")
    check("書式変更で [失敗]", judge({**base, "unknown_runs": 1})[0] == "[失敗]")
    check("ログ取得の失敗で [失敗]", judge({**base, "log_errors": 1})[0] == "[失敗]")
    check("フォルダが消えたら [失敗]", judge({**base, "media_dirs": 0})[0] == "[失敗]")
    check("公開サイト700MB超で [警戒]", judge({**base, "docs_mb": 750.0})[0] == "[警戒]")
    check("リポジトリ900MB超で [警戒]", judge({**base, "repo_mb": 950.0})[0] == "[警戒]")
    print("自己テスト: " + ("すべて合格" if ok else "不合格あり"))
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="消さずに一覧だけ出す")
    ap.add_argument("--selftest", action="store_true", help="判定部分を壊したデータで試す")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else run(a.dry_run))
