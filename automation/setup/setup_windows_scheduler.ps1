# ============================================================================
# Windows Task Scheduler Setup Script
# ============================================================================
# Run this PowerShell script as Administrator to set up scheduled tasks

$ScriptDir = "C:\Users\bmalaraju\Documents\WP-OP Agent\JIRA-Agent"
$PythonExe = "python"  # Or full path: "C:\Python311\python.exe"
$LogDir = "$ScriptDir\automation\logs"

# Create logs directory if it doesn't exist
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "Setting up Windows Task Scheduler for automation..." -ForegroundColor Green

# ============================================================================
# Task 1: Delta Apply Orchestrator (Continuous)
# ============================================================================
Write-Host "`n1. Delta Apply Orchestrator (file watcher + scheduler)" -ForegroundColor Cyan

$Action1 = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "$ScriptDir\automation\orchestrator\delta_apply_orchestrator.py" `
    -WorkingDirectory $ScriptDir

$Trigger1 = New-ScheduledTaskTrigger -AtStartup

$Settings1 = New-ScheduledTaskSettingsSet `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -RestartCount 3 `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -StartWhenAvailable

$Principal1 = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName "WPR_DeltaApply_Orchestrator" `
    -Description "Monitors folder for Excel files and triggers delta apply" `
    -Action $Action1 `
    -Trigger $Trigger1 `
    -Settings $Settings1 `
    -Principal $Principal1 `
    -Force

Write-Host "✅ Created task: WPR_DeltaApply_Orchestrator (runs at startup)" -ForegroundColor Green

# ============================================================================
# Task 2: Morning Status Report (8 AM daily)
# ============================================================================
Write-Host "`n2. Morning Status Report" -ForegroundColor Cyan

$Action2 = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "$ScriptDir\automation\reporter\status_change_reporter.py morning" `
    -WorkingDirectory $ScriptDir

$Trigger2 = New-ScheduledTaskTrigger -Daily -At 8:00AM

$Settings2 = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "WPR_StatusReport_Morning" `
    -Description "Morning status change report for Nokia projects" `
    -Action $Action2 `
    -Trigger $Trigger2 `
    -Settings $Settings2 `
    -Force

Write-Host "✅ Created task: WPR_StatusReport_Morning (daily at 8:00 AM)" -ForegroundColor Green

# ============================================================================
# Task 3: Evening Status Report (5 PM daily)
# ============================================================================
Write-Host "`n3. Evening Status Report" -ForegroundColor Cyan

$Action3 = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "$ScriptDir\automation\reporter\status_change_reporter.py evening" `
    -WorkingDirectory $ScriptDir

$Trigger3 = New-ScheduledTaskTrigger -Daily -At 5:00PM

$Settings3 = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "WPR_StatusReport_Evening" `
    -Description "Evening status change report for Nokia projects" `
    -Action $Action3 `
    -Trigger $Trigger3 `
    -Settings $Settings3 `
    -Force

Write-Host "✅ Created task: WPR_StatusReport_Evening (daily at 5:00 PM)" -ForegroundColor Green

# ============================================================================
# Summary
# ============================================================================
Write-Host "`n" -NoNewline
Write-Host "=" * 80 -ForegroundColor Yellow
Write-Host "Scheduled Tasks Created Successfully!" -ForegroundColor Green
Write-Host "=" * 80 -ForegroundColor Yellow

Write-Host "`nCreated tasks:" -ForegroundColor Cyan
Write-Host "  1. WPR_DeltaApply_Orchestrator  - Runs at system startup (continuous)"
Write-Host "  2. WPR_StatusReport_Morning     - Runs daily at 8:00 AM"
Write-Host "  3. WPR_StatusReport_Evening     - Runs daily at 5:00 PM"

Write-Host "`nTo manage these tasks:" -ForegroundColor Cyan
Write-Host "  • View:   Get-ScheduledTask -TaskName 'WPR_*'"
Write-Host "  • Start:  Start-ScheduledTask -TaskName 'WPR_DeltaApply_Orchestrator'"
Write-Host "  • Stop:   Stop-ScheduledTask -TaskName 'WPR_DeltaApply_Orchestrator'"
Write-Host "  • Remove: Unregister-ScheduledTask -TaskName 'WPR_*' -Confirm:`$false"

Write-Host "`nLogs will be written to: $LogDir" -ForegroundColor Cyan

# Start the orchestrator immediately
Write-Host "`nStarting Delta Apply Orchestrator now..." -ForegroundColor Yellow
Start-ScheduledTask -TaskName "WPR_DeltaApply_Orchestrator"

Write-Host "`n✅ Setup complete!" -ForegroundColor Green
