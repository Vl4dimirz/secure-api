"""Rate limiting — the RIGHT way to slow brute-force on auth: app-level and precise.

(The lesson learned from breaking INKVERSE login with a blunt Cloudflare edge rule:
protect the exact endpoint here in code, not with a broad block at the edge.)
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

# In-memory by default (fine for one instance). Point REDIS_URL at a shared Redis
# and every replica counts against the same limits - so the rate limit actually
# holds when the app is scaled horizontally.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url or "memory://",
)
