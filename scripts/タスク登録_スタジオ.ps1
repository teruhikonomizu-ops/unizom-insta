# タスク「インスタ_火曜リール_夜の制作」を登録する（毎週月曜15:00・2026-09-29 新設／2026-10-27 21:00→15:00）。何度実行しても同じ状態になる。
# 🔴 2026-10-27 のみさん指示で日中へ移した（名前の「夜」は台帳・写しとの対応のため据え置き）。
#    PCは19:00以降・無操作30分で夜スリープする。21:00はタスクがPCを起こしても、同じ21:00の夜スリープの見回りが
#    すぐ寝かせていた（10/26 21:00:02・制作が「Claudeの作業中」と見なされる前）。日中なら必ず起きている。
#    上限2時間を使い切っても17:00に終わる＝19:00の夜スリープとぶつからない。
# 窓を出さない形（conhost --headless）・WakeToRun（念のため）・上限2時間。
# 15時に電源が切れていた週は後から走らせない（StartWhenAvailable=false）＝火曜朝の従来リールに任せる。
$ErrorActionPreference = "Stop"
$script = Join-Path $env:USERPROFILE "repos\unizom-insta\scripts\スタジオ_火曜リール.ps1"
$arg = "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$script`""
$action   = New-ScheduledTaskAction -Execute "conhost.exe" -Argument $arg
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "15:00"
$settings = New-ScheduledTaskSettingsSet -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$settings.StartWhenAvailable = $false
Register-ScheduledTask -TaskName "インスタ_火曜リール_夜の制作" -Action $action -Trigger $trigger -Settings $settings `
  -Description "火曜リールの高品質版（リール・スタジオ）を前日の月曜15:00に作る。正＝repos\unizom-insta\studio\README.md" -Force | Out-Null
Get-ScheduledTask -TaskName "インスタ_火曜リール_夜の制作" | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
