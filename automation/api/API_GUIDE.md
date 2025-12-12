# Delta Apply Upload Service - API Guide

## Quick Start

### 1. Start the Service

```bash
python automation/api/start_service.py
```

The service will start on `http://localhost:8000` by default.

### 2. Upload via Web Interface

Open your browser and navigate to:
```
http://localhost:8000
```

Drag and drop an Excel file or click to browse.

---

## API Endpoints

### POST /upload

Upload an Excel file and trigger delta apply processing.

**Request**:
```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@work_packages.xlsx"
```

**Response** (202 Accepted):
```json
{
  "status": "processing",
  "batch_id": "20251209_110530",
  "message": "File received and processing started",
  "file": "work_packages.xlsx",
  "report_url": "/report/20251209_110530"
}
```

**Error Responses**:
- `400 Bad Request` - Invalid file type or file too large
- `500 Internal Server Error` - Server error

---

### GET /status/{batch_id}

Check processing status for a batch.

**Request**:
```bash
curl http://localhost:8000/status/20251209_110530
```

**Response** (Completed):
```json
{
  "batch_id": "20251209_110530",
  "status": "completed",
  "created_epics": 5,
  "updated_issues": 10,
  "warnings": 0,
  "failures": 0,
  "report_available": true
}
```

**Response** (Processing):
```json
{
  "batch_id": "20251209_110530",
  "status": "processing",
  "message": "Processing in progress or batch not found"
}
```

**Response** (Failed):
```json
{
  "batch_id": "20251209_110530",
  "status": "failed",
  "error": "Error details..."
}
```

---

### GET /report/{batch_id}

Get full JSON report for a completed batch.

**Request**:
```bash
curl http://localhost:8000/report/20251209_110530
```

**Response**:
```json
{
  "batch_id": "20251209_110530",
  "run_id": "20251209T110530Z",
  "mode": {
    "online": true,
    "dry_run": false
  },
  "domains": [
    {
      "domain": "CBAM",
      "project_key": "nokia-cbam",
      "order_count": 5,
      "changed": 5,
      "created_epics": ["CBAM-123", "CBAM-124"],
      "created_stories": ["CBAM-125", "CBAM-126"],
      "updated": ["CBAM-100"],
      "warnings": [],
      "failures": []
    }
  ],
  "totals": {
    "orders": 5,
    "orders_changed": 5,
    "created": 4,
    "updated": 1,
    "warnings": 0,
    "failures": 0
  },
  "started_at": "2025-12-09T11:05:30Z",
  "ended_at": "2025-12-09T11:05:45Z"
}
```

---

### GET /report/{batch_id}/download

Download report as a JSON file.

**Request**:
```bash
curl -O http://localhost:8000/report/20251209_110530/download
```

Downloads: `delta_apply_report_20251209_110530.json`

---

### GET /health

Health check endpoint.

**Request**:
```bash
curl http://localhost:8000/health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "delta-apply-upload-service",
  "version": "1.0.0"
}
```

---

## Python Client Example

```python
import requests

# Upload file
with open('work_packages.xlsx', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/upload',
        files={'file': f}
    )

data = response.json()
print(f"Upload successful! Batch ID: {data['batch_id']}")

# Check status
batch_id = data['batch_id']
status_response = requests.get(f'http://localhost:8000/status/{batch_id}')
print(status_response.json())

# Get full report (when completed)
report_response = requests.get(f'http://localhost:8000/report/{batch_id}')
report = report_response.json()
print(f"Created {report['totals']['created']} issues")
```

---

## Configuration

Add to your `.env` file:

```bash
# API Server Configuration
API_HOST=127.0.0.1  # Use 0.0.0.0 to allow network access
API_PORT=8000
API_RELOAD=false     # Set to true for development

# Email Recipients for Delta Reports
DELTA_REPORT_EMAILS=user1@example.com,user2@example.com

# SMTP Configuration (reuses existing status reporter config)
SMTP_SERVER=smtp.office365.com
SMTP_PORT=587
SMTP_USER=your-email@infinite.com
SMTP_PASSWORD=your-app-password
SENDER_EMAIL=your-email@infinite.com

# Or use OAuth2
USE_OAUTH2_EMAIL=true
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
```

---

## Email Notifications

When delta apply completes, an email is automatically sent to addresses listed int `DELTA_REPORT_EMAILS`.

**Email Content**:
- Subject: `Delta Apply Report - {batch_id}`
- HTML body with summary table
- Attached JSON report file

**Email Summary Includes**:
- Total orders processed
- Orders changed
- Created epics/stories count
- Updated issues count
- Warnings and failures
- Per-domain breakdown

---

## Tips

### Testing with cURL

```bash
# Upload
curl -X POST http://localhost:8000/upload -F "file=@test.xlsx"

# Status
curl http://localhost:8000/status/20251209_110530

# Report
curl http://localhost:8000/report/20251209_110530 | jq .

# Download
curl -O http://localhost:8000/report/20251209_110530/download
```

### Network Access

To allow uploads from other machines on your network:

1. Set `API_HOST=0.0.0.0` in `.env`
2. Access via `http://<your-ip>:8000`
3. **Note**: This exposes the service to your network. Consider adding authentication for production.

### Running as Background Service

**Windows** (using `nssm`):
```cmd
nssm install DeltaApplyAPI python automation\api\start_service.py
nssm start DeltaApplyAPI
```

**Linux** (systemd):
Create `/etc/systemd/system/delta-apply-api.service`:
```ini
[Unit]
Description=Delta Apply Upload Service
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/JIRA-Agent
ExecStart=/usr/bin/python3 automation/api/start_service.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable delta-apply-api
sudo systemctl start delta-apply-api
```

---

## Troubleshooting

### "Module not found" errors
Run: `pip install -r requirements.txt`

### Email not sending
Check `.env` file has correct SMTP credentials or OAuth2 configuration.

### Reports not found
Check `automation/logs/` directory for generated reports.

### Port already in use
Change `API_PORT` in `.env` or stop the conflicting service.
