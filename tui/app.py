"""The Omarchy YouTube Music TUI application."""

from __future__ import annotations

import asyncio
from typing import List, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Input, TabbedContent, TabPane

from . import __version__
from .models import Collection, Track
from .mpv import MpvIpc
from .screens.artist import ArtistScreen
from .screens.auth import AuthScreen
from .screens.collection import CollectionScreen
from .screens.help import HelpScreen
from .screens.home import HomePane
from .screens.library import LibraryPane
from .screens.picker import PlaylistPicker
from .screens.queue import QueuePane
from .screens.search import SearchPane
from .state import StateWriter
from .widgets import PlayerBar
from .ymapi import YtMusic, signed_in


class MainScreen(Screen):
    CSS = """
    TabbedContent { height: 1fr; }
    PlayerBar {
        dock: bottom; height: 4; padding: 0 1;
        background: $surface; color: $text;
        border-top: solid $panel;
    }
    #player-main { height: 1; }
    #player-track { width: 1fr; }
    #player-progress { height: 1; margin-top: 1; color: $text-muted; }
    """

    def compose(self) -> ComposeResult:
        yield PlayerBar(id="now-playing")
        with TabbedContent(initial="home"):
            with TabPane("Home", id="home"):
                yield HomePane()
            with TabPane("Search", id="search"):
                yield SearchPane()
            with TabPane("Library", id="library"):
                yield LibraryPane()
            with TabPane("Queue", id="queue"):
                yield QueuePane(id="queue-pane")
        yield Footer()


