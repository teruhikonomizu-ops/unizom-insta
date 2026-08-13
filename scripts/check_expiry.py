"""トークンの失効が近くないか見張る。近ければ「わざと失敗」して失敗メールを飛ばす。

Instagramの長期アクセストークンは**60日で切れる**。切れても誰も気づかない
（投稿しようとした時に初めて分かる）ので、先回りして知らせる。
ラジオの radio-watchdog と同じ思想＝静か＝正常、メールが来たら本物。

使い方: python3 scripts/check_expiry.py [発行日を書いたファイル]
終了コード 0 = まだ余裕 / 1 = 取り直しが要る
"""

import datetime
import pathlib
import sys

LIFETIME_DAYS = 60      # Metaの長期トークンの寿命
WARN_DAYS = 14          # これを切ったら警告（取り直す時間の余裕を見て2週間）


def read_issued(path):
    # utf-8-sig: メモ帳やPowerShellで編集されるとBOMが付く。それで落ちると
    # 「トークンは無事なのに見張りが誤報を出す」ことになるので、最初から吸収する。
    for line in pathlib.Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            return datetime.date.fromisoformat(line)
        except ValueError:
            raise SystemExit(
                f"発行日の書き方が違う: 「{line}」\n"
                f"YYYY-MM-DD の形で1行目に書くこと（例: 2026-08-13）\n"
                f"ファイル: {path}"
            ) from None
    raise SystemExit(f"発行日が書かれていない: {path}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "token_issued.txt"
    issued = read_issued(path)
    # UTCで動かす（GitHub Actionsの既定）。1日ズレても2週間の余裕の中なので実害はない。
    today = datetime.datetime.now(datetime.timezone.utc).date()
    expires = issued + datetime.timedelta(days=LIFETIME_DAYS)
    left = (expires - today).days

    print(f"トークン発行日: {issued}")
    print(f"失効予定日:     {expires}")
    print(f"残り:           {left}日")

    if left <= 0:
        print("::error::トークンは失効している。取り直してIG_ACCESS_TOKENを更新すること")
        print("手順は token_issued.txt の中に書いてある")
        return 1
    if left <= WARN_DAYS:
        print(f"::error::トークンの残りが{left}日。取り直し時期（手順は token_issued.txt）")
        return 1
    print("まだ余裕がある")
    return 0


if __name__ == "__main__":
    sys.exit(main())
