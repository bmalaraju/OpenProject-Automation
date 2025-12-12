#!/usr/bin/env python3
"""
Delta Apply Orchestrator - Plan A Implementation

Monitors a folder for new Excel files and triggers delta apply on:
1. File arrival (new .xlsx file detected)
2. Scheduled time (morning)

Architecture:
- Uses watchdog for cross-platform file system monitoring
- Uses schedule library for time-based triggers
- Calls delta_apply_influx.py with --ingest-file flag (full ingestion + apply pipeline)
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
import subprocess

# Third-party imports
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import schedule
except ImportError:
    print("ERROR: Required packages not installed.")
    print("Run: pip install watchdog schedule")
    sys.exit(1)

from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configuration from environment variables
WATCH_DIR = Path(os.getenv("EXCEL_WATCH_DIR", "./excel_files"))
DELTA_APPLY_SCRIPT = Path(os.getenv("DELTA_APPLY_SCRIPT", "src/wpr_agent/cli/delta_apply_influx.py"))
EXCEL_SHEET_NAME = os.getenv("EXCEL_SHEET_NAME", "WP_Overall_Order_Report")
SCHEDULED_TIME = os.getenv("DELTA_APPLY_SCHEDULED_TIME", "07:00")  # 7 AM by default
LOG_DIR = Path(os.getenv("LOG_DIR", "automation/logs"))
APPLY_MODE = os.getenv("DELTA_APPLY_MODE", "online")  # online or dry-run

# Setup logging
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / f"delta_apply_orchestrator_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class ExcelFileHandler(FileSystemEventHandler):
    """
    Handles file system events for Excel files.
    Triggers delta apply when a new .xlsx file is created.
    """
    
    def __init__(self, watch_dir: Path):
        self.watch_dir = watch_dir
        self.processed_files = set()
        # Load already processed files from state file
        self.state_file = LOG_DIR / "processed_files.txt"
        self._load_processed_files()
    
    def _load_processed_files(self):
        """Load list of previously processed files"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    self.processed_files = set(line.strip() for line in f if line.strip())
                logger.info(f"Loaded {len(self.processed_files)} previously processed files")
            except Exception as e:
                logger.warning(f"Failed to load processed files state: {e}")
    
    def _save_processed_file(self, file_path: str):
        """Save processed file to state file"""
        try:
            with open(self.state_file, 'a') as f:
                f.write(f"{file_path}\n")
        except Exception as e:
            logger.warning(f"Failed to save processed file state: {e}")
    
    def on_created(self, event):
        """Called when a new file is created"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # Only process Excel files
        if file_path.suffix.lower() not in ['.xlsx', '.xls']:
            return
        
        # Check if already processed
        abs_path = str(file_path.absolute())
        if abs_path in self.processed_files:
            logger.info(f"File already processed, skipping: {file_path.name}")
            return
        
        logger.info(f"New Excel file detected: {file_path.name}")
        
        # Wait a bit to ensure file is fully written (especially for OneDrive sync)
        time.sleep(5)
        
        # Trigger delta apply
        success = run_delta_apply(file_path, trigger_type="file_arrival")
        
        if success:
            self.processed_files.add(abs_path)
            self._save_processed_file(abs_path)


def run_delta_apply_core(excel_path, batch_id: Optional[str] = None, send_email: bool = True) -> dict:
    """
    Core delta apply logic that can be called from multiple sources.
    
    Args:
        excel_path: Path to Excel file (str or Path)
        batch_id: Optional batch ID (generated if not provided)
        send_email: Whether to send email notification
    
    Returns:
        dict with batch_id, report_path, summary_path, success, email_sent
    """
    excel_path = Path(excel_path)
    
    if not excel_path.exists():
        logger.error(f"Excel file not found: {excel_path}")
        return {
            "batch_id": "",
            "report_path": "",
            "summary_path": "",
            "success": False,
            "email_sent": False
        }
    
    # Generate batch ID if not provided
    if batch_id is None:
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Build paths
    report_path = LOG_DIR / f"delta_apply_report_{batch_id}.json"
    summary_path = LOG_DIR / f"delta_apply_summary_{batch_id}.txt"
    
    # Build command
    cmd = [
        sys.executable,
        str(DELTA_APPLY_SCRIPT),
        "--ingest-file", str(excel_path),
        "--sheet", EXCEL_SHEET_NAME,
        "--batch-id", batch_id,
        "--report", str(report_path),
        "--summary", str(summary_path),
    ]
    
    # Add apply mode flag
    if APPLY_MODE == "online":
        cmd.append("--online")
    else:
        cmd.append("--dry-run")
    
    logger.info(f"Running delta apply with batch_id={batch_id}")
    
    try:
        # Run delta apply
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
            timeout=3600
        )
        
        # Log output
        if result.stdout:
            logger.info(f"Delta apply output:\n{result.stdout}")
        if result.stderr and result.returncode != 0:
            logger.warning(f"Delta apply stderr:\n{result.stderr}")
        
        success = result.returncode == 0
        
        if success:
            logger.info(f"✅ Delta apply completed successfully (batch_id={batch_id})")
        else:
            logger.error(f"❌ Delta apply failed with exit code {result.returncode}")
        
        # Send email notification if configured and requested
        email_sent = False
        if success and send_email and report_path.exists():
            try:
                sys.path.insert(0, str(BASE_DIR / "automation"))
                from automation.api.email_notifier import send_delta_report_email
                email_sent = send_delta_report_email(str(report_path), batch_id)
            except Exception as e:
                logger.error(f"Failed to send email notification: {e}")
        
        return {
            "batch_id": batch_id,
            "report_path": str(report_path) if report_path.exists() else "",
            "summary_path": str(summary_path) if summary_path.exists() else "",
            "success": success,
            "email_sent": email_sent
        }
    
    except Exception as e:
        logger.error(f"❌ Delta apply failed: {e}")
        return {
            "batch_id": batch_id,
            "report_path": "",
            "summary_path": "",
            "success": False,
            "email_sent": False
        }


def run_delta_apply(excel_path: Optional[Path] = None, trigger_type: str = "manual") -> bool:
    """
    Execute delta apply script with full ingestion + apply pipeline.
    
    Args:
        excel_path: Path to Excel file (if None, uses latest file in watch dir)
        trigger_type: Reason for trigger (file_arrival, scheduled, manual)
    
    Returns:
        True if successful, False otherwise
    """
    # If no file provided, find latest Excel file
    if excel_path is None:
        logger.info("No file provided, searching for latest Excel file...")
        excel_files = sorted(
            WATCH_DIR.glob("*.xlsx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if not excel_files:
            logger.warning(f"No Excel files found in {WATCH_DIR}")
            return False
        excel_path = excel_files[0]
        logger.info(f"Using latest file: {excel_path.name}")
    
    if not excel_path.exists():
        logger.error(f"Excel file not found: {excel_path}")
        return False
    
    # Generate batch ID
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Build command
    # NOTE: delta_apply_influx.py does FULL pipeline: ingest → compile → validate → apply
    cmd = [
        sys.executable,  # Use current Python interpreter
        str(DELTA_APPLY_SCRIPT),
        "--ingest-file", str(excel_path),
        "--sheet", EXCEL_SHEET_NAME,
        "--batch-id", batch_id,
        "--report", str(LOG_DIR / f"delta_apply_report_{batch_id}.json"),
        "--summary", str(LOG_DIR / f"delta_apply_summary_{batch_id}.txt"),
    ]
    
    # Add apply mode flag
    if APPLY_MODE == "online":
        cmd.append("--online")
    else:
        cmd.append("--dry-run")
    
    logger.info(f"Triggering delta apply (trigger={trigger_type}, batch_id={batch_id})")
    logger.info(f"Command: {' '.join(cmd)}")
    
    try:
        # Run delta apply
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),  # Run from repo root
            timeout=3600  # 1 hour timeout
        )
        
        # Log output
        if result.stdout:
            logger.info(f"Delta apply output:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Delta apply stderr:\n{result.stderr}")
        
        if result.returncode == 0:
            logger.info(f"✅ Delta apply completed successfully (batch_id={batch_id})")
            
            # Write success flag for status tracker
            success_flag = LOG_DIR / "last_delta_apply_success.txt"
            success_flag.write_text(f"{datetime.now().isoformat()}\n{batch_id}\n{excel_path.name}")
            
            return True
        else:
            logger.error(f"❌ Delta apply failed with exit code {result.returncode}")
            return False
    
    except subprocess.TimeoutExpired:
        logger.error("❌ Delta apply timed out after 1 hour")
        return False
    except Exception as e:
        logger.error(f"❌ Delta apply failed with exception: {e}")
        return False


def scheduled_delta_apply():
    """
    Scheduled delta apply job.
    Runs at configured time with latest Excel file.
    """
    logger.info(f"Scheduled delta apply triggered at {datetime.now()}")
    run_delta_apply(trigger_type="scheduled")


def start_orchestrator():
    """
    Main orchestration loop.
    - Starts file watcher for real-time triggers
    - Schedules daily job for time-based triggers
    """
    # Create watch directory if it doesn't exist
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 80)
    logger.info("Delta Apply Orchestrator - Starting")
    logger.info("=" * 80)
    logger.info(f"Watch Directory: {WATCH_DIR.absolute()}")
    logger.info(f"Scheduled Time: {SCHEDULED_TIME}")
    logger.info(f"Apply Mode: {APPLY_MODE}")
    logger.info(f"Log Directory: {LOG_DIR.absolute()}")
    logger.info("=" * 80)
    
    # Setup file watcher
    event_handler = ExcelFileHandler(WATCH_DIR)
    observer = Observer()
    observer.schedule(event_handler, str(WATCH_DIR), recursive=False)
    observer.start()
    logger.info(f"📂 File watcher started for: {WATCH_DIR}")
    
    # Setup scheduled job
    schedule.every().day.at(SCHEDULED_TIME).do(scheduled_delta_apply)
    logger.info(f"⏰ Scheduled job set for: {SCHEDULED_TIME} daily")
    
    logger.info("🚀 Orchestrator ready. Press Ctrl+C to stop.")
    
    try:
        while True:
            # Run pending scheduled jobs
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    except KeyboardInterrupt:
        logger.info("Stopping orchestrator...")
        observer.stop()
    
    observer.join()
    logger.info("Orchestrator stopped.")


if __name__ == "__main__":
    # Parse command-line arguments for manual trigger
    if len(sys.argv) > 1:
        if sys.argv[1] == "manual":
            # Manual trigger with optional file path
            file_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
            run_delta_apply(file_path, trigger_type="manual")
        elif sys.argv[1] == "scheduled":
            # Manual trigger of scheduled job (for testing)
            scheduled_delta_apply()
        else:
            print("Usage:")
            print("  python delta_apply_orchestrator.py              # Start orchestrator")
            print("  python delta_apply_orchestrator.py manual [file] # Manual trigger")
            print("  python delta_apply_orchestrator.py scheduled     # Test scheduled trigger")
    else:
        # Start continuous orchestrator
        start_orchestrator()
