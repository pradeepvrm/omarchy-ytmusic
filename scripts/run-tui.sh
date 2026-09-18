#!/bin/bash

# Launch the Omarchy YouTube Music TUI. Safe to call directly, from a
# keybinding via `omarchy shell -q quickshell.ytmusic.player launchTui`, or
# through the ~/.local/bin/omarchy-ytmusic launcher. Self-heals a missing
# virtualenv by running setup first.

set -euo pipefail

source_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
data_dir="$data_home/omarchy-ytmusic"
venv_python="$data_dir/venv/bin/python"

if [[ ! -x $venv_python ]]; then
  echo "YouTube Music: preparing the Python environment (first run)…" >&2
  "$source_root/scripts/setup.sh" >&2 || {
    echo "YouTube Music: setup failed. See the plugin's README for help." >&2
    exit 1
  }
fi

# Terminals with a minimal TERM cannot render the TUI.
if [[ ${TERM:-} == dumb || -z ${TERM:-} ]]; then
  export TERM=xterm-256color
fi

export PYTHONUNBUFFERED=1

cd "$source_root"
exec "$venv_python" -m tui "$@"
