"""First-run sign-in: browser-cookie auth (recommended) or Google OAuth.

Browser-cookie auth is the method that currently works: you copy request
headers from music.youtube.com in your desktop browser and paste them here.
The cookies stay in your user state directory with owner-only permissions.

Google OAuth (personal Cloud client + device flow) is kept as a fallback,
but YouTube's servers have been rejecting those tokens with HTTP 400
"invalid argument" since late August 2025 (upstream ytmusicapi #813), so it
is expected to fail until YouTube or ytmusicapi resolve it.
"""

from __future__ import annotations

import subprocess

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Static, TextArea

from ..ymapi import DeviceAuthFlow, signed_in, store_browser_headers

BROWSER_INSTRUCTIONS = """[b]Sign in with your browser cookies (recommended)[/b]

YouTube currently rejects app OAuth tokens, so sign in with the cookies
from your own logged-in browser instead:

   1. Open [u]https://music.youtube.com[/u] and log in as usual
   2. Open DevTools (F12), go to the [i]Network[/i] tab, reload the page
   3. Click any request to [i]music.youtube.com[/i] (e.g. browse)
   4. Under [i]Request Headers[/i]: copy them all (right-click, Copy all)
   5. Paste below and press Save (Ctrl+S focuses it, then the button)

Nothing leaves your machine: the headers are stored under
~/.local/state/omarchy-ytmusic/browser.json with owner-only permissions.
"""

OAUTH_INSTRUCTIONS = """[b]Fallback: Google OAuth device flow[/b]

Uses a personal Google Cloud OAuth client (create one of type
[i]TVs and Limited Input devices[/i] with the YouTube Data API v3 enabled
at https://console.cloud.google.com/apis/credentials, then paste the
client ID and secret below).

Note: YouTube's servers currently reject these tokens (HTTP 400), so this
is expected to fail until the upstream issue is fixed. Prefer the browser
method above.
"""


