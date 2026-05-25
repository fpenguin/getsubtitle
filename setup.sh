#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if [ "${PYTHON:-}" ]; then
  PYTHON_CMD="$PYTHON"
else
  PYTHON_CMD=""
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_CMD="$candidate"
      break
    fi
  done
fi

if [ -z "$PYTHON_CMD" ]; then
  echo "Python 3.10 or newer is required."
  echo "Install it from https://www.python.org/ or your OS package manager."
  exit 1
fi

"$PYTHON_CMD" - <<'PY'
import sys
if sys.version_info < (3, 10):
    print(f"Python 3.10 or newer is required; found {sys.version.split()[0]}.")
    print("macOS Homebrew: brew install python@3.11")
    print("Then rerun: PYTHON=python3.11 ./setup.sh")
    raise SystemExit(1)
PY

if [ -f ".venv/pyvenv.cfg" ]; then
  VENV_VERSION="$(.venv/bin/python - <<'PY' 2>/dev/null || true
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
  case "$VENV_VERSION" in
    3.10|3.11|3.12|3.13) ;;
    *)
      echo "Existing .venv uses Python ${VENV_VERSION:-unknown}; recreating it with $PYTHON_CMD."
      rm -rf .venv
      ;;
  esac
fi

"$PYTHON_CMD" -m venv .venv

if [ -f ".venv/bin/activate" ]; then
  # POSIX shells, macOS, Linux, Git Bash, WSL
  . ".venv/bin/activate"
else
  echo "Virtual environment created at .venv."
  echo "On Windows PowerShell, activate it with:"
  echo "  .\\.venv\\Scripts\\Activate.ps1"
  echo "Then run:"
  echo "  python -m pip install --upgrade pip"
  echo "  python -m pip install -e .[furigana]"
  exit 0
fi

python -m pip install --upgrade pip
python -m pip install -e ".[furigana]"

echo "Ready. Run:"
echo "  getsubtitle ..."
