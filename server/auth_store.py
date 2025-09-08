# server/auth_store.py
import uuid, hashlib
from typing import Optional

# nickname -> (user_id, password_hash, token)
_USERS: dict[str, tuple[str, str, Optional[str]]] = {}

def _hash(pw: str) -> str:
    # NOTE: demo only; use bcrypt/passlib for production
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def create_user(nickname: str, password: str) -> tuple[str, str]:
    if nickname in _USERS:
        raise ValueError("nickname already exists")
    uid = str(uuid.uuid4())
    tok = str(uuid.uuid4())
    _USERS[nickname] = (uid, _hash(password), tok)
    return uid, tok

def login_user(nickname: str, password: str) -> tuple[str, str]:
    if nickname not in _USERS:
        raise ValueError("invalid credentials")
    uid, pw_hash, _ = _USERS[nickname]
    if _hash(password) != pw_hash:
        raise ValueError("invalid credentials")
    tok = str(uuid.uuid4())
    _USERS[nickname] = (uid, pw_hash, tok)
    return uid, tok

def get_user_by_token(token: str) -> Optional[tuple[str, str]]:
    for nick, (uid, _pw, tok) in _USERS.items():
        if tok == token:
            return uid, nick
    return None
