#!/usr/bin/env sh
set -eu

REPO_URL="${GETSUBTITLE_REPO_URL:-https://github.com/fpenguin/getsubtitle.git}"
APP_HOME="${GETSUBTITLE_HOME:-$HOME/.local/share/getsubtitle}"
BIN_DIR="${GETSUBTITLE_BIN_DIR:-$HOME/.local/bin}"
APP_VENV="$APP_HOME/.venv"

say() {
  printf '%s\n' "$*"
}

ask() {
  prompt="$1"
  default="$2"
  if [ ! -t 0 ]; then
    printf '%s\n' "$default"
    return
  fi
  printf '%s [%s] ' "$prompt" "$default" >&2
  read -r answer || answer=""
  if [ -z "$answer" ]; then
    printf '%s\n' "$default"
  else
    printf '%s\n' "$answer"
  fi
}

find_python() {
  if [ "${PYTHON:-}" ]; then
    printf '%s\n' "$PYTHON"
    return
  fi
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return
    fi
  done
}

validate_python() {
  "$1" - <<'PY'
import sys
if sys.version_info < (3, 10):
    print(f"Python 3.10 or newer is required; found {sys.version.split()[0]}.")
    print("macOS Homebrew: brew install python@3.11")
    print("Then rerun: PYTHON=python3.11 sh setup.sh")
    raise SystemExit(1)
PY
}

choose_extras() {
  if [ "${GETSUBTITLE_EXTRAS:-}" ]; then
    printf '%s\n' "$GETSUBTITLE_EXTRAS"
    return
  fi
  say ""
  say "Install optional reading-aid backends?"
  say "  1) All CJK helpers: Japanese furigana + Korean romanization + Mandarin pinyin"
  say "  2) Japanese furigana only"
  say "  3) Korean romanization only"
  say "  4) Mandarin pinyin only"
  say "  5) Minimal install"
  choice="$(ask "Choose 1/2/3/4/5" "1")"
  case "$choice" in
    1|"") printf '%s\n' "furigana,romanization-ko,romanization-zh" ;;
    2) printf '%s\n' "furigana" ;;
    3) printf '%s\n' "romanization-ko" ;;
    4) printf '%s\n' "romanization-zh" ;;
    5) printf '%s\n' "" ;;
    *)
      say "Unknown choice: $choice"
      say "Using all CJK helpers."
      printf '%s\n' "furigana,romanization-ko,romanization-zh"
      ;;
  esac
}

install_spec_for_git() {
  extras="$1"
  if [ -n "$extras" ]; then
    printf '%s\n' "getsubtitle[$extras] @ git+$REPO_URL"
  else
    printf '%s\n' "getsubtitle @ git+$REPO_URL"
  fi
}

write_shim() {
  mkdir -p "$BIN_DIR"
  cat > "$BIN_DIR/getsubtitle" <<EOF
#!/usr/bin/env sh
exec "$APP_VENV/bin/getsubtitle" "\$@"
EOF
  chmod +x "$BIN_DIR/getsubtitle"
}

run_first_time_setup() {
  if [ "${GETSUBTITLE_RUN_SETUP:-}" = "0" ]; then
    return
  fi
  if [ ! -t 0 ]; then
    say ""
    say "Installed. Run this when you are ready:"
    say "  getsubtitle setup"
    return
  fi
  answer="$(ask "Run first-time setup now?" "Y")"
  case "$answer" in
    y|Y|yes|YES|"")
      "$APP_VENV/bin/getsubtitle" setup
      ;;
    *)
      say ""
      say "Installed. Run this when you are ready:"
      say "  getsubtitle setup"
      ;;
  esac
}

PYTHON_CMD="$(find_python || true)"
if [ -z "$PYTHON_CMD" ]; then
  say "Python 3.10 or newer is required."
  say "Install it from https://www.python.org/ or your OS package manager."
  exit 1
fi
validate_python "$PYTHON_CMD"

EXTRAS="$(choose_extras)"

if [ -f "./pyproject.toml" ] && [ -f "./getsubtitle_core.py" ]; then
  # Developer/source checkout: keep the historical local editable venv.
  VENV=".venv"
  "$PYTHON_CMD" -m venv "$VENV"
  # POSIX shells, macOS, Linux, Git Bash, WSL.
  . "$VENV/bin/activate"
  python -m pip install --upgrade pip
  if [ -n "$EXTRAS" ]; then
    python -m pip install -e ".[$EXTRAS]"
  else
    python -m pip install -e .
  fi
  say ""
  say "Ready. This checkout is installed in editable mode."
  say "Run:"
  say "  source .venv/bin/activate"
  say "  getsubtitle setup"
  exit 0
fi

# One-line installer path: install into an app venv and expose a small shim.
mkdir -p "$APP_HOME"
"$PYTHON_CMD" -m venv "$APP_VENV"
"$APP_VENV/bin/python" -m pip install --upgrade pip
"$APP_VENV/bin/python" -m pip install "$(install_spec_for_git "$EXTRAS")"
write_shim

say ""
say "getsubtitle is installed at:"
say "  $APP_VENV/bin/getsubtitle"
say ""
say "Command shim written to:"
say "  $BIN_DIR/getsubtitle"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    say ""
    say "Add this to your shell profile if 'getsubtitle' is not found:"
    say "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

run_first_time_setup
