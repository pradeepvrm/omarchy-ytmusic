"""Snapshot writer for the Quickshell service.

The service watches this file (FileView with watchChanges) to show clean
titles, artwork, and the sign-in state in the bar widget, even after the TUI
has been closed. Writes are atomic (tmp + rename) so a reader never sees a
half-written file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Track


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return Path(base) / "omarchy-ytmusic"


def state_path() -> Path:
    return runtime_dir() / "state.json"


class StateWriter:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or state_path()
        self._last_payload: Optional[str] = None

    def write(self, tracks: List[Track], queue_index: int, signed_in: bool,
              source: str = "") -> None:
        payload: Dict[str, Any] = {
            "tracks": [track.to_state() for track in tracks[:500]],
            "queueIndex": int(queue_index),
            "signedIn": bool(signed_in),
            "source": source[:120],
        }
        text = json.dumps(payload, ensure_ascii=False)
        if text == self._last_payload:
            return
        self._last_payload = text
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def clear(self) -> None:
        self._last_payload = None
        try:
            self.path.unlink()
        except OSError:
            pass

    def ensure_signed(self, signed: bool) -> None:
        """Make sure a snapshot exists and its signedIn flag is current.

        Called at startup and after auth changes so the bar widget stops
        nagging about sign-in without waiting for the next playback event.
        Never clobbers an existing track list.
        """
        try:
            current = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            current = None
        if not isinstance(current, dict):
            self.write([], 0, signed, "")
            return
        if bool(current.get("signedIn")) == bool(signed):
            return
        tracks: List[Track] = []
        raw_tracks = current.get("tracks")
        if isinstance(raw_tracks, list):
            for item in raw_tracks:
                if isinstance(item, dict):
                    try:
                        tracks.append(Track.from_state(item))
                    except (TypeError, ValueError, KeyError):
                        continue
        try:
            index = int(current.get("queueIndex", 0) or 0)
        except (TypeError, ValueError):
            index = 0
        source = current.get("source")
        self.write(tracks, index, signed,
                   source if isinstance(source, str) else "")
