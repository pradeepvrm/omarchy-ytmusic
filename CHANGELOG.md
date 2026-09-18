# Changelog

## 1.0.0 — 2026-09-18

First release.

- Omarchy 4 plugin (`quickshell.ytmusic`): service + bar widget with manifest
  settings schema (bar text, scrolling, quality, idle shutdown, terminal).
- Top bar widget: YouTube Music icon, playing state, scrolling title/artist,
  mini player popup with artwork, transport controls, volume, and a
  one-click TUI launcher.
- Full terminal player (Textual): personalized Home shelves, Search with
  type filters, Library (playlists, liked songs, albums, artists, history),
  playlist/album/artist views, live queue, radio mixes, likes, and
  add-to-playlist with creation.
- YouTube account sign-in through the official OAuth device flow; token kept
  under the user state directory with owner-only permissions.
- Shared mpv audio engine with the service: JSON IPC over a private Unix
  socket, MPRIS published through Omarchy's bundled mpv-mpris.
- Self-preparing setup (private virtualenv + pinned requirements + launcher),
  idle supervision, and a complete uninstaller.
