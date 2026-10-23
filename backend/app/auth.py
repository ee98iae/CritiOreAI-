"""Email + password login with two roles.

- team:   CritiOre staff; sees and edits every region.
- client: a pilot client; read-only, and only the regions listed on the account.

Accounts live in a JSON file (CRITIORE_USERS_FILE, default data/users.json),
managed with `python -m scripts.add_user`. Passwords are stored as scrypt
hashes. Sessions are signed JWTs; set CRITIORE_SECRET in any shared deployment
or every restart signs everyone out.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = logging.getLogger(__name__)

Role = Literal["team", "client"]
DEFAULT_USERS = Path(__file__).resolve().parent.parent / "data" / "users.json"
TOKEN_HOURS = 12
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


@dataclass(frozen=True)
class User:
    email: str
    name: str
    role: Role
    regions: tuple[str, ...]  # ("*",) means every region

    def can_see(self, region_id: str) -> bool:
        return self.role == "team" or "*" in self.regions or region_id in self.regions

    def public(self) -> dict:
        return {"email": self.email, "name": self.name, "role": self.role, "regions": list(self.regions)}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def users_path() -> Path:
    return Path(os.environ.get("CRITIORE_USERS_FILE", DEFAULT_USERS))


def load_accounts() -> dict[str, dict]:
    path = users_path()
    if not path.exists():
        return {}
    return {a["email"].lower(): a for a in json.loads(path.read_text())}


def save_accounts(accounts: dict[str, dict]) -> None:
    path = users_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(accounts.values(), key=lambda a: a["email"]), indent=2))


def _to_user(a: dict) -> User:
    return User(email=a["email"].lower(), name=a.get("name", a["email"]), role=a["role"],
                regions=tuple(a.get("regions", ["*"])))


@lru_cache(maxsize=1)
def _secret() -> str:
    secret = os.environ.get("CRITIORE_SECRET")
    if not secret:
        log.warning("CRITIORE_SECRET is not set; using a random key, so sessions end when the API restarts")
        secret = secrets.token_urlsafe(32)
    return secret


def authenticate(email: str, password: str) -> User | None:
    account = load_accounts().get(email.strip().lower())
    if account is None or not verify_password(password, account.get("password_hash", "")):
        return None
    return _to_user(account)


def issue_token(user: User) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user.email, "iat": now, "exp": now + TOKEN_HOURS * 3600}, _secret(), algorithm="HS256")


_bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required", {"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    try:
        claims = jwt.decode(creds.credentials, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise unauthorized
    # Re-read the account so a removed user or changed role takes effect at once.
    account = load_accounts().get(str(claims.get("sub", "")).lower())
    if account is None:
        raise unauthorized
    return _to_user(account)


def require_region(user: User, region_id: str) -> None:
    if not user.can_see(region_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"No access to region '{region_id}'")
