# Omarchy YouTube Music

**YouTube Music in your terminal and your top bar — using your own YouTube account.**

Omarchy YouTube Music is an [Omarchy](https://omarchy.org) 4 plugin that pairs a
small bar widget with a full terminal player. Sign in once with your YouTube
account and the homepage, recommendations, likes, and library you already know
from music.youtube.com are yours on the desktop — without keeping a browser
open. Playback streams through Omarchy's own mpv + yt-dlp stack, so it stays
light and follows your system audio setup.

## Install

```bash
omarchy plugin add https://github.com/<you>/Omarchy-YouTube-Music.git --enable
```

Requires Omarchy 4 with the Quickshell shell. Omarchy's base packages already
provide mpv, yt-dlp, socat, and Python. On first load the plugin builds a
private Python environment (ytmusicapi + textual) under
`~/.local/share/omarchy-ytmusic` — no root, nothing outside your home.

## First run: sign in

Click the YouTube Music icon in the top bar and press **Open YouTube Music
TUI**, or run:

```bash
omarchy-ytmusic
```

Sign-in uses your browser's YouTube Music cookies — no API key needed:

1. Open [music.youtube.com](https://music.youtube.com) and log in as usual.
2. Open DevTools (F12), go to the **Network** tab, and reload the page.
3. Click any request to `music.youtube.com` (e.g. `browse`), then under
   **Request Headers** copy them all (right-click, copy all).
4. Paste into the TUI and save. The headers are kept in
   `~/.local/state/omarchy-ytmusic/browser.json` with owner-only
   permissions and never leave your machine.

Your password is only ever entered on Google's own page. After this one-time
setup, your homepage, recommendations, likes, and library are yours on the
desktop. If the cookies expire (Google rotates them periodically), the TUI
shows auth errors — just paste fresh headers the same way.

The TUI also offers the Google OAuth device flow (personal Cloud client of
type **TVs and Limited Input devices**) as a fallback, but note: since late
August 2025 YouTube's servers reject those tokens with HTTP 400
(`upstream ytmusicapi issue #813`), so OAuth sign-in succeeds yet every
request fails. Use the browser method until that is resolved upstream.

## The bar widget

- **Left-click** opens the mini player: artwork, title, artist, position,
  play/pause, skip, stop, and volume.
- **Right-click** opens the terminal player.
- **Middle-click** toggles play/pause.
- **Mouse wheel** changes volume; **Shift+wheel** changes track.
- The widget follows your Omarchy theme and scrolls long titles softly.

Everything is also reachable from the keyboard without opening the TUI:

```bash
omarchy shell -q quickshell.ytmusic.player toggle
omarchy shell -q quickshell.ytmusic.player next
omarchy shell -q quickshell.ytmusic.player previous
omarchy shell -q quickshell.ytmusic.player volumeUp
omarchy shell -q quickshell.ytmusic.player volumeDown
omarchy shell -q quickshell.ytmusic.player launchTui
```

Two read-only helpers exist for keybindings and debugging: `status`
prints the widget's view of the player as JSON, and `reconnect` cycles
the player's socket without touching mpv.

```bash
omarchy-shell quickshell.ytmusic.player status
```

To bind the player to a key, add this to `~/.config/hypr/bindings.lua`:

```lua
  hl.unbind("SUPER + SHIFT + M") -- previously: Music
  o.bind("SUPER + SHIFT + M", "Omarchy YouTube Music",
    "omarchy shell -q quickshell.ytmusic.player launchTui")
```

The bar widget's mini player opens like Bluetooth and Network do, through
the shell's widget toggle — no plugin code needed beyond the `open()` /
`close()` interface it already exposes:

```lua
  o.bind("SUPER + CTRL + M", "YT Music mini player",
    "omarchy-shell shell toggle quickshell.ytmusic")
```

Run `hyprctl reload` and check `hyprctl configerrors` after saving.

## The terminal player

| Key | What it does |
| --- | --- |
| `/` | Search all of YouTube Music (songs, videos, albums, artists, playlists) |
| `F2` / `F3` / `F4` / `F5` | Home / Search / Library / Queue |
| `Space` | Play or pause |
| `n` / `p` | Next / previous track |
| `,` / `.` | Seek 10 seconds back / forward |
| `+` / `-` / `m` | Volume up / down / mute |
| `Enter` | Play from the selected row — the rest of the list follows |
| `e` / `N` | Queue the selected track / play it next |
| `r` | Start an endless radio mix from the selected track |
| `a` | Add the selected track to one of your playlists (or create one) |
| `l` | Like or unlike the selected track |
| `s` | Shuffle and play (playlist and album screens) |
| `x` / `c` | Queue screen: remove a row / clear the queue |
| `?` | Every shortcut, in the TUI itself |
| `q` | Quit — **music keeps playing** while the bar widget stays in control |

The **Home** tab is your personalized YouTube Music homepage: Listen again,
Mixed for you, New releases, Moods and genres, and whatever else your account
has earned. The **Library** tab holds your playlists, liked songs, albums,
artists, and history. Closing the TUI never stops the music; the bar widget
keeps showing artwork, titles, and controls, and the player goes to sleep by
itself after playback has been stopped for the configured idle time.

## Settings

The plugin ships Omarchy settings alongside the bar widget (pick them from
Omarchy's bar widget settings):

- Show track title / artist name / paused track in the bar
- Scroll long bar text and the maximum bar text width
- Playback quality (best available, capped at 128 or 96 kbps)
- Idle shutdown minutes for the background player
- Terminal command used to launch the TUI (empty = Omarchy default)

## How it works, briefly

Audio runs in a detached, audio-only mpv supervised by the plugin's Quickshell
service. The TUI and the service both speak mpv's JSON IPC on a private Unix
socket, so queue edits from the terminal instantly reflect in the bar and vice
versa. mpv's bundled MPRIS script publishes playback to the rest of the
desktop, so the stock Omarchy media widget and playerctl see it too. Because
Omarchy treats writes inside a plugin folder as plugin changes, the Python
environment, state, and sockets all live outside the plugin directory. See
[docs/TECHNICAL.md](docs/TECHNICAL.md) for the full picture.

## Remove it completely

Run the bundled uninstaller from outside the plugin directory:

```bash
cd "$HOME" && "$HOME/.config/omarchy/plugins/quickshell.ytmusic/scripts/uninstall.sh"
```

It stops the player, disables and removes the plugin, restarts the shell, and
deletes the plugin-owned Python environment, state, launcher, and sockets.
Omarchy base packages (mpv, yt-dlp, socat) are left installed.

## Notes

- YouTube Music Premium is not required; you get the same streams the web
  player serves to your account.
- Like every Omarchy plugin, this runs as unsandboxed code in your shell
  process — review it before installing.
- Omarchy YouTube Music is an independent project and is not affiliated with
  Google or YouTube. YouTube is a trademark of Google LLC.

Licensed under the [MIT License](LICENSE).
