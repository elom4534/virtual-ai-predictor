#!/usr/bin/env python3
"""
Kit de déploiement Alwaysdata (api.alwaysdata.com/v1 + SSH).

Compte cible : elogededivo05417042
  - site Node.js  : /sites/pred-api   (NestJS, commande `node dist/main.js`)
  - site Programme utilisateur : /sites/pred-ml (FastAPI/uvicorn)
  - archive monorepo + install : /home/elogededivo05417042/pred-app

Usage :
    python3 alwaysdata.py preflight   # vérifie tout AVANT de toucher au serveur
    python3 alwaysdata.py check       # teste l'API (token + compte) et liste les sites
    python3 alwaysdata.py push        # envoie le projet en SSH (tar over ssh)
    python3 alwaysdata.py install     # lance les commandes d'installation
    python3 alwaysdata.py site        # crée/met à jour les sites via l'API
    python3 alwaysdata.py restart     # redémarre les sites
    python3 alwaysdata.py deploy      # push + install + site + restart
    python3 alwaysdata.py status      # état des sites + logs

Configuration : /home/user/deploy/config.json (voir config.example.json).
Secrets : variables d'environnement (ALWAYSDATA_API_TOKEN, ALWAYSDATA_SSH_PASSWORD
ou ALWAYSDATA_SSH_KEY) — jamais dans le dépôt.
"""

import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import tarfile
import io
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Le module 'requests' est requis : pip install requests")

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
API = "https://api.alwaysdata.com/v1"

# Types de site Alwaysdata (https://api.alwaysdata.com/v1/site/doc/)
SITE_TYPES = {
    "static": "apache_standard",
    "php": "apache_php",
    "node": "nodejs",            # site Node.js (commande `node …`, écoute IP/PORT)
    "nodejs": "nodejs",
    "python": "wsgi",            # WSGI (uWSGI)
    "user_program": "user_program",  # Programme utilisateur (FastAPI/uvicorn)
}


# --------------------------------------------------------------------------- config
def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(f"config.json introuvable. Copiez config.example.json -> config.json")
    cfg = json.loads(CONFIG_PATH.read_text())
    for key in ("account",):
        if not cfg.get(key):
            sys.exit(f"config.json : champ '{key}' manquant")

    # Surcharges par variables d'environnement (secrets hors dépôt)
    env_token = os.getenv(cfg.get("api_token_env") or "ALWAYSDATA_API_TOKEN")
    if env_token:
        cfg["api_token"] = env_token
    ssh = cfg.setdefault("ssh", {})
    key_env = os.getenv(ssh.get("key_path_env") or "ALWAYSDATA_SSH_KEY")
    if key_env:
        ssh["key_path"] = key_env
    pwd_env = os.getenv(ssh.get("password_env") or "ALWAYSDATA_SSH_PASSWORD")
    if pwd_env:
        ssh["password"] = pwd_env

    # Normalisation : une seule liste de sites
    if "sites" not in cfg:
        if "site" in cfg:
            cfg["sites"] = [cfg["site"]]
        else:
            sys.exit("config.json : aucune section 'sites'")
    return cfg


def auth(cfg):
    user = f"{cfg['api_token']} account={cfg['account']}"
    return (user, "")


# --------------------------------------------------------------------------- API
def api_call(cfg, method, path, **kwargs):
    if not cfg.get("api_token"):
        sys.exit("Token API Alwaysdata absent : définissez ALWAYSDATA_API_TOKEN "
                 "(Profile > Tokens, affiché une seule fois, 2FA requis).")
    resp = requests.request(
        method, API + path, auth=auth(cfg), timeout=60, **kwargs
    )
    if resp.status_code >= 400:
        sys.exit(f"API {method} {path} -> {resp.status_code}\n{resp.text[:2000]}")
    if resp.text.strip():
        try:
            return resp.json()
        except ValueError:
            return resp.text
    return None


def cmd_check(cfg):
    account = api_call(cfg, "GET", "/account/")
    print(f"Compte  : {account.get('account')}")
    sites = api_call(cfg, "GET", "/site/")
    items = sites.get("site", sites) if isinstance(sites, dict) else sites
    print(f"Sites   : {len(items)}")
    for s in items:
        print(f"  #{s['id']:<6} {s.get('type',''):<18} path={s.get('path','')} "
              f"addrs={','.join(s.get('addresses') or [])}")


