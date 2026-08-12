$ErrorActionPreference = "Stop"

$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$SyncScript = Join-Path $ProjectPath "sync_mailbox.py"
$TaskName = "Eduvision Mailbox Sync"

if (-not (Test-Path $PythonPath)) {
    throw "No se encontró el Python del entorno virtual: $PythonPath"
}

if (-not (Test-Path $SyncScript)) {
    throw "No se encontró sync_mailbox.py: $SyncScript"
}

$Arguments = "`"$SyncScript`" --apply --limit 500 --user-id 1 --source SCHEDULER"

$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $Arguments `
    -WorkingDirectory $ProjectPath

$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 10)

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Sincroniza rebotes y respuestas de Eduvision cada 10 minutos." `
    -Force | Out-Null

Write-Host "TASK OK: $TaskName"
Write-Host "Frecuencia: cada 10 minutos"
Write-Host "Proyecto: $ProjectPath"
