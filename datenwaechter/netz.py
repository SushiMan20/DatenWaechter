"""HTTPS wie im Browser: Zertifikate prüft das Betriebssystem (Windows-Zertifikatspeicher), nicht Python allein.

Python liest unter Windows nur die Stammzertifikate, die schon im Speicher liegen. Windows lädt fehlende (z. B. die
neue Let's-Encrypt-Kette „Root YR → ISRG Root X1“) aber erst nach, wenn ein Browser sie braucht – dann scheitert
Python mit „CERTIFICATE_VERIFY_FAILED“, obwohl die Seite im Browser geht. truststore lässt Windows (bzw. macOS)
die Kette prüfen und fehlende Zertifikate nachladen; Firmen-Zertifikate im Windows-Speicher gelten damit auch.
"""

from __future__ import annotations

import ssl
import urllib.request
from functools import lru_cache


@lru_cache(maxsize=1)
def ssl_kontext() -> ssl.SSLContext:
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001 – ohne truststore: Python-Standard plus certifi-Liste
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx.load_verify_locations(certifi.where())
        except Exception:  # noqa: BLE001
            pass
        return ctx


def oeffnen(req: urllib.request.Request | str, timeout: float):
    """urllib.request.urlopen mit Zertifikatsprüfung durch das Betriebssystem."""
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_kontext())
