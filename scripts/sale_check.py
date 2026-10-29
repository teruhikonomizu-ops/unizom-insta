"""投稿日にAmazon・楽天のセールがあるかを調べ、あれば「セールのお知らせ」のネタを作る（2026-10-30 のみさん指示）。

のみさん「火曜・金曜にAmazonや楽天でセールがあった場合は、その告知に変えてほしい。セールと案内をしないと意味がない。
カレンダーでまずAmazonのセール見るでしょ。楽天も。セールがなければネタを投稿すればいいけど、あればセールを優先して」

調べる所:
  Amazon … Googleカレンダー teruhiko.nomizu@gmail.com（朝会がセール告知メールから入れる終日予定・手で入れた【Amazonセール】）
           claude -p に list_events だけを許して呼ばせ、**道具の返事そのもの**（stream-json の tool_result）をこのファイルが読む。
           Claudeの書き写しは使わない＝「読めなかったのに [] と答えた」「別のカレンダーを読んだ」を機械で見分ける（別の目の点検 2026-10-30）。
  楽天   … OneDrive デスクトップ\楽天自動化\ダッシュボード\イベント.json（楽天の大型イベント日程・月1回Claudeが更新）
           ワンダフルデー・5と0のつく日などの定例のポイント日は数えない（ほぼ毎回セール扱いになってしまうため）。

対象にするセール:
  ・投稿日に開催中のもの／投稿日の翌日に始まるもの（「明日から」の予告）
  ・楽天は開始日の20:00に始まる＝開始日当日の投稿は「今夜20時から」。プレ期間は数えない
  ・題名に「要確定」「予定」があるAmazonの予定は載せない（間違ったセールを告知しないため）。載せなかった事は朝会への報告に出す

🔴 公開リポジトリ（docs/media/<パック>/sale.json・_お知らせログ.txt）にはカレンダーの題名そのものや道具の返事の切れ端を出さない。
   出すのは店・セール名（整えた物）・期間・決まった文言の失敗理由だけ。細かい記録はこのPCの %LOCALAPPDATA%\\unizom-insta-sale\\log.txt。

使い方（確認用）: python scripts/sale_check.py 2026-11-06
"""

import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

CALENDAR_ID = "teruhiko.nomizu@gmail.com"
LIST_TOOL = "mcp__claude_ai_Google_Calendar__list_events"
RAKUTEN_EVENTS = (pathlib.Path(os.environ.get("USERPROFILE", str(pathlib.Path.home())))
                  / "OneDrive" / "デスクトップ" / "楽天自動化" / "ダッシュボード" / "イベント.json")
LOG = pathlib.Path(os.environ.get("LOCALAPPDATA", str(pathlib.Path.home()))) / "unizom-insta-sale" / "log.txt"

# Amazonのセールとみなす題名＝「セール」の言葉か、Amazonのセールの名前が入っている物（「Amazon」だけでは数えない＝
# 「膝上長靴｜公開日・発売日」のような商品の予定を拾ったため・2026-10-30 試験で発覚）
AMAZON_HIT = re.compile(r"セール|SALE|Sale|DEAL|プライムデー|プライム感謝祭|ブラックフライデー|サイバーマンデー|初売り")
AMAZON_OTHER = re.compile(r"Yahoo|ヤフー|楽天|メルカリ|Qoo10|ユニクロ|PayPay|au PAY", re.I)
# 作業の予定（確認・申込・価格直しなど）。セールそのものではない
AMAZON_TASK = re.compile(r"前日確認|申込|申し込み|応募|エントリー|✅|完了|直す|価格|点検")
# 確定していないセール＝載せない（報告には出す）
AMAZON_UNSURE = re.compile(r"要確定|予定")
# 楽天の大型イベントの既定の時刻（イベント.json に start_time/end_time が無い時）
RAKUTEN_START = "20:00"
RAKUTEN_END = "01:59"
RAKUTEN_STALE_DAYS = 45


def log(msg):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def _md(d):
    return f"{d.month}/{d.day}"


def _wd(d):
    return "月火水木金土日"[d.weekday()]


def clean_amazon_name(title):
    t = re.sub(r"^.*?【Amazonセール】", "", title)
    t = re.sub(r"[｜|]Claude\s*$", "", t).strip()
    t = re.sub(r"[（(][^）)]*[）)]\s*$", "", t).strip()   # 末尾の（10/13〜10/19）などを外す
    t = re.sub(r"\s*#\s*\d+\s*$", "", t).strip()          # 出品者向けの回の番号（#6）は外す
    if t.startswith("手動"):
        t = "タイムセール（一部商品）"
    return t


