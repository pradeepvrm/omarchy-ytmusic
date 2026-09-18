"""Modal screens: add-to-playlist picker and single-line input."""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView, Static

from ..models import Track


class PlaylistPicker(ModalScreen):
    """Pick a playlist (or create one) for the given track."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    PlaylistPicker { align: center middle; }
    #picker-card {
        width: 60; height: auto; max-height: 70%;
        border: round #ff5252; background: $surface; padding: 1;
    }
    #picker-title { text-style: bold; }
    #picker-list { height: auto; max-height: 16; margin: 1 0; }
    #picker-new { margin: 0 0 1 0; }
    """

    def __init__(self, track: Track, **kwargs) -> None:
        super().__init__(**kwargs)
        self.track = track
        self.playlists = []

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-card"):
            yield Label(f"Add “{self.track.label()}” to…", id="picker-title")
            yield ListView(id="picker-list")
            yield Input(placeholder="…or type a new playlist name and press Enter",
                        id="picker-new")

    def on_mount(self) -> None:
        self.run_worker(self.load, thread=True)

    def load(self) -> None:
        try:
            playlists = self.app.api.playlists_for_add()
        except Exception:
            playlists = []
        def render() -> None:
            from textual.widgets import ListItem

            self.playlists = playlists
            view = self.query_one("#picker-list", ListView)
            view.clear()
            for playlist in playlists:
                if isinstance(playlist, dict):
                    title = str(playlist.get("title", ""))
                    view.append(ListItem(Label(title)))
            view.focus()
        self.app.call_from_thread(render)

    def on_list_view_selected(self, event: ListView.Selected) -> None:  # noqa: N802
        event.stop()
        index = event.list_view.index or 0
        if not (0 <= index < len(self.playlists)):
            return
        playlist = self.playlists[index]
        playlist_id = str(playlist.get("playlistId", "")
                          or playlist.get("browseId", ""))
        track = self.track
        self.dismiss()
        if playlist_id:
            self.run_worker(lambda: self.add(playlist_id, playlist, track), thread=True)

    def add(self, playlist_id: str, playlist: dict, track: Track) -> None:
        app = self.app
        try:
            app.api.add_to_playlist(playlist_id, track.video_id)
        except Exception as error:
            app.call_from_thread(
                lambda message=str(error): app.notify(
                    f"Could not add: {message}", severity="error"))
            return
        name = str(playlist.get("title", "playlist"))
        app.call_from_thread(
            lambda: app.notify(f"Added to {name}", severity="information"))

    def on_input_submitted(self, event: Input.Submitted) -> None:  # noqa: N802
        event.stop()
        title = event.value.strip()
        if not title:
            return
        track = self.track
        self.dismiss()
        self.run_worker(lambda: self.create(title, track), thread=True)

    def create(self, title: str, track: Track) -> None:
        app = self.app
        playlist_id = app.api.create_playlist(title)
        if not playlist_id:
            app.call_from_thread(
                lambda: app.notify("Could not create the playlist",
                                   severity="error"))
            return
        try:
            app.api.add_to_playlist(playlist_id, track.video_id)
        except Exception as error:
            app.call_from_thread(
                lambda message=str(error): app.notify(
                    f"Playlist created, but adding failed: {message}",
                    severity="warning"))
            return
        app.call_from_thread(
            lambda: app.notify(f"Created {title} and added the track",
                               severity="information"))

    def action_cancel(self) -> None:
        self.dismiss()


class InputModal(ModalScreen):
    """Ask for a single line of text."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    InputModal { align: center middle; }
    #input-card {
        width: 50; height: auto; border: round #ff5252;
        background: $surface; padding: 1;
    }
    """

    def __init__(self, prompt: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="input-card"):
            yield Static(self.prompt)
            yield Input(id="modal-input")

    def on_mount(self) -> None:
        self.query_one("#modal-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:  # noqa: N802
        event.stop()
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss("")
