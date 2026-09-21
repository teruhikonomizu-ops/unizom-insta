"""毎週金曜、投稿パックを1つ組み立てる（投稿はしない）。

流れ:
  1. topics.json から「承認済み」のネタを上から1つ取る
  2. 執筆の指示書＋ネタを claude に渡してキャプションとカード文言を書かせる
  3. stock/index.json から場面の合う素材を、使った回数の少ない順に選ぶ
  4. 文字を載せてJPEGにする
  5. 安全チェック（落ちたらここで止める。パックは作らない）
  6. topics.json と stock/index.json を更新（使用済み・使った回数）

投稿は別（publish.yml）。**のみさんが承認するまで何も公開されない。**

使い方: python3 scripts/build_weekly.py <パック名> [--topic <id>] [--reel]

--reel（2026-09-11追加・火曜の「リールの日」用）:
  カードを 9:16 で作り、build_reel.py で 1.mp4 に組み立てる。パック直下には動画だけを置く
  （publish_post.py は画像と動画の混在を弾くので、カードは cards/ に入れる）。
  ネタは「形式」にリールと書いてあるものを優先し、無ければ承認済みの先頭を使う
  （どのネタもカード文言は同じ形なので、リールにできる）。
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


def pick_topic(topics, wanted_id=None, reel=False):
    approved = [t for t in topics["ネタ"] if t["状態"] == "承認済み"]
    if reel:
        # リール向きと書いてあるネタを先に。無ければ普通の順
        approved.sort(key=lambda t: 0 if "リール" in t.get("形式", "") else 1)
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


def run_claude(topic, reel=False):
    """執筆させる。JSONで返らなければ作り直させる。"""
    exe = claude_cmd()
    body = (
        PROMPT.read_text(encoding="utf-8")
        + "\n\n---\n\n# 今回のネタ\n\n```json\n"
        + json.dumps(topic, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    if reel:
        body += (
            "\n# 今回はリール（動画）です\n\n"
            "指示書の「リールのとき」の節に従ってください。ネタの「形式」に書いてある枚数は無視し、"
            "cards は 4〜6 枚にしてください。\n"
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
            # 禁止語に当たったら、NG一覧を見せて書き直させる（2026-09-22追加）。
            # 執筆役は共通の禁止語辞書を知らないので、黙って落とすと毎回同じ語で落ちる
            # （9/22の火曜リールが「実際」1語でパックごと捨てられた）。
            # 最後の回はそのまま返し、後段の安全チェックに判定させる（禁止語入りは従来どおり捨てる）。
            ng = caption_ng(data["caption"])
            if ng and attempt < 3:
                print(f"禁止語に当たったので書き直させる（{attempt}回目）\n{ng}", file=sys.stderr)
                body += (
                    "\n\n【重要】前回のキャプションは安全チェックで落ちた。下のNGの語を使わずに、"
                    "同じ内容を別の言い回しで書き直すこと。\n" + ng
                )
                continue
            return data
        print(f"caption か cards が空（{attempt}回目）", file=sys.stderr)
    raise SystemExit("執筆に3回失敗した")


def caption_ng(caption):
    """キャプションを safe_check.py に通し、落ちたらNG一覧（文字列）を返す。通れば空文字。

    判定は safe_check.py と辞書に任せる（ここに禁止語を書かない＝2か所に書くと食い違う）。
    """
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "caption.txt"
        p.write_text(caption.strip() + "\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "safe_check.py"), str(p)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    return "" if r.returncode == 0 else r.stdout.strip()


def pick_stock(stock, scene, used_ids):
    """場面が合う風景素材を、使った回数の少ない順に。同じ回で重複させない。"""
    scenery = [s for s in stock["素材"] if s.get("種類", "写真") == "写真"]
    cands = [s for s in scenery if s["場面"] == scene and s["id"] not in used_ids]
    if not cands:
        # 場面が合うものが尽きたら、まだ使っていない何かで代用する（止めない）
        cands = [s for s in scenery if s["id"] not in used_ids]
    if not cands:
        raise SystemExit("素材が足りない。stock を補充すること")
    cands.sort(key=lambda s: (s["使った回数"], s["id"]))
    return cands[0]


def pick_product(stock, products, kind, used_ids, text=""):
    """商品の素材（種類=商品写真／商品動画）を選ぶ。無ければ None。

    2026-09-11 のみさん指示「風景だけ流れて商品が1個も出てない。商品もちゃんと出して」。
    ネタに「商品」が書いてあれば、表紙と偶数枚目は商品の写真・動画カットにする。
    札の文言（text）に合う素材を優先する（「止水ファスナー」の札にはファスナーの寄り、など）。
    """
    cands = [s for s in stock["素材"]
             if s.get("種類") == kind and s.get("商品") in products and s["id"] not in used_ids]
    if not cands:
        return None

    def score(s):
        hit = sum(1 for k in s.get("キーワード", []) if k and k in text)
        return (-hit, 0 if s.get("主役") else 1, s["使った回数"], s["id"])

    cands.sort(key=score)
    return cands[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pack", help="作るパック名（例: 2026-08-29-sole-choice）")
    ap.add_argument("--topic", help="ネタのidを指定（既定は承認済みの先頭）")
    ap.add_argument("--reel", action="store_true", help="リール（9:16の動画）として作る")
    ap.add_argument(
        "--no-ledger",
        action="store_true",
        help="topics.json と stock/index.json を更新しない（動作確認用）",
    )
    args = ap.parse_args()

    topics = load(TOPICS)
    stock = load(STOCK_INDEX)
    topic = pick_topic(topics, args.topic, reel=args.reel)
    print(f"ネタ: {topic['id']} / {topic['テーマ']}" + ("  [リール]" if args.reel else ""))

    written = run_claude(topic, reel=args.reel)
    cards_spec = written["cards"]
    print(f"カード {len(cards_spec)}枚 / キャプション {len(written['caption'])}文字")

    pack_dir = MEDIA / args.pack
    raw_dir = pack_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # --- キャプション ---
    (pack_dir / "caption.txt").write_text(written["caption"].strip() + "\n", encoding="utf-8")

    # --- 素材を選んで並べる ---
    # ネタに「商品」があれば、表紙＝商品写真、偶数枚目＝商品の動画カット（リール）か商品写真、
    # 奇数枚目＝風景（Claudeが scene に「商品」と書いた枚も商品写真）。締めの1枚は風景でよい。
    products = topic.get("商品") or []
    if isinstance(products, str):
        products = [products]
    used, cards = [], []
    n = len(cards_spec)
    for i, c in enumerate(cards_spec, start=1):
        scene = c.get("scene") or (topic["素材の場面"][0] if topic["素材の場面"] else "")
        chosen = None
        # 札の文言（素材選びの手がかり）と、札ごとの商品指定（例: インソールの札には insole）
        text = c.get("kicker", "") + " ".join(c.get("lines", [])) + " ".join(c.get("subs", []))
        card_products = [c["product"]] if c.get("product") in products else products
        if products:
            want_product = (i == 1) or (i % 2 == 0 and i != n) or scene == "商品" or c.get("product")
            if want_product:
                if args.reel and i != 1:
                    chosen = pick_product(stock, card_products, "商品動画", used, text)
                if chosen is None:
                    chosen = pick_product(stock, card_products, "商品写真", used, text)
        if chosen is None:
            if scene == "商品":
                scene = topic["素材の場面"][0] if topic["素材の場面"] else ""
            chosen = pick_stock(stock, scene, used)
        used.append(chosen["id"])
        ext = pathlib.Path(chosen["ファイル"]).suffix.lower()
        is_video = ext in (".mp4", ".mov")
        shutil.copy(REPO / chosen["ファイル"], raw_dir / f"{i}{ext}")
        card = {
            "src": f"raw/{i}{ext}",
            "out": (f"cards/{i}.png" if is_video else f"cards/{i}.jpg") if args.reel else f"{i}.jpg",
            "kicker": c.get("kicker", ""),
            "lines": c.get("lines", []),
            "subs": c.get("subs", []),
            "line_size": 96 if len(c.get("lines", [""])[0]) > 6 else 116,
        }
        if chosen.get("開始秒"):
            card["start"] = chosen["開始秒"]
        cards.append(card)
        print(f"  {i}枚目: {scene} -> {chosen['id']}" + (" [商品]" if chosen.get("種類", "").startswith("商品") else ""))
    save(pack_dir / "cards.json", {"format": "reel" if args.reel else "feed", "cards": cards})

    # --- 文字を載せる ---
    subprocess.run([sys.executable, str(REPO / "scripts" / "overlay_cards.py"), str(pack_dir)],
                   check=True)

    # --- リールなら動画に組む（パック直下は 1.mp4 だけになる） ---
    if args.reel:
        subprocess.run([sys.executable, str(REPO / "scripts" / "build_reel.py"), str(pack_dir)],
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
