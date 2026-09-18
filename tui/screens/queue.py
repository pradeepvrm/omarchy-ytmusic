"""The live queue view over the mpv playlist."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from ..widgets import TrackTable


class QueueTable(TrackTable):
    BINDINGS = TrackTable.BINDINGS + [
        ("x", "remove_cursor", "Remove"),
        ("c", "clear", "Clear"),
    ]

    async def action_remove_cursor(self) -> None:
        app = self.app
        index = self.cursor_row
        if not (0 <= index < len(self.tracks)):
            return
        if hasattr(app, "remove_queue_index"):
            await app.remove_queue_index(index)
            del self.tracks[index]
            try:
                row_key = self.coordinate_to_cell_key(self.cursor_coordinate).row_key
                self.remove_row(row_key)
            except Exception:
                self.set_tracks(self.tracks)

    async def action_clear(self) -> None:
        app = self.app
        if hasattr(app, "clear_queue"):
            await app.clear_queue()
            self.clear()
            self.tracks = []


class QueuePane(Container):
    CSS = """
    QueuePane { height: 1fr; }
    #queue-hint { height: auto; padding: 0 1; color: $text-muted; }
    #queue-table { height: 1fr; margin: 0 1; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.table: QueueTable | None = None
        self._last_signature: tuple = ()

    def compose(self) -> ComposeResult:
        yield Static("Queue", id="queue-hint")
        yield QueueTable(id="queue-table")

    def on_mount(self) -> None:
        self.table = self.query_one("#queue-table", QueueTable)

    def refresh_queue(self) -> None:
        """Called by the app whenever the queue or position changes."""
        if self.table is None:
            return
        app = self.app
        tracks = getattr(app, "queue_tracks", [])
        position = app.player.state.playlist_pos
        signature = (len(tracks), position,
                     tracks[position].video_id if 0 <= position < len(tracks) else "")
        if signature == self._last_signature:
            return
        self._last_signature = signature
        self.table.set_tracks(tracks, numbered=False)
        hint = self.query_one("#queue-hint", Static)
        if not tracks:
            hint.update("Queue — nothing queued. Play something from Home, "
                        "Search, or your Library.")
        else:
            hint.update(
                f"Queue · {len(tracks)} tracks — Enter jumps, x removes, c clears")
        if 0 <= position < len(tracks):
            try:
                self.table.move_cursor(row=position, animate=False)
            except Exception:
                pass
