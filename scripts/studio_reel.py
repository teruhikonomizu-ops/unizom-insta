"""火曜リールを「高品質版」で作る（リール・スタジオ・2026-09-29 のみさん指示「毎週この品質で出せるよう組み込んで」）。

月曜15:00にタスク「インスタ_火曜リール_夜の制作」が次の火曜の分を作る（2026-10-27〜・~~月曜21:00~~は夜スリープに止められた）。できれば docs/media/<日付>-reel/ に置く
→ 火曜07:30の「インスタ_火曜のリール」は“用意済み”として通知だけする。失敗したら何も置かない
→ 火曜朝は従来の自動リールで作る（空の週は出ない）。

🔴 無人のClaudeには「文章を書く」「画像を見る」「Higgsfieldで決まった数だけ作る」以外をさせない。
   - 書き手   : claude -p --tools ""（道具なし）→ JSONの文章だけ返す
   - 確認     : claude -p --tools Read（見本コマ一覧を見るだけ）
   - 生成係   : claude -p で Higgsfield の生成3機能だけ許可（動画1本・画像2枚まで＝上限84クレジット＝Seedance 2.5 の動画80＋画像2×2。
                2026-10-18 のみさん決定「より良いモデルに変えていく」で 2.0（上限60）から切り替え）
   それ以外（声・書き出し・音・合成・禁止語チェック・公開）はこのプログラムが決まった手順で行う。

使い方: python scripts/studio_reel.py <パック名> [--topic <id>] [--dry] [--hf-from <フォルダ>]
  --dry      : docs/media・台帳を触らない（作業フォルダに mp4 を作るだけ）
  --hf-from  : Higgsfieldを呼ばず、フォルダ内の <キー>.mp4 / <キー>.png を使う（試験用・クレジット0）
"""
import argparse, datetime, functools, http.server, json, os, re, shutil, subprocess, sys, threading, time, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "studio"))
import build_weekly as bw   # pick_topic / load / save / caption_ng / claude_cmd を流用
import media

sys.stdout.reconfigure(encoding="utf-8")
STUDIO = REPO / "studio"
CUTOUTS = REPO / "stock" / "cutouts" / "index.json"
HISTORY = STUDIO / "history.json"
RESULT = REPO / "_スタジオ結果.txt"
HEARTBEAT = Path(os.environ["USERPROFILE"]) / ".claude" / "tasks" / "unizom-studio-制作中.txt"
MAX_IMAGES = 2
LOG = []


def log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"; print(line, flush=True); LOG.append(line)


def result(mark, msg):
    RESULT.write_text(f"[{mark}] {datetime.datetime.now():%Y-%m-%d %H:%M} {msg}\n", encoding="utf-8-sig")


# ---------- 夜スリープに「制作中」を伝える（~/.claude/tasks の更新＝作業中と判定される） ----------
class Heartbeat:
    def __enter__(self):
        self.stop = threading.Event()
        def beat():
            while not self.stop.is_set():
                try:
                    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
                    HEARTBEAT.write_text(f"リール・スタジオ制作中 {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n", encoding="utf-8")
                except Exception:
                    pass
                self.stop.wait(300)
        threading.Thread(target=beat, daemon=True).start(); return self
    def __exit__(self, *a):
        self.stop.set()
        try: HEARTBEAT.unlink()
        except Exception: pass


# ---------- Claude 呼び出し（道具を絞る） ----------
def claude(prompt, work, tools="", allowed=None, model="opus", strict_mcp=True, timeout=3600):
    cmd = [bw.claude_cmd(), "-p", "--model", model, "--tools", tools, "--permission-mode", "dontAsk", "--no-session-persistence"]
    if strict_mcp: cmd += ["--strict-mcp-config"]
    if tools: cmd += ["--add-dir", str(work)]
    if allowed: cmd += ["--allowedTools", ",".join(allowed)]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, cwd=str(work))
    if r.returncode != 0:
        raise RuntimeError(f"claude が失敗 exit={r.returncode}: {(r.stderr or r.stdout)[-800:]}")
    return r.stdout


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m: raise ValueError("JSONが見つからない")
    return json.loads(m.group(0))


