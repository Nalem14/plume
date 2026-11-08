"""What the background blur needs (engine/blur.js): MediaPipe's wasm and its selfie segmentation model, 11 MB
fetched once from orneos.eu (tools/meet-vision.sh publishes them) and checked against the sums below, then kept
in the cache. Nothing comes from a third party; the JS part of MediaPipe is in engine/vendor/.
"""
import hashlib
import threading
import urllib.request

import system

VERSION = "0.10.35"
BASE = f"https://orneos.eu/downloads/meet/vision-{VERSION}/"
FILES = {
    "loader": ("vision_wasm_internal.js", "e7fd9858e8e8f221d9b96eddc11f8e077f263e0b7bbd79d3cbe882b134274f8c"),
    "wasm": ("vision_wasm_internal.wasm", "6a5c64584c2ab61c763b6e204afbdbc7ce1caf7f5216187322bca8df94f646bc"),
    "model": ("selfie_segmenter.tflite", "191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b"),
}
DIR = system.CACHE / f"meet-vision-{VERSION}"
_lock = threading.Lock()


def _ok(path, digest):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() == digest
    except OSError:
        return False


def paths():
    """{loader, wasm, model} as file paths when all are there and sound, else None."""
    out = {}
    for key, (name, digest) in FILES.items():
        path = DIR / name
        if not path.exists():
            return None
        out[key] = str(path)
    return out


def ensure():
    """Blocking: fetch what is missing (run it off the UI thread). The paths, or None (offline, bad file)."""
    with _lock:
        DIR.mkdir(parents=True, exist_ok=True)
        for name, digest in FILES.values():
            path = DIR / name
            if path.exists() and _ok(path, digest):
                continue
            try:
                req = urllib.request.Request(BASE + name, headers={"User-Agent": "Orneos Meet"})
                with urllib.request.urlopen(req, timeout=120) as res:
                    data = res.read()
            except OSError:
                return None
            if hashlib.sha256(data).hexdigest() != digest:
                return None
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(path)
        return paths()
