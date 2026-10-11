import os
import sys

# Ensure current directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app
import uvicorn

if __name__ == "__main__":
    # Alwaysdata provides IP (IPv6 address like fd00::... or ::) and PORT
    host = os.environ.get("IP", "::")
    port = int(os.environ.get("PORT", 8100))
    print(f"Starting Virtual AI Predictor on host={host}, port={port}...")
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except Exception as e:
        print(f"Host {host} failed ({e}), falling back to ::")
        uvicorn.run(app, host="::", port=port, log_level="info")