# ---------- 材料をそろえる ----------
def catalog(topic):
    prods = set(topic.get("商品") or [])
    cut = [c for c in json.loads(CUTOUTS.read_text(encoding="utf-8"))["切り抜き"] if not c["商品"] or c["商品"] in prods]
    stock = bw.load(bw.STOCK_INDEX)["素材"]
    scenes = set(topic.get("素材の場面") or [])
    photos = [s for s in stock if s.get("ファイル", "").lower().endswith((".jpg", ".jpeg", ".png")) and
              ((s.get("商品") in prods) or (not s.get("商品") and s.get("場面") in scenes))]
    keep = ("id", "ファイル", "種類", "商品", "場面", "キーワード", "メモ", "使った回数")
    return cut, [{k: s[k] for k in keep if k in s} for s in photos][:40]


def writer_prompt(topic, cut, photos, history):
    ex_script = json.loads((STUDIO / "example" / "script.json").read_text(encoding="utf-8")); ex_script.pop("_お手本", None)
    return "\n\n".join([
        (STUDIO / "STUDIO.md").read_text(encoding="utf-8"),
        "---\n# キャプション指示書（caption は これに従う。『出力の形』『画像に載せる文字』『リールのとき』の節は無視し、出力は上の形）\n\n"
        + bw.PROMPT.read_text(encoding="utf-8"),
        "---\n# 今回のネタ\n```json\n" + json.dumps(topic, ensure_ascii=False, indent=1) + "\n```",
        "---\n# 使える素材\n## 切り抜き（cutout:<id>）\n```json\n" + json.dumps(cut, ensure_ascii=False, indent=1)
        + "\n```\n## 写真（stock:<id>・photoCard か coverImg で使う）\n```json\n" + json.dumps(photos, ensure_ascii=False, indent=1) + "\n```",
        "---\n# 最近使った画風（同じ並びにしない）\n```json\n" + json.dumps(history[-4:], ensure_ascii=False, indent=1) + "\n```",
        "---\n# お手本の script（形の見本。中身は今回のネタで書く）\n```json\n" + json.dumps(ex_script, ensure_ascii=False, indent=1)
        + "\n```\n# お手本の scenes.js\n```js\n" + (STUDIO / "example" / "scenes.js").read_text(encoding="utf-8") + "\n```",
        "JSONだけを出力してください。",
    ])


def validate(d):
    sc = d["script"]["scenes"]
    if not 4 <= len(sc) <= 6: raise ValueError(f"場面数が {len(sc)}（4〜6にする）")
    ids = [s["id"] for s in sc]
    if len(set(ids)) != len(ids): raise ValueError("場面のidが重複")
    for s in sc:
        if not s.get("sentences") or len(s["sentences"]) > 2: raise ValueError(f"{s['id']}: sentences は1〜2文")
    if not d.get("caption") or not d.get("scenes_js"): raise ValueError("caption か scenes_js が空")
    hf = d.get("higgsfield") or {}
    if len(hf.get("images") or []) > MAX_IMAGES: hf["images"] = hf["images"][:MAX_IMAGES]
    return d


def write(d, topic, cut, photos, history, work, fix_note=""):
    body = writer_prompt(topic, cut, photos, history) + fix_note
    last = None
    for attempt in (1, 2, 3):
        try:
            d = validate(parse_json(claude(body, work)))
            ng = bw.caption_ng(d["caption"])
            if ng and attempt < 3:
                body += "\n\n【重要】前回のキャプションは安全チェックで落ちた。次の語を使わずに書き直すこと。\n" + ng; continue
            return d
        except Exception as e:
            last = e; log(f"書き手の出力が使えない（{attempt}回目）: {e}")
            body += f"\n\n【重要】前回の出力は使えなかった（{e}）。上の形のJSONだけを出力すること。"
    raise RuntimeError(f"書き手が3回失敗: {last}")


