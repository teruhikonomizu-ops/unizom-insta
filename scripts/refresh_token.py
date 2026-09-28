"""Instagramの長期トークンを延長し、新しい値をGitHub Secretsへ書き戻す。

60日で切れるトークンを毎週延長して、Metaでの取り直し（手作業）を無くすためのもの
（2026-09-28 のみさん承認）。token-refresh.yml から毎週呼ばれる。

流れ:
  1. graph.instagram.com/refresh_access_token で延長する
     （Metaの条件: 発行から24時間以上たった、まだ有効なトークンだけ受け付ける）
  2. 新しいトークンで疎通確認（me）が通ることを確かめてから
  3. gh secret set IG_ACCESS_TOKEN で書き戻す
     （GH_TOKEN＝このリポジトリの Secrets 書き込みだけを許した合鍵 SECRETS_WRITER_TOKEN）
  4. token_issued.txt の日付を「新しい失効日の60日前」に直す（token-check の残り日数の起点）

トークンの値はログにも画面にも一切出さない。gh へは標準入力で渡す（コマンドラインに載せない）。

使い方:
  python3 scripts/refresh_token.py token_issued.txt          # 延長して書き戻す
  python3 scripts/refresh_token.py token_issued.txt --check  # 延長せず、合鍵と今のトークンが使えるかだけ見る
終了コード 0 = 成功 / 1 = 失敗（GitHubの失敗メールが飛ぶ）
"""

import datetime
import os
import pathlib
import re
import subprocess
import sys

import ig_api

LIFETIME_DAYS = 60   # check_expiry.py と同じ。Metaの長期トークンの寿命
SECRET_NAME = "IG_ACCESS_TOKEN"
WRITE_TEST_NAME = "TOKEN_REFRESH_WRITE_TEST"   # --check で書き込み権限を試す専用の名前（中身は日時だけ）
DATE_LINE = re.compile(r"^\d{4}-\d{2}-\d{2}\s*$")


def gh(args, stdin_text=None, secret=""):
    """gh を呼ぶ。失敗メッセージにトークンが混ざっても伏せてから出す。"""
    res = subprocess.run(
        ["gh", *args],
        input=stdin_text,
        text=True,
        capture_output=True,
        timeout=60,
    )
    out = ig_api._scrub(res.stdout + res.stderr, secret).strip()
    return res.returncode, out


def check_writer():
    """合鍵（GH_TOKEN）でこのリポジトリの Secrets 一覧が読めるか。書き込み権限の目安。"""
    if not os.environ.get("GH_TOKEN", "").strip():
        print("::error::SECRETS_WRITER_TOKEN が登録されていない（GitHub Secretsを確認）")
        return False
    code, out = gh(["secret", "list"])
    if code != 0 or SECRET_NAME not in out:
        print(f"::error::合鍵で Secrets を読めない。権限（Secrets: Read and write）と対象リポジトリを確認: {out}")
        return False
    print("合鍵: このリポジトリの Secrets を読めた")
    return True


def write_issued(path, issued):
    """1行目の日付だけ差し替える。説明のコメント行は残す。"""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for i, line in enumerate(lines):
        if DATE_LINE.match(line):
            lines[i] = issued.isoformat()
            break
    else:
        lines.insert(0, issued.isoformat())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check_only = "--check" in sys.argv
    path = pathlib.Path(args[0] if args else "token_issued.txt")

    if not check_writer():
        return 1

    if check_only:
        try:
            who = ig_api.me()
        except ig_api.IgError as e:
            print(f"::error::今のトークンで疎通できない: {e}")
            return 1
        print(f"今のトークン: OK @{who.get('username')}")
        # 書き込み権限の確認。本物（IG_ACCESS_TOKEN）には触らず、試験用の名前に日時だけ書く。
        # 消さずに残す＝次の確認で上書きされるだけ（削除の手間と危険を増やさない）。
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        code, out = gh(["secret", "set", WRITE_TEST_NAME], stdin_text=f"checked {stamp}")
        if code != 0:
            print(f"::error::合鍵で Secrets に書き込めない。権限が Read-only になっていないか確認: {out}")
            return 1
        print(f"合鍵: 書き込みもできた（試験用 {WRITE_TEST_NAME} に日時を書いた）")
        print("確認のみ（延長はしていない）")
        return 0

    # 1. 延長
    try:
        got = ig_api.refresh_token()
    except ig_api.IgError as e:
        print(f"::error::延長に失敗: {e}")
        print("発行から24時間たっていない、またはトークンが既に失効している可能性。"
              "失効していたら token_issued.txt の手順で取り直す")
        return 1
    new = (got.get("access_token") or "").strip()
    expires_in = int(got.get("expires_in") or 0)
    if not new:
        print("::error::延長の返答に access_token が無い")
        return 1

    # 2. 書き戻す前に、新しいトークンが本当に使えるか確かめる
    os.environ["IG_ACCESS_TOKEN"] = new
    try:
        who = ig_api.me()
    except ig_api.IgError as e:
        print(f"::error::延長後のトークンで疎通できない（書き戻さずに止めた）: {e}")
        return 1
    print(f"延長後のトークン: OK @{who.get('username')}")

    # 3. 書き戻す（標準入力で渡す＝コマンドラインやログに値が出ない）
    code, out = gh(["secret", "set", SECRET_NAME], stdin_text=new, secret=new)
    if code != 0:
        print(f"::error::{SECRET_NAME} の書き戻しに失敗（Secretsは前の値のまま）: {out}")
        return 1
    print(f"{SECRET_NAME} を書き戻した")

    # 4. 発行日を直す。失効日から逆算するので、Metaの返した寿命がそのまま反映される
    now = datetime.datetime.now(datetime.timezone.utc)
    if expires_in > 0:
        expires = (now + datetime.timedelta(seconds=expires_in)).date()
    else:
        print("::warning::返答に expires_in が無い。寿命60日として扱う")
        expires = now.date() + datetime.timedelta(days=LIFETIME_DAYS)
    issued = expires - datetime.timedelta(days=LIFETIME_DAYS)
    write_issued(path, issued)
    print(f"失効予定日: {expires}（{path} を {issued} に更新）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