def _claude():
    for name in ("claude", "claude.cmd", "claude.exe"):
        exe = shutil.which(name)
        if exe:
            return exe
    raise RuntimeError("claude が見つからない")


def _tool_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def read_calendar(post_date):
    """投稿日〜翌日に重なる予定を、カレンダーの道具の返事から直接読む。確かめられなければ例外（理由は決まった短い文）。"""
    exe = _claude()
    start = post_date.isoformat() + "T00:00:00"
    end = (post_date + datetime.timedelta(days=2)).isoformat() + "T00:00:00"
    prompt = (
        f"Googleカレンダーの予定を list_events で1回だけ読んでください（calendarId は必ず \"{CALENDAR_ID}\"、"
        f"startTime \"{start}\"、endTime \"{end}\"、pageSize 250）。読んだら「済」とだけ答えてください。"
    )
    reason = "カレンダーの道具が呼ばれなかった"
    for attempt in (1, 2):
        try:
            r = subprocess.run(
                # 読むだけ＝カレンダーの一覧を読む道具1つしか渡さない
                [exe, "-p", "--model", "haiku", "--permission-mode", "dontAsk", "--allowedTools", LIST_TOOL,
                 "--output-format", "stream-json", "--verbose"],
                input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
            )
        except subprocess.TimeoutExpired:
            reason = "カレンダーの読み取りが時間内に終わらなかった"
            log(f"{post_date} {attempt}回目 時間切れ")
            continue
        uses, results = {}, {}
        for ln in r.stdout.splitlines():
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            if o.get("type") not in ("assistant", "user"):
                continue
            for c in (o.get("message") or {}).get("content") or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use" and str(c.get("name", "")).endswith("list_events"):
                    uses[c.get("id")] = c.get("input") or {}
                elif c.get("type") == "tool_result":
                    results[c.get("tool_use_id")] = c
        log(f"{post_date} {attempt}回目 exit={r.returncode} 道具の呼び出し={len(uses)} stderr={r.stderr[-300:]!r}")
        if not uses:
            reason = "カレンダーの道具が呼ばれなかった（接続が切れている恐れ）"
            continue
        if any(i.get("calendarId") != CALENDAR_ID for i in uses.values()):
            reason = "仕事用ではないカレンダーが読まれた"
            continue
        events, ok = [], True
        for uid in uses:
            res = results.get(uid)
            if not res or res.get("is_error"):
                ok, reason = False, "カレンダーの道具がエラーを返した"
                break
            try:
                data = json.loads(_tool_text(res.get("content")))
            except ValueError:
                ok, reason = False, "カレンダーの返事が読めなかった"
                break
            # 予定が0件の日は events の項目そのものが無い形で返る（2026-10-30 実測）
            if (not isinstance(data, dict) or "accessRole" not in data
                    or not isinstance(data.get("events", []), list)
                    or data.get("summary", CALENDAR_ID) != CALENDAR_ID):
                ok, reason = False, "カレンダーの返事の形が違った"
                break
            if data.get("nextPageToken"):
                ok, reason = False, "予定が多すぎて1回で読み切れなかった"
                break
            events += data.get("events", [])
        if ok:
            log(f"{post_date} 予定 {len(events)}件を読んだ")
            return events
        log(f"{post_date} {attempt}回目 {reason}")
    raise RuntimeError(reason)


def _span(ev):
    """予定の (始まりの日, 最後の日) を返す。セールらしくない（短い時刻付き）予定は None。"""
    s, e = ev.get("start") or {}, ev.get("end") or {}
    if isinstance(s, str):
        s, e = {"date": s}, {"date": e}
    if s.get("date"):
        sd = datetime.date.fromisoformat(str(s["date"])[:10])
        ed = datetime.date.fromisoformat(str(e.get("date") or s["date"])[:10])
        return sd, max(sd, ed - datetime.timedelta(days=1))    # 終日予定の終わりは「翌日」で入っている
    if s.get("dateTime") and e.get("dateTime"):
        st = datetime.datetime.fromisoformat(str(s["dateTime"]).replace("Z", "+00:00"))
        en = datetime.datetime.fromisoformat(str(e["dateTime"]).replace("Z", "+00:00"))
        jst = datetime.timezone(datetime.timedelta(hours=9))
        st, en = st.astimezone(jst), en.astimezone(jst)
        if en - st < datetime.timedelta(hours=20):
            return None                                       # 作業・会議の予定
        last = en.date() if en.time() > datetime.time(0, 0) else en.date() - datetime.timedelta(days=1)
        return st.date(), last
    return None


