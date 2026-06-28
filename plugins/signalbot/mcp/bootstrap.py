from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = PLUGIN_ROOT / ".venv"
REQUIREMENTS = PLUGIN_ROOT / "requirements.txt"
SERVER = PLUGIN_ROOT / "mcp" / "signalbot_mcp_server.py"
REQUIRED_IMPORTS = ("cryptography", "sqlcipher3", "tzdata")


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv() -> Path:
    python_path = venv_python()
    if not python_path.exists():
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)

    if dependencies_missing(python_path):
        subprocess.check_call(
            [
                str(python_path),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "-r",
                str(REQUIREMENTS),
            ],
            stdout=sys.stderr,
            stderr=sys.stderr,
        )
    return python_path


def dependencies_missing(python_path: Path) -> bool:
    code = "; ".join(f"import {module}" for module in REQUIRED_IMPORTS)
    result = subprocess.run(
        [str(python_path), "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode != 0


def main() -> None:
    try:
        python_path = ensure_venv()
    except Exception as exc:
        print(f"Signalbot failed to prepare its Python environment: {exc}", file=sys.stderr)
        sys.exit(1)

    os.execv(str(python_path), [str(python_path), str(SERVER)])


if __name__ == "__main__":
    main()
