#!/usr/bin/env bash
# Deploy the AP01 agents-dashboard bridge to a standalone macOS directory.
set -euo pipefail

target="$HOME/Library/Application Support/Cuktech/AP01/agents-dashboard-service"
port=18765
interval=300
python_bin=""
start=false
label="com.cuktech.ap01.agents-dashboard"

usage() {
  printf '%s\n' 'Usage: tools/deploy-agents-dashboard.sh [--target-dir PATH] [--port PORT] [--interval-seconds SECONDS] [--python PATH] [--start]'
}

while (($#)); do
  case "$1" in
    --target-dir) target="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --interval-seconds) interval="$2"; shift 2 ;;
    --python) python_bin="$2"; shift 2 ;;
    --start) start=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

case "$port" in (*[!0-9]*|'') printf '%s\n' 'port must be a number' >&2; exit 2;; esac
case "$interval" in (*[!0-9]*|'') printf '%s\n' 'interval must be a number' >&2; exit 2;; esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
package_dir="$repo_root/features/agents_dashboard"
font_dir="$repo_root/fonts"
template="$package_dir/deployment/macos/$label.plist.template"
launch_dir="$HOME/Library/LaunchAgents"
plist="$launch_dir/$label.plist"
log_dir="$HOME/Library/Logs/Cuktech/AP01"

if [[ -z "$python_bin" ]]; then python_bin="$(command -v python3 || true)"; fi
[[ -n "$python_bin" && -x "$python_bin" ]] || { printf '%s\n' 'python3 not found; pass --python with an absolute path' >&2; exit 1; }
"$python_bin" -c 'import PIL' >/dev/null 2>&1 || { printf '%s\n' 'Pillow is not installed for this Python interpreter' >&2; exit 1; }
command -v plutil >/dev/null || { printf '%s\n' 'plutil is required on macOS' >&2; exit 1; }
command -v launchctl >/dev/null || { printf '%s\n' 'launchctl is required on macOS' >&2; exit 1; }
command -v curl >/dev/null || { printf '%s\n' 'curl is required on macOS' >&2; exit 1; }
[[ -d "$package_dir" && -d "$font_dir" && -f "$template" ]] || { printf '%s\n' 'required project deployment files are missing' >&2; exit 1; }

if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
  printf 'port %s is already in use; stop the existing service first\n' "$port" >&2; exit 1
fi
if [[ -e "$target/run-bridge.sh" || -e "$target/features/agents_dashboard/bridge.py" ]]; then
  printf 'target already deployed: %s; choose another directory\n' "$target" >&2; exit 1
fi

mkdir -p "$target/features" "$target/service-output" "$target/service-cache" "$log_dir" "$launch_dir"
cp "$repo_root/features/__init__.py" "$target/features/__init__.py"
ditto "$package_dir" "$target/features/agents_dashboard"
ditto "$font_dir" "$target/fonts"
escape() { printf '%s' "$1" | sed 's/[&|\\]/\\&/g'; }
sed -e "s|{{PYTHON}}|$(escape "$python_bin")|g" -e "s|{{PORT}}|$port|g" \
    -e "s|{{INTERVAL}}|$interval|g" -e "s|{{PROJECT}}|$(escape "$target")|g" \
    -e "s|{{FONTS}}|$(escape "$target/fonts")|g" -e "s|{{OUTPUT}}|$(escape "$target/service-output")|g" \
    -e "s|{{CACHE}}|$(escape "$target/service-cache")|g" -e "s|{{CODEX_HOME}}|$(escape "$HOME/.codex")|g" \
    -e "s|{{LOG}}|$(escape "$log_dir/bridge.log")|g" -e "s|{{ERROR_LOG}}|$(escape "$log_dir/bridge-err.log")|g" \
    "$template" > "$plist"
plutil -lint "$plist" >/dev/null
launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
printf 'Deployed to: %s\nLogin service: %s\n' "$target" "$label"

if [[ "$start" == true ]]; then
  deadline=$((SECONDS + 30))
  until curl --fail --silent --show-error "http://127.0.0.1:$port/health" >/dev/null; do
    (( SECONDS < deadline )) || { printf 'service did not become healthy; check %s\n' "$log_dir" >&2; exit 1; }
    sleep 2
  done
  printf '%s\n' 'Health check passed'
fi
