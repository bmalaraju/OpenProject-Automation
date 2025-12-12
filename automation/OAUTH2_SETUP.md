# OAuth2 Setup Guide for Office 365

## Overview

This guide walks you through setting up OAuth2 authentication for sending emails from your Office 365 account with MFA enabled.

We'll use **Microsoft Graph API** with **Application Permissions** (service-to-service) which doesn't require user interaction.

---

## Step 1: Register Application in Azure AD

### 1.1 Go to Azure Portal
1. Navigate to https://portal.azure.com
2. Sign in with your admin account
3. Search for "Azure Active Directory" or "Microsoft Entra ID"

### 1.2 Register New Application
1. Go to **App registrations** (left sidebar)
2. Click **+ New registration**
3. Fill in:
   - **Name**: `WPR Status Reporter` (or any descriptive name)
   - **Supported account types**: Select "Accounts in this organizational directory only"
   - **Redirect URI**: Leave blank (not needed for service apps)
4. Click **Register**

### 1.3 Save Application Details
After registration, you'll see the **Overview** page. **Save these values**:
- **Application (client) ID**: Copy this (example: `12345678-1234-1234-1234-123456789abc`)
- **Directory (tenant) ID**: Copy this (example: `87654321-4321-4321-4321-cba987654321`)

```bash
# Add to your .env file:
AZURE_CLIENT_ID=12345678-1234-1234-1234-123456789abc
AZURE_TENANT_ID=87654321-4321-4321-4321-cba987654321
```

---

## Step 2: Create Client Secret

### 2.1 Generate Secret
1. In your app registration, go to **Certificates & secrets** (left sidebar)
2. Click **+ New client secret**
3. Add description: `WPR Status Reporter Secret`
4. Set expiration: Choose **24 months** (or per your policy)
5. Click **Add**

### 2.2 Save Secret Value
⚠️ **IMPORTANT**: Copy the **Value** (not the Secret ID) immediately! You can't see it again.

Example value: `abc~XyZ123.456-QwE~rty789`

```bash
# Add to your .env file:
AZURE_CLIENT_SECRET=abc~XyZ123.456-QwE~rty789
```

---

## Step 3: Configure API Permissions

### 3.1 Add Mail.Send Permission
1. Go to **API permissions** (left sidebar)
2. Click **+ Add a permission**
3. Select **Microsoft Graph**
4. Select **Application permissions** (not Delegated)
5. Search for and select: **Mail.Send**
6. Click **Add permissions**

### 3.2 Grant Admin Consent
⚠️ **CRITICAL**: Admin consent is required for application permissions

1. Click **Grant admin consent for [Your Organization]**
2. Confirm by clicking **Yes**
3. Status should change to ✅ **Granted for [Your Organization]**

**Without admin consent, the app cannot send emails!**

---

## Step 4: Configure .env File

Add all OAuth2 credentials to your `.env` file:

```bash
# ============================================================================
# OAuth2 Configuration for Office 365 (Microsoft Graph API)
# ============================================================================

# Azure AD App Registration
AZURE_TENANT_ID=87654321-4321-4321-4321-cba987654321
AZURE_CLIENT_ID=12345678-1234-1234-1234-123456789abc
AZURE_CLIENT_SECRET=abc~XyZ123.456-QwE~rty789

# Email Configuration
SENDER_EMAIL=bmalaraju@infinite.com
STATUS_REPORT_EMAILS=recipient1@example.com,recipient2@example.com

# Enable OAuth2 mode (instead of SMTP)
USE_OAUTH2_EMAIL=true
```

---

## Step 5: Install Required Package

```bash
# Install requests library if not already installed
pip install requests
```

---

## Step 6: Test OAuth2 Email

```bash
# Run test script
python automation/oauth2_email.py
```

**Expected output:**
```
Testing OAuth2 Email Sender...
================================================================================
✅ OAuth2 sender initialized
Tenant ID: 87654321-4321-4321-4321-cba987654321
Client ID: 12345678-1234-1234-1234-123456789abc
Sender Email: bmalaraju@infinite.com

Sending test email to: ['recipient@example.com']
✅ Email sent successfully to ['recipient@example.com']

================================================================================
✅ TEST PASSED - OAuth2 email working!
================================================================================
```

