import os
import uvicorn
from app import app

if __name__ == "__main__":
    ip = os.environ.get("IP", "::")
    port = int(os.environ.get("PORT", 8100))
    print(f"Starting Virtual AI Predictor on [{ip}]:{port}...")
    try:
        uvicorn.run(app, host=ip, port=port, log_level="info")
    except Exception as e:
        print(f"Fallback to 0.0.0.0 due to: {e}")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
