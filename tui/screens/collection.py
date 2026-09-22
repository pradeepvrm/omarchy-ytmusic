"""Playlist and album views with their track lists."""

from __future__ import annotations

from typing import List

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Static

from ..models import Collection, Track
from ..widgets import TrackTable


class CollectionScreen(Screen):
    BINDINGS = [
        ("s", "shuffle", "Shuffle"),
        ("escape", "back", "Back"),
    ]

    CSS = """
    #coll-header { height: auto; padding: 0 1; }
    #coll-title { text-style: bold; color: #ff5252; }
    #coll-meta { color: $text-muted; }
    #coll-tracks { height: 1fr; margin: 0 1; }
    """

    def __init__(self, collection: Collection, **kwargs) -> None:
        super().__init__(**kwargs)
        self.collection = collection
        self.tracks: List[Track] = []

    def compose(self) -> ComposeResult:
        yield Static(f"{self.collection.title}", id="coll-title")
        yield Static("Loading…", id="coll-meta")
        yield TrackTable(id="coll-tracks")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self.load, thread=True)

    def load(self) -> None:
        api = self.app.api
        try:
            if self.collection.kind == "album":
                payload = api.album(self.collection.browse_id)
            elif self.collection.kind == "podcast":
                payload = api.podcast(self.collection.playlist_id
                                      or self.collection.browse_id)
            else:
                playlist_id = self.collection.playlist_id or self.collection.browse_id
                payload = api.playlist(playlist_id)
        except Exception as error:
            self.app.call_from_thread(
                lambda message=str(error):
                self.query_one("#coll-meta", Static).update(
                    f"Could not load: {message}")
            )
            return
        self.tracks = payload.get("tracks") or []
        kind_label = {"album": "Album", "podcast": "Podcast"}.get(
            self.collection.kind, "Playlist")
        count = payload.get("trackCount") or len(self.tracks)
        duration = payload.get("duration") or ""
        from ..format import total_duration_text
        total = duration or total_duration_text(t.duration_text or t.duration_s for t in self.tracks)
        meta = f"{kind_label} · {count} tracks" + (f" · {total}" if total else "")
        self.app.call_from_thread(self.render_collection, meta)

    # NOTE: must not be named `render` — that would override
    # textual's Widget.render() and crash the app on layout.
    def render_collection(self, meta: str) -> None:
        self.query_one("#coll-meta", Static).update(meta)
        table = self.query_one("#coll-tracks", TrackTable)
        table.set_tracks(self.tracks, numbered=True)
        table.source_label = self.collection.title
        table.focus()

    async def action_shuffle(self) -> None:
        if not self.tracks:
            return
        import random

        shuffled = list(self.tracks)
        random.shuffle(shuffled)
        await self.app.play_tracks(shuffled, 0, source=f"Shuffle · {self.collection.title}")

    def action_back(self) -> None:
        self.app.pop_screen()
