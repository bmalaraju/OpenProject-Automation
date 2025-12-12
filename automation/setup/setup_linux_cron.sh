#!/bin/bash
# ============================================================================
# Linux Cron Setup Script
# ============================================================================
# Run this script to set up cron jobs for automation

SCRIPT_DIR="/path/to/JIRA-Agent"  # UPDATE THIS PATH
PYTHON_EXE="python3"  # Or full path: /usr/bin/python3
LOG_DIR="$SCRIPT_DIR/automation/logs"

# Create logs directory
mkdir -p "$LOG_DIR"

echo "Setting up cron jobs for automation..."
echo "========================================"

# Create temporary crontab file
CRON_FILE=$(mktemp)

# Get existing crontab (if any)
crontab -l > "$CRON_FILE" 2>/dev/null || true

# Remove any existing WPR automation entries
sed -i '/# WPR Automation/d' "$CRON_FILE"
sed -i '/delta_apply_orchestrator/d' "$CRON_FILE"
sed -i '/status_change_reporter/d' "$CRON_FILE"

# Add new cron jobs
cat >> "$CRON_FILE" << 'EOF'

# ============================================================================
# WPR Automation - Plan A
# ============================================================================

# Delta Apply Orchestrator (run at system startup and keep alive)
@reboot cd SCRIPT_DIR && PYTHON_EXE automation/orchestrator/delta_apply_orchestrator.py >> LOG_DIR/orchestrator.log 2>&1

# Morning Status Report (8:00 AM daily)
0 8 * * * cd SCRIPT_DIR && PYTHON_EXE automation/reporter/status_change_reporter.py morning >> LOG_DIR/status_morning.log 2>&1

# Evening Status Report (5:00 PM daily)
0 17 * * * cd SCRIPT_DIR && PYTHON_EXE automation/reporter/status_change_reporter.py evening >> LOG_DIR/status_evening.log 2>&1

EOF

# Replace placeholders
sed -i "s|SCRIPT_DIR|$SCRIPT_DIR|g" "$CRON_FILE"
sed -i "s|PYTHON_EXE|$PYTHON_EXE|g" "$CRON_FILE"
sed -i "s|LOG_DIR|$LOG_DIR|g" "$CRON_FILE"

# Install the new crontab
crontab "$CRON_FILE"

# Clean up
rm "$CRON_FILE"

echo ""
echo "✅ Cron jobs installed successfully!"
echo ""
echo "Installed jobs:"
echo "  1. Delta Apply Orchestrator - Runs at system startup (continuous)"
echo "  2. Morning Status Report    - Runs daily at 8:00 AM"
echo "  3. Evening Status Report    - Runs daily at 5:00 PM"
echo ""
echo "To manage cron jobs:"
echo "  • View:   crontab -l"
echo "  • Edit:   crontab -e"
echo "  • Remove: crontab -r"
echo ""
echo "Logs will be written to: $LOG_DIR"
echo ""
echo "Starting orchestrator now..."
cd "$SCRIPT_DIR" && nohup "$PYTHON_EXE" automation/orchestrator/delta_apply_orchestrator.py >> "$LOG_DIR/orchestrator.log" 2>&1 &
echo "✅ Orchestrator started (PID: $!)"