def cmd_site(cfg):
    """Crée ou met à jour chaque site déclaré dans config.json."""
    created_ids = []
    for site in cfg["sites"]:
        name = site.get("name")
        path = site.get("path")
        stype = SITE_TYPES.get(site.get("type", "static"), site.get("type", "static"))
        payload = {
            "type": stype,
            "path": path,
            "addresses": site.get("addresses", []),
        }
        if name:
            payload["name"] = name
        if site.get("environment"):
            payload["environment"] = site["environment"]
        if site.get("ssl_force") is not None:
            payload["ssl_force"] = site["ssl_force"]
        if site.get("max_idle_time") is not None:
            payload["max_idle_time"] = site["max_idle_time"]
        for extra in ("command", "working_directory", "vhost_additional_directives"):
            if site.get(extra):
                payload[extra] = site[extra]

        site_id = site.get("id")
        if site_id:
            api_call(cfg, "PUT", f"/site/{site_id}/", json=payload)
            print(f"Site #{site_id} mis a jour ({stype}, path={path})")
        else:
            created = api_call(cfg, "POST", "/site/", json=payload)
            new_id = created["id"]
            created_ids.append(new_id)
            print(f"Site cree : #{new_id} ({name}, {stype}, path={path})")
            print(f'  Ajoutez "id": {new_id} dans config.json (section sites / {name}).')
    return created_ids


def cmd_restart(cfg):
    for site in cfg["sites"]:
        site_id = site.get("id")
        if not site_id:
            print(f"Site {site.get('name')} : pas d'id dans config.json — ignore")
            continue
        api_call(cfg, "POST", f"/site/{site_id}/restart/")
        print(f"Site #{site_id} ({site.get('name')}) redemarre.")


# --------------------------------------------------------------------------- SSH
def ssh_target(cfg):
    ssh = cfg.get("ssh", {})
    account = cfg["account"]
    host = ssh.get("host") or f"ssh-{account}.alwaysdata.com"
    user = ssh.get("user") or account
    return f"{user}@{host}"


def ssh_prefix(cfg):
    """Construit le préfixe ssh (clé si dispo, sinon sshpass si mot de passe fourni)."""
    ssh = cfg.get("ssh", {})
    cmd = []
    if ssh.get("key_path"):
        cmd += ["-i", ssh["key_path"]]
    elif ssh.get("password"):
        if not shutil.which("sshpass"):
            sys.exit("sshpass n'est pas installé : installez-le (apt install sshpass) "
                     "ou fournissez une clé SSH (ALWAYSDATA_SSH_KEY).")
        cmd += ["-o", "PreferredAuthentications=password", "-o", "PubkeyAuthentication=no"]
    cmd += ["-o", "StrictHostKeyChecking=accept-new"]
    return cmd


def _askpass_env(cfg):
    """
    Prépare le mot de passe SSH sans sshpass : OpenSSH sait lire le mot de passe
    dans un script si on force SSH_ASKPASS (nécessite un session sans TTY →
    on lance ssh via `setsid`).

    Retourne (env, askpass_path) ou (None, None) si aucun mot de passe n'est
    configuré ou si sshpass est disponible.
    """
    ssh = cfg.get("ssh", {})
    pwd = ssh.get("password")
    if not pwd or ssh.get("key_path") or shutil.which("sshpass"):
        return None, None
    d = Path(tempfile.mkdtemp(prefix="alwaysdata-askpass-"))
    script = d / "askpass.sh"
    script.write_text("#!/bin/bash\nprintf '%s\\n' \"$ALWAYSDATA_SSH_PASSWORD\"\n", encoding="utf-8")
    script.chmod(0o700)
    env = dict(os.environ)
    env["ALWAYSDATA_SSH_PASSWORD"] = pwd
    env["DISPLAY"] = ":0"
    env["SSH_ASKPASS"] = str(script)
    env["SSH_ASKPASS_REQUIRE"] = "force"
    return env, str(script)


def _ssh_argv(cfg, remote_cmd):
    """Commande ssh complète, avec askpass si nécessaire."""
    ssh = cfg.get("ssh", {})
    argv = []
    env, _ = _askpass_env(cfg)
    if env is not None:
        # sans TTY → OpenSSH ne lit le mot de passe que via SSH_ASKPASS + setsid
        argv += ["setsid", "-w"]
    argv += ["ssh"]
    if ssh.get("key_path"):
        argv += ["-i", ssh["key_path"]]
    else:
        argv += ["-o", "PreferredAuthentications=password", "-o", "PubkeyAuthentication=no"]
    argv += ["-o", "StrictHostKeyChecking=accept-new", "-o", "NumberOfPasswordPrompts=1"]
    argv += [ssh_target(cfg), remote_cmd]
    return argv, env


