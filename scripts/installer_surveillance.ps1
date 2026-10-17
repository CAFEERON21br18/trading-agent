# ============================================================
# AlphaSignal - installer_surveillance.ps1 (TODO 34)
# Cree la tache \AlphaSignal\surveillance : scripts\surveiller_dashboard.py
# toutes les 5 minutes. Le script NE lance PAS la tache : elle demarre
# a son prochain declenchement.
#
# A lancer dans PowerShell ouvert EN ADMINISTRATEUR :
#   powershell -ExecutionPolicy Bypass -File scripts\installer_surveillance.ps1
# Relancable sans risque : la tache existante est remplacee.
# Desinstaller : Unregister-ScheduledTask -TaskPath "\AlphaSignal\" -TaskName "surveillance" -Confirm:$false
# ============================================================

$ErrorActionPreference = "Stop"

$Root   = "C:\Users\ruben\Documents\prog.cc\trading-agent"
$Py     = "$Root\.venv\Scripts\python.exe"
$Logs   = "$Root\logs"
$Folder = "\AlphaSignal\"
$Script = "scripts\surveiller_dashboard.py"

if (-not (Test-Path $Py)) { throw "Python introuvable : $Py" }
if (-not (Test-Path "$Root\$Script")) { throw "Script introuvable : $Script" }
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

# Meme principal que les cycles (install_tasks_windows.ps1) : S4U, sans mot de passe stocke
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited

# -X utf8 -u : comme les cycles ; sortie ajoutee a logs\task_surveillance.log
$Action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c $Py -X utf8 -u $Script >> $Logs\task_surveillance.log 2>&1" -WorkingDirectory $Root

$Minuit  = (Get-Date).Date
$Trigger = New-ScheduledTaskTrigger -Once -At $Minuit -RepetitionInterval (New-TimeSpan -Minutes 5)

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

Register-ScheduledTask -TaskPath $Folder -TaskName "surveillance" `
    -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null

Write-Host "OK  surveillance (toutes les 5 min) - non lancee ; prochain passage :"
Get-ScheduledTask -TaskPath $Folder -TaskName "surveillance" |
    Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime | Format-Table -AutoSize
