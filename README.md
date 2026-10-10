# unizom-insta

@unizom.jp（unizom／Amazon表示 NOMIZU）のInstagram投稿を、**週2本（火曜＝リール・金曜＝カルーセル/写真）このPCが無人で作り、のみさんの承認後にAPIで投稿する**仕組み。
（2026-09-11 に週1→週2へ。リールは `scripts/build_reel.py` が素材写真から ffmpeg で組み立てる）
姉妹プロジェクト `ai-radio`（ラジオ2番組）と同じ構成。

> 🚧 **構築中**（2026-08-13 着手）。今はトークンの疎通確認まで。

## 仕組み（決定済みの設計）

```
【のみさんが居る時】Higgsfieldで画像/動画、SunoでBGMを作って stock/ に貯金
        ↓
【毎週金曜 07:00】ネタ選定 → キャプション執筆 → 素材と合成 → 安全チェック → 通知
【毎週金曜 08:00】停止フラグが無ければ投稿
```

- **猶予つき自動**：投稿30〜60分前にスマホへ通知。止めなければ出る
- **素材プール方式**：Higgsfield/Sunoは無人実行できない（ブラウザ認証のみでAPIキーが無い）ため、素材は先に貯めておく
- **ネタは実際の記録から**：AIに「今日やったこと」を想像させない

設計の詳細は OneDrive 側の `ai記事自動/インスタ/自動投稿/README.md` が正典。

## 投稿済み素材の片付け（`cleanup`・2026-10-11〜）

GitHub Pages の公開サイトは **1GB まで**（GitHub公式）。投稿した画像・動画は Instagram 側に写しがあるので、
`cleanup`（毎週月曜 03:30 JST・クラウドで動く）が **投稿から14日たったパックの画像・動画だけ**を消す。
投稿済みかどうかは publish の実行ログ（「投稿した: media_id=…」）で確かめ、パックに `posted.json` を残す。
文字ファイル（caption.txt 等）とフォルダは残る。**未投稿・テスト用のパックと `stock/` には触らない。**
消した物は git の履歴から戻せる。結果は `_片付け結果.txt`（1行目 `[成功]`／`[警戒]`／`[失敗]`）。
公開サイト700MB・リポジトリ900MBを超えると `[警戒]`。
🔴 **投稿済みのパックのフォルダを使い回さない**（次の投稿は新しい名前で作る）。使い回すと、前の投稿から14日で新しい素材まで消える。本体と規則は `scripts/cleanup_media.py` の冒頭が正。

## 必要なSecrets

| 名前 | 中身 | 備考 |
|---|---|---|
| `IG_ACCESS_TOKEN` | Instagram長期アクセストークン | 60日で失効する。`token-refresh`（毎週月曜06:17 JST）が `scripts/refresh_token.py` で自動延長して書き戻す（2026-09-28〜） |
| `SECRETS_WRITER_TOKEN` | fine-grained PAT `unizom-insta-token-refresh` | 上の書き戻し専用の合鍵。このリポジトリの **Secrets 読み書きだけ**・無期限。のみさんが作成（Claudeは値を扱わない） |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code の認証 | `weekly.yml`（クラウドでのパック作り）用。401で通らずPC側へ寄せたため現在は未使用 |
| `TOKEN_REFRESH_WRITE_TEST` | 日時だけ | 秘密ではない。`token-refresh` の確認モード（check_only）が書き込み権限を試す専用の名前。消さなくてよい |

延長が何週も失敗して残り14日を切ると `token-check` が失敗メールを出す。その時だけ `token_issued.txt` の手順で手で取り直す。

`IG_USER_ID`（`17841451592190940`）は秘密情報ではない（公開アカウントの識別子）ので、
Secretsには入れずワークフローに直書きしている。Secretsに入れる物を減らすほど取り違えが減るため。

App ID は `2159294371304005`（Metaアプリ名 `unizom-sns-auto` / Instagramアプリ名 `unizom-sns-auto-IG`）。
Facebookページは使わない（「Instagramログイン」方式）。自分のアカウントへの投稿なのでApp Reviewも不要。

## 動作確認

Actionsタブ → `token-check` → Run workflow。
`OK: @unizom.jp (id=..., type=BUSINESS)` と出れば繋がっている。
トークンの値はログに一切出さない設計（`_scrub()` で最後に伏せる）。
