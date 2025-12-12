#!/usr/bin/env python3
"""
OAuth2 Email Sender for Office 365 with Microsoft Graph API

Uses Modern Authentication (OAuth2) to send emails via Microsoft Graph API.
Required for Office 365 accounts with MFA enabled.

Setup:
1. Register an app in Azure AD
2. Configure API permissions (Mail.Send)
3. Create client secret
4. Add credentials to .env file
"""

import os
import json
import requests
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()


class OAuth2EmailSender:
    """
    Send emails using Microsoft Graph API with OAuth2 authentication.
    Supports both delegated (user) and application (service) permissions.
    """
    
    def __init__(self):
        """Initialize OAuth2 email sender with credentials from environment."""
        self.tenant_id = os.getenv("AZURE_TENANT_ID")
        self.client_id = os.getenv("AZURE_CLIENT_ID")
        self.client_secret = os.getenv("AZURE_CLIENT_SECRET")
        self.sender_email = os.getenv("SENDER_EMAIL")
        
        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise ValueError(
                "Missing required OAuth2 credentials. Set AZURE_TENANT_ID, "
                "AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET in .env"
            )
        
        self.token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        self.graph_api_url = "https://graph.microsoft.com/v1.0"
        self._access_token = None
    
    def _get_access_token(self) -> str:
        """
        Get OAuth2 access token using client credentials flow.
        
        Returns:
            Access token string
        
        Raises:
            Exception if authentication fails
        """
        if self._access_token:
            # TODO: Add token expiration check and refresh logic
            return self._access_token
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
        
        try:
            response = requests.post(self.token_url, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self._access_token = token_data["access_token"]
            return self._access_token
        
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get OAuth2 token: {e}")
    
    def send_email(
        self,
        to_addresses: List[str],
        subject: str,
        body_html: str,
        from_address: Optional[str] = None
    ) -> bool:
        """
        Send an email using Microsoft Graph API.
        
        Args:
            to_addresses: List of recipient email addresses
            subject: Email subject
            body_html: HTML email body
            from_address: Sender email (defaults to SENDER_EMAIL from env)
        
        Returns:
            True if successful, False otherwise
        """
        if not to_addresses:
            raise ValueError("No recipients specified")
        
        from_address = from_address or self.sender_email
        if not from_address:
            raise ValueError("No sender email specified")
        
        # Get access token
        try:
            token = self._get_access_token()
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return False
        
        # Prepare email message
        message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html
                },
                "toRecipients": [
                    {"emailAddress": {"address": addr}} for addr in to_addresses
                ]
            },
            "saveToSentItems": "true"
        }
        
        # Send email via Graph API
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Use /users/{userId}/sendMail endpoint
        url = f"{self.graph_api_url}/users/{from_address}/sendMail"
        
        try:
            response = requests.post(url, headers=headers, json=message)
            response.raise_for_status()
            
            print(f"✅ Email sent successfully to {to_addresses}")
            return True
        
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to send email: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_details = e.response.json()
                    print(f"Error details: {json.dumps(error_details, indent=2)}")
                except:
                    print(f"Response text: {e.response.text}")
            return False


def test_oauth2_email():
    """Test OAuth2 email sending."""
    print("Testing OAuth2 Email Sender...")
    print("=" * 80)
    
    try:
        sender = OAuth2EmailSender()
        print(f"✅ OAuth2 sender initialized")
        print(f"Tenant ID: {sender.tenant_id}")
        print(f"Client ID: {sender.client_id}")
        print(f"Sender Email: {sender.sender_email}")
        print()
        
        # Test email
        test_recipients = os.getenv("STATUS_REPORT_EMAILS", "").split(",")
        if not test_recipients or not test_recipients[0]:
            print("⚠️ No recipients configured in STATUS_REPORT_EMAILS")
            test_recipients = [sender.sender_email]  # Send to self
        
        print(f"Sending test email to: {test_recipients}")
        
        subject = "🧪 OAuth2 Email Test - Status Reporter"
        body = """
        <html>
          <body>
            <h2>OAuth2 Authentication Test</h2>
            <p>This is a test email sent using Microsoft Graph API with OAuth2 authentication.</p>
            <p><strong>Status:</strong> ✅ OAuth2 email sending is working correctly!</p>
            <p>Your status change reporter is now configured to work with Office 365 MFA accounts.</p>
          </body>
        </html>
        """
        
        success = sender.send_email(test_recipients, subject, body)
        
        if success:
            print()
            print("=" * 80)
            print("✅ TEST PASSED - OAuth2 email working!")
            print("=" * 80)
        else:
            print()
            print("=" * 80)
            print("❌ TEST FAILED - Check error messages above")
            print("=" * 80)
    
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_oauth2_email()
