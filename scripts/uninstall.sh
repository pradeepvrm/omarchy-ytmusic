#!/bin/bash

# Complete removal for the Omarchy YouTube Music plugin. Run from outside the
# plugin directory (mirrors Omarchy-Spotify's uninstaller contract):
#
#   cd "$HOME" && "$HOME/.config/omarchy/plugins/quickshell.ytmusic/scripts/uninstall.sh"

set -uo pipefail

plugin_id="quickshell.ytmusic"
plugin_dir="$HOME/.config/omarchy/plugins/$plugin_id"
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
state_home=${XDG_STATE_HOME:-"$HOME/.local/state"}
runtime_base=${XDG_RUNTIME_DIR:-"/tmp"}

data_dir="$data_home/omarchy-ytmusic"
state_dir="$state_home/omarchy-ytmusic"
runtime_dir="$runtime_base/omarchy-ytmusic"
launcher_file="$HOME/.local/bin/omarchy-ytmusic"

if [[ $PWD == "$plugin_dir"* ]]; then
  echo "uninstall.sh: run me from outside $plugin_dir (for example: cd \$HOME)" >&2
  exit 1
fi

echo "Stopping the player"
if [[ -S $runtime_dir/mpv.sock ]] && command -v socat >/dev/null 2>&1; then
  printf '{"command": ["quit"]}\n' | timeout 2 socat - UNIX-CONNECT:"$runtime_dir/mpv.sock" >/dev/null 2>&1 || true
fi
sleep 0.3

echo "Removing plugin-owned files"
rm -rf -- "$data_dir" "$state_dir" "$runtime_dir"
rm -f -- "$launcher_file"

if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin disable "$plugin_id" 2>/dev/null || true
  omarchy plugin remove "$plugin_id" --yes 2>/dev/null || true
  omarchy restart shell 2>/dev/null || true
else
  echo "The omarchy command is unavailable; remove $plugin_dir manually." >&2
fi

echo "Done. Omarchy base packages (mpv, yt-dlp, socat) were left installed."
