#!/usr/bin/env bash
# Install find-research-papers-mcp into your MCP client.
# Usage: bash install.sh [--claude|--cursor|--opencode|--windsurf|--vscode] [--src <name>]
# No flag: auto-detect the harness from existing config files.
# Telemetry: anonymous install metrics, opt out with FIND_RESEARCH_PAPERS_MCP_TELEMETRY=false,
# DISABLE_TELEMETRY=1, DO_NOT_TRACK=1, or NO_TELEMETRY=1
set -euo pipefail

NAME="find-research-papers-mcp"
SRC="${FIND_RESEARCH_PAPERS_MCP_SOURCE:-installer}"
HARNESS=""
ARGS=("$@")
while [[ $# -gt 0 ]]; do
  case "$1" in
    --claude) HARNESS=claude ;;
    --cursor) HARNESS=cursor ;;
    --opencode) HARNESS=opencode ;;
    --windsurf) HARNESS=windsurf ;;
    --vscode) HARNESS=vscode ;;
    --src) shift; [[ -n "${1:-}" ]] && SRC="$1" ;;
    --src=*) SRC="${1#--src=}" ;;
    --help|-h)
      sed -n '2,4p' "$0"; exit 0 ;;
    *) warn "unknown flag: $1"; exit 1 ;;
  esac
  shift
done
SRC="${SRC:-installer}"

TELEMETRY_URL="${FIND_RESEARCH_PAPERS_MCP_TELEMETRY_URL:-https://papers-mcp-install-telemetry.reachsuren.workers.dev/telemetry}"
# Opt-out semantics mirror papers_mcp/telemetry.py: the server var disables on
# false/0/off; any of DISABLE_TELEMETRY / DO_NOT_TRACK / NO_TELEMETRY disables
# on 1/true/yes/on. Any disable flag wins.
TELEMETRY_ON=1
case "$(printf '%s' "${FIND_RESEARCH_PAPERS_MCP_TELEMETRY:-true}" | tr '[:upper:]' '[:lower:]')" in
  false|0|off) TELEMETRY_ON=0 ;;
esac
for _optout in "${DISABLE_TELEMETRY:-}" "${DO_NOT_TRACK:-}" "${NO_TELEMETRY:-}"; do
  case "$(printf '%s' "$_optout" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) TELEMETRY_ON=0 ;;
  esac
done

say()  { printf "\033[1;32m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[!]\033[0m %s\n" "$*" >&2; }

# Persist identity + source BEFORE the server's first run, so the server's
# events (mcp_started, tool_executed) join this install in the funnel.
# Opt-out gates ALL side effects: no identity/source writes when disabled
# (an existing identity file may still be read).
ANON_ID="inst_$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || echo $RANDOM$RANDOM)"
if [[ -f "$HOME/.find_research_papers_mcp/installation_id" ]]; then
  ANON_ID="$(cat "$HOME/.find_research_papers_mcp/installation_id")"
elif [[ "$TELEMETRY_ON" == "1" ]]; then
  mkdir -p "$HOME/.find_research_papers_mcp" 2>/dev/null || true
  echo "$ANON_ID" > "$HOME/.find_research_papers_mcp/installation_id" 2>/dev/null || true
fi
if [[ "$TELEMETRY_ON" == "1" ]]; then
  echo "$SRC" > "$HOME/.find_research_papers_mcp/source" 2>/dev/null || true
fi

OS_NAME="$(uname -s 2>/dev/null || echo unknown)"
ARCH="$(uname -m 2>/dev/null || echo unknown)"
SHELL_TYPE="${SHELL##*/}"
PYTHON_VERSION="$(python3 --version 2>/dev/null | awk '{print $2}' || echo none)"
HAS_UV="$(command -v uv >/dev/null 2>&1 && echo true || echo false)"
HAS_BREW="$(command -v brew >/dev/null 2>&1 && echo true || echo false)"
DETECTED=""
WIRED=""

