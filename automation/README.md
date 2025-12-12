# Plan A Automation - Setup & Usage Guide

## 🎯 Overview

This guide covers the implementation of **Plan A: Lightweight Python Automation** for:
1. **Delta Apply Orchestrator**: Monitors folder for Excel files and triggers full ingestion + apply pipeline
2. **Status Change Reporter**: Queries OpenProject for status changes and sends email reports

---

## 📁 Files Created

### Core Scripts
- **`automation/orchestrator/delta_apply_orchestrator.py`** - File watcher + scheduler for delta apply
- **`automation/reporter/status_change_reporter.py`** - Status change tracker with email notifications

### Configuration
- **`automation/config.env.example`** - Environment variable template

### Scheduler Setup
- **`automation/setup/setup_windows_scheduler.ps1`** - Windows Task Scheduler setup (PowerShell)
- **`automation/setup/setup_linux_cron.sh`** - Linux cron job setup (Bash)

---

## ⚙️ Setup Instructions

### Step 1: Install Dependencies

```bash
# Install new automation dependencies
pip install watchdog schedule

# Or install all requirements
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables

```bash
# Copy the example config
cp automation/config.env.example automation/config.env

# Edit with your settings
# On Windows: notepad automation/config.env
# On Linux: nano automation/config.env
```

**Key Configuration:**
- `EXCEL_WATCH_DIR`: Path to folder containing Excel files (can be OneDrive local sync folder)
- `STATUS_REPORT_EMAILS`: Comma-separated email addresses
- `SMTP_USER` / `SMTP_PASSWORD`: Email credentials (use app password for Gmail)
- `DELTA_APPLY_MODE`: `online` (real updates) or `dry-run` (test mode)

**For Gmail:**
1. Enable 2FA on your Google account
2. Generate an App Password: [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Use the app password in `SMTP_PASSWORD`

### Step 3: Set Up Scheduling

#### Windows (PowerShell - Run as Administrator)

```powershell 
# Navigate to repo
cd "C:\Users\bmalaraju\Documents\WP-OP Agent\JIRA-Agent"

# Run setup script
.\automation\setup\setup_windows_scheduler.ps1
```

This creates 3 scheduled tasks:
- **WPR_DeltaApply_Orchestrator**: Runs at system startup (continuous)
- **WPR_StatusReport_Morning**: Daily at 8:00 AM
- **WPR_StatusReport_Evening**: Daily at 5:00 PM

#### Linux (Bash)

```bash
# Navigate to repo
cd /path/to/JIRA-Agent
```

### Adjust Report Time Windows

Edit `automation/reporter/status_change_reporter.py`:
```python
# Line ~250: Morning report
changes = fetch_status_changes(hours_back=12)  # Change to 24 for full day

# Line ~273: Evening report
changes = fetch_status_changes(hours_back=6)   # Change to 8 for longer window
```

### Filter Different Projects

Edit `automation_config.env`:
```bash
# Change filter keyword
NOKIA_PROJECT_FILTER=ericsson  # Or any other keyword
```

---

## ✅ Verification Checklist

- [ ] Dependencies installed (`watchdog`, `schedule`)
- [ ] Environment variables configured in `.env`
- [ ] SMTP credentials tested
- [ ] Excel watch directory created and accessible
- [ ] Scheduled tasks/cron jobs created
- [ ] Orchestrator running (check task manager/ps)
- [ ] Logs directory created
- [ ] Test manual delta apply trigger
- [ ] Test manual status report
- [ ] Verify email delivery

---

## 📧 Support

For issues or questions:
1. Check logs in `logs/` directory
2. Verify configuration in `.env` / `automation_config.env`
3. Test individual components manually before troubleshooting automation

---

## 🔄 Next Steps

After successful setup:
1. Place a test Excel file in watch directory → Verify delta apply triggers
2. Wait for scheduled status reports → Verify emails received
3. Monitor logs for first few days → Adjust settings as needed
4. Set up email filtering/folders for status reports
5. Configure additional alerts if needed (e.g., Slack integration)