class YtMusicApp(App):
    TITLE = f"Omarchy YouTube Music — {__version__}"
    CSS = """
    Screen { background: $background; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("f1", "help", "Help"),
        ("question_mark", "help", "Help"),
        ("/", "focus_search", "Search"),
        ("space", "toggle", "Play/Pause"),
        ("n", "next", "Next"),
        ("p", "previous", "Previous"),
        ("comma", "seek_back", "-10s"),
        ("period", "seek_forward", "+10s"),
        ("plus", "volume_up", "Vol +"),
        ("equals", "volume_up", "Vol +"),
        ("minus", "volume_down", "Vol -"),
        ("m", "mute", "Mute"),
        ("f2", "show_home", "Home"),
        ("f3", "focus_search", "Search"),
        ("f4", "show_library", "Library"),
        ("f5", "show_queue", "Queue"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.api = YtMusic()
        self.player = MpvIpc()
        self.state_writer = StateWriter()
        self.queue_tracks: List[Track] = []
        self.queue_source: str = ""
        # True once THIS session has loaded its own playlist into mpv.
        # Only an owning session may (over)write the state.json snapshot the
        # bar widget reads; otherwise a fresh TUI would clobber the previous
        # session's titles with its empty queue on the first player event.
        self._owns_playlist: bool = False
        self._volume_before_mute: float = 100.0
        self._liked: set = set()

    # ------------------------------------------------------------- lifecycle

    def on_mount(self) -> None:
        self.player.add_observer(self._on_player_event)
        self.set_interval(1.0, self._tick)
        # Publish auth state promptly so the bar widget doesn't nag about
        # sign-in while waiting for the first playback event. This never
        # touches an existing track list (see StateWriter.ensure_signed).
        try:
            self.state_writer.ensure_signed(signed_in())
        except Exception:
            pass
        if signed_in():
            self.push_screen(MainScreen())
        else:
            self.push_screen(AuthScreen())

    def enter_main(self) -> None:
        self.switch_screen(MainScreen())

    async def _tick(self) -> None:
        await self.player.refresh_position()
        self.refresh_now_playing()

    # -------------------------------------------------------- player events

    def _on_player_event(self, name: str, value) -> None:
        interesting = {
            "pause", "idle-active", "playlist-pos", "playlist-count",
            "volume", "metadata", "path", "media-title", "disconnected",
        }
        if name in interesting:
            try:
                self.call_later(self._sync_after_player_event)
            except Exception:
                pass

    def _sync_after_player_event(self) -> None:
        state = self.player.state
        index = state.playlist_pos
        if not self._owns_playlist:
            # mpv is playing a playlist owned by another session (e.g. kept
            # going after this TUI was restarted or the previous one quit).
            # Don't overwrite its state.json snapshot with our queue —
            # the bar widget reads that snapshot for titles.
            self.refresh_now_playing()
            self.refresh_queue_pane()
            return
        signed = signed_in()
        self.state_writer.write(self.queue_tracks, index if index >= 0 else 0,
                                signed, self.queue_source)
        self.refresh_now_playing()
        self.refresh_queue_pane()

    def current_track(self) -> Optional[Track]:
        state = self.player.state
        index = state.playlist_pos
        if 0 <= index < len(self.queue_tracks):
            return self.queue_tracks[index]
        return None

    def refresh_now_playing(self) -> None:
        try:
            bar = self.screen.query_one("#now-playing", PlayerBar)
        except Exception:
            return
        track = self.current_track()
        bar.render_bar(self.player.state, track, liked=bool(track and track.video_id in self._liked))

    def refresh_queue_pane(self) -> None:
        try:
            pane = self.screen.query_one("#queue-pane", QueuePane)
        except Exception:
            return
        pane.refresh_queue()

    # ------------------------------------------------------------ playback

    async def _ensure(self) -> bool:
        ok = await self.player.ensure_running()
        if not ok:
            self.notify("Could not start the audio player (mpv).",
                        severity="error")
        return ok

    async def play_tracks(self, tracks: List[Track], index: int = 0,
                          source: str = "") -> None:
        playable = [track for track in tracks if track.available]
        if not playable:
            self.notify("Nothing playable here.", severity="warning")
            return
        index = max(0, min(index, len(playable) - 1))
        if not await self._ensure():
            return
        try:
            await self.player.play_tracks([t.video_id for t in playable[index:]])
        except Exception as error:
            self.notify(f"Playback failed: {error}", severity="error")
            return
        self.queue_tracks = playable[index:]
        self.queue_source = source
        self._owns_playlist = True
        self._sync_after_player_event()

    async def enqueue(self, track: Track, play_next: bool = False) -> None:
        if not await self._ensure():
            return
        state = self.player.state
        try:
            if state.idle or not state.playlist_count:
                await self.player.play_tracks([track.video_id])
                self.queue_tracks = [track]
                self.queue_source = "Single track"
            elif play_next:
                await self.player.load(track.video_id, "insert-next")
                position = state.playlist_pos
                self.queue_tracks.insert(position + 1, track)
            else:
                await self.player.load(track.video_id, "append")
                self.queue_tracks.append(track)
        except Exception as error:
            self.notify(f"Could not queue: {error}", severity="error")
            return
        self.notify(("Playing next: " if play_next else "Queued: ") + track.label(),
                    severity="information")
        self._sync_after_player_event()

    async def remove_queue_index(self, index: int) -> None:
        if not (0 <= index < len(self.queue_tracks)):
            return
        try:
            await self.player.remove(index)
        except Exception as error:
            self.notify(f"Could not remove: {error}", severity="error")
            return
        self.queue_tracks.pop(index)
        self._sync_after_player_event()

    async def clear_queue(self) -> None:
        try:
            await self.player.clear_queue()
        except Exception:
            pass
        current = self.current_track()
        self.queue_tracks = [current] if current else []
        self._sync_after_player_event()

    async def start_radio(self, track: Track) -> None:
        self.notify(f"Building a radio mix from {track.label()}…")
        self._radio_worker(track)

    @work(thread=True)
    def _radio_worker(self, track: Track) -> None:
        try:
            tracks = self.api.watch_playlist(track.video_id, limit=60)
        except Exception as error:
            self.call_from_thread(
                lambda message=str(error): self.notify(
                    f"Radio failed: {message}", severity="error"))
            return
        source = f"Radio · {track.label()}"

        def start() -> None:
            asyncio.get_running_loop().create_task(
                self.play_tracks(tracks, 0, source=source))

        self.call_from_thread(start)

    # -------------------------------------------------------------- actions

    async def action_toggle(self) -> None:
        if not self.player.connected:
            if not await self._ensure():
                return
        try:
            await self.player.toggle()
        except Exception:
            pass
        self.refresh_now_playing()

    async def action_next(self) -> None:
        try:
            await self.player.next()
        except Exception:
            pass

    async def action_previous(self) -> None:
        try:
            await self.player.previous()
        except Exception:
            pass

    async def action_seek_back(self) -> None:
        try:
            await self.player.command("seek", -10, "relative")
        except Exception:
            pass
        await self.player.refresh_position()
        self.refresh_now_playing()

    async def action_seek_forward(self) -> None:
        try:
            await self.player.command("seek", 10, "relative")
        except Exception:
            pass
        await self.player.refresh_position()
        self.refresh_now_playing()

    async def action_volume_up(self) -> None:
        try:
            await self.player.set_volume(self.player.state.volume + 5)
        except Exception:
            pass
        self.refresh_now_playing()

    async def action_volume_down(self) -> None:
        try:
            await self.player.set_volume(self.player.state.volume - 5)
        except Exception:
            pass
        self.refresh_now_playing()

    async def action_mute(self) -> None:
        try:
            if self.player.state.volume > 0:
                self._volume_before_mute = self.player.state.volume
                await self.player.set_volume(0)
            else:
                restore = self._volume_before_mute or 100.0
                await self.player.set_volume(restore)
        except Exception:
            pass
        self.refresh_now_playing()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def _activate_tab(self, pane_id: str) -> None:
        try:
            tabs = self.screen.query_one(TabbedContent)
        except Exception:
            return
        tabs.active = pane_id
        if pane_id == "search":
            try:
                self.screen.query_one("#search-input", Input).focus()
            except Exception:
                pass
        elif pane_id == "queue":
            self.refresh_queue_pane()

    def action_focus_search(self) -> None:
        self._activate_tab("search")

    def action_show_home(self) -> None:
        self._activate_tab("home")

    def action_show_library(self) -> None:
        self._activate_tab("library")

    def action_show_queue(self) -> None:
        self._activate_tab("queue")

    # ------------------------------------------------------------- likes/UI

    async def toggle_like(self, track: Track) -> None:
        turning_on = track.video_id not in self._liked

        def done(ok: bool) -> None:
            if ok:
                if turning_on:
                    self._liked.add(track.video_id)
                    track.liked = True
                    self.notify(f"Liked {track.label()}")
                else:
                    self._liked.discard(track.video_id)
                    track.liked = False
                    self.notify(f"Unliked {track.label()}")
            else:
                self.notify("Could not update the like on YouTube.",
                            severity="error")
            self.refresh_now_playing()

        self._like_worker(track, turning_on, done)

    @work(thread=True)
    def _like_worker(self, track: Track, turning_on: bool, done) -> None:
        try:
            ok = self.api.like(track.video_id) if turning_on \
                else self.api.unlike(track.video_id)
        except Exception:
            ok = False
        self.call_from_thread(done, ok)

    def open_playlist_picker(self, track: Track) -> None:
        self.push_screen(PlaylistPicker(track))

    async def open_collection(self, collection: Collection) -> None:
        browse_id = collection.browse_id
        if browse_id.startswith("UC"):
            self.push_screen(ArtistScreen(browse_id, name=collection.title))
        elif collection.kind == "album" or browse_id.startswith("MPREb"):
            self.push_screen(CollectionScreen(collection))
        else:
            self.push_screen(CollectionScreen(collection))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="omarchy-ytmusic",
        description="Terminal YouTube Music player for Omarchy",
    )
    parser.add_argument("--version", action="version",
                        version=f"omarchy-ytmusic {__version__}")
    parser.parse_args()
    YtMusicApp().run()
