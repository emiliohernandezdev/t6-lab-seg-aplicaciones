# Rate limit sencillo en memoria, ventana deslizante.
# La clave es el sub del token y no la IP: detras del gateway todos llegarian
# con la misma IP, y ademas lo que quiero limitar es a cada usuario.
import math
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

from . import config, db
from .auth import User, require_scope


class SlidingWindow:
    def __init__(self, limit, window):
        self.limit = limit
        self.window = window
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def wait_time(self, key):
        """0 si puede pasar; si no, cuantos segundos le faltan."""
        t = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and t - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return self.window - (t - q[0])
            q.append(t)
            return 0


limiter = SlidingWindow(config.RATE_LIMIT_MAX, config.RATE_LIMIT_WINDOW_S)


def limited_read(user: User = Depends(require_scope("orders:read"))):
    if config.INSECURE_MODE:
        return user
    wait = limiter.wait_time(user.sub)
    if wait:
        db.audit(user.sub, "rate_limit", f"{config.RATE_LIMIT_MAX} cada {config.RATE_LIMIT_WINDOW_S:g}s")
        raise HTTPException(429, "demasiadas solicitudes", headers={"Retry-After": str(max(1, math.ceil(wait)))})
    return user
