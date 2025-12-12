#!/usr/bin/env python3
"""
Start the Delta Apply Upload Service

Simple startup script for the FastAPI upload service.
Loads environment configuration and starts uvicorn server.
"""

import os
import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv

# Load environment
load_dotenv()
load_dotenv(BASE_DIR / ".env")

if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from environment
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "false").lower() == "true"
    
    print("=" * 80)
    print("Delta Apply Upload Service")
    print("=" * 80)
    print(f"Starting server on http://{host}:{port}")
    print(f"Upload interface: http://{host}:{port}")
    print(f"API documentation: http://{host}:{port}/docs")
    print(f"Health check: http://{host}:{port}/health")
    print("=" * 80)
    print("Press Ctrl+C to stop the server")
    print("=" * 80)
    
    uvicorn.run(
        "automation.api.upload_service:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