def amazon_sales(post_date, events):
    out, skipped = [], []
    tomorrow = post_date + datetime.timedelta(days=1)
    for ev in events:
        title = str(ev.get("summary") or "")
        if not AMAZON_HIT.search(title) or AMAZON_OTHER.search(title) or AMAZON_TASK.search(title):
            continue
        span = _span(ev)
        if not span:
            continue
        s, last = span
        if s <= post_date <= last:
            when = "開催中"
        elif s == tomorrow:
            when = "明日から"
        else:
            continue
        name = clean_amazon_name(title)
        if AMAZON_UNSURE.search(title):
            skipped.append({"store": "Amazon", "name": name, "reason": "日程が要確定"})
            continue
        # 手動タイムセールが2件重なる時など、同じ名前は1回だけ（終わりの遅い方を残す）
        dup = next((o for o in out if o["name"] == name), None)
        if dup:
            if last.isoformat() <= dup["last"]:
                continue
            out.remove(dup)
        out.append({"store": "Amazon", "name": name, "start": s.isoformat(), "last": last.isoformat(), "when": when,
                    "period": f"{_md(s)}({_wd(s)})〜{_md(last)}({_wd(last)})"})
    return out, skipped


def rakuten_sales(post_date):
    d = json.loads(RAKUTEN_EVENTS.read_text(encoding="utf-8-sig"))
    errors = []
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(d.get("_確認日", "")))
    checked = datetime.date.fromisoformat(m.group(1)) if m else None
    if not checked or (post_date - checked).days > RAKUTEN_STALE_DAYS:
        errors.append(f"楽天のイベント日程が{RAKUTEN_STALE_DAYS}日以上更新されていない（Claudeに「楽天のイベント日程を入れて」）")
    ends = [datetime.date.fromisoformat(e["end"]) for e in d.get("events", []) if e.get("end")]
    if not ends or max(ends) < post_date:
        errors.append("楽天のイベント日程が投稿日まで入っていない（Claudeに「楽天のイベント日程を入れて」）")
    out = []
    tomorrow = post_date + datetime.timedelta(days=1)
    for e in d.get("events", []):
        s, en = datetime.date.fromisoformat(e["start"]), datetime.date.fromisoformat(e["end"])
        st_t, en_t = e.get("start_time") or RAKUTEN_START, e.get("end_time") or RAKUTEN_END
        # 終わりが深夜（01:59など）なら、終了日の朝の投稿ではもう終わっている
        last_morning = en - datetime.timedelta(days=1) if en_t < "08:00" else en
        if s < post_date <= last_morning:
            when = "開催中"
        elif s == post_date:
            when = f"今夜{int(st_t[:2])}時から" if st_t >= "12:00" else "開催中"
        elif s == tomorrow:
            when = f"明日{int(st_t[:2])}時から"
        else:
            continue
        name = e["name"]
        name = name if name.startswith("楽天") else "楽天" + name
        out.append({"store": "楽天", "name": name, "start": s.isoformat(), "last": en.isoformat(), "when": when,
                    "period": f"{_md(s)}({_wd(s)}) {st_t}〜{_md(en)}({_wd(en)}) {en_t}"})
    return out, errors


def check(post_date):
    """{'sales','skipped','errors'} を返す。調べられなかった所は errors に決まった短い文で書く（静かに飛ばさない）。"""
    sales, skipped, errors = [], [], []
    try:
        a, sk = amazon_sales(post_date, read_calendar(post_date))
        sales += a
        skipped += sk
    except Exception as e:  # noqa: BLE001
        msg = str(e) if isinstance(e, RuntimeError) else "読み取り中に止まった"
        log(f"{post_date} Amazon 失敗: {e!r}")
        errors.append(f"Amazon（カレンダー）を確認できなかった: {msg}")
    try:
        r, errs = rakuten_sales(post_date)
        sales += r
        errors += errs
    except Exception as e:  # noqa: BLE001
        log(f"{post_date} 楽天 失敗: {e!r}")
        errors.append("楽天（イベント日程）を確認できなかった: イベント.json が読めない")
    return {"post_date": post_date.isoformat(), "sales": sales, "skipped": skipped, "errors": errors}