def ssh_exec(cfg, remote_cmd, capture=False):
    argv, env = _ssh_argv(cfg, remote_cmd)
    if capture:
        out = subprocess.run(argv, capture_output=True, text=True, env=env,
                             timeout=cfg.get("ssh", {}).get("timeout", 180))
        if out.returncode != 0:
            sys.exit(f"SSH erreur:\n{out.stdout}\n{out.stderr}")
        return out.stdout
    subprocess.run(argv, check=True, env=env)


def _tar_filter(excludes):
    def keep(rel_parts):
        return not any(part in excludes for part in rel_parts)
    return keep


def _upload(cfg, src: Path, remote_dir: str, excludes):
    """Archive src (hors exclusions) et la dépose dans remote_dir via tar|ssh."""
    src = src.resolve()
    if not src.exists():
        sys.exit(f"Dossier source introuvable : {src}")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for item in src.rglob("*"):
            rel = item.relative_to(src)
            if any(part in excludes for part in rel.parts):
                continue
            if item.is_file():
                tar.add(item, arcname=str(rel), recursive=False)
    data = buf.getvalue()

    target = ssh_target(cfg)
    tar_cmd = f"mkdir -p {shlex.quote(remote_dir)} && tar xzf - -C {shlex.quote(remote_dir)}"
    ssh = cfg.get("ssh", {})
    if ssh.get("key_path"):
        cmd = (f"cat | ssh -i {shlex.quote(ssh['key_path'])} -o StrictHostKeyChecking=accept-new "
               f"{target} '{tar_cmd}'")
        proc = subprocess.run(cmd, shell=True, input=data, capture_output=True)
    elif ssh.get("password"):
        if shutil.which("sshpass"):
            cmd = (f"cat | sshpass -p {shlex.quote(ssh['password'])} "
                   f"-o StrictHostKeyChecking=accept-new {target} '{tar_cmd}'")
            proc = subprocess.run(cmd, shell=True, input=data, capture_output=True)
        else:
            # SSH_ASKPASS : le mot de passe est lu par OpenSSH, jamais en ligne de commande
            argv, env = _ssh_argv(cfg, tar_cmd)
            proc = subprocess.run(argv, input=data, capture_output=True, env=env)
    else:
        cmd = (f"cat | ssh -o StrictHostKeyChecking=accept-new {target} '{tar_cmd}'")
        proc = subprocess.run(cmd, shell=True, input=data, capture_output=True)
    if proc.returncode != 0:
        sys.exit(f"Erreur upload:\n{proc.stderr.decode(errors='replace')}")
    print(f"  {src.name} → {remote_dir} ({len(data)/1024:.0f} Ko)")


def cmd_push(cfg):
    """
    Envoie le code sur le serveur.

    - `push` (liste) : une entrée par dossier à transférer
        {"source": ".", "remote": "/home/god/pred-app"}
    - sinon : repli sur l'ancienne logique « un sous-dossier applicatif par site ».
    """
    root = Path(cfg.get("source_dir", "/home/user/app")).resolve()
    if not root.exists():
        sys.exit(f"Dossier source introuvable : {root}")
    excludes = set(cfg.get("exclude", [".git", "node_modules", ".venv", "__pycache__",
                                       ".env", "dist", "build"]))

    print(f"Upload de {root} → {ssh_target(cfg)}")
    targets = cfg.get("push")
    if isinstance(targets, list) and targets:
        for entry in targets:
            src = root / entry.get("source", ".")
            remote = entry.get("remote") or cfg.get("remote_dir")
            if not remote:
                sys.exit("remote manquant dans un push")
            if not src.exists():
                print(f"  ⚠️  {src} absent — ignoré")
                continue
            _upload(cfg, src, remote, excludes)
    else:
        for site in cfg["sites"]:
            sub = site.get("source_subdir")
            if not sub:
                continue
            src = root / sub
            if not src.exists():
                print(f"  ⚠️  {sub} absent — site {site.get('name')} ignoré")
                continue
            _upload(cfg, src, site["path"], excludes)
        for extra in ("pipelines", "db", "deploy"):
            src = root / extra
            if src.exists():
                _upload(cfg, src, f"{cfg['remote_dir']}/{extra}", excludes)
    print("  ✓ upload terminé")


def cmd_install(cfg):
    """Lance la commande de build/install configurée."""
    cmd = cfg.get("install_command")
    if not cmd:
        print("Aucun install_command configure.")
        return
    print(f"→ {cmd}")
    ssh_exec(cfg, cmd)
    print("OK: install terminé")