class AuthScreen(Screen):
    BINDINGS = [
        ("o", "open_browser", "Open browser"),
        ("r", "restart", "Restart flow"),
        ("q", "quit", "Quit"),
    ]

    CSS = """
    AuthScreen { align: center middle; }
    #auth-card {
        width: 84; height: auto; max-height: 96%;
        border: round #ff5252; padding: 1 2;
        background: $surface;
    }
    #auth-title { text-align: center; text-style: bold; color: #ff5252; }
    #auth-instructions { margin: 1 0; }
    #browser-headers { height: 8; }
    #auth-url { color: $text-success; }
    #auth-code { text-style: bold; }
    #auth-status { color: $text-muted; margin-top: 1; }
    Input { margin: 0 0 1 0; }
    #auth-buttons { height: auto; margin-top: 1; }
    #auth-buttons Button { margin-right: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.mode = "browser"
        self.flow: DeviceAuthFlow | None = None
        self.auth_url: str = ""
        self.device_code: str = ""
        self.in_device_phase: bool = False

    def compose(self) -> ComposeResult:
        with Vertical(id="auth-card"):
            yield Static("Sign in with your YouTube account", id="auth-title")
            yield Static(BROWSER_INSTRUCTIONS, id="auth-instructions",
                         markup=True)
            yield TextArea(id="browser-headers")
            yield Input(placeholder="Client ID (xxxx.apps.googleusercontent.com)",
                        id="client-id")
            yield Input(placeholder="Client secret", id="client-secret",
                        password=True)
            yield Static("Paste the headers above, then save.",
                         id="auth-status")
            yield Static("", id="auth-url", markup=True)
            yield Static("", id="auth-code")
            with Horizontal(id="auth-buttons"):
                yield Button("Save & sign in", id="save-browser",
                             variant="success")
                yield Button("OAuth device flow instead", id="use-oauth")
                yield Button("Browser method instead", id="use-browser")
        yield Footer()

    def on_mount(self) -> None:
        self.show_browser_mode()
        self.query_one("#browser-headers", TextArea).focus()

    # ------------------------------------------------------------ mode switch

    def show_browser_mode(self) -> None:
        self.mode = "browser"
        if self.flow:
            self.flow.cancel()
            self.flow = None
        self.in_device_phase = False
        self.query_one("#auth-instructions", Static).update(
            BROWSER_INSTRUCTIONS)
        self.query_one("#browser-headers", TextArea).display = True
        self.query_one("#save-browser", Button).display = True
        self.query_one("#client-id", Input).display = False
        self.query_one("#client-secret", Input).display = False
        self.query_one("#use-oauth", Button).display = True
        self.query_one("#use-browser", Button).display = False
        self.query_one("#auth-url", Static).update("")
        self.query_one("#auth-code", Static).update("")
        self.query_one("#auth-status", Static).update(
            "Paste the headers above, then save.")

    def show_oauth_mode(self) -> None:
        self.mode = "oauth"
        self.query_one("#auth-instructions", Static).update(
            OAUTH_INSTRUCTIONS)
        self.query_one("#browser-headers", TextArea).display = False
        self.query_one("#save-browser", Button).display = False
        self.query_one("#client-id", Input).display = True
        self.query_one("#client-secret", Input).display = True
        self.query_one("#use-oauth", Button).display = False
        self.query_one("#use-browser", Button).display = True
        self.query_one("#auth-status", Static).update(
            "Press Enter in the secret field to continue.")
        self.query_one("#client-id", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "save-browser":
            self.save_browser_headers()
        elif button_id == "use-oauth":
            self.show_oauth_mode()
        elif button_id == "use-browser":
            self.show_browser_mode()

    # ---------------------------------------------------------- browser flow

    def save_browser_headers(self) -> None:
        raw = self.query_one("#browser-headers", TextArea).text
        if not raw.strip():
            self.query_one("#auth-status", Static).update(
                "Paste the request headers first — the box is empty.")
            return
        self.query_one("#auth-status", Static).update("Checking…")
        self.run_worker(lambda: self.verify_browser_headers(raw), thread=True,
                        exclusive=True)

    def verify_browser_headers(self, raw: str) -> None:
        try:
            store_browser_headers(raw)
        except Exception as error:
            self.app.call_from_thread(self.browser_failed,
                                      f"could not parse the headers: {error}")
            return
        try:
            self.app.api.reload_auth()
            self.app.api.home()
        except Exception as error:
            self.app.call_from_thread(
                self.browser_failed,
                f"headers saved, but YouTube rejected them: {error}. "
                "Make sure you copied the headers while logged in.")
            return
        self.app.call_from_thread(self.browser_done)

    def browser_failed(self, message: str) -> None:
        self.query_one("#auth-status", Static).update(message)

    def browser_done(self) -> None:
        try:
            self.app.state_writer.ensure_signed(True)
        except Exception:
            pass
        self.app.notify("Signed in to YouTube Music", severity="information")
        self.app.enter_main()

    # ------------------------------------------------------------- oauth flow

    def on_input_submitted(self, event: Input.Submitted) -> None:  # noqa: N802
        event.stop()
        if self.mode != "oauth" or self.in_device_phase:
            return
        client_id = self.query_one("#client-id", Input).value.strip()
        client_secret = self.query_one("#client-secret", Input).value.strip()
        if not client_id or not client_secret:
            self.query_one("#auth-status", Static).update(
                "Enter both the client ID and the client secret to continue.")
            return
        self.start_flow(client_id, client_secret)

    def start_flow(self, client_id: str, client_secret: str) -> None:
        self.in_device_phase = True
        self.query_one("#auth-status", Static).update(
            "Requesting a sign-in code from Google…")
        self.flow = DeviceAuthFlow(
            client_id, client_secret,
            on_progress=lambda payload:
                self.app.call_from_thread(self.on_progress, payload),
        )
        self.run_worker(self.flow.run, thread=True, exclusive=True)

    def on_progress(self, payload: dict) -> None:
        phase = payload.get("phase", "")
        if phase == "code":
            self.auth_url = str(payload.get("url", ""))
            self.device_code = str(payload.get("user_code", ""))
            url_display = self.auth_url
            self.query_one("#auth-url", Static).update(
                f"Open [u]{url_display}?user_code={self.device_code}[/u]"
                f"  (press o to open)")
            self.query_one("#auth-code", Static).update(
                f"Code: {self.device_code}")
            self.query_one("#auth-status", Static).update(
                "Waiting for you to authorize in the browser…")
        elif phase == "waiting":
            self.query_one("#auth-status", Static).update(
                "Waiting for you to authorize in the browser…")
        elif phase == "done":
            ok = payload.get("ok") is True
            message = str(payload.get("message", ""))
            if ok and signed_in():
                try:
                    self.app.state_writer.ensure_signed(True)
                except Exception:
                    pass
                self.app.notify("Signed in to YouTube Music",
                                severity="information")
                self.app.enter_main()
            else:
                self.in_device_phase = False
                self.query_one("#auth-status", Static).update(
                    f"Sign-in failed: {message}. Press r to retry.")

    # ---------------------------------------------------------------- actions

    def action_open_browser(self) -> None:
        if self.mode == "oauth":
            if not self.auth_url:
                self.app.notify("Waiting for the sign-in URL…",
                                severity="warning")
                return
            url = self.auth_url
            if self.device_code and "user_code" not in url:
                url = f"{url}?user_code={self.device_code}"
        else:
            url = "https://music.youtube.com"
        try:
            subprocess.Popen(["xdg-open", url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.app.notify("Could not open a browser; visit the URL manually.",
                            severity="error")

    def action_restart(self) -> None:
        if self.mode == "oauth":
            if self.flow:
                self.flow.cancel()
            self.in_device_phase = False
            self.auth_url = ""
            self.device_code = ""
            self.query_one("#auth-url", Static).update("")
            self.query_one("#auth-code", Static).update("")
            self.query_one("#auth-status", Static).update(
                "Press Enter in the secret field to continue.")
            self.query_one("#client-id", Input).focus()
        else:
            self.query_one("#auth-status", Static).update(
                "Paste the headers above, then save.")
            self.query_one("#browser-headers", TextArea).focus()
