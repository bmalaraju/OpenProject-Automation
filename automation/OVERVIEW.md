# Automation Folder Structure

This folder contains the **Plan A: Lightweight Python Automation** implementation for WPR Agent.

## 📁 Folder Structure

```
automation/
├── README.md                          # This file - setup & usage guide
├── config.env.example                 # Environment configuration template
├── orchestrator/
│   └── delta_apply_orchestrator.py    # File watcher + scheduler
├── reporter/
│   └── status_change_reporter.py      # Status change tracker
├── setup/
│   ├── setup_windows_scheduler.ps1    # Windows Task Scheduler setup
│   └── setup_linux_cron.sh            # Linux cron setup
└── logs/                               # Auto-created - all logs go here
    ├── delta_apply_orchestrator_*.log
    ├── status_reporter_*.log
    ├── delta_apply_report_*.json
    ├── delta_apply_summary_*.txt
    └── processed_files.txt
```

## 🚀 Quick Start

1. **Install dependencies**:
   ```bash
   pip install -r ../requirements.txt
   ```

2. **Configure**:
   ```bash
   cp config.env.example config.env
   # Edit config.env with your settings
   ```

3. **Setup automation** (Windows):
   ```powershell
   .\setup\setup_windows_scheduler.ps1
   ```

   Or (Linux):
   ```bash
   chmod +x setup/setup_linux_cron.sh
   ./setup/setup setup_linux_cron.sh
   ```

4. **Test manually**:
   ```bash
   # Test delta apply
   python orchestrator/delta_apply_orchestrator.py manual path/to/test.xlsx
   
   # Test status report
   python reporter/status_change_reporter.py morning
   ```

See [README.md](README.md) for complete documentation.

## 📋 What It Does

### Delta Apply Orchestrator
- Monitors folder for new Excel files
- Triggers on file arrival OR at 7 AM daily  
- Runs full pipeline: Ingest → Compile → Validate → Apply
- Logs all activity to `automation/logs/`

### Status Change Reporter
- Queries OpenProject for Nokia project status changes
- Morning report (8 AM): Last 12 hours
- Evening report (5 PM): Last 6 hours
- Sends HTML email via SMTP
- Runs independently (no prerequisites)

## 🔧 Configuration Options

Edit `config.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `EXCEL_WATCH_DIR` | `./excel_files` | Folder to monitor for Excel files |
| `DELTA_APPLY_SCHEDULED_TIME` | `07:00` | Daily scheduled time (24hr format) |
| `DELTA_APPLY_MODE` | `online` | `online` or `dry-run` |
| `STATUS_REPORT_EMAILS` | (empty) | Comma-separated email addresses |
| `SMTP_SERVER` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | (empty) | SMTP username |
| `SMTP_PASSWORD` | (empty) | SMTP password (use app password for Gmail) |
| `LOG_DIR` | `automation/logs` | Log output directory |

## 📊 Monitoring

All logs are in `automation/logs/`:

```bash
# View orchestrator activity
tail -f automation/logs/delta_apply_orchestrator_*.log

# View status reports
cat automation/logs/status_reporter_*.log

# Check delta apply results
cat automation/logs/delta_apply_report_*.json | jq .
```

## 🛠️ Troubleshooting

### Orchestrator not running
```powershell
# Windows
Get-ScheduledTask -TaskName 'WPR_*'
Start-ScheduledTask -TaskName 'WPR_DeltaApply_Orchestrator'

# Linux
ps aux | grep delta_apply_orchestrator
```

### Email not sending
1. Check SMTP credentials in `config.env`
2. For Gmail: Use app password with 2FA enabled
3. Test connection: `python reporter/status_change_reporter.py morning`

### Check logs
```bash
# Latest orchestrator log
cat automation/logs/delta_apply_orchestrator_$(date +%Y%m%d).log

# Latest status report log
cat automation/logs/status_reporter_$(date +%Y%m%d).log
```

---

For detailed documentation, see [README.md](README.md)
