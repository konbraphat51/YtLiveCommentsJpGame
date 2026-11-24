"""Immutable store of raw API responses as gzipped JSON files under Data/Raw/."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


class RawStore:
    """Writes each response once to Raw/{kind}/{YYYY-MM-DD}/{timestamp}_{digest}.json.gz and never modifies it."""

    def __init__(self, root: Path) -> None:
        """Creates a store rooted at Data/Raw."""
        self._root = root

    def put_json(self, kind: str, payload: dict[str, Any], request: dict[str, Any], fetched_at: datetime) -> Path:
        """Stores a response together with the request that produced it.

        Args:
            kind: Category such as "Api/channels.list".
            payload: The response body.
            request: The request parameters, without credentials.
            fetched_at: When the response was received.
        """
        body = json.dumps({"request": request, "fetched_at": fetched_at.isoformat(), "response": payload}, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(body).hexdigest()[:16]
        directory = self._root / kind / fetched_at.date().isoformat()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{fetched_at.strftime('%H%M%S%f')}_{digest}.json.gz"
        if not path.exists():
            path.write_bytes(gzip.compress(body))
        return path
