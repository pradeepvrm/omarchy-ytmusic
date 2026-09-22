"""Search across YouTube Music with result-type filters."""

from __future__ import annotations

from typing import Any, Dict, List

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, Static

from ..models import ArtistRef, Collection, Track
from ..widgets import CollectionTable, TrackTable

FILTERS = [
    ("all", "All"),
    ("songs", "Songs"),
    ("videos", "Videos"),
    ("albums", "Albums"),
    ("artists", "Artists"),
    ("playlists", "Playlists"),
    ("podcasts", "Podcasts"),
    ("episodes", "Episodes"),
]


class SearchPane(Container):
    CSS = """
    SearchPane { height: 1fr; }
    #search-input { height: 3; margin: 0 1; }
    #filter-row { height: 3; margin: 0 1; }
    #filter-row Button {
        margin: 0 1 0 0; min-width: 10; background: $surface;
    }
    #filter-row Button.active { background: #ff5252 20%; border: round #ff5252; }
    #search-hint { height: auto; color: $text-muted; padding: 0 1; }
    #search-songs, #search-collections { height: 1fr; margin: 0 1; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.filter_name = "songs"
        self.results: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search songs, artists, albums, playlists…  (Enter)",
                    id="search-input")
        with Horizontal(id="filter-row"):
            for key, label in FILTERS:
                button = Button(label, id=f"filter-{key}", compact=True)
                if key == self.filter_name:
                    button.add_class("active")
                yield button
        yield Static("Type a query and press Enter.", id="search-hint")
        yield TrackTable(id="search-songs")
        yield CollectionTable(id="search-collections")

    def on_mount(self) -> None:
        self.query_one("#search-songs", TrackTable).styles.display = "none"
        self.query_one("#search-collections", CollectionTable).styles.display = "none"

    def active_filter(self) -> str | None:
        if self.filter_name == "all":
            return None
        return self.filter_name

    def on_input_submitted(self, event: Input.Submitted) -> None:  # noqa: N802
        event.stop()
        query = event.value.strip()
        if not query:
            return
        self.query_one("#search-hint", Static).update(f"Searching for {query}…")
        self.run_worker(lambda: self.run_search(query), thread=True)

    def run_search(self, query: str) -> None:
        try:
            results = self.app.api.search(query, self.active_filter())
        except Exception as error:
            message = str(error)

            def failed(text=message) -> None:
                self.query_one("#search-hint", Static).update(
                    f"Search failed: {text}")

            self.app.call_from_thread(failed)
            return
        self.app.call_from_thread(self.render_results, results)

    def render_results(self, results: List[Dict[str, Any]]) -> None:
        self.results = results
        songs = self.query_one("#search-songs", TrackTable)
        collections = self.query_one("#search-collections", CollectionTable)
        hint = self.query_one("#search-hint", Static)
        tracks: List[Track] = []
        colls: List[Collection] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("resultType", ""))
            if kind in ("song", "video"):
                track = Track.from_result(item)
                if track:
                    tracks.append(track)
            elif kind in ("album", "single", "ep"):
                browse_id = str(item.get("browseId", ""))
                if browse_id:
                    colls.append(Collection(
                        browse_id=browse_id,
                        title=str(item.get("title", "")),
                        subtitle=" ".join(filter(None, [
                            str(item.get("artist", "") or ""),
                            str(item.get("year", "") or ""),
                        ])),
                        kind=kind,
                    ))
            elif kind in ("playlist", "community_playlist"):
                browse_id = str(item.get("browseId", ""))
                if browse_id:
                    try:
                        count = int(str(item.get("count", "0") or "0").split(" ")[0] or 0)
                    except ValueError:
                        count = 0
                    colls.append(Collection(
                        browse_id=browse_id,
                        title=str(item.get("title", "")),
                        subtitle=str(item.get("author", "")),
                        kind="playlist",
                        track_count=count,
                    ))
            elif kind == "artist":
                browse_id = str(item.get("browseId", ""))
                if browse_id:
                    colls.append(Collection(
                        browse_id=browse_id,
                        title=str(item.get("artist", "")),
                        subtitle="Artist",
                        kind="playlist",  # artist pages route through the same opener
                    ))
            elif kind == "podcast":
                browse_id = str(item.get("browseId", ""))
                if browse_id:
                    colls.append(Collection(
                        browse_id=browse_id,
                        title=str(item.get("title", "")),
                        subtitle="Podcast",
                        kind="podcast",
                    ))
            elif kind == "episode":
                track = Track.from_result(item)
                if track:
                    tracks.append(track)

        if tracks and (self.filter_name in ("all", "songs", "videos",
                                               "episodes")):
            songs.set_tracks(tracks)
            songs.source_label = "Search"
            songs.styles.display = "block"
        else:
            songs.styles.display = "none"
        if colls:
            collections.set_collections(colls)
            collections.styles.display = "block"
        else:
            collections.styles.display = "none"
        total = len(tracks) + len(colls)
        hint.update(f"{total} results — Enter plays or opens, ? for help"
                    if total else "No results. Try a different query.")

    def on_button_pressed(self, event: Button.Pressed) -> None:  # noqa: N802
        event.stop()
        button = event.button
        if not button.id or not button.id.startswith("filter-"):
            return
        key = button.id[len("filter-"):]
        self.filter_name = key
        for name, _ in FILTERS:
            candidate = self.query_one(f"#filter-{name}", Button)
            candidate.set_class(name == key, "active")
