#!/usr/bin/env python3
"""
Status Change Reporter - Plan A Implementation

Queries OpenProject API for status changes in Nokia subprojects and sends email reports.

Architecture:
- Fetches all work packages from Nokia subprojects
- Queries activities API for each work package
- Filters status changes within the specified time window
- Formats results as HTML email
- Sends via SMTP

Reports run:
- Morning (after delta apply scheduled time)
- Evening (end of business day)
"""

import os
import sys
import json
import smtplib
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

# Load environment
load_dotenv()

# BASE_DIR should be repo root - go up 2 levels from automation/reporter/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

# Configuration from environment
STATUS_REPORT_EMAILS = os.getenv("STATUS_REPORT_EMAILS", "").split(",")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", SMTP_USER)
LOG_DIR = Path(os.getenv("LOG_DIR", "automation/logs"))

# Nokia project filtering
NOKIA_PROJECT_FILTER = os.getenv("NOKIA_PROJECT_FILTER", "nokia").lower()

# Setup logging
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / f"status_reporter_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_nokia_projects() -> List[str]:
    """
    Get all Nokia subproject keys from product registry.
    
    Returns:
        List of project keys that match Nokia filter
    """
    # Registry is in config/ at repo root (BASE_DIR)
    registry_path = BASE_DIR / "config" / "product_project_registry.json"
    
    if not registry_path.exists():
        logger.warning(f"Registry not found: {registry_path}")
        return []
    
    try:
        with open(registry_path, 'r') as f:
            registry = json.load(f)
        
        # Filter projects that contain "nokia" in product name
        nokia_projects = [
            proj_key for product, proj_key in registry.items()
            if NOKIA_PROJECT_FILTER in product.lower()
        ]
        
        logger.info(f"Found {len(nokia_projects)} Nokia projects: {nokia_projects}")
        return nokia_projects
    
    except Exception as e:
        logger.error(f"Failed to load product registry: {e}")
        return []


def fetch_status_changes(hours_back: int = 12) -> List[Dict[str, Any]]:
    """
    Fetch status changes from OpenProject activities API.
    
    Args:
        hours_back: Number of hours to look back for changes
    
    Returns:
        List of status change records
    """
    from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2
    
    logger.info(f"Fetching status changes from last {hours_back} hours...")
    
    svc = OpenProjectServiceV2()
    client = svc.client
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    logger.info(f"Cutoff time: {cutoff_time.isoformat()}")
    
    nokia_projects = get_nokia_projects()
    
    if not nokia_projects:
        logger.warning("No Nokia projects found!")
        return []
    
    changes = []
    total_wps_checked = 0
    
    for project_key in nokia_projects:
        logger.info(f"Processing project: {project_key}")
        
        try:
            # Get project ID
            pid = svc._project_id(project_key)
            if not pid:
                logger.warning(f"Could not resolve project ID for: {project_key}")
                continue
            
            # Query all work packages in this project
            filters = [{"project": {"operator": "=", "values": [str(pid)]}}]
            
            try:
                wps = client.search_work_packages(filters, page_size=1000)
                logger.info(f"Found {len(wps)} work packages in {project_key}")
            except Exception as e:
                logger.error(f"Failed to search work packages in {project_key}: {e}")
                continue
            
            # Process each work package
            for wp in wps:
                total_wps_checked += 1
                wp_id = wp.get('id')
                wp_subject = wp.get('subject', 'Unknown')
                
                # Get WP Order ID from custom field
                # Try multiple possible field names
                wp_order_id = None
                for field_key in wp.keys():
                    if 'customField' in str(field_key):
                        # This could be the WP Order ID field
                        val = wp.get(field_key)
                        if val and isinstance(val, str) and val.startswith('WPO'):
                            wp_order_id = val
                            break
                
                # Fallback: try to extract from subject
                if not wp_order_id:
                    # Subject often contains "WPO00XXXXXX :: ..."
                    if '::' in wp_subject:
                        wp_order_id = wp_subject.split('::')[0].strip()
                    elif wp_subject.startswith('WPO'):
                        wp_order_id = wp_subject.split()[0].strip()
                
                try:
                    # Fetch activities for this work package
                    resp = client._request("GET", f"/api/v3/work_packages/{wp_id}/activities")
                    
                    if resp.status_code != 200:
                        logger.debug(f"Failed to fetch activities for WP {wp_id}: {resp.status_code}")
                        continue
                    
                    activities_data = resp.json()
                    activities = activities_data.get('_embedded', {}).get('elements', [])
                    
                    # Process each activity
                    for activity in activities:
                        # Check if activity is within time window
                        created_at_str = activity.get('createdAt')
                        if not created_at_str:
                            continue
                        
                        try:
                            # Parse ISO timestamp
                            created_at = datetime.fromisoformat(
                                created_at_str.replace('Z', '+00:00')
                            )
                        except Exception as e:
                            logger.debug(f"Failed to parse timestamp: {created_at_str}: {e}")
                            continue
                        
                        # Skip activities outside time window
                        if created_at < cutoff_time:
                            continue
                        
                        # Check if this activity contains a status change
                        details = activity.get('details', [])
                        
                        for detail in details:
                            # Status changes have format: {"attribute": "status", ...}
                            if detail.get('format') == 'custom' and detail.get('html'):
                                # Parse HTML for status change
                                html = detail.get('html', '')
                                if 'status' in html.lower():
                                    # This is likely a status change
                                    # Try to extract old and new values
                                    # HTML format: "<strong>Status</strong> changed from <i>Old</i> to <i>New</i>"
                                    
                                    # Simple parsing (could be improved with BeautifulSoup)
                                    parts = html.split('to')
                                    if len(parts) == 2:
                                        from_part = parts[0].split('from')[-1] if 'from' in parts[0] else parts[0]
                                        to_part = parts[1]
                                        
                                        # Extract text between <i> tags
                                        import re
                                        old_match = re.search(r'<i[^>]*>(.*?)</i>', from_part)
                                        new_match = re.search(r'<i[^>]*>(.*?)</i>', to_part)
                                        
                                        old_status = old_match.group(1) if old_match else 'Unknown'
                                        new_status = new_match.group(1) if new_match else 'Unknown'
                                        
                                        changes.append({
                                            'wp_order_id': wp_order_id or f"WP-{wp_id}",
                                            'work_package': wp_subject,
                                            'from_status': old_status,
                                            'to_status': new_status,
                                            'changed_at': created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
                                            'project': project_key
                                        })
                
                except Exception as e:
                    logger.debug(f"Error processing activities for WP {wp_id}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error processing project {project_key}: {e}")
            continue
    
    logger.info(f"Checked {total_wps_checked} work packages, found {len(changes)} status changes")
    return changes