# ---------- Higgsfield（生成係） ----------
# 生成係の報告で気づいた注意（作られたジョブが件数より多い等）。結果の1行に「・⚠…」で添える（2026-10-18 点検の指摘）
HF_NOTES = []


def higgsfield(d, work, hf_from=None):
    hf = d.get("higgsfield") or {}
    jobs = []
    if hf.get("video"): jobs.append(("video", hf["video"]["key"], hf["video"]["prompt"]))
    for im in (hf.get("images") or [])[:MAX_IMAGES]: jobs.append(("image", im["key"], im["prompt"]))
    got = {}
    if not jobs: return got
    if hf_from:
        for kind, key, _ in jobs:
            ext = ".mp4" if kind == "video" else ".png"
            p = Path(hf_from) / (key + ext)
            if not p.exists():   # 呼び名が違っても試験できるよう、同じ種類の先頭のファイルで代用
                cands = sorted(Path(hf_from).glob("*" + ext))
                if not cands: raise RuntimeError(f"--hf-from に {ext} が無い")
                p = cands[0]
            got[key] = p
        return got
    spec = []
    for kind, key, prompt in jobs:
        if kind == "video":
            # 主力の動画モデルは skills/higgsfield/SKILL.md の「モデル早見」が正。変えたらここも直す（2026-10-18〜 seedance_2_5）
            spec.append({"key": key, "tool": "generate_video", "params": {"model": "seedance_2_5", "aspect_ratio": "9:16", "duration": 5,
                         "resolution": "1080p", "generate_audio": True, "count": 1, "use_unlim": False, "prompt": prompt}})
        else:
            spec.append({"key": key, "tool": "generate_image", "params": {"model": "nano_banana_pro", "aspect_ratio": "9:16",
                         "resolution": "2k", "count": 1, "use_unlim": False, "prompt": prompt}})
    prompt = ("あなたはHiggsfieldの生成係です。下の一覧を、書いてあるパラメータのまま1件につき1回だけ生成してください。"
              "パラメータを変えない・件数を増やさない・作り直さない。失敗した件は作り直さずに失敗として報告する。\n"
              "例外は1つだけ：返事にジョブ（id）が1つも無く、preset_recommendation と retry_literal_with だけが返った時は、"
              "まだ作られていないので、同じパラメータに retry_literal_with の declined_preset_id を足して1回だけ出し直す。"
              "返事にジョブ（id）があれば、お勧めが添えてあっても出し直さない。出し直しでもまたジョブが無ければ、その件は failed にして終える（3回目は出さない）。"
              "通信が切れるなどで結果が分からない時も出し直さない（failed にする）。\n"
              "全部を出したら jobs_wait で全件が終わるまで待つ（最大60回まで呼んでよい）。\n"
              "最後に JSON だけを出力: {\"results\": {\"<key>\": \"<result_url>\"}, \"failed\": [\"<key>\"], "
              "\"jobs_created\": <実際にジョブ（id）が作られた生成の回数>}\n\n```json\n"
              + json.dumps(spec, ensure_ascii=False, indent=1) + "\n```")
    out = claude(prompt, work, tools="", model="sonnet", strict_mcp=False, timeout=2400,
                 allowed=["mcp__higgsfield__generate_video", "mcp__higgsfield__generate_image", "mcp__higgsfield__jobs_wait"])
    res = parse_json(out)
    # 上限（動画1本＋画像2枚）は生成係への約束でしかない＝作られたジョブの数を報告させて照らす
    made = res.get("jobs_created")
    log(f"Higgsfield 作られたジョブ {made} 件（予定 {len(jobs)} 件）")
    if isinstance(made, int) and made > len(jobs):
        HF_NOTES.append(f"・⚠Higgsfieldのジョブが予定より多い（{made}件／予定{len(jobs)}件＝クレジットを余計に使った可能性）")
    for kind, key, _ in jobs:
        url = (res.get("results") or {}).get(key)
        if not url: raise RuntimeError(f"Higgsfieldで {key} が作れなかった: {res.get('failed')}（作られたジョブ {made} 件＝クレジットは使った可能性）")
        p = work / "hf" / (key + (".mp4" if kind == "video" else ".png")); p.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(url, p); got[key] = p
        log(f"Higgsfield {key} を受け取った（{p.stat().st_size//1024}KB）")
    return got


