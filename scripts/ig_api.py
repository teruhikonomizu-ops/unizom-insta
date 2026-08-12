"""Instagram Content Publishing API の薄いラッパー。

「Instagramログイン」方式（graph.instagram.com）を使う。Facebookページは不要。
トークンは環境変数からのみ読み、ログには絶対に出さない。
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GRAPH = "https://graph.instagram.com"
VERSION = "v23.0"


class IgError(RuntimeError):
    """APIがエラーを返した。メッセージにトークンは含めない。"""


def _token():
    tok = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not tok:
        raise IgError("IG_ACCESS_TOKEN が設定されていない（GitHub Secretsを確認）")
    return tok


def _user_id():
    uid = os.environ.get("IG_USER_ID", "").strip()
    if not uid:
        raise IgError("IG_USER_ID が設定されていない（GitHub Secretsを確認）")
    return uid


def _scrub(text, token):
    """例外メッセージやログにトークンが混ざるのを防ぐ最後の砦。"""
    return text.replace(token, "<REDACTED>") if token else text


def _call(method, path, params):
    """graph.instagram.com を叩いてJSONを返す。失敗時は IgError。"""
    tok = _token()
    params = dict(params or {})
    params["access_token"] = tok
    url = f"{GRAPH}/{VERSION}/{path.lstrip('/')}"

    if method == "GET":
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params))
    else:
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode(params).encode("utf-8"), method="POST"
        )

    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise IgError(f"HTTP {e.code}: {_scrub(body, tok)}") from None
    except urllib.error.URLError as e:
        raise IgError(f"接続失敗: {e.reason}") from None


def me():
    """トークンの持ち主を返す。疎通確認に使う。"""
    return _call("GET", "me", {"fields": "id,username,account_type"})


def refresh_token():
    """長期トークン(60日)を延長する。app secret は不要。

    返り値の access_token は呼び出し側で GitHub Secrets に入れ直すこと。
    ここでは値を出力しない（expires_in だけ返す）。
    """
    tok = _token()
    url = f"{GRAPH}/refresh_access_token?" + urllib.parse.urlencode(
        {"grant_type": "ig_refresh_token", "access_token": tok}
    )
    try:
        with urllib.request.urlopen(url, timeout=60) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise IgError(f"HTTP {e.code}: {_scrub(body, tok)}") from None


def create_container(**fields):
    """メディアコンテナを作る。image_url / video_url は公開HTTPSであること。"""
    return _call("POST", f"{_user_id()}/media", fields)["id"]


def container_status(container_id):
    got = _call("GET", container_id, {"fields": "status_code,status"})
    return got.get("status_code", "UNKNOWN"), got.get("status", "")


def wait_ready(container_id, timeout_sec=600, interval_sec=10):
    """動画は変換に時間がかかる。FINISHED になるまで待つ。"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        code, detail = container_status(container_id)
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise IgError(f"コンテナの変換に失敗: {detail}")
        time.sleep(interval_sec)
    raise IgError(f"コンテナが {timeout_sec}秒 以内に FINISHED にならなかった")


def publish(container_id):
    """コンテナを公開する。返り値は投稿のメディアID。"""
    return _call("POST", f"{_user_id()}/media_publish", {"creation_id": container_id})["id"]


def permalink(media_id):
    return _call("GET", media_id, {"fields": "permalink"}).get("permalink", "")


def publish_limit():
    """24時間の投稿枠の残りを返す（上限100）。"""
    got = _call("GET", f"{_user_id()}/content_publishing_limit", {"fields": "quota_usage"})
    data = got.get("data") or [{}]
    return data[0].get("quota_usage", 0)


if __name__ == "__main__":
    # 疎通確認用。トークンは一切表示しない。
    try:
        who = me()
    except IgError as e:
        print(f"NG: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: @{who.get('username')} (id={who.get('id')}, type={who.get('account_type')})")
    print(f"直近24時間の投稿数: {publish_limit()} / 100")