def format_email_body(changes: List[Dict[str, Any]], period: str = "Morning") -> str:
    """
    Format status changes into HTML email body.
    
    Args:
        changes: List of status change records
        period: Morning or Evening
    
    Returns:
        HTML email body
    """
    if not changes:
        return f"""
        <html>
          <body>
            <h2>{period} Status Change Report - Nokia Projects</h2>
            <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p style="color: green;"><strong>✅ No status changes detected in the last reporting period.</strong></p>
          </body>
        </html>
        """
    
    html = f"""
    <html>
      <head>
        <style>
          body {{
            font-family: Arial, sans-serif;
            margin: 20px;
          }}
          table {{
            border-collapse: collapse;
            width: 100%;
            margin-top: 20px;
          }}
          th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
          }}
          th {{
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
          }}
          tr:nth-child(even) {{
            background-color: #f2f2f2;
          }}
          tr:hover {{
            background-color: #ddd;
          }}
          .summary {{
            background-color: #e7f3ff;
            padding: 10px;
            border-left: 4px solid #2196F3;
            margin: 10px 0;
          }}
        </style>
      </head>
      <body>
        <h2>📊 {period} Status Change Report - Nokia Projects</h2>
        <div class="summary">
          <p><strong>Report Period:</strong> Last {6 if period == "Evening" else 12} hours</p>
          <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
          <p><strong>Total Status Changes:</strong> {len(changes)}</p>
        </div>
        <table>
          <tr>
            <th>WP Order ID</th>
            <th>Work Package</th>
            <th>Project</th>
            <th>From Status</th>
            <th>To Status</th>
            <th>Changed At</th>
          </tr>
    """
    
    for change in changes:
        html += f"""
          <tr>
            <td><strong>{change['wp_order_id']}</strong></td>
            <td>{change['work_package'][:80]}...</td>
            <td>{change['project']}</td>
            <td><span style="color: #666;">{change['from_status']}</span></td>
            <td><span style="color: #4CAF50;"><strong>{change['to_status']}</strong></span></td>
            <td>{change['changed_at']}</td>
          </tr>
        """
    
    html += """
        </table>
      </body>
    </html>
    """
    
    return html


