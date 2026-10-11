from app import app

# Entrypoint for Alwaysdata ASGI / Uvicorn runner
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
