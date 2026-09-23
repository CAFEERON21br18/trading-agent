# ============================================================
# AlphaSignal - install_tasks_windows.ps1
# Equivalent Windows de install_launchd.sh : cree les 7 taches
# planifiees dans le dossier \AlphaSignal\ du Planificateur.
#
# A lancer dans PowerShell ouvert EN ADMINISTRATEUR.
# Relançable sans risque : chaque tâche existante est remplacée.
# ============================================================

$ErrorActionPreference = "Stop"

$Root   = "C:\Users\ruben\Documents\prog.cc\trading-agent"
$Py     = "$Root\.venv\Scripts\python.exe"
$Logs   = "$Root\logs"
$Folder = "\AlphaSignal\"

if (-not (Test-Path $Py)) { throw "Python introuvable : $Py" }
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

# S4U : la tâche tourne que ta session soit ouverte ou non,
# sans mot de passe stocké et sans fenêtre qui s'ouvre toutes les 5 min.
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited

function New-CycleAction([string]$Script, [string]$Nom) {
    # -X utf8 : les logs contiennent des emojis ; sans ce mode, la
    #           redirection vers un fichier fait planter Python sous Windows.
    # -u      : sortie non bufferisée, le log s'écrit au fil de l'eau.
    # >> ... 2>&1 : TOUT est gardé, y compris une trace Python si le
    #           cycle plante (ex. LockAcquisitionError).
    $arg = "/c $Py -X utf8 -u $Script >> $Logs\task_$Nom.log 2>&1"
    New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arg -WorkingDirectory $Root
}

function New-CycleSettings([int]$MaxMinutes, [switch]$Continu) {
    $p = @{
        StartWhenAvailable         = $true        # rattrape un cycle manqué (PC éteint)
        MultipleInstances          = "IgnoreNew"  # jamais deux instances du même cycle
        AllowStartIfOnBatteries    = $true
        DontStopIfGoingOnBatteries = $true
    }
    if ($Continu) {
        $p.ExecutionTimeLimit = [TimeSpan]::Zero               # pas de limite
        $p.RestartCount       = 999                            # relance si crash
        $p.RestartInterval    = New-TimeSpan -Minutes 1
    } else {
        $p.ExecutionTimeLimit = New-TimeSpan -Minutes $MaxMinutes
    }
    New-ScheduledTaskSettingsSet @p
}

$Minuit = (Get-Date).Date

$Taches = @(
    @{ Nom = "critical";  Script = "scripts\cycle_critical.py";  Max = 10
       Triggers = @(New-ScheduledTaskTrigger -Once -At $Minuit -RepetitionInterval (New-TimeSpan -Minutes 5)) }

    @{ Nom = "tactical";  Script = "scripts\cycle_tactical.py";  Max = 30
       Triggers = @(New-ScheduledTaskTrigger -Once -At $Minuit -RepetitionInterval (New-TimeSpan -Minutes 15)) }

    # 0h, 4h, 8h, 12h, 16h, 20h : départ à minuit, puis toutes les 4 h
    @{ Nom = "strategic"; Script = "scripts\cycle_strategic.py"; Max = 45
       Triggers = @(New-ScheduledTaskTrigger -Once -At $Minuit -RepetitionInterval (New-TimeSpan -Hours 4)) }

    @{ Nom = "daily";     Script = "scripts\cycle_daily.py";     Max = 60
       Triggers = @(
           (New-ScheduledTaskTrigger -Daily -At "07:30"),
           (New-ScheduledTaskTrigger -Daily -At "12:00")) }

    @{ Nom = "weekly";    Script = "scripts\cycle_weekly.py";    Max = 60
       Triggers = @(New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "20:00") }

    @{ Nom = "cleanup";   Script = "scripts\cleanup.py";         Max = 30
       Triggers = @(New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "03:00") }

    @{ Nom = "dashboard"; Script = "dashboard\app.py";           Max = 0; Continu = $true
       Triggers = @(New-ScheduledTaskTrigger -AtStartup) }
)

foreach ($t in $Taches) {
    if (-not (Test-Path "$Root\$($t.Script)")) {
        Write-Warning "Script introuvable, tâche ignorée : $($t.Script)"
        continue
    }
    $settings = if ($t.Continu) { New-CycleSettings -Continu } else { New-CycleSettings -MaxMinutes $t.Max }

    Register-ScheduledTask -TaskPath $Folder -TaskName $t.Nom `
        -Action (New-CycleAction $t.Script $t.Nom) `
        -Trigger $t.Triggers -Principal $Principal -Settings $settings -Force | Out-Null

    Write-Host "OK  $($t.Nom)"
}

# Le dashboard démarre au boot ; on le lance aussi tout de suite.
Start-ScheduledTask -TaskPath $Folder -TaskName "dashboard"

Write-Host ""
Write-Host "Prochains passages :"
Get-ScheduledTask -TaskPath $Folder |
    Get-ScheduledTaskInfo |
    Select-Object TaskName, NextRunTime, LastRunTime, LastTaskResult |
    Format-Table -AutoSize
