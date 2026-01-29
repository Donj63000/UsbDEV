from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import AsyncIterator, Dict, Iterable, Literal, Optional, Sequence, TypedDict


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


def codex_install_prefix(root_dir: Path) -> Path:
    """Retourne le préfixe d'installation portable pour Codex."""
    return root_dir / ".usbide" / "codex"


def codex_bin_dir(prefix: Path) -> Path:
    """Retourne le répertoire des scripts selon l'OS."""
    return prefix / ("Scripts" if os.name == "nt" else "bin")


def codex_env(root_dir: Path, base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Construit un environnement incluant le binaire Codex portable."""
    env = dict(base_env) if base_env is not None else os.environ.copy()
    bin_dir = codex_bin_dir(codex_install_prefix(root_dir))
    path_value = env.get("PATH", "")
    path_parts = path_value.split(os.pathsep) if path_value else []
    # Ajoute le binaire portable en tête du PATH.
    if str(bin_dir) not in path_parts:
        env["PATH"] = os.pathsep.join([str(bin_dir), *path_parts]) if path_parts else str(bin_dir)
    return env


def tools_install_prefix(root_dir: Path) -> Path:
    """Retourne le préfixe d'installation portable pour les outils (ex: PyInstaller)."""
    return root_dir / ".usbide" / "tools"


def tools_env(root_dir: Path, base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Construit un environnement incluant les outils portables."""
    env = dict(base_env) if base_env is not None else os.environ.copy()
    bin_dir = codex_bin_dir(tools_install_prefix(root_dir))
    path_value = env.get("PATH", "")
    path_parts = path_value.split(os.pathsep) if path_value else []
    # Ajoute le binaire des outils en tête du PATH pour garantir la portabilité.
    if str(bin_dir) not in path_parts:
        env["PATH"] = os.pathsep.join([str(bin_dir), *path_parts]) if path_parts else str(bin_dir)
    return env


def parse_tool_list(raw: str) -> list[str]:
    """Nettoie une liste d'outils depuis une chaîne (virgules / espaces)."""
    items = [item.strip() for item in raw.replace(",", " ").split()]
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def tool_available(
    tool: str, root_dir: Optional[Path] = None, env: Optional[Dict[str, str]] = None
) -> bool:
    """Vérifie la présence d'un outil dans le PATH (local ou système)."""
    if not tool.strip():
        # Protection: un nom vide n'est pas valide.
        raise ValueError("tool ne doit pas être vide")
    search_env = env
    if root_dir is not None:
        search_env = tools_env(root_dir, env)
    return shutil.which(tool, path=search_env.get("PATH") if search_env else None) is not None


def pyinstaller_available(root_dir: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> bool:
    """Vérifie la présence du binaire `pyinstaller` dans le PATH."""
    return tool_available("pyinstaller", root_dir=root_dir, env=env)


def pyinstaller_install_argv(prefix: Path) -> list[str]:
    """Commande pour installer PyInstaller via pip dans un préfixe portable."""
    return pip_install_argv(prefix, ["pyinstaller"])


def pip_install_argv(prefix: Path, packages: Iterable[str]) -> list[str]:
    """Commande pour installer des packages via pip dans un préfixe portable."""
    cleaned = [pkg.strip() for pkg in packages if pkg.strip()]
    if not cleaned:
        # Protection: il faut au moins un package valide.
        raise ValueError("packages ne doit pas être vide")
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--prefix",
        str(prefix),
        *cleaned,
    ]


def pyinstaller_build_argv(script: Path, dist_dir: Path, *, onefile: bool = True) -> list[str]:
    """Commande pour générer un exécutable depuis un script Python."""
    if not script.name.strip():
        # Protection: un script vide n'est pas valide.
        raise ValueError("script ne doit pas être vide")
    argv = [
        "pyinstaller",
        "--noconfirm",
        "--distpath",
        str(dist_dir),
        str(script),
    ]
    if onefile:
        argv.insert(1, "--onefile")
    return argv


def codex_cli_available(root_dir: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> bool:
    """Vérifie la présence du binaire `codex` dans le PATH."""
    search_env = env
    if root_dir is not None:
        search_env = codex_env(root_dir, env)
    # Utilise shutil.which pour rester portable entre OS.
    return shutil.which("codex", path=search_env.get("PATH") if search_env else None) is not None


def codex_login_argv() -> list[str]:
    """Commande pour initier l'authentification Codex (via navigateur ChatGPT)."""
    return ["codex", "auth", "login"]


def codex_status_argv() -> list[str]:
    """Commande pour vérifier l'état d'authentification Codex."""
    return ["codex", "auth", "status"]


def codex_install_argv(prefix: Path, package: str) -> list[str]:
    """Commande pour installer Codex via pip dans un préfixe portable."""
    if not package.strip():
        # Protection: un nom de package vide n'est pas valide.
        raise ValueError("package ne doit pas être vide")
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--prefix",
        str(prefix),
        package,
    ]
