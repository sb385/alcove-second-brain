"""Create or rotate the website password and upload token.

    python -m secondbrain.web_auth                 # upload token only (site stays open)
    python -m secondbrain.web_auth --password      # also require a login password
    python -m secondbrain.web_auth --keep-token    # keep the current upload token

Writes the plain values to .env (DASHBOARD_PASSWORD, UPLOAD_TOKEN; git-ignored)
and only salted hashes to web_auth.json (committed, read by app.py).
Push afterwards so the hosted app picks up the new hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets

from .config import ROOT

ITERATIONS = 310_000


def _set_env(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        return re.sub(rf"^{key}=.*$", line, text, flags=re.M)
    return text.rstrip("\n") + "\n" + line + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-token", action="store_true")
    ap.add_argument("--password", action="store_true", help="also set a website password")
    a = ap.parse_args()

    env_path = ROOT / ".env"
    env = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    m = re.search(r"^UPLOAD_TOKEN=(\S+)$", env, flags=re.M)
    token = m.group(1) if (a.keep_token and m) else secrets.token_hex(24)
    # Readable but strong: 4 groups of 4 from an unambiguous alphabet.
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    password = "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))

    salt = secrets.token_bytes(16)
    record = {"upload_token_sha256": hashlib.sha256(token.encode()).hexdigest()}
    if a.password:
        record["password"] = {
            "salt": salt.hex(),
            "iterations": ITERATIONS,
            "hash": hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex(),
        }
    (ROOT / "web_auth.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    if a.password:
        env = _set_env(env, "DASHBOARD_PASSWORD", password)
    env = _set_env(env, "UPLOAD_TOKEN", token)
    env_path.write_text(env, encoding="utf-8")
    print("Wrote web_auth.json (hashes only); token" + (" and password" if a.password else "")
          + " saved in .env" + ("" if a.password else ". Website has no password."))


if __name__ == "__main__":
    main()
