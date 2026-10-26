# 火曜リールの「高品質版」を前夜に作る（リール・スタジオ・2026-09-29 のみさん指示）
#
#   月曜 15:00  タスク インスタ_火曜リール_夜の制作  → 次の火曜の <日付>-reel を studio_reel.py で作る
#               （2026-10-27〜。~~月曜21:00~~は夜スリープに止められたため日中へ移した＝タスク登録_スタジオ.ps1 の冒頭）
#   火曜 07:30  タスク インスタ_火曜のリール        → パックが用意済みなら通知だけ／無ければ従来の自動リールで作る
#
# 🔴 無人のClaudeには文章（台本・場面コード）を書かせ、見本コマを「見る」だけ。Higgsfieldは生成3機能だけ許可
#    （動画1本・画像2枚まで＝1本84クレジット上限・2026-10-18 のみさん決定で Seedance 2.5 に。~~60~~は2.0の頃）。権限バイパスは使わない。
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
  # コマンドが見つからない時に前の終了コードを使い回さない
  $global:LASTEXITCODE = -1
  try { & $cmd 2>&1 | ForEach-Object { "$_" } }
  finally { $ErrorActionPreference = $old }
}
# git は必ずこれで呼ぶ。🔴 "Stop" のまま `git … 2>&1` にすると、Gitの無害な注意書き
#（"LF will be replaced by CRLF" 等）が例外になってスクリプトが止まる（2026-10-05 21:12・完成済みの動画がpushされずに残った）。
# 合否は $LASTEXITCODE で見る。戻り値＝終了コード。
function GitRun {
  $gargs = $args
  $out = @(RunAll { git @gargs })
  $code = $LASTEXITCODE
  if ($code -ne 0) { $out | Select-Object -Last 3 | ForEach-Object { Note ("  git: " + $_) } }
  return $code
}
function StudioFail($msg) {
  $line = "[失敗] {0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $msg
  [System.IO.File]::WriteAllText((Join-Path $repo "_スタジオ結果.txt"), $line + "`r`n", (New-Object System.Text.UTF8Encoding $true))
}

try {
  Set-Location $repo
  $env:PYTHONIOENCODING = "utf-8"
  $null = GitRun fetch --quiet origin
  $null = GitRun merge --ff-only origin/main

  # パック名＝次の火曜（火曜に動いた時はその日）。🔴 ~~実行日の翌日~~だと、PCが寝て火曜の朝にずれ込んだ時に
  #「水曜」の名前になり、火曜07:30の従来リールと同じネタで2本できた（2026-10-27・10-28-reel）
  $today = (Get-Date).Date
  $pack = $today.AddDays(([int][DayOfWeek]::Tuesday - [int]$today.DayOfWeek + 7) % 7).ToString("yyyy-MM-dd") + "-reel"
  # その日のパックが既にある（感謝祭など のみさんと手で作った物）＝作らずに見送る。失敗ではないので[成功]と書く
  #（2026-10-12 総点検: 「既にある」で[失敗]になり、翌週まで名札が赤＝誤報になっていた）
  if (Test-Path (Join-Path $repo "docs\media\$pack")) {
    Note "その日のパックは既にある（$pack）＝高品質版は作らない"
    $line = "[成功] {0} {1} は既に用意済みのため制作を見送り（クレジットは使っていない）" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $pack
    [System.IO.File]::WriteAllText((Join-Path $repo "_スタジオ結果.txt"), $line + "`r`n", (New-Object System.Text.UTF8Encoding $true))
    exit 0
  }
  Note "高品質版を作る: $pack"
  $out = @(RunAll { python (Join-Path $repo "scripts\studio_reel.py") $pack })
  $code = $LASTEXITCODE
  $out | Select-Object -Last 15 | ForEach-Object { Note ("  " + $_) }
  if ($code -eq 0) {
    $null = GitRun add "docs/media/$pack" topics.json stock/index.json studio/history.json
    $msg = "投稿パックを作った: $pack（高品質版・リール・スタジオ。まだ投稿していない。承認待ち）"
    $null = GitRun -c user.name="unizom-insta bot" -c user.email="teruhiko.nomizu@gmail.com" commit -q -m $msg
    # 夜のあいだにクラウド側のコミット（トークン延長など）が入っていても push できるよう、直前に取り込む
    # 衝突したら途中状態で残さず元に戻す（残すと翌週以降の取り込みが毎回失敗する）
    if ((GitRun pull --rebase --autostash -q) -ne 0) { $null = GitRun rebase --abort }
    if ((GitRun push -q) -eq 0) {
      Note "pushした（火曜07:30の通知で のみさんへ届く）"
    }
    else {
      # 動画は手元にある。火曜07:30のスクリプトが手元の先行分を push し直す
      Note "push に失敗した（パックは手元にある。火曜07:30に送り直す）"
      StudioFail "$pack は作れたが GitHub への push に失敗した（火曜07:30に送り直す）"
      exit 1
    }
  }
  else {
    Note "高品質版は作れなかった。火曜07:30に従来の自動リールで作る（理由は _スタジオ結果.txt）"
  }
}
catch {
  Note ("失敗: " + $_.Exception.Message)
  StudioFail ("スタジオの起動スクリプトが途中で止まった: " + $_.Exception.Message)
  exit 1
}
