# 火曜リールの「高品質版」を前夜に作る（リール・スタジオ・2026-09-29 のみさん指示）
#
#   月曜 21:00  タスク インスタ_火曜リール_夜の制作  → 翌日（火曜）の <日付>-reel を studio_reel.py で作る
#   火曜 07:30  タスク インスタ_火曜のリール        → パックが用意済みなら通知だけ／無ければ従来の自動リールで作る
#
# 🔴 無人のClaudeには文章（台本・場面コード）を書かせ、見本コマを「見る」だけ。Higgsfieldは生成3機能だけ許可
#    （動画1本・画像2枚まで＝1本60クレジット上限・のみさん決定）。権限バイパスは使わない。
# 結果は _スタジオ結果.txt の1行目（[成功]/[失敗]）。火曜朝の通知に失敗の理由が添えられる。
$ErrorActionPreference = "Stop"
$repo = Join-Path $env:USERPROFILE "repos\unizom-insta"
$log  = Join-Path $repo "_お知らせログ.txt"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Note($msg) {
  $line = "{0}  [スタジオ] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Write-Host $line
  Add-Content -Path $log -Value $line -Encoding utf8
}
function RunAll([scriptblock]$cmd) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try { & $cmd 2>&1 | ForEach-Object { "$_" } }
  finally { $ErrorActionPreference = $old }
}

try {
  Set-Location $repo
  $env:PYTHONIOENCODING = "utf-8"
  git fetch --quiet origin 2>&1 | Out-Null
  git merge --ff-only origin/main 2>&1 | Out-Null

  $pack = (Get-Date).AddDays(1).ToString("yyyy-MM-dd") + "-reel"
  Note "高品質版を作る: $pack"
  $out = @(RunAll { python (Join-Path $repo "scripts\studio_reel.py") $pack })
  $code = $LASTEXITCODE
  $out | Select-Object -Last 15 | ForEach-Object { Note ("  " + $_) }
  if ($code -eq 0) {
    git add "docs/media/$pack" topics.json stock/index.json studio/history.json
    $msg = "投稿パックを作った: $pack（高品質版・リール・スタジオ。まだ投稿していない。承認待ち）"
    git -c user.name="unizom-insta bot" -c user.email="teruhiko.nomizu@gmail.com" commit -q -m $msg 2>&1 | Out-Null
    git push -q 2>&1 | Out-Null
    Note "pushした（火曜07:30の通知で のみさんへ届く）"
  }
  else {
    Note "高品質版は作れなかった。火曜07:30に従来の自動リールで作る（理由は _スタジオ結果.txt）"
  }
}
catch {
  Note ("失敗: " + $_.Exception.Message)
  $line = "[失敗] {0} スタジオの起動スクリプトが途中で止まった: {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $_.Exception.Message
  [System.IO.File]::WriteAllText((Join-Path $repo "_スタジオ結果.txt"), $line + "`r`n", (New-Object System.Text.UTF8Encoding $true))
  exit 1
}
