"""Artist page: top songs, albums, and singles."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Static

from ..models import Collection, Track
from ..widgets import CollectionTable, TrackTable


class ArtistScreen(Screen):
    BINDINGS = [
        ("escape", "back", "Back"),
    ]

    CSS = """
    #artist-header { height: auto; padding: 0 1; }
    #artist-name { text-style: bold; color: #ff5252; }
    #artist-top { color: $text-muted; margin: 1 1 0 1; }
    #artist-songs { height: 40%; margin: 0 1; }
    #artist-albums { height: 1fr; margin: 0 1; }
    #artist-status { padding: 0 1; color: $text-muted; }
    """

    def __init__(self, browse_id: str, name: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.browse_id = browse_id
        self.artist_name = name

    def compose(self) -> ComposeResult:
        yield Static(self.artist_name or "Artist", id="artist-name")
        yield Static("Loading…", id="artist-status")
        yield Static("Top songs", id="artist-top")
        yield TrackTable(id="artist-songs")
        yield CollectionTable(id="artist-albums")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self.load, thread=True)

    def load(self) -> None:
        try:
            payload = self.app.api.artist(self.browse_id)
        except Exception as error:
            self.app.call_from_thread(
                lambda message=str(error):
                self.query_one("#artist-status", Static).update(
                    f"Could not load: {message}")
            )
            return
        self.app.call_from_thread(self.render_artist, payload)

    # NOTE: must not be named `render` — that would override
    # textual's Widget.render() and crash the app on layout.
    def render_artist(self, payload: dict) -> None:
        name = str(payload.get("name") or self.artist_name or "Artist")
        self.query_one("#artist-name", Static).update(name)
        tracks: list[Track] = payload.get("track_list") or []
        albums: list[Collection] = payload.get("album_list") or []
        singles: list[Collection] = payload.get("single_list") or []
        description = str(payload.get("description") or "").strip()
        status = self.query_one("#artist-status", Static)
        status.update((description[:140] + "…") if len(description) > 140 else description)

        songs = self.query_one("#artist-songs", TrackTable)
        songs.set_tracks(tracks, numbered=True)
        songs.source_label = name

        table = self.query_one("#artist-albums", CollectionTable)
        table.set_collections(albums + singles)
        self.query_one("#artist-top", Static).update(
            f"Top songs · {len(tracks)}   Albums & singles · {len(albums) + len(singles)}")
        songs.focus()

    def action_back(self) -> None:
        self.app.pop_screen()
