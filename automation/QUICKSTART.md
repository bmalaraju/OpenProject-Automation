# Quick Start Guide - Status Change Reporter

## 🚀 Running Status Change Reports

Now that you've configured your Office 365 SMTP settings, here's how to run the status change reports.

---

## Step 1: Set Email Recipients

Edit your `.env` file and add the email addresses that should receive reports:

```bash
# Add this line to .env
STATUS_REPORT_EMAILS=recipient1@example.com,recipient2@example.com,recipient3@example.com
```

**Example**:
```bash
STATUS_REPORT_EMAILS=bmalaraju@infinite.com,manager@infinite.com
```

---

## Step 2: Manual Test (Recommended First)

Before setting up automation, test the script manually:

### Morning Report Test (12-hour window)

```bash
# From repo root directory
python automation/reporter/status_change_reporter.py morning
```

### Evening Report Test (6-hour window)

```bash
python automation/reporter/status_change_reporter.py evening
```

**What to expect:**
- Script will query OpenProject for all Nokia projects
- Fetch activities for each work package
- Filter status changes in the time window
- Send HTML email to configured recipients
- Log output to `automation/logs/status_reporter_YYYYMMDD.log`

---

## Step 3: Check the Logs

After running, check the log file:

```bash
# View latest log
cat automation/logs/status_reporter_*.log

# Or on Windows
type automation\logs\status_reporter_*.log
```

Look for:
- ✅ "Found X Nokia projects"
- ✅ "Checked X work packages, found Y status changes"
- ✅ "Email sent successfully to [...]"

---

## Step 4: Set Up Automated Scheduling

Once manual testing works, set up automated daily reports.

### Windows (Task Scheduler)

**Run as Administrator**:

```powershell
cd "C:\Users\bmalaraju\Documents\WP-OP Agent\JIRA-Agent"
.\automation\setup\setup_windows_scheduler.ps1
```

This creates:
- **Morning Report**: Runs daily at 8:00 AM
- **Evening Report**: Runs daily at 5:00 PM

### Linux (Cron)

```bash
cd /path/to/JIRA-Agent

# Edit script to set correct path
nano automation/setup/setup_linux_cron.sh
# Update: SCRIPT_DIR="/path/to/JIRA-Agent"

# Run setup
chmod +x automation/setup/setup_linux_cron.sh
./automation/setup/setup_linux_cron.sh
```

---

## Managing Scheduled Tasks

### Windows

```powershell
# View scheduled tasks
Get-ScheduledTask -TaskName 'WPR_StatusReport_*'

# Run morning report manually
Start-ScheduledTask -TaskName 'WPR_StatusReport_Morning'

# Run evening report manually  
Start-ScheduledTask -TaskName 'WPR_StatusReport_Evening'

# Check last run time
Get-ScheduledTask -TaskName 'WPR_StatusReport_Morning' | Get-ScheduledTaskInfo

# Stop a task
Stop-ScheduledTask -TaskName 'WPR_StatusReport_Morning'

# Remove tasks
Unregister-ScheduledTask -TaskName 'WPR_StatusReport_*' -Confirm:$false
```

### Linux

```bash
# View cron jobs
crontab -l

# Edit cron jobs
crontab -e

# View logs
tail -f automation/logs/status_morning.log
tail -f automation/logs/status_evening.log
```

---

## Troubleshooting

### ❌ Email Not Sending

1. **Check SMTP credentials**:
   ```bash
   # Verify .env has correct settings
   grep SMTP_ .env
   ```

2. **Test SMTP connection**:
   ```python
   python -c "import smtplib; s=smtplib.SMTP('smtp.office365.com', 587); s.starttls(); s.login('bmalaraju@infinite.com', 'BroWar@199720261'); print('✅ Connection successful'); s.quit()"
   ```

3. **Check firewall** - Ensure port 587 is not blocked

4. **Check Office 365 settings** - Verify SMTP is enabled for your account

### ❌ No Status Changes Found

This is normal if:
- No status changes occurred in the time window
- Nokia projects have no recent activity
- Work packages haven't been updated

To verify it's working:
- Check logs for "Found X Nokia projects"
- Confirm projects are being queried
- Manually change a work package status in OpenProject and re-run

### ❌ "No Nokia projects found"

1. **Check product registry**:
   ```bash
   cat config/product_project_registry.json | grep -i nokia
   ```

2. **Verify filter**:
   ```bash
   # In .env, check:
   NOKIA_PROJECT_FILTER=nokia
   ```

3. **Update filter** if your projects use different naming:
   ```bash
   # Example for different naming
   NOKIA_PROJECT_FILTER=nok
   ```

---

## Customization

### Change Report Times

Edit the scheduled time in setup script **before** running it:

**Windows** (`automation/setup/setup_windows_scheduler.ps1`):
```powershell
# Line ~57 - Morning report
$Trigger2 = New-ScheduledTaskTrigger -Daily -At 9:00AM  # Change to 9 AM

# Line ~83 - Evening report
$Trigger3 = New-ScheduledTaskTrigger -Daily -At 6:00PM  # Change to 6 PM
```

**Linux** (`automation/setup/setup_linux_cron.sh`):
```bash
# Morning at 9 AM instead of 8 AM
0 9 * * * cd SCRIPT_DIR && PYTHON_EXE automation/reporter/status_change_reporter.py morning

# Evening at 6 PM instead of 5 PM  
0 18 * * * cd SCRIPT_DIR && PYTHON_EXE automation/reporter/status_change_reporter.py evening
```

### Change Time Windows

Edit `automation/reporter/status_change_reporter.py`:

```python
# Line ~250 - Morning report (default 12 hours)
changes = fetch_status_changes(hours_back=24)  # Change to 24 hours

# Line ~273 - Evening report (default 6 hours)
changes = fetch_status_changes(hours_back=12)  # Change to 12 hours
```

### Filter Different Projects

Edit `.env`:
```bash
# Filter for different project names
NOKIA_PROJECT_FILTER=customer_name
```

---

## Email Report Format

Recipients will receive an HTML email with:

📊 **Summary Section**:
- Report period (last X hours)
- Generation timestamp
- Total status changes count

📋 **Status Change Table**:
| WP Order ID | Work Package | Project | From Status | To Status | Changed At |
|-------------|-------------|---------|-------------|-----------|------------|
| WPO00123456 | Feature XYZ | Nokia-5G | In Progress | Completed | 2025-12-04 10:00:00 UTC |

**Styling**:
- Professional green header
- Alternating row colors
- Hover effects
- Color-coded status transitions

---

## Next Steps

1. ✅ **Test manually** - Run `python automation/reporter/status_change_reporter.py morning`
2. ✅ **Verify email received** - Check your inbox
3. ✅ **Set up scheduling** - Run the setup script for your OS
4. ✅ **Monitor for a week** - Check logs daily to ensure it's working
5. ✅ **Adjust settings** - Fine-tune time windows and filters as needed

---

## Summary Commands

```bash
# Test morning report
python automation/reporter/status_change_reporter.py morning

# Test evening report  
python automation/reporter/status_change_reporter.py evening

# View log
cat automation/logs/status_reporter_*.log

# Set up automation (Windows)
.\automation\setup\setup_windows_scheduler.ps1

# Set up automation (Linux)
./automation/setup/setup_linux_cron.sh
```

---

**Ready to test?** Run the morning report and check your email! 📧
