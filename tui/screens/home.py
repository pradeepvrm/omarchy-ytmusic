"""Personalized homepage: the shelves YouTube Music builds for your account.

Each shelf is a vertical section — tracks in a table, collections in a
list below — navigated with the arrow keys. Tab jumps between sections.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ..models import Shelf
from ..widgets import CollectionTable, SectionTitle, TrackTable

# Rows per shelf section: enough to browse, short enough to keep the page
# navigable. The full list is one Enter away on a collection.
SHELF_ROWS = 12


class HomePane(VerticalScroll):
    BINDINGS = [
        ("r", "refresh", "Refresh"),
    ]

    CSS = """
    HomePane { padding: 0 1; }
    SectionTitle {
        color: #ff5252; text-style: bold; margin: 2 0 1 0;
    }
    HomePane TrackTable, HomePane CollectionTable {
        height: auto; max-height: 14; margin: 0 0 1 0;
    }
    #home-status { padding: 1 1; color: $text-muted; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.loaded = False

    def compose(self) -> ComposeResult:
        yield Static("Loading your homepage…", id="home-status")

    def on_mount(self) -> None:
        if not self.loaded:
            self.run_worker(self.load_home, thread=True)

    def load_home(self) -> None:
        try:
            shelves = self.app.api.home()
        except Exception as error:
            self.app.call_from_thread(self.render_error, str(error))
            return
        self.app.call_from_thread(self.render_shelves, shelves)

    async def render_error(self, message: str) -> None:
        await self.remove_children()
        await self.mount(Static(
            f"Could not load your homepage: {message}\nPress r to retry.",
            id="home-status"))

    async def render_shelves(self, shelves: list[Shelf]) -> None:
        self.loaded = True
        await self.remove_children()
        if not shelves:
            await self.mount(Static(
                "Your homepage is empty. Listen to a few songs and it fills up "
                "with Listen again, Mixed for you, and New releases.",
                id="home-status"))
            return
        for shelf in shelves:
            await self.mount(SectionTitle(shelf.title))
            entries = list(shelf.videos) + list(shelf.tracks)
            if entries:
                table = TrackTable()
                table.set_tracks(entries[:SHELF_ROWS])
                table.source_label = shelf.title
                await self.mount(table)
            if shelf.collections:
                colls = CollectionTable()
                colls.set_collections(shelf.collections[:SHELF_ROWS])
                await self.mount(colls)
        await self.mount(Static(
            "Enter plays a track or opens a collection. "
            "Tab jumps between sections. Press ? for all shortcuts.",
            id="home-status"))

    async def action_refresh(self) -> None:
        self.loaded = False
        await self.remove_children()
        await self.mount(Static("Refreshing…", id="home-status"))
        self.run_worker(self.load_home, thread=True)
