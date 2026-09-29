# タスク「インスタ_火曜リール_夜の制作」を登録する（毎週月曜21:00・2026-09-29）。何度実行しても同じ状態になる。
# 窓を出さない形（conhost --headless）・PCが寝ていたら起こす（WakeToRun）・上限2時間。
# 21時に電源が切れていた週は後から走らせない（StartWhenAvailable=false）＝翌朝の従来リールに任せる。
$ErrorActionPreference = "Stop"
$script = Join-Path $env:USERPROFILE "repos\unizom-insta\scripts\スタジオ_火曜リール.ps1"
$arg = "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$script`""
$action   = New-ScheduledTaskAction -Execute "conhost.exe" -Argument $arg
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "21:00"
$settings = New-ScheduledTaskSettingsSet -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$settings.StartWhenAvailable = $false
Register-ScheduledTask -TaskName "インスタ_火曜リール_夜の制作" -Action $action -Trigger $trigger -Settings $settings `
  -Description "火曜リールの高品質版（リール・スタジオ）を前夜に作る。正＝repos\unizom-insta\studio\README.md" -Force | Out-Null
Get-ScheduledTask -TaskName "インスタ_火曜リール_夜の制作" | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