def sale_topic(result, reel=False):
    """セールがあれば、topics.json のネタと同じ形の『セールのお知らせ』を返す。無ければ None。
    id は sale- で始まる＝topics.json に無いので、台帳（ネタ帳）は減らない。"""
    sales = result["sales"]
    if not sales:
        return None
    stores = sorted({s["store"] for s in sales}, key=lambda x: 0 if x == "Amazon" else 1)
    facts = [f"{s['store']}の「{s['name']}」は {s['period']}（投稿日から見て: {s['when']}）" for s in sales]
    facts += [
        "unizomの長靴・ウェーダー・専用インソール・防水リュックは " + "と".join(stores) + " で販売している",
        "対象の商品や価格は、各ストアのページで確認してもらう",
    ]
    if len(stores) == 1:
        other = "楽天" if stores[0] == "Amazon" else "Amazon"
        facts.append(f"今回セールがあるのは{stores[0]}だけ（{other}のセールは書かない）")
    themes = "／".join(f"{s['name']}（{s['when']}）" for s in sales)
    return {
        "id": f"sale-{result['post_date']}",
        "状態": "承認済み",
        "柱": "製品（セールのお知らせ）",
        "テーマ": f"セールのお知らせ: {themes}",
        "形式": "リール" if reel else "単写真4:5",
        "商品": ["nw99", "hw94", "chest", "hipw", "insole", "bag"],
        "素材の場面": ["田んぼ", "渓流"],
        "季節": ["通年"],
        "伝える事実": facts,
        "使ってはいけない表現": [
            "割引率・価格・ポイント倍率・クーポン額などの数字（その時の実態を確認していないため）",
            "「全品」「全商品が対象」など、対象商品を断定する書き方",
            "上に書いていないストアやセール名・上に書いた期間と違う日付",
            "「最安」「今だけ」「急いで」など、あおる言い方",
            "他社ブランド名",
        ],
        "出典": "Googleカレンダー teruhiko.nomizu（Amazonセール）／楽天自動化/ダッシュボード/イベント.json（楽天の大型イベント）",
        "メモ": "セールの日は通常のネタより優先する（2026-10-30 のみさん指示）。見出し（1行目）でセール名と期間がすぐ分かるように。"
                "「開催中」なら期間の終わりを、「明日から」「今夜20時から」なら始まりを目立たせる。"
                "商品は1〜2点に絞らず『長靴・ウェーダーなど』とまとめてよい。",
        "使った日": None,
        "_セール": result,
    }


def choose_topic(bw, topics, wanted_id, reel, pack):
    """ネタを決める。--topic 指定が無く、パック名の日付にセールがあればセールのお知らせを優先する。"""
    if wanted_id:
        return bw.pick_topic(topics, wanted_id, reel=reel)
    m = re.match(r"(\d{4}-\d{2}-\d{2})", pack)
    if not m:
        print("::warning::パック名が日付で始まらないので、セールは調べなかった")
        return bw.pick_topic(topics, None, reel=reel)
    res = check(datetime.date.fromisoformat(m.group(1)))
    for err in res["errors"]:
        print("::warning::" + err)
    for sk in res["skipped"]:
        print(f"::warning::載せなかったセール: {sk['store']}「{sk['name']}」（{sk['reason']}）")
    t = sale_topic(res, reel=reel)
    if t:
        print("セールがあるので、セールのお知らせを作る: " + "／".join(s["name"] for s in res["sales"]))
        return t
    print("セールは無い（ネタ帳から作る）" + ("。ただし確認できなかった所がある" if res["errors"] else ""))
    topic = bw.pick_topic(topics, None, reel=reel)
    if res["errors"] or res["skipped"]:
        topic = dict(topic, _セール=res)
    return topic


def save_sale_note(pack_dir, topic):
    """パックに sale.json を置く（朝会への報告に「セールのお知らせにした／載せなかった／確認できなかった」を出すため）。
    🔴 公開リポジトリに載る＝店・整えたセール名・期間・決まった文言だけ（カレンダーの題名そのものは入れない）。"""
    res = topic.get("_セール")
    if not res:
        return
    keep = {"post_date": res["post_date"],
            "sales": [{k: s[k] for k in ("store", "name", "period", "when")} for s in res["sales"]],
            "skipped": res.get("skipped", []),
            "errors": res.get("errors", [])}
    pathlib.Path(pack_dir, "sale.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    day = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today()
    print(json.dumps(check(day), ensure_ascii=False, indent=1))
