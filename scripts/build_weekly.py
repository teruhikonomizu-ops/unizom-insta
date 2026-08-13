"""毎週金曜、投稿パックを1つ組み立てる（投稿はしない）。

流れ:
  1. topics.json から「承認済み」のネタを上から1つ取る
  2. 執筆の指示書＋ネタを claude に渡してキャプションとカード文言を書かせる
  3. stock/index.json から場面の合う素材を、使った回数の少ない順に選ぶ
  4. 文字を載せてJPEGにする
  5. 安全チェック（落ちたらここで止める。パックは作らない）
  6. topics.json と stock/index.json を更新（使用済み・使った回数）

投稿は別（publish.yml）。**のみさんが承認するまで何も公開されない。**

使い方: python3 scripts/build_weekly.py <パック名> [--topic <id>]
"""

import argparse
import datetime
import json
import pathlib
import re
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TOPICS = REPO / "topics.json"
STOCK_INDEX = REPO / "stock" / "index.json"
PROMPT = REPO / "prompts" / "caption.md"
MEDIA = REPO / "docs" / "media"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pick_topic(topics, wanted_id=None):
    approved = [t for t in topics["ネタ"] if t["状態"] == "承認済み"]
    if wanted_id:
        for t in topics["ネタ"]:
            if t["id"] == wanted_id:
                return t
        raise SystemExit(f"そのネタが無い: {wanted_id}")
    if not approved:
        raise SystemExit(
            "承認済みのネタが尽きた。topics.json に足すまで投稿は作れない。\n"
            "（勝手にネタを作らせない設計。のみさんに『ネタ帳に足して』と言ってもらう）"
        )
    return approved[0]


def claude_cmd():
    """claudeの実行ファイルを探す。

    Windowsでは実体が claude.cmd / claude.ps1 のシムなので、名前だけでは起動できない。
    クラウド(ubuntu)では素の claude で通る。ローカルでも試せるように両対応にする。
    """
    for name in ("claude", "claude.cmd", "claude.exe"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("claude が見つからない（npm install -g @anthropic-ai/claude-code）")


def run_claude(topic):
    """執筆させる。JSONで返らなければ作り直させる。"""
    exe = claude_cmd()
    body = (
        PROMPT.read_text(encoding="utf-8")
        + "\n\n---\n\n# 今回のネタ\n\n```json\n"
        + json.dumps(topic, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    for attempt in (1, 2, 3):
        r = subprocess.run(
            [exe, "-p", "--model", "sonnet"],
            input=body, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            # 何が起きたか分からないと直せない。終了コード・標準出力・標準エラーを全部出す。
            print(f"claudeの呼び出しが失敗（{attempt}回目）exit={r.returncode}", file=sys.stderr)
            print(f"--- stdout ---\n{r.stdout[-1500:]}", file=sys.stderr)
            print(f"--- stderr ---\n{r.stderr[-1500:]}", file=sys.stderr)
            continue
        out = r.stdout.strip()
        # ```json ... ``` に包まれていても拾えるようにする
        m = re.search(r"\{.*\}", out, re.S)
        if not m:
            print(f"JSONが見つからない（{attempt}回目）", file=sys.stderr)
            body += "\n\n【重要】JSONだけを出力すること。前後に文章を付けないこと。"
            continue
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            print(f"JSONとして読めない（{attempt}回目）: {e}", file=sys.stderr)
            body += f"\n\n【重要】前回の出力はJSONとして壊れていた（{e}）。整形し直すこと。"
            continue
        if data.get("caption") and data.get("cards"):
            return data
        print(f"caption か cards が空（{attempt}回目）", file=sys.stderr)
    raise SystemExit("執筆に3回失敗した")


def pick_stock(stock, scene, used_ids):
    """場面が合う素材を、使った回数の少ない順に。同じ回で重複させない。"""
    cands = [s for s in stock["素材"] if s["場面"] == scene and s["id"] not in used_ids]
    if not cands:
        # 場面が合うものが尽きたら、まだ使っていない何かで代用する（止めない）
        cands = [s for s in stock["素材"] if s["id"] not in used_ids]
    if not cands:
        raise SystemExit("素材が足りない。stock を補充すること")
    cands.sort(key=lambda s: (s["使った回数"], s["id"]))
    return cands[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pack", help="作るパック名（例: 2026-08-29-sole-choice）")
    ap.add_argument("--topic", help="ネタのidを指定（既定は承認済みの先頭）")
    ap.add_argument(
        "--no-ledger",
        action="store_true",
        help="topics.json と stock/index.json を更新しない（動作確認用）",
    )
    args = ap.parse_args()

    topics = load(TOPICS)
    stock = load(STOCK_INDEX)
    topic = pick_topic(topics, args.topic)
    print(f"ネタ: {topic['id']} / {topic['テーマ']}")

    written = run_claude(topic)
    cards_spec = written["cards"]
    print(f"カード {len(cards_spec)}枚 / キャプション {len(written['caption'])}文字")

    pack_dir = MEDIA / args.pack
    raw_dir = pack_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # --- キャプション ---
    (pack_dir / "caption.txt").write_text(written["caption"].strip() + "\n", encoding="utf-8")

    # --- 素材を選んで並べる ---
    used, cards = [], []
    for i, c in enumerate(cards_spec, start=1):
        scene = c.get("scene") or (topic["素材の場面"][0] if topic["素材の場面"] else "")
        chosen = pick_stock(stock, scene, used)
        used.append(chosen["id"])
        shutil.copy(REPO / chosen["ファイル"], raw_dir / f"{i}.jpg")
        cards.append({
            "src": f"raw/{i}.jpg",
            "out": f"{i}.jpg",
            "kicker": c.get("kicker", ""),
            "lines": c.get("lines", []),
            "subs": c.get("subs", []),
            "line_size": 96 if len(c.get("lines", [""])[0]) > 6 else 116,
        })
        print(f"  {i}枚目: {scene} -> {chosen['id']}")
    save(pack_dir / "cards.json", {"cards": cards})

    # --- 文字を載せる ---
    subprocess.run([sys.executable, str(REPO / "scripts" / "overlay_cards.py"), str(pack_dir)],
                   check=True)

    # --- 安全チェック（落ちたらパックごと捨てる） ---
    check = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "safe_check.py"), str(pack_dir / "caption.txt")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print(check.stdout)
    if check.returncode != 0:
        shutil.rmtree(pack_dir)
        raise SystemExit(
            "安全チェックに落ちたのでパックを捨てた。禁止語が混ざったまま公開しないため。\n"
            "上のNG一覧を見て、ネタの『使ってはいけない表現』を足すか、執筆の指示書を直す。"
        )

    # --- 台帳を更新 ---
    if args.no_ledger:
        print("\n--no-ledger のため台帳は更新しない（動作確認用の実行）")
        print(f"完成: docs/media/{args.pack}")
        return

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    for t in topics["ネタ"]:
        if t["id"] == topic["id"]:
            t["状態"] = "使用済み"
            t["使った日"] = today
    save(TOPICS, topics)

    for s in stock["素材"]:
        if s["id"] in used:
            s["使った回数"] += 1
            s["最後に使った日"] = today
    save(STOCK_INDEX, stock)

    remain = sum(1 for t in topics["ネタ"] if t["状態"] == "承認済み")
    print(f"\n完成: docs/media/{args.pack}")
    print(f"承認済みのネタの残り: {remain}件")
    if remain <= 2:
        print("::warning::ネタ帳の残りが少ない。のみさんに補充を頼むこと")


if __name__ == "__main__":
    main()
