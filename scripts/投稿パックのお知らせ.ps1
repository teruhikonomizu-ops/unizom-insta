# 投稿パックを作って Chatwork で のみさんに知らせる（週2本・2026-09-11から）。
#
#   火曜 07:30  タスク インスタ_火曜のリール      → -Reel 付き → <日付>-reel   （動画1本）
#   金曜 07:30  タスク インスタ_金曜のお知らせ    → 引数なし   → <日付>-weekly （カルーセル/写真）
#
# PCは 07:00 に自動起動する（タスク スマホ遠隔_PC自動起動）ので、その後に動く。
# ※旧名 金曜のお知らせ.ps1（2026-09-11に改名。タスクの登録先も直した）
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
param([switch]$Reel)
$ErrorActionPreference = "Stop"
$repo = Join-Path $env:USERPROFILE "repos\unizom-insta"
$log  = Join-Path $repo "_お知らせログ.txt"
# 結果を1行で書き出すファイル（2026-09-22追加）。conhost --headless 越しだとタスクの
# LastTaskResult は中身が失敗しても 0 になるので、合否はこのファイルの1行目で見る。
# notify_chatwork.py もこれを読んで、失敗の理由をChatworkの通知に載せる。
$result = Join-Path $repo "_最終結果.txt"

# Pythonの出力(UTF-8)をCP932として読むとログが文字化けする（2026-09-22まで化けていた）
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Result($mark, $msg) {
  $line = "[{0}] {1} {2}" -f $mark, (Get-Date -Format "yyyy-MM-dd HH:mm"), $msg
  [System.IO.File]::WriteAllText($result, $line + "`r`n", (New-Object System.Text.UTF8Encoding $true))
}

# 外部コマンドを「エラー出力が出ても打ち切らずに」最後まで走らせ、全行を文字列で返す。
# 🔴 $ErrorActionPreference="Stop" のまま `2>&1` を付けると、Pythonがエラー出力に1行書いた瞬間に
#    例外になって catch へ飛び、明細（どの禁止語で落ちたか）がログに残らない（2026-09-22に実際に起きた）。
#    合否は例外ではなく $LASTEXITCODE で見る。
function RunAll([scriptblock]$cmd) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try { & $cmd 2>&1 | ForEach-Object { "$_" } }
  finally { $ErrorActionPreference = $old }
}

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
  $suffix = "weekly"; $extra = @()
  if ($Reel) { $suffix = "reel"; $extra = @("--reel") }
  $exists = Get-ChildItem (Join-Path $repo "docs\media") -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "$today-*" } | Select-Object -First 1
  if ($exists) {
    Note "その日のパックは用意済み($($exists.Name))。作らずに通知だけする。"
    Result "成功" "その日のパックは用意済み($($exists.Name))"
  }
  else {
    Note "パックを作る: $today-$suffix"
    $out = @(RunAll { python (Join-Path $repo "scripts\build_weekly.py") "$today-$suffix" @extra })
    $code = $LASTEXITCODE
    $out | ForEach-Object { Note ("  " + $_) }
    if ($code -ne 0) {
      # 理由＝禁止語のNG行があればそれ、無ければ出力の最後の意味のある行
      $why = @($out | Where-Object { $_ -match '^\s*NG ' } | ForEach-Object { $_.Trim() } | Select-Object -Unique)
      if (-not $why) { $why = @($out | Where-Object { $_.Trim() } | Select-Object -Last 2) }
      Result "失敗" ("$today-$suffix を作れなかった: " + ($why -join " ／ "))
      Note "パック作成に失敗した。通知だけ送って終わる（黙って消えないように）。"
    }
    else {
      # 3) 出来たものを push（のみさんが見られるように）
      # ⚠ コミットメッセージは1行にする。複数行にすると、バッククォート継続と
      #    組み合わさってPowerShellのパーサが壊れる（2026-08-13に実際に起きた）。
      $msg = "投稿パックを作った: $today-$suffix（自動生成。まだ投稿していない。承認待ち）"
      git add -A
      git -c user.name="unizom-insta bot" -c user.email="teruhiko.nomizu@gmail.com" commit -q -m $msg 2>&1 | Out-Null
      git push -q 2>&1 | Out-Null
      Note "pushした"
      Result "成功" "$today-$suffix を作った（未投稿・承認待ち）"
    }
  }

  # 4) Chatworkで知らせる
  $out = @(RunAll { python (Join-Path $repo "scripts\notify_chatwork.py") })
  Note ("通知: " + ($out -join " / "))
}
catch {
  Note ("失敗: " + $_.Exception.Message)
  Result "失敗" ("お知らせスクリプトが途中で止まった: " + $_.Exception.Message)
  # 失敗してもChatworkには知らせる（静かに死なせない）
  try { RunAll { python (Join-Path $repo "scripts\notify_chatwork.py") } | Out-Null } catch {}
  exit 1
}
