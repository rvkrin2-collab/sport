"""Sport backend package.

The server already has a 5-minute Git update timer.  To avoid requiring a new
systemd unit for every feature, this module also runs a lightweight hourly
Tredict sync loop inside the application process.  It starts only after a short
delay and silently skips sync while no token is configured.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request

_SYNC_URL = "http://127.0.0.1:8911/api/integrations/tredict/sync"
_INITIAL_DELAY_SECONDS = 300
_INTERVAL_SECONDS = 3600


def _sync_loop() -> None:
    time.sleep(_INITIAL_DELAY_SECONDS)
    while True:
        try:
            request = urllib.request.Request(_SYNC_URL, method="POST")
            with urllib.request.urlopen(request, timeout=120) as response:
                response.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        except Exception:
            pass
        time.sleep(_INTERVAL_SECONDS)


threading.Thread(target=_sync_loop, name="sport-tredict-sync", daemon=True).start()
