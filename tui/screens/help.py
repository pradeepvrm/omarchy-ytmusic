"""Keybinding reference and about screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from .. import __version__

HELP_TEXT = f"""[b #ff5252]Omarchy YouTube Music[/] — v{__version__}

[b]Playback[/]
  Space          Play or pause
  n / p          Next / previous track
  < / >          Seek 10 seconds back / forward
  + / -          Volume up / down (5%)
  m              Mute or restore

[b]Navigation[/]
  /              Jump to Search
  F2 / F3 / F4 / F5   Home / Search / Library / Queue
  Tab            Move focus
  Esc            Go back / close
  q              Quit (music keeps playing)

[b]Track lists and cards[/]
  Enter          Play from the selected row (rest of the list follows)
  e              Add the selected track to the queue
  N              Play the selected track next
  r              Start a radio mix from the selected track
  a              Add the selected track to one of your playlists
  l              Like or unlike the selected track
  x / c          Queue screen: remove a row / clear the queue
  s              Playlist or album screen: shuffle and play

[b]Account[/]
  The first launch signs you in with your YouTube account through
  Google's device flow, using a personal Google Cloud OAuth client
  (created once at console.cloud.google.com — type "TVs and Limited
  Input devices"). After that the homepage, recommendations, library,
  and likes are yours.

  Sign-in token:   [i]~/.local/state/omarchy-ytmusic/oauth.json[/]
  OAuth client:    [i]~/.local/state/omarchy-ytmusic/client.json[/]
  Python runtime:  [i]~/.local/share/omarchy-ytmusic/venv[/]

[b]Bar widget[/]
  Click the YouTube Music icon in the top bar for the mini player:
  artwork, controls, volume, and a button that opens this TUI.
  Wheel changes volume; Shift+wheel changes track.
"""


class HelpScreen(Screen):
    BINDINGS = [
        ("question_mark", "close", "Close"),
        ("f1", "close", "Close"),
        ("escape", "close", "Close"),
    ]

    CSS = """
    HelpScreen VerticalScroll { padding: 1 2; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(HELP_TEXT)
        yield Footer()

    def action_close(self) -> None:
        self.app.pop_screen()
