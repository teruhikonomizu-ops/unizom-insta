# 毎週金曜の朝、クラウドが作った投稿パックを取り込んで Chatwork で知らせる。
#
# タスクスケジューラから呼ばれる（タスク名: インスタ_金曜のお知らせ）。
# クラウド側は 07:00 JST にパックを作るので、こちらは 07:30 に動かす。
#
# 🔴 Claude Code は使わない。ただのgit pullとPythonなので、
#    無人実行でも権限バイパス（--dangerously-skip-permissions）が要らない。
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

  # クラウドが作ったパックを取り込む（ローカルの変更は触らない）
  git fetch --quiet origin 2>&1 | Out-Null
  git merge --ff-only origin/main 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Note "早送りできなかった（ローカルに未コミットの変更があるかも）。通知は続行する。"
  }

  $env:PYTHONUTF8 = "1"
  $env:PYTHONIOENCODING = "utf-8"
  $out = & python (Join-Path $repo "scripts\notify_chatwork.py") 2>&1
  Note ("通知: " + ($out -join " / "))
}
catch {
  Note ("失敗: " + $_.Exception.Message)
  exit 1
}
