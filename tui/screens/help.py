"""Keybinding reference and about screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Static

from .. import __version__
from .auth import AuthScreen

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
  Sign-in uses your browser's YouTube Music cookies: paste request
  headers from a logged-in music.youtube.com session (DevTools,
  Network tab) on the sign-in screen. The Google OAuth device flow
  is offered as a fallback, but YouTube's servers currently reject
  those tokens, so prefer the browser method.

  Browser cookies: [i]~/.local/state/omarchy-ytmusic/browser.json[/]
  Sign-in token:   [i]~/.local/state/omarchy-ytmusic/oauth.json[/]
  OAuth client:    [i]~/.local/state/omarchy-ytmusic/client.json[/]
  Python runtime:  [i]~/.local/share/omarchy-ytmusic/venv[/]

  If requests start failing (expired cookies, revoked access), sign
  out below and sign back in with fresh headers.

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
            yield Button("Sign out and switch account", id="sign-out",
                         variant="warning")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if (event.button.id or "") != "sign-out":
            return
        self.app.api.sign_out()
        self.app.pop_screen()
        self.app.switch_screen(AuthScreen())

    def action_close(self) -> None:
        self.app.pop_screen()