def cmd_status(cfg):
    """Sites + logs récents (dernières lignes)."""
    try:
        cmd_check(cfg)
    except SystemExit as e:
        print(f"API indisponible : {e}")
    out = ssh_exec(cfg, "tail -n 20 /home/%s/admin/logs/sites/* 2>/dev/null | tail -n 40"
                   % cfg["account"], capture=True)
    print("\n--- logs sites (20 dernières lignes) ---")
    print(out)


# --------------------------------------------------------------------------- preflight
def cmd_preflight(cfg):
    """
    Vérifie TOUT avant le moindre déploiement : configuration, secrets,
    connectivité API, connectivité SSH, versions, disque.

    Sort en code 1 si un élément bloquant manque (liste explicite).
    """
    blockers, warnings = [], []
    print("=== PREFLIGHT Alwaysdata ===\n")

    print(f"[1] Compte      : {cfg['account']}")
    print(f"    SSH         : {ssh_target(cfg)}")

    token = cfg.get("api_token")
    if not token:
        blockers.append("Token API Alwaysdata absent (ALWAYSDATA_API_TOKEN) — "
                        "Profile > Tokens, affiché une seule fois, 2FA requis")
    else:
        print(f"    Token API   : présent ({token[:4]}…)")
    ssh = cfg.get("ssh", {})
    if not ssh.get("key_path") and not ssh.get("password"):
        blockers.append("Aucun accès SSH : définissez ALWAYSDATA_SSH_PASSWORD ou "
                        "ALWAYSDATA_SSH_KEY (votre ligne « Accès ssh: … » était tronquée)")
    elif ssh.get("key_path"):
        keyp = Path(ssh["key_path"])
        if not keyp.exists():
            blockers.append(f"Clé SSH introuvable : {keyp}")
        else:
            print(f"    Clé SSH     : {keyp}")
    else:
        print("    SSH         : mot de passe (via sshpass)")

    if token:
        try:
            account = api_call(cfg, "GET", "/account/")
            print(f"[2] API         : OK — compte {account.get('account')}")
            sites = api_call(cfg, "GET", "/site/")
            items = sites.get("site", sites) if isinstance(sites, dict) else sites
            print(f"    Sites       : {len(items)}")
            for s in items:
                print(f"      #{s['id']:<5} {s.get('type',''):<16} {s.get('path','')} "
                      f"{','.join(s.get('addresses') or [])}")
        except SystemExit as e:
            blockers.append(f"API Alwaysdata injoignable : {e}")

    print("[3] SSH")
    try:
        out = ssh_exec(cfg, "echo OK && uname -a && df -h /home | tail -1 && "
                            "python3 --version && node --version 2>/dev/null || true",
                       capture=True)
        print("    " + out.strip().replace("\n", "\n    "))
        if "df -h" in out:
            for line in out.splitlines():
                if "/" in line and "%" in line:
                    used = line.split()[-2] if len(line.split()) > 1 else "?"
                    try:
                        pct = int(used.rstrip("%"))
                        if pct > 80:
                            warnings.append(f"Disque {pct} % utilisé")
                    except ValueError:
                        pass
    except (SystemExit, subprocess.SubprocessError) as e:
        blockers.append(f"SSH injoignable : {e}")

    print("[4] Secrets applicatifs (à définir sur le serveur, hors dépôt)")
    for var in ("DATABASE_URL", "REDIS_URL", "JWT_SECRET",
                "MEGAPARI_CLIENT_ID", "MEGAPARI_CLIENT_SECRET",
                "XBET_CLIENT_ID", "XBET_CLIENT_SECRET",
                "LIVE_FOOTBALL_API_KEY"):
        print(f"    - {var}")

    print("\n=== BILAN ===")
    for w in warnings:
        print(f"  ⚠️  {w}")
    for b in blockers:
        print(f"  ❌ {b}")
    if blockers:
        print(f"\n{len(blockers)} bloqueur(s) — déploiement impossible en l'état.")
        return 1
    print("\n✅ Preflight OK — déploiement possible.")
    return 0


def cmd_deploy(cfg):
    cmd_push(cfg)
    cmd_install(cfg)
    cmd_site(cfg)
    cmd_restart(cfg)


COMMANDS = {
    "check": cmd_check,
    "preflight": cmd_preflight,
    "push": cmd_push,
    "install": cmd_install,
    "site": cmd_site,
    "restart": cmd_restart,
    "deploy": cmd_deploy,
    "status": cmd_status,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"Commandes : {', '.join(COMMANDS)}")
    cfg = load_config()
    result = COMMANDS[sys.argv[1]](cfg)
    if isinstance(result, int):
        raise SystemExit(result)
