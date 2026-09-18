"""First-run sign-in: Google OAuth client credentials + device flow.

ytmusicapi 1.x signs in with a personal Google Cloud OAuth client (TV type)
through Google's device flow. This screen collects the client ID and secret
once, then walks the user through authorizing this computer.
"""

from __future__ import annotations

import subprocess

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, Static

from ..ymapi import DeviceAuthFlow, signed_in

SETUP_INSTRUCTIONS = """[b]One-time setup — your own YouTube API key[/b]

YouTube Music sign-in uses a personal Google Cloud OAuth client:

  1. Open [u]https://console.cloud.google.com/apis/credentials[/u]
  2. Create a project (any name), then create credentials:
     [i]OAuth client ID[/i] of type [b]TVs and Limited Input devices[/b]
  3. Enable the [i]YouTube Data API v3[/i] for the project
  4. Copy the client ID and client secret below

Your password is only ever entered on Google's own page. The token and the
client secret stay in your user state directory with owner-only permissions.
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
        width: 80; height: auto; max-height: 90%;
        border: round #ff5252; padding: 1 2;
        background: $surface;
    }
    #auth-title { text-align: center; text-style: bold; color: #ff5252; }
    #auth-instructions { margin: 1 0; }
    #auth-url { color: $text-success; }
    #auth-code { text-style: bold; }
    #auth-status { color: $text-muted; margin-top: 1; }
    Input { margin: 0 0 1 0; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.flow: DeviceAuthFlow | None = None
        self.auth_url: str = ""
        self.device_code: str = ""
        self.in_device_phase: bool = False

    def compose(self) -> ComposeResult:
        with Vertical(id="auth-card"):
            yield Static("Sign in with your YouTube account", id="auth-title")
            yield Static(SETUP_INSTRUCTIONS, id="auth-instructions", markup=True)
            yield Input(placeholder="Client ID (xxxx.apps.googleusercontent.com)",
                        id="client-id")
            yield Input(placeholder="Client secret", id="client-secret",
                        password=True)
            yield Static("Press Enter in the secret field to continue.",
                        id="auth-status")
            yield Static("", id="auth-url", markup=True)
            yield Static("", id="auth-code")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:  # noqa: N802
        event.stop()
        if self.in_device_phase:
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
                self.app.notify("Signed in to YouTube Music",
                                severity="information")
                self.app.enter_main()
            else:
                self.in_device_phase = False
                self.query_one("#auth-status", Static).update(
                    f"Sign-in failed: {message}. Press r to retry.")

    def action_open_browser(self) -> None:
        if not self.auth_url:
            self.app.notify("Waiting for the sign-in URL…", severity="warning")
            return
        url = self.auth_url
        if self.device_code and "user_code" not in url:
            url = f"{url}?user_code={self.device_code}"
        try:
            subprocess.Popen(["xdg-open", url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.app.notify("Could not open a browser; visit the URL manually.",
                            severity="error")

    def action_restart(self) -> None:
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