# ---------- 書き出しの準備 ----------
def stage(d, work, hf_files):
    web = work / "web"; a = web / "a"
    if web.exists(): shutil.rmtree(web)
    a.mkdir(parents=True)
    shutil.copy(STUDIO / "lib.js", web); shutil.copy(STUDIO / "player.html", web); shutil.copy(STUDIO / "render.js", web)
    shutil.copy(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "NotoSansJP-VF.ttf", a / "njp.ttf")
    cuts = {c["id"]: c for c in json.loads(CUTOUTS.read_text(encoding="utf-8"))["切り抜き"]}
    stock = {s["id"]: s for s in bw.load(bw.STOCK_INDEX)["素材"]}
    man, used_stock = {}, []
    for key, src in (d.get("assets") or {}).items():
        kind, _, ref = src.partition(":")
        if kind == "cutout" and ref in cuts: p = REPO / cuts[ref]["ファイル"]
        elif kind == "stock" and ref in stock: p = REPO / stock[ref]["ファイル"]; used_stock.append(ref)
        elif kind == "hf" and ref in hf_files: p = hf_files[ref]
        elif kind == "hf" and len([f for f in hf_files.values() if f.suffix == ".png"]) == 1:
            p = next(f for f in hf_files.values() if f.suffix == ".png")   # 呼び名がずれた時は唯一の画像へ付け替える
        else: raise RuntimeError(f"素材が見つからない: {key}={src}")
        if p.suffix.lower() == ".mp4":
            if kind == "hf": continue   # 動画は合成で使う（Canvasには載せない）
            raise RuntimeError(f"動画はCanvasに載せられない: {key}={src}")
        shutil.copy(p, a / (key + p.suffix.lower())); man[key] = key + p.suffix.lower()
    (web / "assets.json").write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    (web / "scenes.js").write_text(d["scenes_js"], encoding="utf-8")
    return used_stock


class Server:
    def __init__(self, root):
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a, **k): pass
        h = functools.partial(Quiet, directory=str(root))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/player.html"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
    def close(self): self.httpd.shutdown()


