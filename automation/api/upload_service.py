"""
Delta Apply Upload Service - FastAPI Web Server

Provides HTTP endpoints for uploading Excel files and triggering delta apply.
Returns immediate response with batch_id and processes files in background.
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import shutil

from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Setup paths
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "src"))

# Import delta apply orchestrator
from automation.orchestrator.delta_apply_orchestrator import run_delta_apply_core
from automation.api.email_notifier import send_delta_report_email

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Delta Apply Upload Service",
    description="Upload Excel files and trigger delta apply processing",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Directories
UPLOAD_DIR = BASE_DIR / "automation" / "uploads"
LOGS_DIR = BASE_DIR / "automation" / "logs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Max file size (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024


def process_upload(file_path: str, batch_id: str):
    """
    Background task to process uploaded file.
    
    Args:
        file_path: Path to uploaded Excel file
        batch_id: Unique batch identifier
    """
    try:
        logger.info(f"Processing upload: {file_path} (batch_id={batch_id})")
        
        # Run delta apply
        result = run_delta_apply_core(file_path, batch_id=batch_id)
        
        logger.info(f"Delta apply completed for batch {batch_id}: {result}")
        
        # Send email notification if configured
        report_path = result.get("report_path")
        if report_path and os.path.exists(report_path):
            try:
                email_sent = send_delta_report_email(report_path, batch_id)
                logger.info(f"Email notification sent: {email_sent}")
            except Exception as e:
                logger.error(f"Failed to send email notification: {e}")
        
    except Exception as e:
        logger.error(f"Error processing upload {batch_id}: {e}")
        # Log error to file
        error_file = LOGS_DIR / f"upload_error_{batch_id}.txt"
        with open(error_file, 'w') as f:
            f.write(str(e))


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve upload form"""
    html_file = static_dir / "upload.html"
    if html_file.exists():
        return FileResponse(html_file)
    
    # Return basic form if static file doesn't exist
    return HTMLResponse(content="""
    <html>
        <head><title>Delta Apply Upload</title></head>
        <body>
            <h1>Delta Apply Upload Service</h1>
            <p>Upload an Excel file to trigger delta apply processing.</p>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file" accept=".xlsx" required>
                <button type="submit">Upload</button>
            </form>
        </body>
    </html>
    """)


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Upload Excel file and trigger delta apply.
    
    Returns:
        JSON response with batch_id and status
    """
    # Validate file extension
    if not file.filename.endswith('.xlsx'):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only .xlsx files are allowed."
        )
    
    # Generate batch ID
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save uploaded file
    upload_path = UPLOAD_DIR / f"{batch_id}_{file.filename}"
    
    try:
        # Read and validate file size
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size is {MAX_FILE_SIZE // (1024*1024)}MB."
            )
        
        # Write file
        with open(upload_path, 'wb') as f:
            f.write(contents)
        
        logger.info(f"File uploaded: {upload_path} (batch_id={batch_id})")
        
        # Queue background processing
        background_tasks.add_task(process_upload, str(upload_path), batch_id)
        
        return JSONResponse(
            status_code=202,
            content={
                "status": "processing",
                "batch_id": batch_id,
                "message": "File received and processing started",
                "file": file.filename,
                "report_url": f"/report/{batch_id}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{batch_id}")
async def get_status(batch_id: str):
    """
    Get processing status for a batch.
    
    Args:
        batch_id: Batch identifier
    
    Returns:
        JSON with status information
    """
    report_path = LOGS_DIR / f"delta_apply_report_{batch_id}.json"
    error_path = LOGS_DIR / f"upload_error_{batch_id}.txt"
    
    if report_path.exists():
        # Processing completed
        with open(report_path, 'r') as f:
            report = json.load(f)
        
        totals = report.get("totals", {})
        
        return {
            "batch_id": batch_id,
            "status": "completed",
            "created_epics": totals.get("created", 0),
            "updated_issues": totals.get("updated", 0),
            "warnings": totals.get("warnings", 0),
            "failures": totals.get("failures", 0),
            "report_available": True
        }
    elif error_path.exists():
        # Processing failed
        with open(error_path, 'r') as f:
            error = f.read()
        
        return {
            "batch_id": batch_id,
            "status": "failed",
            "error": error
        }
    else:
        # Still processing or not found
        return {
            "batch_id": batch_id,
            "status": "processing",
            "message": "Processing in progress or batch not found"
        }


@app.get("/report/{batch_id}")
async def get_report(batch_id: str):
    """
    Get full report for a batch.
    
    Args:
        batch_id: Batch identifier
    
    Returns:
        JSON report
    """
    report_path = LOGS_DIR / f"delta_apply_report_{batch_id}.json"
    
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Report not found for batch {batch_id}"
        )
    
    with open(report_path, 'r') as f:
        report = json.load(f)
    
    return report


@app.get("/report/{batch_id}/download")
async def download_report(batch_id: str):
    """
    Download report as JSON file.
    
    Args:
        batch_id: Batch identifier
    
    Returns:
        File download
    """
    report_path = LOGS_DIR / f"delta_apply_report_{batch_id}.json"
    
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Report not found for batch {batch_id}"
        )
    
    return FileResponse(
        report_path,
        media_type='application/json',
        filename=f"delta_apply_report_{batch_id}.json"
    )


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Service health status
    """
    return {
        "status": "healthy",
        "service": "delta-apply-upload-service",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from environment
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    
    logger.info(f"Starting Delta Apply Upload Service on {host}:{port}")
    
    uvicorn.run(
        "upload_service:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
