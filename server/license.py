"""License token validation for the scheMAGIC sidecar.

The public key is embedded at build time. Only the Vercel API holds
the private key, so tokens cannot be forged locally.
"""

import os
import jwt

PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArsLw9pgDhBfygzjX7v0n
Tv6Wje3gmhQJ1rgY4fsCL+Aw1BxP5xhZRNv0hPCg03qzHk58jppvyPnj+tw3OZFa
PrsObtVrJZdru6IGrJxVJtxEhnStNv+VT5qRs2J8u6DpJseEvKcK/rPiQ+CZEOSb
XXAxyQaw6dX9TF0gTJOvHKcjE+VFHzuCeoIuPkBRKnA8nessQkNpZ0zatXqUZsxa
rYqBK2bz2+1crTr4VarssaF1o/CGY2bFnSycJmJ1QNezd0QVHjjlFUd27nLJcorB
98CWhLs8lhuyxuEO58bC+l5Mu/0rbUK3XTY/LBN8lHd8aO8de1Z2gPyyUrLrVjgk
aQIDAQAB
-----END PUBLIC KEY-----"""


# Tauri passes the stable per-install UUID via SCHEMAGIC_MACHINE_ID at spawn.
# Empty when the sidecar runs outside Tauri (webapp demo / pytest); in that
# mode the machine_id check in require_license is skipped.
LOCAL_MACHINE_ID = os.environ.get("SCHEMAGIC_MACHINE_ID", "")


def validate_license_token(token: str) -> dict:
    """Validate a JWT license token against the embedded public key.

    Returns the decoded claims dict on success.
    Raises jwt.InvalidTokenError (or subclass) on failure.
    """
    return jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"])
