from app import app
import os
import uvicorn

# Entrypoint for Alwaysdata ASGI / Uvicorn runner
if __name__ == "__main__":
    ip = os.environ.get("IP", "::")
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Virtual AI Predictor on {ip}:{port}...")
    try:
        uvicorn.run("app:app", host=ip, port=port, reload=False)
    except Exception as e:
        print(f"Fallback to 0.0.0.0 due to: {e}")
        uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
