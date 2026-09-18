"""Async mpv JSON IPC client.

The TUI and the Quickshell service share one mpv process through the same
Unix socket. The service spawns and supervises it; the TUI asks the service
to start it when needed and falls back to spawning mpv itself when the shell
IPC is unavailable (for example when running the TUI over SSH).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

SOCKET_NAME = "omarchy-ytmusic/mpv.sock"
OMARCHY_ENSURE = ["omarchy-shell", "-q", "quickshell.ytmusic.player", "ensurePlayer"]


def socket_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(runtime, SOCKET_NAME)


def spawn_arguments() -> List[str]:
    return [
        "mpv",
        "--idle",
        "--no-terminal",
        "--no-video",
        "--audio-display=no",
        "--force-window=no",
        "--keep-open=no",
        "--gapless-audio=weak",
        "--prefetch-playlist=yes",
        "--input-ipc-server=" + socket_path(),
        "--ytdl-format=bestaudio/best",
        "--title=Omarchy YouTube Music",
        "--volume=100",
    ]


@dataclass
class PlayerState:
    paused: bool = True
    idle: bool = True
    playlist_pos: int = -1
    playlist_count: int = 0
    duration: float = 0.0
    playback_time: float = 0.0
    volume: float = 100.0
    media_title: str = ""
    path: str = ""


Observer = Callable[[str, Any], None]


class MpvIpc:
    """Minimal mpv JSON IPC client with property observation."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or socket_path()
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
        self._observers: List[Observer] = []
        self.state = PlayerState()
        self._observed_ids = {
            1: "pause",
            2: "idle-active",
            3: "playlist-pos",
            4: "playlist-count",
            5: "duration",
            6: "volume",
            7: "metadata",
            8: "path",
            9: "media-title",
        }

    # ------------------------------------------------------------- lifecycle

    @property
    def connected(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()

    def add_observer(self, observer: Observer) -> None:
        self._observers.append(observer)

    def _emit(self, name: str, value: Any) -> None:
        for observer in self._observers:
            try:
                observer(name, value)
            except Exception:  # observers must never kill the read loop
                pass

    async def try_connect(self) -> bool:
        if self.connected:
            return True
        if not os.path.exists(self.path):
            return False
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self.path), timeout=1.0
            )
        except (OSError, asyncio.TimeoutError):
            self.reader = None
            self.writer = None
            return False
        self._read_task = asyncio.get_running_loop().create_task(self._read_loop())
        for obs_id, name in self._observed_ids.items():
            try:
                await self.command("observe_property", obs_id, name)
            except Exception:
                pass
        return True

    async def ensure_running(self) -> bool:
        if await self.try_connect():
            return True
        runtime_dir = os.path.dirname(self.path)
        try:
            os.makedirs(runtime_dir, exist_ok=True)
        except OSError:
            pass

        # Prefer the shell service: it owns the mpv lifecycle on the desktop.
        if shutil.which("omarchy-shell"):
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(
                        OMARCHY_ENSURE, capture_output=True, timeout=6
                    ),
                )
            except Exception:
                pass

        for _ in range(14):
            if await self.try_connect():
                return True
            await asyncio.sleep(0.25)

        # Fallback: spawn mpv ourselves (SSH sessions, shell not running).
        if shutil.which("mpv"):
            try:
                subprocess.Popen(
                    spawn_arguments(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError:
                return False
            for _ in range(20):
                if await self.try_connect():
                    return True
                await asyncio.sleep(0.25)
        return False

    async def close(self) -> None:
        if self._read_task:
            self._read_task.cancel()
            self._read_task = None
        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass
            self.writer = None
            self.reader = None

    # --------------------------------------------------------------- protocol

    async def _read_loop(self) -> None:
        assert self.reader is not None
        try:
            while True:
                line = await self.reader.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").strip()
                if not text:
                    continue
                try:
                    message = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                event = message.get("event")
                if event == "property-change":
                    self._apply_property(
                        str(message.get("name", "")), message.get("data")
                    )
                elif "request_id" in message:
                    request_id = int(message.get("request_id", 0))
                    future = self._pending.pop(request_id, None)
                    if future and not future.done():
                        if message.get("error") == "success":
                            future.set_result(message.get("data"))
                        else:
                            future.set_exception(
                                MpvError(str(message.get("error", "failed")))
                            )
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            self.writer = None
            self.reader = None
            self.state = PlayerState()
            self._emit("disconnected", None)

    def _apply_property(self, name: str, value: Any) -> None:
        state = self.state
        if name == "pause":
            state.paused = bool(value)
        elif name == "idle-active":
            state.idle = value is True
        elif name == "playlist-pos":
            state.playlist_pos = -1 if value is None else int(value)
        elif name == "playlist-count":
            state.playlist_count = 0 if value is None else int(value)
        elif name == "duration":
            state.duration = 0.0 if value is None else float(value)
        elif name == "volume":
            state.volume = 100.0 if value is None else float(value)
        elif name == "media-title":
            state.media_title = "" if value is None else str(value)
        elif name == "path":
            state.path = "" if value is None else str(value)
        self._emit(name, value)

    async def command(self, *args: Any) -> Any:
        if not self.connected:
            raise MpvError("mpv is not running")
        self._request_id += 1
        request_id = self._request_id
        payload = json.dumps({"command": list(args), "request_id": request_id})
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        assert self.writer is not None
        self.writer.write((payload + "\n").encode("utf-8"))
        await self.writer.drain()
        return await asyncio.wait_for(future, timeout=5.0)

    async def get_property(self, name: str) -> Any:
        return await self.command("get_property", name)

    async def set_property(self, name: str, value: Any) -> None:
        await self.command("set_property", name, value)

    # ------------------------------------------------------------- actions

    async def load(self, video_id: str, mode: str = "replace") -> None:
        url = f"https://music.youtube.com/watch?v={video_id}"
        await self.command("loadfile", url, mode)

    async def play_tracks(self, video_ids: List[str]) -> None:
        """Load the first entry and append the rest in order."""
        if not video_ids:
            return
        await self.load(video_ids[0], "replace")
        for video_id in video_ids[1:]:
            await self.load(video_id, "append-play")

    async def toggle(self) -> None:
        await self.set_property("pause", not self.state.paused)

    async def next(self) -> None:
        await self.command("playlist-next", "force")

    async def previous(self) -> None:
        await self.command("playlist-prev", "force")

    async def stop(self) -> None:
        await self.command("stop")

    async def quit(self) -> None:
        try:
            await self.command("quit")
        except (MpvError, asyncio.TimeoutError):
            pass

    async def set_volume(self, volume: float) -> None:
        await self.set_property("volume", max(0.0, min(130.0, volume)))

    async def jump(self, index: int) -> None:
        if 0 <= index < self.state.playlist_count:
            await self.command("playlist-play-index", index)

    async def remove(self, index: int) -> None:
        if 0 <= index < self.state.playlist_count:
            await self.command("playlist-remove", index)

    async def clear_queue(self) -> None:
        await self.command("playlist-clear")

    async def refresh_position(self) -> None:
        if not self.connected or self.state.idle:
            return
        try:
            value = await self.get_property("playback-time")
        except (MpvError, asyncio.TimeoutError):
            return
        if isinstance(value, (int, float)):
            self.state.playback_time = float(value)
            self._emit("playback-time", value)


class MpvError(Exception):
    pass