def render(work, url, out, times=None):
    cmd = ["node", str(work / "web" / "render.js"), url, str(out)] + ([",".join(f"{t:.2f}" for t in times)] if times else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    lines = (r.stdout + r.stderr).splitlines()
    errs = [l for l in lines if "[pageerror]" in l]
    render.audit = sorted({l.replace("[audit] ", "") for l in lines if l.startswith("[audit]")})
    return r.returncode == 0, errs


def build_samples(work, url, timing):
    """場面ごとに3コマ（出だし・中ほど・終わり）を書き出し、場面ごとの見本（540×960×3）と機械の検査結果を返す。"""
    from PIL import Image
    times, t = [], 0.0
    for s in timing:
        times += [round(t + 0.6, 2), round(t + s["scene"] * 0.55, 2), round(t + s["scene"] - 0.35, 2)]
        t += s["scene"]
    shots = work / "samples"
    if shots.exists(): shutil.rmtree(shots)
    ok, errs = render(work, url, shots, times)
    if not ok: return [], errs, []
    audit = list(render.audit)
    w, h = 540, 960; paths = []
    for si, sc in enumerate(timing):
        sheet = Image.new("RGB", (w * 3, h), (90, 120, 90))
        for k in range(3):
            im = Image.open(shots / f"t_{times[si*3+k]:.2f}.png").convert("RGBA")
            bg = Image.new("RGBA", im.size, (90, 120, 90, 255)); bg.alpha_composite(im)   # 透明部分（冒頭の動画が入る所）は緑
            sheet.paste(bg.convert("RGB").resize((w, h)), (k * w, 0))
        p = work / f"見本_{si+1}_{sc['id']}.jpg"; sheet.save(p, quality=88); paths.append(p)
    return paths, [], audit


# ---------- 🆕 テンポの測定（2026-10-17 のみさん決定「切り替えの早い型」） ----------
# 0.25秒ごとのコマを 108×192 に縮めて隣どうしの差を見る。物差しは 2026-10-17 に実物2本で合わせた：
#   手作りの速い見本＝大きな変化の間隔 平均0.69秒・止まっている秒 0/20 ／ 10/06 のスタジオ版＝4.17秒・9/25（36%）
PACE_STEP, PACE_BIG, PACE_STILL = 0.25, 16.0, 1.5     # 大きな変化＝差>16 ／ 止まっている1秒＝4歩とも差<1.5
PACE_MAX_GAP, PACE_MAX_STILL = 1.8, 0.20             # 目標：間隔が平均1.8秒以内・止まっている秒が2割以下（指示書どおり1場面3回で届く値・別の目の点検で1.5→1.8）
# ⚠ 限界: 写真の壁の流れ・flash などの連続の動きも「大きな変化」に数える（切り替えが無くても合格しうる）


def pace_check(d, work, url, timing):
    """冒頭の実写動画の場面と最後の場面を除いて測る。戻り値＝(合格か, 説明の1文, 安全域の問題の一覧)"""
    from PIL import Image, ImageChops, ImageStat
    scenes = d["script"]["scenes"]; spans, t = [], 0.0
    for i, s in enumerate(timing):
        vid = bool(scenes[i].get("video")) if i < len(scenes) else False
        if not vid and i != len(timing) - 1: spans.append((t, t + s["scene"]))
        t += s["scene"]
    times = []
    for a, b in spans:
        k = a
        while k <= b - 0.05: times.append(round(k, 2)); k += PACE_STEP
    if len(times) < 8: return True, "テンポ: 測れる場面が短いので測らなかった", []
    out = work / "pace"
    if out.exists(): shutil.rmtree(out)
    ok, errs = render(work, url, out, times)
    safe = [a for a in render.audit if ("下420px" in a or "右190px" in a or "画面の外" in a)]
    if not ok: return True, "テンポ: 測定用のコマを書き出せなかった（" + " / ".join(errs[:2]) + "）", safe
    ims = {tt: Image.open(out / f"t_{tt:.2f}.png").convert("RGBA").resize((108, 192)) for tt in times}
    def flat(im):
        bg = Image.new("RGBA", im.size, (90, 120, 90, 255)); bg.alpha_composite(im); return bg.convert("RGB")
    diffs, span_len = [], 0.0
    for a, b in spans:
        seq = [tt for tt in times if a <= tt < b]
        span_len += b - a
        for p, q in zip(seq, seq[1:]):
            diffs.append(sum(ImageStat.Stat(ImageChops.difference(flat(ims[p]), flat(ims[q]))).mean) / 3)
    shutil.rmtree(out, ignore_errors=True)
    big = sum(1 for x in diffs if x > PACE_BIG)
    gap = span_len / max(1, big)
    secs = [diffs[i:i + 4] for i in range(0, len(diffs) - 3, 4)]
    still = sum(1 for s in secs if max(s) < PACE_STILL); ratio = still / max(1, len(secs))
    msg = f"テンポ: 大きく絵が変わるのは平均{gap:.1f}秒ごと（目標{PACE_MAX_GAP}秒以内）・ほぼ止まっている秒 {still}/{len(secs)}（目標2割以下）"
    passed = gap <= PACE_MAX_GAP and ratio <= PACE_MAX_STILL
    return passed, msg, safe


def review(d, work, sheets, readings, voice_report, errs, audit):
    prompt = ("あなたは今週の火曜リールの監督です。下のJSONはあなたが書いた案です。書き出した見本（場面ごとに1枚・出だし／中ほど／終わりの3コマ。"
              "緑の部分は冒頭の実写動画が入る所）を**全部** Read で開いて目で確認し、次の点を点検してください：\n"
              "文字のはみ出し・重なり・欠け／字幕の黒い帯に他の文字や絵がかぶっていないか／右190px・下420px（y>1500）に文字が入っていないか／"
              "引き出し線が写っている部位を指しているか／場面ごとに画風が変わっているか／背景がぼやけていないか／読みの誤り（下の『実際の読み』）。\n"
              "**機械の検査で見つかった問題は必ず直すこと。**\n"
              "🔴 higgsfield の中身と、assets の `hf:<キー>` のキー名は変えないこと（画像・動画はもう作ってある）。\n"
              "問題が無ければ {\"ok\": true} だけを出力。直す所があれば、同じ形の完全なJSON（topic_id から caption まで全部）を出力。前後に文章を付けない。\n\n"
              "見本:\n" + "\n".join(f"- {p}" for p in sheets) + "\n\n# 機械の検査で見つかった問題\n" + ("\n".join(f"- {a}" for a in audit) or "（なし）")
              + "\n\n# 実際の読み（音声エンジンの読み）\n" + "\n".join(f"- {r['scene']}: {r['text']} → {r['reading']}" for r in readings)
              + "\n\n# 速さ\n" + "\n".join(voice_report) + ("\n\n# 書き出しのエラー\n" + "\n".join(errs) if errs else "")
              + "\n\n# あなたの案\n```json\n" + json.dumps(d, ensure_ascii=False, indent=1) + "\n```\n\n"
              + "---\n参考: 制作指示書\n" + (STUDIO / "STUDIO.md").read_text(encoding="utf-8"))
    out = claude(prompt, work, tools="Read", allowed=["Read"])
    r = parse_json(out)
    if r.get("ok"): return None
    r = validate(r); r["higgsfield"] = d.get("higgsfield")   # 作り済みの物は変えさせない
    return r


def texts_for_check(d):
    lit = re.findall(r"'([^'\n]*[ぁ-んァ-ヶ一-龠][^'\n]*)'", d["scenes_js"]) + re.findall(r'"([^"\n]*[ぁ-んァ-ヶ一-龠][^"\n]*)"', d["scenes_js"])
    return "\n".join([s["show"] for s in d["script"]["scenes"]] + [" ".join(s["sentences"]) for s in d["script"]["scenes"]] + lit)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("pack"); ap.add_argument("--topic"); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--hf-from"); args = ap.parse_args()
    work = Path(os.environ["LOCALAPPDATA"]) / "unizom-studio" / args.pack
    if work.exists(): shutil.rmtree(work)
    work.mkdir(parents=True)
    out_dir = REPO / "docs" / "media" / args.pack
    t0 = time.time()
    try:
        with Heartbeat():
            if out_dir.exists(): raise RuntimeError(f"{args.pack} は既にある（上書きしない）")
            topics = bw.load(bw.TOPICS); topic = bw.pick_topic(topics, args.topic, reel=True)
            log(f"ネタ: {topic['id']} / {topic['テーマ']}")
            history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
            cut, photos = catalog(topic)
            media.start_engine()
            d = write(None, topic, cut, photos, history, work)
            log("台本と場面コードができた: " + " / ".join(d.get("style_plan", [])))
            (work / "draft1.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            hf_files = higgsfield(d, work, args.hf_from)

            def build(d):
                used = stage(d, work, hf_files)
                timing, vrep = media.make_voice(d["script"], work)
                shutil.copy(work / "timing.json", work / "web" / "timing.json")
                return used, timing, vrep

            used_stock, timing, vrep = build(d)
            srv = Server(work / "web")
            try:
                def check(timing):
                    sheets, errs, audit = build_samples(work, srv.url, timing)
                    try:   # 🔴 測定の失敗でその週を止めない（測れなければ合格扱い・ログに残す）
                        pace_ok, pace_msg, safe = pace_check(d, work, srv.url, timing) if not errs else (True, "テンポ: 書き出しエラーのため測らなかった", [])
                    except Exception as e:
                        pace_ok, pace_msg, safe = True, f"テンポ: 測定に失敗したので測らなかった（{str(e)[:120]}）", []
                    log(pace_msg + ("" if pace_ok else "  → 目標に届かない"))
                    # safe＝0.25秒ごとの測定コマで見つけた安全域の問題。確認役には渡すが、週を止める判定には使わない（一瞬の通過は実害が小さい）
                    # 「3.60秒: 」の時刻を外した本文で重複を除く（同じ文字が1場面ずっと帯に入っていても1行にする）
                    body = lambda s: re.sub(r"^[0-9.]+秒: ", "", s)
                    seen, uniq = {body(a) for a in audit}, []
                    for a in safe:
                        if body(a) not in seen: seen.add(body(a)); uniq.append(a)
                    return sheets, errs, audit, uniq, pace_ok, pace_msg
                sheets, errs, audit, safe, pace_ok, pace_msg = check(timing)
                # 問題（エラー・見本コマの検査）の無かった最後の版を覚えておく＝確認役の最後の直しで壊れたら、そこへ戻す（別の目の点検 2026-10-17）
                good = (d, pace_ok, pace_msg) if not (errs or audit) else None
                # 確認は最大2回。1回目は必ず見る。2回目は機械の検査（テンポを含む）かエラーが残っている時だけ
                for rnd_no in (1, 2):
                    if rnd_no == 2 and not (audit or errs or safe or not pace_ok): break
                    if audit or safe: log("機械の検査: " + " / ".join((audit + safe)[:6]))
                    try:   # 確認役の直しが例外（JSONの崩れ・無い素材・claudeの失敗）で壊れても、問題の無かった版があればそこへ戻す
                        readings = media.check_readings(d["script"])
                        issues = audit + safe + ([] if pace_ok else [pace_msg + "。STUDIO.md の『テンポ＝切り替えの早い型』どおり、1場面の中で cutAt で絵を3〜5回切り替え、場面の切り替えは cut を基本にすること"])
                        fixed = review(d, work, sheets, readings, vrep, errs, issues)
                        if not fixed:
                            if rnd_no == 1: log("確認: 直す所なし")
                            break
                        log(f"確認{rnd_no}回目で直しが入った"); d = fixed
                        (work / f"draft{rnd_no+1}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
                        used_stock, timing, vrep = build(d)
                        sheets, errs, audit, safe, pace_ok, pace_msg = check(timing)
                        if not (errs or audit): good = (d, pace_ok, pace_msg)
                    except Exception as e:
                        if not good: raise
                        log(f"確認{rnd_no}回目の直しで例外: {str(e)[:200]}")
                        errs, audit = [f"確認役の直しで例外: {str(e)[:150]}"], []
                        break
                reverted = False
                if (errs or audit) and good:
                    log("最後の直しで誤りが残った（" + " / ".join((errs + audit)[:2]) + "）→ 問題の無かった版に戻して作る")
                    d, pace_ok, pace_msg = good; reverted = True
                    (work / "draft_final.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
                    used_stock, timing, vrep = build(d)
                    _, errs, audit = build_samples(work, srv.url, timing)
                    if errs or audit: log("戻した版でも検査に落ちた（声を作り直した分のずれの可能性）")
                if errs: raise RuntimeError(("戻した版でも " if reverted else "") + "書き出しのエラー: " + " / ".join(errs[:3]))
                if audit: raise RuntimeError(("戻した版でも " if reverted else "") + "文字の重なり・はみ出しが直らなかった: " + " / ".join(audit[:3]))
                # テンポが目標に届かなくても、その週は止めない（ゆっくりでも高品質版の方が従来版より良い）。結果の行に残す
                pace_note = "" if pace_ok else f"・⚠テンポ目標に届かず（{pace_msg.replace('テンポ: ', '')}）"
                # 見張り自身の故障を黙らせない：測れなかった週も火曜07:30の通知に出す（「測れる場面が短い」は故障ではないので出さない）
                if pace_ok and ("測定に失敗" in pace_msg or "書き出せなかった" in pace_msg):
                    why = pace_msg.replace('テンポ: ', ''); why = why if len(why) <= 90 else why[:88] + '…'
                    pace_note += f"・⚠テンポを測れなかった（{why}）"
                if reverted: pace_note += "・⚠確認役の最後の直しで誤りが出たので、その前の版で作った"
                pace_note += "".join(HF_NOTES)
                log("全コマを書き出す")
                ok, errs = render(work, srv.url, work / "frames")
                if not ok: raise RuntimeError("全コマの書き出しに失敗: " + " / ".join(errs[:3]))
            finally:
                srv.close()
            hook_key = next((s.get("video") for s in d["script"]["scenes"] if s.get("video")), None)
            hook = hf_files.get(hook_key) if hook_key else None
            amb = None
            if hook:
                amb = work / "hook_amb.wav"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(hook), "-vn", "-ac", "1", "-ar", "48000", str(amb)], check=False)
            total = media.make_audio(work, timing, amb)
            first = timing[0]["scene"] + 0.45
            mp4 = work / "1.mp4"; media.compose(work, total, mp4, hook, first)
            media.contact_sheet(mp4, work / "コマ一覧_1秒ごと.jpg")
            # 検査
            if not 15 <= total <= 60: raise RuntimeError(f"長さが {total:.1f}秒（15〜60秒の外）")
            chk = work / "onscreen.txt"; chk.write_text(texts_for_check(d) + "\n" + d["caption"], encoding="utf-8")
            r = subprocess.run([sys.executable, str(REPO / "scripts" / "safe_check.py"), str(chk)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0: raise RuntimeError("禁止語: " + " ".join(l.strip() for l in r.stdout.splitlines() if "NG" in l)[:300])
            log(f"完成 {total:.1f}秒・{mp4.stat().st_size//1024//1024}MB・{(time.time()-t0)/60:.0f}分")
            if args.dry:
                result("成功", f"{args.pack}（試験・--dry）を作った: {mp4}{pace_note}"); return
            # 置く（ここまで来て初めて docs/media を作る＝途中の失敗で半端なパックを残さない）
            out_dir.mkdir(parents=True)
            shutil.copy(mp4, out_dir / "1.mp4")
            (out_dir / "caption.txt").write_text(d["caption"].strip() + "\n", encoding="utf-8")
            (out_dir / "studio.json").write_text(json.dumps({"topic_id": topic["id"], "style_plan": d.get("style_plan"), "script": d["script"],
                                                             "assets": d.get("assets"), "higgsfield": d.get("higgsfield")}, ensure_ascii=False, indent=1), encoding="utf-8")
            today = datetime.date.today().isoformat()
            for t in topics["ネタ"]:
                if t["id"] == topic["id"]: t["状態"] = "使用済み"; t["使った日"] = today
            bw.save(bw.TOPICS, topics)
            stock = bw.load(bw.STOCK_INDEX)
            for s in stock["素材"]:
                if s["id"] in used_stock: s["使った回数"] = s.get("使った回数", 0) + 1; s["最後に使った日"] = today
            bw.save(bw.STOCK_INDEX, stock)
            history.append({"pack": args.pack, "topic": topic["id"], "style_plan": d.get("style_plan")})
            HISTORY.write_text(json.dumps(history[-12:], ensure_ascii=False, indent=1), encoding="utf-8")
            result("成功", f"{args.pack} を高品質版で作った（{total:.0f}秒・未投稿・承認待ち）{pace_note}")
    except Exception as e:
        log(f"失敗: {e}")
        result("失敗", f"{args.pack} の高品質版を作れなかった: {str(e)[:200]}")
        sys.exit(1)
    finally:
        (work / "log.txt").write_text("\n".join(LOG), encoding="utf-8")


if __name__ == "__main__":
    main()
