"""Rate limiting — the RIGHT way to slow brute-force on auth: app-level and precise.

(The lesson learned from breaking INKVERSE login with a blunt Cloudflare edge rule:
protect the exact endpoint here in code, not with a broad block at the edge.)
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
