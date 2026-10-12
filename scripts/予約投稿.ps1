# 予約投稿（のみさんが事前に承認したパックだけを、決めた時刻に投稿する）
#   使い方: powershell -ExecutionPolicy Bypass -File scripts\予約投稿.ps1 -Pack 2026-10-13-reel -Note "感謝祭の先行スタート"
#   タスクスケジューラの1回きりのタスクから conhost --headless で呼ぶ（2026-10-12 プライム感謝祭で新設）。
#   結果＝リポジトリ直下 _予約投稿結果.txt の1行目（[成功]/[失敗]）＋ OneDrive の _朝会への報告.txt を [投稿済み]/[失敗] に書き替える。
#   🔴 承認の無いパックをここに渡さない（予約するのは のみさんがチャットでOKした物だけ）。
param([Parameter(Mandatory = $true)][string]$Pack, [string]$Note = "", [switch]$DryRun)
# -DryRun＝投稿せずコンテナ作成までで止める試運転（報告ファイル・posted.json は書かない）

$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
$report = Join-Path $env:USERPROFILE "OneDrive\デスクトップ\ai記事自動\インスタ\自動投稿\_朝会への報告.txt"
$resultFile = Join-Path $repo "_予約投稿結果.txt"
$utf8 = New-Object System.Text.UTF8Encoding $true
$now = { Get-Date -Format "yyyy-MM-dd HH:mm" }

function Result($kind, $msg) {
  [System.IO.File]::WriteAllText($resultFile, ("[{0}] {1} {2} {3}`r`n" -f $kind, (& $now), $Pack, $msg), $utf8)
}
function Report($first) {
  if ($DryRun) { return }
  $body = "$first`r`n予約投稿（のみさんが10/12に承認済み）: $Note`r`n書いた時刻: $(& $now)（予約投稿.ps1）`r`n"
  [System.IO.File]::WriteAllText($report, $body, $utf8)
}

try {
  Set-Location $repo
  git pull -q --ff-only 2>$null | Out-Null
  if (-not (Test-Path (Join-Path $repo "docs\media\$Pack\1.mp4"))) { throw "パックが無い: docs/media/$Pack" }
  if (Test-Path (Join-Path $repo "docs\media\$Pack\posted.json")) { throw "既に投稿済みの印がある（二重投稿しない）" }

  $before = Get-Date
  $dr = if ($DryRun) { "true" } else { "false" }
  gh workflow run publish -R teruhikonomizu-ops/unizom-insta -f "pack=$Pack" -f "dry_run=$dr" 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "投稿ワークフローを起動できなかった（gh の認証かネットを確認）" }

  # 起動した実行を探す（最大2分）
  $runId = $null
  for ($i = 0; $i -lt 12 -and -not $runId; $i++) {
    Start-Sleep -Seconds 10
    $runs = gh run list -R teruhikonomizu-ops/unizom-insta --workflow publish --limit 3 --json databaseId,createdAt | ConvertFrom-Json
    $runId = ($runs | Where-Object { [datetime]$_.createdAt -gt $before.ToUniversalTime().AddSeconds(-30) } | Select-Object -First 1).databaseId
  }
  if (-not $runId) { throw "起動した実行が見つからない" }

  # 終わるまで待つ（最大15分＝90回×10秒。終わらなければ諦めて失敗にする）
  $status = ""; $concl = ""
  for ($i = 0; $i -lt 90; $i++) {
    $r = gh run view $runId -R teruhikonomizu-ops/unizom-insta --json status,conclusion | ConvertFrom-Json
    $status = $r.status; $concl = $r.conclusion
    if ($status -eq "completed") { break }
    Start-Sleep -Seconds 10
  }
  if ($status -ne "completed") { throw "15分たっても投稿が終わらない（run $runId）" }
  if ($concl -ne "success") { throw "投稿ワークフローが失敗した（run $runId・$concl）" }

  if ($DryRun) { Result "成功" "試運転OK（投稿はしていない・run $runId）"; exit 0 }
  $log = gh run view $runId -R teruhikonomizu-ops/unizom-insta --log 2>$null
  $url = ($log | Select-String -Pattern "公開URL: (\S+)" | Select-Object -Last 1).Matches.Groups[1].Value
  $mid = ($log | Select-String -Pattern "media_id=(\d+)" | Select-Object -Last 1).Matches.Groups[1].Value
  if (-not $url) { throw "投稿は成功扱いだが公開URLがログに無い（run $runId）＝Instagramで目視が要る" }

  $posted = @{ pack = $Pack; posts = @(@{ media_id = $mid; permalink = $url; posted_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"); run_id = $runId }) } | ConvertTo-Json -Depth 4
  [System.IO.File]::WriteAllText((Join-Path $repo "docs\media\$Pack\posted.json"), $posted, (New-Object System.Text.UTF8Encoding $false))
  git add "docs/media/$Pack/posted.json" 2>$null | Out-Null
  git -c user.name="unizom-insta bot" -c user.email="teruhiko.nomizu@gmail.com" commit -q -m "予約投稿した: $Pack $url" 2>$null | Out-Null
  git pull -q --rebase --autostash 2>$null | Out-Null
  git push -q 2>$null | Out-Null

  Report ("[投稿済み] {0} {1} → 投稿 {2} {3}" -f (Get-Date -Format "yyyy-MM-dd"), $Pack, (& $now), $url)
  Result "成功" "投稿した $url (run $runId)"
  exit 0
}
catch {
  $msg = $_.Exception.Message
  Report ("[失敗] {0} {1} 予約投稿できなかった: {2}（PCのClaudeに「インスタ出して」で手で出せる）" -f (Get-Date -Format "yyyy-MM-dd"), $Pack, $msg)
  Result "失敗" $msg
  exit 1
}
