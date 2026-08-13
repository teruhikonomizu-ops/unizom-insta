# unizom-insta

@unizom.jp（unizom／Amazon表示 NOMIZU）のInstagram投稿を、**毎週金曜にクラウドが無人で作って投稿する**仕組み。
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

## 必要なSecrets

| 名前 | 中身 | 備考 |
|---|---|---|
| `IG_ACCESS_TOKEN` | Instagram長期アクセストークン | **これだけがSecret。** 60日で失効するので `refresh_token()` で自動延長する |

`IG_USER_ID`（`17841451592190940`）は秘密情報ではない（公開アカウントの識別子）ので、
Secretsには入れずワークフローに直書きしている。Secretsに入れる物を減らすほど取り違えが減るため。

App ID は `2159294371304005`（Metaアプリ名 `unizom-sns-auto` / Instagramアプリ名 `unizom-sns-auto-IG`）。
Facebookページは使わない（「Instagramログイン」方式）。自分のアカウントへの投稿なのでApp Reviewも不要。

## 動作確認

Actionsタブ → `token-check` → Run workflow。
`OK: @unizom.jp (id=..., type=BUSINESS)` と出れば繋がっている。
トークンの値はログに一切出さない設計（`_scrub()` で最後に伏せる）。
