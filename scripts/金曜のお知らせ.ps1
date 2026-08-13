# 毎週金曜の朝、投稿パックを作って Chatwork で のみさんに知らせる。
#
# タスク名: インスタ_金曜のお知らせ（毎週金曜 07:30）
# PCは 07:00 に自動起動する（タスク スマホ遠隔_PC自動起動）ので、その後に動く。
#
# 🔴 なぜクラウドでなくPCで作るのか（2026-08-13の判断）
#   クラウドで書かせるには CLAUDE_CODE_OAUTH_TOKEN が要るが、
#   何度入れ直しても 401（invalid）で通らなかった。
#   PCのClaude Codeは認証済みで、同じコードが通しテストに成功している。
#   Chatwork通知もどのみちPCで動かすので、PC側に寄せた方が部品が減って壊れにくい。
#   ※クラウド側の weekly.yml は残してある（cronは止めてある）。トークンが直れば戻せる。
#
# 🔴 Claude Code の権限バイパス（--dangerously-skip-permissions）は使わない。
#   build_weekly.py は claude を「標準入力→標準出力」の文章書きとしてだけ呼び、
#   ファイル操作やコマンド実行をさせないため。
$ErrorActionPreference = "Stop"
$repo = Join-Path $env:USERPROFILE "repos\unizom-insta"
$log  = Join-Path $repo "_お知らせログ.txt"

function Note($msg) {
  $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Write-Host $line
  Add-Content -Path $log -Value $line -Encoding utf8
}

try {
  Set-Location $repo
  $env:PYTHONUTF8 = "1"
  $env:PYTHONIOENCODING = "utf-8"

  # 1) 最新を取り込む（他の場所で直した分を拾う）
  git fetch --quiet origin 2>&1 | Out-Null
  git merge --ff-only origin/main 2>&1 | Out-Null

  # 2) その日のパックが既にあるなら作らない
  #    人が先に用意した回（例: 2026-08-21-bag-teaser）を週次が上書きしないため
  $today = Get-Date -Format "yyyy-MM-dd"
  $exists = Get-ChildItem (Join-Path $repo "docs\media") -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "$today-*" } | Select-Object -First 1
  if ($exists) {
    Note "その日のパックは用意済み($($exists.Name))。作らずに通知だけする。"
  }
  else {
    Note "パックを作る: $today-weekly"
    $out = & python (Join-Path $repo "scripts\build_weekly.py") "$today-weekly" 2>&1
    $out | ForEach-Object { Note ("  " + $_) }
    if ($LASTEXITCODE -ne 0) {
      Note "パック作成に失敗した。通知だけ送って終わる（黙って消えないように）。"
    }
    else {
      # 3) 出来たものを push（のみさんが見られるように）
      # ⚠ コミットメッセージは1行にする。複数行にすると、バッククォート継続と
      #    組み合わさってPowerShellのパーサが壊れる（2026-08-13に実際に起きた）。
      $msg = "今週の投稿パックを作った: $today-weekly（自動生成。まだ投稿していない。承認待ち）"
      git add -A
      git -c user.name="unizom-insta bot" -c user.email="teruhiko.nomizu@gmail.com" commit -q -m $msg 2>&1 | Out-Null
      git push -q 2>&1 | Out-Null
      Note "pushした"
    }
  }

  # 4) Chatworkで知らせる
  $out = & python (Join-Path $repo "scripts\notify_chatwork.py") 2>&1
  Note ("通知: " + ($out -join " / "))
}
catch {
  Note ("失敗: " + $_.Exception.Message)
  # 失敗してもChatworkには知らせる（静かに死なせない）
  try { & python (Join-Path $repo "scripts\notify_chatwork.py") 2>&1 | Out-Null } catch {}
  exit 1
}
