#!/usr/bin/env bash
# Install homebench into a local venv and write $HOMEBENCH_HOME/config.json.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

DEFAULT_HOST="http://127.0.0.1:8080"
DEFAULT_KEY_FILE="${HOME}/llm-server/llama/api-key.txt"
DEFAULT_MODEL_DIR="/home/eskudo/ai-models"

die() {
    echo "setup.sh: $*" >&2
    exit 1
}

require_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        die "python3 not found on PATH"
    fi
    python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 9) else 1)
PY
}

create_venv() {
    if [[ ! -d .venv ]]; then
        python3 -m venv .venv
    fi
}

install_package() {
    if [[ "${HOMEBENCH_SETUP_SKIP_PIP:-}" == "1" ]]; then
        return 0
    fi
    .venv/bin/python -m pip install -e .
}

read_defaults_flag() {
    USE_DEFAULTS=0
    for arg in "$@"; do
        if [[ "$arg" == "--defaults" ]]; then
            USE_DEFAULTS=1
        fi
    done
}

prompt_value() {
    local label="$1"
    local default="$2"
    local reply
    read -r -p "${label} [${default}]: " reply
    if [[ -z "$reply" ]]; then
        printf '%s' "$default"
    else
        printf '%s' "$reply"
    fi
}

collect_config() {
    if [[ "$USE_DEFAULTS" == "1" ]]; then
        HB_HOST="$DEFAULT_HOST"
        HB_API_KEY_FILE="$DEFAULT_KEY_FILE"
        HB_MODEL_DIR="$DEFAULT_MODEL_DIR"
        return 0
    fi
    HB_HOST="$(prompt_value "Router host" "$DEFAULT_HOST")"
    HB_API_KEY_FILE="$(prompt_value "API key file" "$DEFAULT_KEY_FILE")"
    HB_MODEL_DIR="$(prompt_value "Model directory" "$DEFAULT_MODEL_DIR")"
}

write_config() {
    export HB_HOST HB_API_KEY_FILE HB_MODEL_DIR
    .venv/bin/python - <<'PY'
import os
from homebench.config import HomebenchConfig, save

cfg = HomebenchConfig(
    host=os.environ["HB_HOST"],
    api_key_file=os.environ["HB_API_KEY_FILE"],
    model_dir=os.environ["HB_MODEL_DIR"],
)
save(cfg)
PY
}

install_launcher() {
    local bindir="${HOME}/.local/bin"
    local wrapper="${bindir}/homebench"
    local target="${ROOT}/.venv/bin/homebench"
    if ! mkdir -p "$bindir" 2>/dev/null; then
        echo "setup.sh: could not create ${bindir}; skipping launcher" >&2
        return 0
    fi
    cat > "$wrapper" <<EOF
#!/usr/bin/env bash
exec "${target}" "\$@"
EOF
    if ! chmod +x "$wrapper" 2>/dev/null; then
        echo "setup.sh: could not install launcher at ${wrapper}" >&2
        rm -f "$wrapper"
        return 0
    fi
}

run_doctor() {
    if ! .venv/bin/homebench doctor >/dev/null 2>&1; then
        echo "setup.sh: router check failed; config and venv are still installed" >&2
    fi
}

main() {
    read_defaults_flag "$@"
    require_python
    create_venv
    install_package
    collect_config
    write_config
    install_launcher
    run_doctor
}

main "$@"