send_telemetry() {
  [[ "$TELEMETRY_ON" == "0" ]] && return 0
  local outcome="$1" extra="${2:-}"
  local payload="{\"anonymous_id\":\"$ANON_ID\",\"src\":\"$SRC\",\"install_outcome\":\"$outcome\",\"os_name\":\"$OS_NAME\",\"arch\":\"$ARCH\",\"shell_type\":\"$SHELL_TYPE\",\"python_version\":\"$PYTHON_VERSION\",\"has_uv\":$HAS_UV,\"has_brew\":$HAS_BREW,\"harnesses_detected\":\"$DETECTED\",\"wired_clients\":\"$WIRED\",\"runtime\":\"$RUNTIME\",\"error_code\":$extra}"
  curl -s -m 3 -X POST "$TELEMETRY_URL" -H "Content-Type: application/json" -d "$payload" >/dev/null 2>&1 || true
}

handle_error() {
  local code=$?
  send_telemetry "error" "$code"
  exit $code
}
trap handle_error ERR

if command -v uvx >/dev/null 2>&1; then
  RUNTIME="uvx"
  CMD='["uvx", "--from", "find-research-papers-mcp", "find-research-papers-mcp-server"]'
elif command -v npx >/dev/null 2>&1; then
  RUNTIME="npx"
  CMD='["npx", "-y", "find-research-papers-mcp"]'
else
  warn "need uvx (uv) or npx (node) on PATH — https://docs.astral.sh/uv/ or https://nodejs.org/"
  send_telemetry "error" "no_runtime"
  exit 1
fi
say "runtime: $RUNTIME"

detect() {
  command -v claude >/dev/null 2>&1 && echo claude && return
  [[ -f "$HOME/.config/opencode/opencode.json" || -f "$HOME/.config/opencode/opencode.jsonc" ]] && echo opencode && return
  [[ -d "$HOME/.cursor" ]] && echo cursor && return
  [[ -d "$HOME/.codeium/windsurf" ]] && echo windsurf && return
  command -v code >/dev/null 2>&1 && echo vscode && return
  echo generic
}

if [[ -z "$HARNESS" ]]; then
  HARNESS=$(detect)
  say "detected harness: $HARNESS"
fi

case "$HARNESS" in
  claude)
    DETECTED="$DETECTED claude"
    if [[ -f ".mcp.json" ]]; then FILE=".mcp.json"; KEY="mcpServers";
    else FILE="$HOME/.claude.json"; KEY="mcpServers"; fi ;;
  cursor)   FILE="$HOME/.cursor/mcp.json";      KEY="mcpServers"; DETECTED="$DETECTED cursor" ;;
  windsurf) FILE="$HOME/.codeium/windsurf/mcp_config.json"; KEY="mcpServers"; DETECTED="$DETECTED windsurf" ;;
  vscode)   FILE=".vscode/mcp.json";            KEY="mcpServers"; DETECTED="$DETECTED vscode" ;;
  opencode)
    DETECTED="$DETECTED opencode"
    if [[ -f "$HOME/.config/opencode/opencode.json" ]]; then FILE="$HOME/.config/opencode/opencode.json";
    else FILE="$HOME/.config/opencode/opencode.jsonc"; fi
    KEY="mcp" ;;
  generic)
    FILE=".mcp.json"; KEY="mcpServers" ;;
  *) warn "unknown harness: $HARNESS"; exit 1 ;;
esac

mkdir -p "$(dirname "$FILE")"
[[ ! -f "$FILE" ]] && printf '{\n}\n' > "$FILE"

say "writing $FILE [$KEY]"

python3 - "$FILE" "$KEY" "$CMD" "$NAME" <<'PY'
import json, sys

path, key, cmd, name = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), sys.argv[4]
raw = open(path).read()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("PARSE_FAIL")
    sys.exit(0)

if key == "mcpServers":
    data.setdefault("mcpServers", {})[name] = {"command": cmd[0], "args": cmd[1:]}
else:
    servers = data.setdefault("mcp", {}).setdefault(name, {})
    servers.update({"type": "local", "command": cmd, "enabled": True, "env": {}})

with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print("OK")
PY

WIRED="$HARNESS"
say "installed. restart the client, then check:"
case "$HARNESS" in
  claude)   echo "  claude mcp list | grep $NAME" ;;
  opencode) echo "  opencode: /mcp list should show $NAME" ;;
  *)        echo "  the client's MCP servers list should show $NAME" ;;
esac
send_telemetry "success"
