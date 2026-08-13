"""金曜の朝、その週の投稿パックができたことを Chatwork で のみさんに知らせる。

このPCで動く（クラウドではない）。理由：
  Chatworkのトークンは執事zetaが Google Secret Manager 経由で
  `~/unizom-chatwork/keys.json` に持っている。それを読めば済むので、
  **公開リポジトリのSecretsへトークンを置かずに済む**。

🔴 安全のかたち（執事zetaと同じ）
  - 送信先は「のみさん⇔BOTの1対1ダイレクトトーク」**1つに固定**。
  - room_id を引数に取る関数を作らない＝**業者ルームへ送るコードパスが存在しない**。
  - 1対1が0個または2個以上見つかったら、推測せずに中止する。

ついでに、リポジトリに写した辞書が OneDrive の master とズレていないかも見る。
写しは放っておけば必ず食い違うので、週に一度ここで気づけるようにしている。

使い方: python3 scripts/notify_chatwork.py [--dry-run]
"""

import argparse
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
KEYS = pathlib.Path.home() / "unizom-chatwork" / "keys.json"
API = "https://api.chatwork.com/v2"

DESKTOP = pathlib.Path.home() / "OneDrive" / "デスクトップ"
DICT_PAIRS = [
    (DESKTOP / "ai記事自動" / "インスタ" / "brand" / "ng_dictionary.json",
     REPO / "brand" / "ng_dictionary.json"),
    (DESKTOP / "_tools" / "画像QA" / "禁止語辞書.json",
     REPO / "brand" / "禁止語辞書.json"),
]


def token():
    if not KEYS.is_file():
        raise SystemExit(
            f"鍵が無い: {KEYS}\n"
            "先に _tools/chatwork-butler/restore-keys.ps1 を実行して復元すること"
        )
    tok = json.loads(KEYS.read_text(encoding="utf-8-sig")).get("api_token", "").strip()
    if not tok:
        raise SystemExit("keys.json に api_token が無い")
    return tok


def api(method, path, params=None):
    tok = token()
    url = f"{API}{path}"
    data = urllib.parse.urlencode(params or {}).encode() if method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"X-ChatWorkToken": tok})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = res.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace").replace(tok, "<REDACTED>")
        raise SystemExit(f"Chatwork API エラー HTTP {e.code}: {detail}")


def direct_room():
    """のみさんとの1対1トークを1つだけ見つける。曖昧なら送らない。"""
    rooms = api("GET", "/rooms") or []
    directs = [r for r in rooms if r.get("type") == "direct"]
    if not directs:
        raise SystemExit("1対1トークが見つからない。執事zetaのコンタクト承認を確認すること")
    if len(directs) > 1:
        names = "／".join(str(r.get("name", "?")) for r in directs)
        raise SystemExit(f"1対1トークが複数ある（{names}）。誤送信を避けるため中止した")
    return directs[0]


def post(text):
    """1対1トークへ投稿する。**送信先を引数に取らない**（業者ルームへ送る道を作らない）。"""
    room = direct_room()
    api("POST", f"/rooms/{room['room_id']}/messages", {"body": text})
    return room.get("name", "?")


def dict_drift():
    """リポジトリの写しが master とズレていないか。"""
    drift = []
    for master, copy in DICT_PAIRS:
        if not master.is_file() or not copy.is_file():
            drift.append(f"{master.name}（ファイルが見つからない）")
            continue
        m = json.loads(master.read_text(encoding="utf-8-sig"))
        c = json.loads(copy.read_text(encoding="utf-8-sig"))
        c = {k: v for k, v in c.items() if not k.startswith("_コピー元")
             and not k.startswith("_写した日") and k != "_注意"}
        if json.dumps(m, sort_keys=True, ensure_ascii=False) != \
           json.dumps(c, sort_keys=True, ensure_ascii=False):
            drift.append(master.name)
    return drift


def this_week_pack():
    """今日（金曜）の日付のパックを探す。"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    for d in sorted((REPO / "docs" / "media").iterdir()):
        if d.is_dir() and d.name.startswith(today):
            return d
    return None


def build_message():
    pack = this_week_pack()
    drift = dict_drift()

    if pack is None:
        body = (
            "[info][title]インスタ（今週）[/title]"
            "今週分の投稿がまだできていません。\n"
            "ネタ帳が尽きたか、安全チェックで止まった可能性があります。\n"
            "Claudeに「インスタの今週どうなってる？」と聞いてください。[/info]"
        )
    else:
        caption = (pack / "caption.txt").read_text(encoding="utf-8-sig").strip()
        head = caption.split("\n")[0][:60]
        media = sorted(p.name for p in pack.iterdir()
                       if p.suffix.lower() in (".jpg", ".mp4"))
        body = (
            "[info][title]インスタ（今週の投稿ができました）[/title]"
            f"{head}…\n\n"
            f"中身: {'／'.join(media)}\n"
            f"見る: https://github.com/teruhikonomizu-ops/unizom-insta/tree/main/docs/media/{pack.name}\n\n"
            "出してよければ、スマホのClaudeアプリ（NOMIZU-スマホ用）で\n"
            "「インスタ出して」と言ってください。\n"
            "何もしなければ投稿されません。[/info]"
        )

    if drift:
        body += (
            "\n[info][title]⚠ 辞書のズレ[/title]"
            f"{'／'.join(drift)} が OneDrive の正典と食い違っています。\n"
            "Claudeに「インスタの辞書を同期して」と言ってください。[/info]"
        )
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="送らずに本文だけ出す")
    args = ap.parse_args()

    body = build_message()
    if args.dry_run:
        print("--- 送る本文（実際には送っていない）---")
        print(body)
        return 0
    name = post(body)
    print(f"送った先: {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