---

## Step 7: Update Status Reporter

The status reporter will automatically use OAuth2 if `USE_OAUTH2_EMAIL=true` is set in `.env`.

Test the full flow:
```bash
$env:PYTHONPATH = "src"; python automation/reporter/status_change_reporter.py morning
```

---

## Troubleshooting

### Error: "Insufficient privileges to complete the operation"

**Cause**: Admin consent not granted for Mail.Send permission

**Solution**:
1. Go to Azure Portal → App registrations → Your app
2. API permissions → Grant admin consent
3. Wait 5 minutes for changes to propagate
4. Test again

### Error: "Invalid client secret provided"

**Cause**: Client secret is incorrect or expired

**Solution**:
1. Go to Azure Portal → App registrations → Your app → Certificates & secrets
2. Generate a new client secret
3. Update `AZURE_CLIENT_SECRET` in `.env`
4. Test again

### Error: "Authorization_RequestDenied"

**Cause**: The service principal doesn't have permission to send on behalf of the user

**Solution**:
- Ensure Mail.Send **Application** permission is added (not Delegated)
- Ensure admin consent is granted
- Wait 10-15 minutes after granting consent

### Error: "Forbidden" when sending

**Cause**: Trying to send from an email address the app doesn't have permission for

**Solution**:
- Ensure `SENDER_EMAIL` matches your Office 365 account
- OR configure **Application Access Policy** to allow sending from any mailbox:
  ```powershell
  # PowerShell (run as admin)
  New-ApplicationAccessPolicy -AppId "YOUR_CLIENT_ID" -PolicyScopeGroupId "sender@domain.com" -AccessRight RestrictAccess -Description "Restrict app to specific mailbox"
  ```

---

## Security Best Practices

### 1. Rotate Secrets Regularly
- Client secrets expire (24 months max)
- Set calendar reminder to rotate before expiration
- Azure will send expiration notifications

### 2. Limit Permissions
- Only grant **Mail.Send** permission (don't add unnecessary permissions)
- Review permissions periodically

### 3. Restrict to Specific Mailboxes (Optional)
Use Exchange Online PowerShell to limit which mailboxes the app can send from:

```powershell
# Connect to Exchange Online
Connect-ExchangeOnline

# Create application access policy
New-ApplicationAccessPolicy `
    -AppId "YOUR_CLIENT_ID" `
    -PolicyScopeGroupId "bmalaraju@infinite.com" `
    -AccessRight RestrictAccess `
    -Description "WPR Status Reporter - Send only"

# Verify
Test-ApplicationAccessPolicy -Identity "bmalaraju@infinite.com" -AppId "YOUR_CLIENT_ID"
```

### 4. Monitor App Activity
- Azure AD → Sign-in logs → Filter by your app
- Review sent emails regularly
- Set up alerts for unusual activity

---

## Alternative: Delegated Permissions (User Flow)

If you can't get admin consent for application permissions, you can use delegated permissions with interactive login:

**Not recommended for automated scripts** but available if needed. This requires:
1. User to sign in interactively
2. Refresh tokens to be stored securely
3. More complex authentication flow

Let me know if you need this approach instead.

---

## Quick Reference

### Environment Variables Required
```bash
AZURE_TENANT_ID=<your-tenant-id>
AZURE_CLIENT_ID=<your-client-id>
AZURE_CLIENT_SECRET=<your-client-secret>
SENDER_EMAIL=<your-email@infinite.com>
USE_OAUTH2_EMAIL=true
```

### Test Command
```bash
python automation/oauth2_email.py
```

### Production Use
```bash
$env:PYTHONPATH = "src"; python automation/reporter/status_change_reporter.py morning
```

---

**Next**: After completing setup, run the test to verify OAuth2 email works, then test the full status reporter! 🚀
