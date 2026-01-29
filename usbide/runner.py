from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import AsyncIterator, Dict, Literal, Optional, Sequence, TypedDict


class ProcEvent(TypedDict):
    kind: Literal["line", "exit"]
    text: str
    returncode: Optional[int]


async def stream_subprocess(
    argv: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> AsyncIterator[ProcEvent]:
    """Lance un subprocess et stream la sortie.

    - stdout est capturé
    - stderr est redirigé vers stdout
    - encodage sortie: on décode en UTF-8 avec errors='replace'

    Yield des évènements :
      - {'kind': 'line', 'text': '...', 'returncode': None}
      - {'kind': 'exit', 'text': 'exit <rc>', 'returncode': <rc>}
    """
    if not argv:
        # Protection: une commande vide ne doit pas lancer de subprocess.
        raise ValueError("argv ne doit pas être vide")

    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )

    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        yield {"kind": "line", "text": raw.decode("utf-8", errors="replace").rstrip("\n"), "returncode": None}

    rc = await proc.wait()
    yield {"kind": "exit", "text": f"exit {rc}", "returncode": rc}


def windows_cmd_argv(command: str) -> list[str]:
    """Construit argv pour exécuter une commande via cmd.exe sur Windows."""
    comspec = os.environ.get("COMSPEC") or "cmd.exe"
    # /d: ignore AutoRun, /s: string parsing, /c: execute then terminate
    return [comspec, "/d", "/s", "/c", command]


def python_run_argv(script: Path) -> list[str]:
    """Commande pour exécuter un script python avec l'interpréteur courant."""
    return [sys.executable, str(script)]


def codex_cli_available() -> bool:
    """Vérifie la présence du binaire `codex` dans le PATH."""
    # Utilise shutil.which pour rester portable entre OS.
    return shutil.which("codex") is not None


def codex_login_argv() -> list[str]:
    """Commande pour initier l'authentification Codex (via navigateur ChatGPT)."""
    return ["codex", "auth", "login"]
