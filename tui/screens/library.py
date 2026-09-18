"""Library: your playlists, liked songs, albums, artists, and history."""

from __future__ import annotations

from typing import List

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static, TabbedContent, TabPane

from ..models import Collection, Track
from ..widgets import CollectionTable, TrackTable


class LibraryPane(Container):
    CSS = """
    LibraryPane { height: 1fr; }
    LibraryPane TabbedContent { height: 1fr; }
    TrackTable, CollectionTable { height: 1fr; margin: 0 1; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.loaded = {"playlists": False, "liked": False, "albums": False,
                       "artists": False, "history": False}

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="playlists"):
            with TabPane("Playlists", id="playlists"):
                yield Static("Loading playlists…", id="playlists-status")
                yield CollectionTable(id="playlists-table")
            with TabPane("Liked", id="liked"):
                yield Static("Loading liked songs…", id="liked-status")
                yield TrackTable(id="liked-table")
            with TabPane("Albums", id="albums"):
                yield Static("Loading albums…", id="albums-status")
                yield CollectionTable(id="albums-table")
            with TabPane("Artists", id="artists"):
                yield Static("Loading artists…", id="artists-status")
                yield CollectionTable(id="artists-table")
            with TabPane("History", id="history"):
                yield Static("Loading history…", id="history-status")
                yield TrackTable(id="history-table")

    def on_mount(self) -> None:
        self.load_tab("playlists")

    def on_tabbed_content_tab_activated(self, event) -> None:  # noqa: N802
        pane_id = event.pane.id if event.pane is not None else ""
        if pane_id:
            self.load_tab(pane_id)

    def load_tab(self, pane_id: str) -> None:
        if pane_id not in self.loaded or self.loaded[pane_id]:
            return
        self.loaded[pane_id] = True
        loaders = {
            "playlists": self.load_playlists,
            "liked": self.load_liked,
            "albums": self.load_albums,
            "artists": self.load_artists,
            "history": self.load_history,
        }
        loader = loaders.get(pane_id)
        if loader:
            self.run_worker(loader, thread=True)

    def _fail(self, pane_id: str, error: str) -> None:
        status = self.query_one(f"#{pane_id}-status", Static)
        status.update(f"Could not load: {error}\nSwitch tabs and back, or press u to retry.")

    def _mark_loaded_retry(self, pane_id: str) -> None:
        self.loaded[pane_id] = False

    # ------------------------------------------------------------ loaders

    def load_playlists(self) -> None:
        try:
            playlists: List[Collection] = self.app.api.library_playlists()
        except Exception as error:
            self.app.call_from_thread(self._fail, "playlists", str(error))
            return
        def render() -> None:
            table = self.query_one("#playlists-table", CollectionTable)
            table.set_collections(playlists)
            self.query_one("#playlists-status", Static).update(
                f"{len(playlists)} playlists — Enter opens")
        self.app.call_from_thread(render)

    def load_liked(self) -> None:
        try:
            tracks: List[Track] = self.app.api.liked_songs()
        except Exception as error:
            self.app.call_from_thread(self._fail, "liked", str(error))
            return
        def render() -> None:
            table = self.query_one("#liked-table", TrackTable)
            table.set_tracks(tracks, numbered=True)
            table.source_label = "Liked songs"
            self.query_one("#liked-status", Static).update(
                f"{len(tracks)} liked songs")
        self.app.call_from_thread(render)

    def load_albums(self) -> None:
        try:
            albums: List[Collection] = self.app.api.library_albums()
        except Exception as error:
            self.app.call_from_thread(self._fail, "albums", str(error))
            return
        def render() -> None:
            table = self.query_one("#albums-table", CollectionTable)
            table.set_collections(albums)
            self.query_one("#albums-status", Static).update(
                f"{len(albums)} albums")
        self.app.call_from_thread(render)

    def load_artists(self) -> None:
        try:
            artists = self.app.api.library_artists()
        except Exception as error:
            self.app.call_from_thread(self._fail, "artists", str(error))
            return
        collections = [
            Collection(browse_id=artist.browse_id, title=artist.name,
                       subtitle=artist.subtitle, kind="playlist")
            for artist in artists
        ]
        def render() -> None:
            table = self.query_one("#artists-table", CollectionTable)
            table.set_collections(collections)
            self.query_one("#artists-status", Static).update(
                f"{len(collections)} artists")
        self.app.call_from_thread(render)

    def load_history(self) -> None:
        try:
            tracks: List[Track] = self.app.api.history()
        except Exception as error:
            self.app.call_from_thread(self._fail, "history", str(error))
            return
        def render() -> None:
            table = self.query_one("#history-table", TrackTable)
            table.set_tracks(tracks, numbered=True)
            table.source_label = "History"
            self.query_one("#history-status", Static).update(
                f"{len(tracks)} recently played")
        self.app.call_from_thread(render)
