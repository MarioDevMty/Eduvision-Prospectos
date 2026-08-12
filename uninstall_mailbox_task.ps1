$TaskName = "Eduvision Mailbox Sync"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "TASK REMOVED: $TaskName"
}
else {
    Write-Host "La tarea no existe: $TaskName"
}
