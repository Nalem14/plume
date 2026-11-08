"""What the mail servers still have to do: messages to send, drafts to keep, reads, stars, tags and moves made
while the server could not be reached (or in the seconds a send can still be cancelled).

Kept on disk outside the cache (a cleaned cache, a crash or quitting offline loses nothing), one JSON file per
operation, with the message itself beside it for sends and drafts. Operations of a mailbox run in their order.
Only this user can read them (0600): they hold whole messages.
"""
import json
import os
import threading
import time
import uuid
from pathlib import Path

import system

ROOT = system.DATA / "plume-mail-queue"


class Queue:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or ROOT)
        self._lock = threading.Lock()
        self._ops = {}
        self._load()

    def _load(self):
        try:
            files = sorted(self.root.glob("*.json"))
        except OSError:
            files = []
        for path in files:
            try:
                op = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(op, dict) and op.get("id") == path.stem:
                self._ops[op["id"]] = op

    def _write(self, op):
        system.private_write(self.root / f"{op['id']}.json", json.dumps(op, ensure_ascii=False))

    def add(self, op: dict, raw: bytes | None = None) -> dict:
        """op: {"box", "kind", "owner", …}. Returns it with its id and its place in the order."""
        op = dict(op)
        op["id"] = f"{time.time_ns():020d}-{uuid.uuid4().hex[:8]}"
        op["seq"] = op["id"]
        op.setdefault("tries", 0)
        with self._lock:
            if raw is not None:
                self.root.mkdir(parents=True, exist_ok=True)
                path = self.root / f"{op['id']}.eml"
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                op["raw"] = True
            self._write(op)
            self._ops[op["id"]] = op
        return dict(op)

    def update(self, op_id: str, **changes) -> None:
        with self._lock:
            op = self._ops.get(op_id)
            if op is None:
                return
            op.update(changes)
            self._write(op)

    def remove(self, op_id: str) -> dict | None:
        with self._lock:
            op = self._ops.pop(op_id, None)
            for suffix in (".json", ".eml"):
                try:
                    (self.root / f"{op_id}{suffix}").unlink()
                except OSError:
                    pass
        return op

    def get(self, op_id: str) -> dict | None:
        with self._lock:
            op = self._ops.get(op_id)
            return dict(op) if op else None

    def raw(self, op_id: str) -> bytes | None:
        try:
            return (self.root / f"{op_id}.eml").read_bytes()
        except OSError:
            return None

    def items(self, box=None, kind=None, owner=None) -> list:
        with self._lock:
            ops = [dict(op) for op in self._ops.values()
                   if (box is None or op.get("box") == box) and (kind is None or op.get("kind") in
                       ((kind,) if isinstance(kind, str) else kind)) and (owner is None or op.get("owner") == owner)]
        return sorted(ops, key=lambda op: op["seq"])

    def __len__(self):
        with self._lock:
            return len(self._ops)
