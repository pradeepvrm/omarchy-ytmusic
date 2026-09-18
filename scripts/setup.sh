#!/bin/bash

# Setup for the Omarchy YouTube Music plugin. Omarchy's plugin installer
# deliberately clones and validates plugins without running install hooks,
# so the enabled plugin prepares itself on first load instead.
#
# Everything this script writes lives OUTSIDE the plugin directory: Omarchy
# treats any write inside a plugin folder as a plugin change and hot-reloads
# it, which would kill a build in progress.

set -euo pipefail

source_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
state_home=${XDG_STATE_HOME:-"$HOME/.local/state"}
runtime_base=${XDG_RUNTIME_DIR:-"/tmp"}

data_dir="$data_home/omarchy-ytmusic"
state_dir="$state_home/omarchy-ytmusic"
runtime_dir="$runtime_base/omarchy-ytmusic"
venv_dir="$data_dir/venv"
venv_python="$venv_dir/bin/python"
marker_file="$data_dir/setup.marker"
launcher_dir="$HOME/.local/bin"
launcher_file="$launcher_dir/omarchy-ytmusic"

requirements_file="$source_root/tui/requirements.txt"

fail() {
  echo "failed: $*" >&2
  exit 1
}

plugin_version() {
  local version
  version=$(python3 - "$source_root/manifest.json" <<'PY' 2>/dev/null || true
import json
import sys

try:
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        print(json.load(handle).get("version", "unknown"))
except (OSError, ValueError):
    print("unknown")
PY
)
  [[ -n $version ]] || version=unknown
  printf '%s' "$version"
}

expected_marker() {
  local requirements_hash
  if [[ -f $requirements_file ]]; then
    requirements_hash=$(sha256sum -- "$requirements_file") || requirements_hash="none"
    requirements_hash=${requirements_hash%% *}
  else
    requirements_hash="none"
  fi
  printf '%s\n%s\n' "$(plugin_version)" "$requirements_hash"
}

check_ready() {
  [[ -x $venv_python && -f $marker_file ]] || return 1
  [[ -f $requirements_file ]] || return 1
  [[ $(<"$marker_file") == "$(expected_marker)" ]] || return 1
  return 0
}

check_dependencies() {
  for command_name in python3 mpv yt-dlp; do
    command -v "$command_name" >/dev/null 2>&1 || {
      echo "failed: Omarchy base command is missing: $command_name" >&2
      return 1
    }
  done
  return 0
}

if [[ ${1:-} == "--status" ]]; then
  if ! check_dependencies; then
    exit 1
  fi
  if check_ready; then
    echo "ready"
  else
    echo "needed"
  fi
  exit 0
fi

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  cat <<'EOF'
Usage: scripts/setup.sh [--status]

Prepare the plugin-owned Python environment and launcher. Without arguments
this creates or refreshes the virtualenv under
$XDG_DATA_HOME/omarchy-ytmusic, installs the TUI dependencies, and installs
the omarchy-ytmusic launcher into ~/.local/bin. With --status it only prints
"ready" or "needed" and exits.
EOF
  exit 0
fi

check_dependencies || exit 1

install -d -m 700 -- "$data_dir" "$state_dir" "$runtime_dir" "$launcher_dir"

if [[ -d $venv_dir && ! -x $venv_python ]]; then
  echo "Removing broken virtualenv"
  rm -rf -- "$venv_dir"
fi

if [[ ! -d $venv_dir ]]; then
  echo "Creating Python virtualenv"
  python3 -m venv "$venv_dir" || fail "could not create the virtualenv"
fi

echo "Installing TUI dependencies"
"$venv_python" -m pip install --disable-pip-version-check --no-input \
  --no-python-version-warning -r "$requirements_file" \
  || fail "pip install failed (is the network reachable?)"

expected_marker >"$marker_file"

chmod +x -- "$source_root/scripts/setup.sh" \
  "$source_root/scripts/run-tui.sh" \
  "$source_root/scripts/uninstall.sh" 2>/dev/null || true

printf '#!/bin/bash\nexec %q/scripts/run-tui.sh "$@"\n' "$source_root" >"$launcher_file"
chmod +x -- "$launcher_file"

echo "ready"
echo "Installed launcher: $launcher_file"
