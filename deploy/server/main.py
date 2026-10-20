"""
Point d'entrée du site Alwaysdata « Programme utilisateur » (dossier /home/god).

La plateforme lance : uvicorn main:app --port $PORT --host $IP ...
On ne fait donc qu'exposer l'application d'edge (FastAPI) qui sert :
  - /health, /ml/v1/*   → API FastAPI
  - /api/v1/*           → relais vers le service NestJS (127.0.0.1:3000)
  - /                   → application Flutter web (statique)

Les secrets applicatifs (bookmaker, Live Football, JWT…) ne sont pas dans
l'environnement fourni par la plateforme : ils sont lus ici dans
/home/god/.config/pred-app.env (chmod 600, hors dépôt git).
"""
import os
from pathlib import Path

_ENV_FILE = Path(os.getenv("APP_ENV_FILE", "/home/god/.config/pred-app.env"))
if _ENV_FILE.is_file():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        if _line.startswith("export "):
            _line = _line[len("export "):]
        _k, _, _v = _line.partition("=")
        _v = _v.strip().strip('"').strip("'")
        os.environ.setdefault(_k.strip(), _v)

from app.edge import app  # noqa: E402,F401  (l'edge expose `app`)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("IP", "127.0.0.1"),
        port=int(os.getenv("PORT", "8100")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )

