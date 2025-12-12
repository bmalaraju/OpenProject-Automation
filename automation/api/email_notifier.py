"""
Email Notifier for Delta Apply Reports

Sends formatted email notifications with delta apply report summaries.
Reuses SMTP/OAuth2 infrastructure from status_change_reporter.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Optional
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import smtplib

# Setup logging
logger = logging.getLogger(__name__)

# Base directory (repo root)
BASE_DIR = Path(__file__).resolve().parents[2]


def send_delta_report_email(report_path: str, batch_id: str) -> bool:
    """
    Send delta apply report via email.
    
    Args:
        report_path: Path to the JSON report file
        batch_id: Batch ID for this run
    
    Returns:
        True if email sent successfully, False otherwise
    """
    # Load email configuration
    recipients_str = os.getenv("DELTA_REPORT_EMAILS", "")
    if not recipients_str:
        logger.info("DELTA_REPORT_EMAILS not configured, skipping email")
        return False
    
    recipients = [email.strip() for email in recipients_str.split(",") if email.strip()]
    if not recipients:
        logger.warning("No valid email recipients found in DELTA_REPORT_EMAILS")
        return False
    
    # Check if OAuth2 is enabled
    use_oauth2 = os.getenv("USE_OAUTH2_EMAIL", "false").lower() == "true"
    
    if use_oauth2:
        return _send_email_oauth2(report_path, batch_id, recipients)
    else:
        return _send_email_smtp(report_path, batch_id, recipients)


def _send_email_oauth2(report_path: str, batch_id: str, recipients: List[str]) -> bool:
    """Send email via OAuth2 (Microsoft Graph API)"""
    try:
        sys.path.insert(0, str(BASE_DIR / "automation"))
        from oauth2_email import OAuth2EmailSender
        
        # Load report
        with open(report_path, 'r') as f:
            report = json.load(f)
        
        subject = f"Delta Apply Report - {batch_id}"
        body_html = _format_email_body(report, batch_id)
        
        sender = OAuth2EmailSender()
        
        # For OAuth2, we'll send the body with report summary
        # Attachments via Graph API require more complex handling
        # For now, include report data in email body
        success = sender.send_email(recipients, subject, body_html)
        
        if success:
            logger.info(f"✅ Delta report email sent via OAuth2 to {recipients}")
        else:
            logger.error(f"❌ Failed to send delta report email via OAuth2")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Failed to send delta report email via OAuth2: {e}")
        return False


def _send_email_smtp(report_path: str, batch_id: str, recipients: List[str]) -> bool:
    """Send email via SMTP with attachment"""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.office365.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    sender_email = os.getenv("SENDER_EMAIL", smtp_user)
    
    if not smtp_user or not smtp_password:
        logger.error("SMTP credentials not configured!")
        return False
    
    # Load report
    with open(report_path, 'r') as f:
        report = json.load(f)
    
    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Delta Apply Report - {batch_id}"
    msg['From'] = sender_email
    msg['To'] = ', '.join(recipients)
    
    # Email body
    body_html = _format_email_body(report, batch_id)
    msg.attach(MIMEText(body_html, 'html'))
    
    # Attach report JSON
    try:
        with open(report_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
        
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename=delta_apply_report_{batch_id}.json'
        )
        msg.attach(part)
    except Exception as e:
        logger.warning(f"Could not attach report file: {e}")
    
    # Send email
    try:
        logger.info(f"Connecting to SMTP server: {smtp_server}:{smtp_port}")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        logger.info(f"✅ Delta report email sent via SMTP to {recipients}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send delta report email via SMTP: {e}")
        return False


def _format_email_body(report: dict, batch_id: str) -> str:
    """Format HTML email body from report data"""
    totals = report.get("totals", {})
    domains = report.get("domains", [])
    mode = report.get("mode", {})
    
    # Build domain details
    domain_rows = ""
    for domain in domains:
        domain_name = domain.get("domain", "Unknown")
        project_key = domain.get("project_key", "N/A")
        order_count = domain.get("order_count", 0)
        changed = domain.get("changed", 0)
        created = len(domain.get("created_epics", [])) + len(domain.get("created_stories", []))
        updated = len(domain.get("updated", []))
        warnings_count = len(domain.get("warnings", []))
        failures_count = len(domain.get("failures", []))
        
        status_color = "green" if failures_count == 0 else "red"
        
        domain_rows += f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{domain_name}</td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{project_key}</td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: center;">{order_count}</td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: center;">{changed}</td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: center;">{created}</td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: center;">{updated}</td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: center; color: orange;">{warnings_count}</td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: center; color: {status_color};">{failures_count}</td>
        </tr>
        """
    
    # Mode info
    mode_str = "Online (Applied Changes)" if mode.get("online") else "Dry-Run (No Changes Applied)"
    mode_color = "green" if mode.get("online") else "orange"
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: #0078d4; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .summary {{ background-color: #f5f5f5; padding: 15px; margin: 20px 0; border-radius: 5px; }}
            .summary-item {{ display: inline-block; margin: 10px 20px; }}
            .summary-label {{ font-weight: bold; color: #666; }}
            .summary-value {{ font-size: 24px; font-weight: bold; color: #0078d4; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th {{ background-color: #0078d4; color: white; padding: 10px; text-align: left; }}
            .footer {{ background-color: #f5f5f5; padding: 15px; margin-top: 20px; text-align: center; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Delta Apply Report</h1>
            <p>Batch ID: {batch_id}</p>
        </div>
        
        <div class="content">
            <div class="summary">
                <h2>Summary</h2>
                <div class="summary-item">
                    <div class="summary-label">Mode</div>
                    <div class="summary-value" style="color: {mode_color}; font-size: 16px;">{mode_str}</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">Total Orders</div>
                    <div class="summary-value">{totals.get("orders", 0)}</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">Changed</div>
                    <div class="summary-value">{totals.get("orders_changed", 0)}</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">Created</div>
                    <div class="summary-value" style="color: green;">{totals.get("created", 0)}</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">Updated</div>
                    <div class="summary-value" style="color: blue;">{totals.get("updated", 0)}</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">Warnings</div>
                    <div class="summary-value" style="color: orange;">{totals.get("warnings", 0)}</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">Failures</div>
                    <div class="summary-value" style="color: red;">{totals.get("failures", 0)}</div>
                </div>
            </div>
            
            <h2>Domain Details</h2>
            <table>
                <thead>
                    <tr>
                        <th>Domain</th>
                        <th>Project</th>
                        <th>Orders</th>
                        <th>Changed</th>
                        <th>Created</th>
                        <th>Updated</th>
                        <th>Warnings</th>
                        <th>Failures</th>
                    </tr>
                </thead>
                <tbody>
                    {domain_rows}
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>This is an automated report from the WPR Delta Apply system.</p>
            <p>Report file is attached as JSON.</p>
        </div>
    </body>
    </html>
    """
    
    return html
