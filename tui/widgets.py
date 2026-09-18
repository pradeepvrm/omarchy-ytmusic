"""Shared TUI widgets: the now-playing bar and the track/collection tables."""

from __future__ import annotations

from typing import List, Optional

from textual.widgets import Button, DataTable, Static

from .format import format_duration
from .models import Collection, Track


class NowPlaying(Static):
    """One-line player status docked to the bottom of the main screen."""

    def render_bar(self, state, track: Optional[Track], liked: bool = False) -> None:
        if state is None or state.idle or not state.playlist_count:
            self.update("  Nothing playing — press / to search, F2 for home")
            return
        icon = "||" if state.paused else ">"
        title = track.label() if track else (state.media_title or "Playing…")
        position = format_duration(int(state.playback_time))
        total = format_duration(int(state.duration)) if state.duration else ""
        progress = f"{position}/{total}" if total else position
        heart = "  *" if liked else ""
        volume = f"  vol {round(state.volume)}%"
        self.update(f"  {icon} {title}   {progress}{heart}{volume}")


class TrackTable(DataTable):
    """A table of playable tracks with row-level keybindings.

    ``tracks`` stays parallel to the table rows; subclasses and screens read
    the cursor row through :meth:`cursor_track`.
    """

    BINDINGS = [
        ("enter", "play_cursor", "Play"),
        ("e", "enqueue_cursor", "Queue"),
        ("N", "play_next_cursor", "Play next"),
        ("a", "add_cursor_to_playlist", "Add to playlist"),
        ("l", "like_cursor", "Like"),
        ("r", "radio_cursor", "Radio"),
    ]

    def __init__(self, tracks: Optional[List[Track]] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tracks: List[Track] = list(tracks or [])
        self.show_cursor = True
        self.cursor_type = "row"
        self.zebra_stripes = True

    def set_tracks(self, tracks: List[Track], numbered: bool = False) -> None:
        self.tracks = list(tracks)
        headers = (["#"] if numbered else []) + ["Title", "Artist", "Time"]
        if len(self.columns) != len(headers):
            self.clear(columns=True)
            self.add_columns(*headers)
        else:
            self.clear()
        for index, track in enumerate(self.tracks):
            row = [str(index + 1)] if numbered else []
            row.extend([
                track.title,
                track.artist,
                track.duration_text,
            ])
            self.add_row(*row, key=track.video_id)

    def cursor_track(self) -> Optional[Track]:
        if not self.tracks:
            return None
        row = self.cursor_row
        if 0 <= row < len(self.tracks):
            return self.tracks[row]
        return None

    # Row actions are delegated to the app so every table behaves the same.

    async def action_play_cursor(self) -> None:
        app = self.app
        track = self.cursor_track()
        if track and hasattr(app, "play_tracks"):
            await app.play_tracks(self.tracks, self.cursor_row,
                                  source=getattr(self, "source_label", ""))

    async def action_enqueue_cursor(self) -> None:
        track = self.cursor_track()
        if track and hasattr(self.app, "enqueue"):
            await self.app.enqueue(track, play_next=False)

    async def action_play_next_cursor(self) -> None:
        track = self.cursor_track()
        if track and hasattr(self.app, "enqueue"):
            await self.app.enqueue(track, play_next=True)

    async def action_add_cursor_to_playlist(self) -> None:
        track = self.cursor_track()
        if track and hasattr(self.app, "open_playlist_picker"):
            self.app.open_playlist_picker(track)

    async def action_like_cursor(self) -> None:
        track = self.cursor_track()
        if track and hasattr(self.app, "toggle_like"):
            await self.app.toggle_like(track)

    async def action_radio_cursor(self) -> None:
        track = self.cursor_track()
        if track and hasattr(self.app, "start_radio"):
            await self.app.start_radio(track)


class CollectionTable(DataTable):
    """A table of playlists/albums that open on Enter."""

    BINDINGS = [
        ("enter", "open_cursor", "Open"),
    ]

    def __init__(self, collections: Optional[List[Collection]] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.collections: List[Collection] = list(collections or [])
        self.show_cursor = True
        self.cursor_type = "row"
        self.zebra_stripes = True

    def set_collections(self, collections: List[Collection]) -> None:
        self.collections = list(collections)
        headers = ["Title", "Detail", "Kind", "Tracks"]
        if len(self.columns) != len(headers):
            self.clear(columns=True)
            self.add_columns(*headers)
        else:
            self.clear()
        for collection in self.collections:
            kind = {"playlist": "Playlist", "album": "Album",
                    "single": "Single", "ep": "EP"}.get(collection.kind, "List")
            count = f"{collection.track_count} tracks" if collection.track_count else ""
            self.add_row(collection.title, collection.subtitle, kind, count,
                         key=collection.browse_id)

    def cursor_collection(self) -> Optional[Collection]:
        if not self.collections:
            return None
        row = self.cursor_row
        if 0 <= row < len(self.collections):
            return self.collections[row]
        return None

    async def action_open_cursor(self) -> None:
        collection = self.cursor_collection()
        if collection and hasattr(self.app, "open_collection"):
            await self.app.open_collection(collection)


class CardButton(Button):
    """A clickable card used on the homepage shelves."""

    def __init__(self, title: str, subtitle: str, payload, **kwargs) -> None:
        self.payload = payload
        label = f"{title}\n{subtitle}" if subtitle else title
        super().__init__(label, **kwargs)

    def on_button_pressed(self, event) -> None:  # noqa: N802 (textual event name)
        event.stop()
        app = self.app
        payload = self.payload
        if isinstance(payload, Collection) and hasattr(app, "open_collection"):
            app.call_later(app.open_collection, payload)
        elif isinstance(payload, Track) and hasattr(app, "play_tracks"):
            app.call_later(app.play_tracks, [payload], 0, source="Home")


class SectionTitle(Static):
    pass
