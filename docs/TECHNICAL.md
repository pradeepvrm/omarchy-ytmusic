# Technical notes

Implementation details for anyone working on the plugin. The user-facing
summary lives in the README.

## Architecture

The plugin runs inside Omarchy's `omarchy-shell` Quickshell process and provides
two entry points: a shared `Service.qml` and a `BarWidget.qml`. There is no
resident helper daemon of our own. Audio runs in a detached mpv process that
the service spawns on demand and puts to sleep after a configurable idle
period — mirroring the on-demand playback model of Omarchy-Spotify, but with
mpv instead of a Rust backend.

```
┌──────────────────────────── omarchy-shell (Quickshell) ─────────────────────┐
│  Service.qml ── PlayerClient.qml (Quickshell.Io Socket, reconnect loop)     │
│      │            observes pause/idle/playlist/volume/metadata/path         │
│      │            1 s position polling via get_property                     │
│      │            FileView-watches state.json for TUI queue metadata        │
│      │            IpcHandler target quickshell.ytmusic.player              │
│  BarWidget.qml ◀─ service properties (title/artist/art/playing/position)    │
└──────┬──────────────────────────────────────────────────────────────────────┘
       │ Unix socket $XDG_RUNTIME_DIR/omarchy-ytmusic/mpv.sock (JSON IPC)
       ▼
     mpv --idle --no-video --ytdl-format=bestaudio…  ── yt-dlp ──▶ YouTube Music
       │ mpv-mpris (bundled with Omarchy) ──▶ MPRIS bus (stock media widget,
       │                                          playerctl, lock screen art)
       ▲
       │ same socket, second client
┌──────┴──────────────────────────── TUI (python -m tui) ─────────────────────┐
│  mpv.py: asyncio IPC client (loadfile, queue edits, transport)              │
│  ymapi.py: ytmusicapi OAuth + home/search/library/radio queries             │
│  state.py: atomic state.json snapshot for the service                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

Both the service and the TUI are clients of the same mpv socket. The service is
the only spawner on the desktop (the TUI asks it via
`omarchy-shell -q quickshell.ytmusic.player ensurePlayer`, with a direct-spawn
fallback for sessions where the shell IPC is unavailable). mpv's IPC accepts
multiple concurrent clients, and property observation is per-client, so there
is no contention: the TUI owns queue edits, the service owns transport controls
and lifecycle.

## Display metadata

mpv's `metadata` (filled by yt-dlp) is the base layer, but YouTube topic
channels occasionally carry ugly names. The TUI therefore writes
`state.json` — an atomic tmp+rename snapshot of the loaded queue
(`tracks[]`, `queueIndex`, `signedIn`, `source`) — next to the socket. The
service FileView-watches it and resolves display metadata as:
TUI snapshot at the current playlist position → mpv metadata → `media-title`,
with the video id parsed from mpv's `path` for artwork
(`https://i.ytimg.com/vi/<id>/mqdefault.jpg`). Because the snapshot holds the
whole queue, the widget keeps showing clean titles after the TUI exits.

## Position handling

Quickshell interpolates nothing here; the service polls `playback-time` once
per second over the local socket only while a track actually plays. The queue
index and everything else arrives through `observe_property` events, one
authoritative update per change.

## Setup model

Omarchy's plugin installer clones and validates plugins without running any
hook, so the enabled plugin prepares itself on first load. `Service.qml` runs
`scripts/setup.sh --status`; when the answer is `needed`, it runs the full
setup and reports completion through `omarchy-notification-send`. Setup:

1. verifies the Omarchy base commands (`python3`, `mpv`, `yt-dlp`),
2. creates `$XDG_DATA_HOME/omarchy-ytmusic/venv` and pip-installs
   `tui/requirements.txt` (ytmusicapi, textual),
3. writes a marker file (plugin version + requirements hash) so upgrades
   refresh the environment,
4. installs a wrapper launcher at `~/.local/bin/omarchy-ytmusic`.

Everything is written outside the plugin directory: Omarchy treats any write
inside a plugin folder as a plugin change and hot-reloads it, which would kill
a setup in progress.

## Authentication

Sign-in follows ytmusicapi's OAuth setup for custom clients, which the
library requires since it stopped shipping default OAuth credentials. The
user creates a Google Cloud OAuth client (type *TVs and Limited Input
devices*, with the YouTube Data API enabled) once; the TUI collects its ID
and secret on the auth screen and runs Google's device flow directly through
`OAuthCredentials.get_code()` / `token_from_code()` — the same calls the
library's own CLI makes, replayed with a polling loop because the stock
`prompt_for_token` blocks on `input()`, which cannot work under Textual.
Polling honors Google's `interval`, backs off on `slow_down`, and stops on
expiry or cancel.

Two files persist under `$XDG_STATE_HOME/omarchy-ytmusic/`, both mode 0600:
`oauth.json` (the refreshable token) and `client.json` (the OAuth client
credentials). `YTMusic` is constructed with both — the token path and an
`OAuthCredentials` instance — because a custom-client token cannot refresh
without its client. No password ever exists outside Google's page.

## Idle lifecycle

The service supervises mpv on a 20 s timer. When the playlist is empty or mpv
is idle for `idleShutdownMinutes` (default 10), it sends `quit` over the
socket and stops the reconnect loop. Any later playback request — from the
widget, the TUI, or the IPC target — respawns mpv with the currently
configured `--ytdl-format`. A quality setting change stops an idle player so
the next start uses the new format; a playing player is never touched.

## Terminal detection for launchTui

The service resolves the terminal once: the plugin setting (used as an
argument prefix, e.g. `alacritty -e`) → `$TERMINAL` (Omarchy sets
`xdg-terminal-exec`) → `foot`, `kitty`, `alacritty`, `ghostty`, `wezterm`,
whichever exists first. Known terminals get the right argument form; unknown
commands are invoked as `<command> <launcher>`.

## Local development

From a checkout on Omarchy 4, link the plugin manually:

```bash
omarchy plugin validate ./Omarchy-YouTube-Music
mkdir -p ~/.config/omarchy/plugins
cp -r ./Omarchy-YouTube-Music ~/.config/omarchy/plugins/quickshell.ytmusic
omarchy plugin enable quickshell.ytmusic --section left
omarchy restart shell
./scripts/setup.sh
```

Python checks:

```bash
~/.local/share/omarchy-ytmusic/venv/bin/python -m compileall tui
```

QML changes hot-reload when files inside the plugin directory change.

## Upstream projects

- [Omarchy](https://github.com/basecamp/omarchy) — the distro and plugin system
- [ytmusicapi](https://github.com/sigma67/ytmusicapi) — the YouTube Music data API
- [mpv](https://mpv.io) and [yt-dlp](https://github.com/yt-dlp/yt-dlp) — playback
- [Textual](https://github.com/Textualize/textual) — the TUI framework
- [Omarchy-Spotify](https://github.com/stappmus/Omarchy-Spotify) — the plugin
  this one's structure and bar-widget patterns follow
