"""Personalized homepage: the shelves YouTube Music builds for your account."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import HorizontalScroll, VerticalScroll
from textual.widgets import Static

from ..models import Shelf
from ..widgets import CardButton, SectionTitle


class HomePane(VerticalScroll):
    BINDINGS = [
        ("r", "refresh", "Refresh"),
    ]

    CSS = """
    HomePane { padding: 0 1; }
    SectionTitle {
        color: #ff5252; text-style: bold; margin: 1 0 0 0;
    }
    HomePane HorizontalScroll { height: auto; margin: 0 0 1 0; }
    CardButton {
        width: 30; height: 5; margin: 0 1 0 0;
        background: $surface; color: $text;
        border: round $panel; text-align: left; overflow: hidden;
    }
    CardButton:focus { border: round #ff5252; }
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
            row = HorizontalScroll()
            await self.mount(row)
            for collection in shelf.collections[:14]:
                await row.mount(CardButton(collection.title, collection.subtitle,
                                           collection))
            for track in shelf.videos[:14]:
                await row.mount(CardButton(track.title, track.artist, track))
        await self.mount(Static(
            "\nUse the arrow keys to move, Enter or click a card to open it. "
            "Press ? for all shortcuts.", id="home-status"))

    async def action_refresh(self) -> None:
        self.loaded = False
        await self.remove_children()
        await self.mount(Static("Refreshing…", id="home-status"))
        self.run_worker(self.load_home, thread=True)