def send_email_smtp(subject: str, body_html: str, recipients: List[str]) -> bool:
    """
    Send email via SMTP or OAuth2 (Microsoft Graph API).
    
    Automatically uses OAuth2 if USE_OAUTH2_EMAIL=true, otherwise falls back to SMTP.
    
    Args:
        subject: Email subject
        body_html: HTML email body
        recipients: List of recipient email addresses
    
    Returns:
        True if successful, False otherwise
    """
    if not recipients or not recipients[0]:
        logger.error("No recipients configured!")
        return False
    
    # Check if OAuth2 is enabled
    use_oauth2 = os.getenv("USE_OAUTH2_EMAIL", "false").lower() == "true"
    
    if use_oauth2:
        logger.info("Using OAuth2 (Microsoft Graph API) for email")
        return _send_email_oauth2(subject, body_html, recipients)
    else:
        logger.info("Using SMTP for email")
        return _send_email_smtp_basic(subject, body_html, recipients)


def _send_email_oauth2(subject: str, body_html: str, recipients: List[str]) -> bool:
    """
    Send email using Microsoft Graph API with OAuth2 authentication.
    Required for Office 365 accounts with MFA.
    """
    try:
        # Import OAuth2 email sender
        sys.path.insert(0, str(BASE_DIR / "automation"))
        from oauth2_email import OAuth2EmailSender
        
        sender = OAuth2EmailSender()
        success = sender.send_email(recipients, subject, body_html)
        
        if success:
            logger.info(f"✅ Email sent successfully via OAuth2 to {recipients}")
        else:
            logger.error("❌ Failed to send email via OAuth2")
        
        return success
    
    except ImportError as e:
        logger.error(f"❌ OAuth2 email module not found: {e}")
        logger.error("Install with: pip install requests")
        return False
    except Exception as e:
        logger.error(f"❌ Failed to send email via OAuth2: {e}")
        return False


def _send_email_smtp_basic(subject: str, body_html: str, recipients: List[str]) -> bool:
    """
    Send email via basic SMTP authentication.
    Works for non-MFA accounts or alternative SMTP servers.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.error("SMTP credentials not configured!")
        return False
    
    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = ', '.join(recipients)
    
    # Attach HTML body
    msg.attach(MIMEText(body_html, 'html'))
    
    try:
        logger.info(f"Connecting to SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"✅ Email sent successfully via SMTP to {recipients}")
        return True
    
    except Exception as e:
        logger.error(f"❌ Failed to send email via SMTP: {e}")
        return False


def morning_report():
    """
    Morning status change report.
    Runs regardless of delta apply success (per user request).
    """
    logger.info("=" * 80)
    logger.info("MORNING STATUS REPORT - Starting")
    logger.info("=" * 80)
    
    # Fetch changes from last 12 hours
    changes = fetch_status_changes(hours_back=12)
    
    # Format email
    body = format_email_body(changes, period="Morning")
    subject = f"🌅 Morning Status Change Report - {datetime.now().strftime('%Y-%m-%d')}"
    
    # Send email
    if STATUS_REPORT_EMAILS and STATUS_REPORT_EMAILS[0]:
        success = send_email_smtp(subject, body, STATUS_REPORT_EMAILS)
        if success:
            logger.info("Morning report sent successfully")
        else:
            logger.error("Morning report failed to send")
    else:
        logger.warning("No email recipients configured, skipping email send")
        logger.info(f"Report preview:\n{subject}")
        logger.info(f"Found {len(changes)} status changes")


def evening_report():
    """
    Evening status change report.
    Runs regardless of delta apply success (per user request).
    """
    logger.info("=" * 80)
    logger.info("EVENING STATUS REPORT - Starting")
    logger.info("=" * 80)
    
    # Fetch changes from last 6 hours
    changes = fetch_status_changes(hours_back=6)
    
    # Format email
    body = format_email_body(changes, period="Evening")
    subject = f"🌆 Evening Status Change Report - {datetime.now().strftime('%Y-%m-%d')}"
    
    # Send email
    if STATUS_REPORT_EMAILS and STATUS_REPORT_EMAILS[0]:
        success = send_email_smtp(subject, body, STATUS_REPORT_EMAILS)
        if success:
            logger.info("Evening report sent successfully")
        else:
            logger.error("Evening report failed to send")
    else:
        logger.warning("No email recipients configured, skipping email send")
        logger.info(f"Report preview:\n{subject}")
        logger.info(f"Found {len(changes)} status changes")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "morning":
            morning_report()
        elif sys.argv[1] == "evening":
            evening_report()
        else:
            print("Usage:")
            print("  python status_change_reporter.py morning   # Run morning report")
            print("  python status_change_reporter.py evening   # Run evening report")
    else:
        print("Usage:")
        print("  python status_change_reporter.py morning   # Run morning report")
        print("  python status_change_reporter.py evening   # Run evening report")
