il faut changer de mental model : Codex “comme dans le terminal” n’est pas une lib Python que tu “importes”, c’est un CLI (programme) que tu lances. Et le CLI officiel s’installe via npm (package @openai/codex) et se connecte via codex login (OAuth ChatGPT) ou via clé API selon le mode.

Donc l’intégration propre dans ton appli USB = embarquer les binaires nécessaires sur la clé + lancer Codex en subprocess + rediriger stdout/stderr vers un panneau UI. Et pour éviter que Codex écrive sur le PC hôte, tu forces CODEX_HOME vers un dossier sur la clé (exactement ce que tu as commencé à faire). Codex utilise par défaut ~/.codex et une config ~/.codex/config.toml (ou .codex/config.toml au niveau projet), mais tu peux déporter en mettant CODEX_HOME.

Je te donne un plan concret (mode “portable pro”) + du code complet (Textual, comme ton projet).

1) Architecture “USB portable” qui marche vraiment
Ce que tu veux obtenir

Tu branches ta clé sur n’importe quel PC Windows.

Tu lances ton IDE (ton app).

Dans l’app : un panneau “Shell logs” + un panneau “Codex logs”.

Tu cliques “Login Codex” → ça ouvre le navigateur et tu te connectes avec ton compte ChatGPT (Pro) → token stocké sur la clé.

Tu tapes un prompt → l’app lance codex exec et stream la sortie dans la fenêtre Codex.

La contrainte clé

Le CLI officiel s’installe via npm (npm i -g @openai/codex dans la doc).
Donc pour zéro-install sur le PC, tu dois embarquer :

un Node portable (zip Windows, décompressé sur la clé)

le package @openai/codex installé localement sur la clé (pas en global sur le PC)

Oui, tu peux tenter de “télécharger à la volée” via npm quand tu branches la clé, mais en entreprise c’est souvent bloqué. Le meilleur = pré-installer Codex sur la clé.

2) Layout de dossiers recommandé sur la clé
USB_ROOT/
  run_ide.bat
  usbide/                # ton code Python (Textual)
  tools/
    python-x64/          # ton python portable (si tu l'embarques)
    git/                 # git portable (optionnel mais utile)
    node/                # Node portable (node.exe + node_modules/npm/...)
  .usbide/
    codex/               # installation npm locale de @openai/codex (node_modules/...)
    tools/               # pip --prefix pour pyinstaller + tools dev
  codex_home/            # auth/config/history codex (CODEX_HOME)
  cache/
    pip/
    pycache/
    npm/
  tmp/

3) Auth Codex “avec ton compte OpenAI / ChatGPT”

Codex CLI supporte deux modes d’auth :

Login ChatGPT (subscription access) : codex login ouvre un navigateur pour l’OAuth ChatGPT

Device auth : codex login --device-auth (utile si browser bloqué / machine verrouillée)

L’important pour toi : en forçant CODEX_HOME=USB_ROOT\codex_home, tout ce que Codex stocke (config/historique/auth) reste sur la clé et pas dans C:\Users\...\.codex.

4) Intégration UI : la manière robuste (non-interactive)

Le point “dur” quand tu veux intégrer un CLI dans une UI : les CLI interactifs (TUI) utilisent souvent un TTY et des séquences ANSI.
La manière la plus stable est d’utiliser le mode non-interactif :

codex exec est fait pour ça (maturity “Stable” dans la doc)

et tu peux demander une sortie JSON Lines : codex exec --json "..."

Donc dans ton app, tu fais :

input “Codex” → à l’enter tu lances codex exec --json "<prompt>"

tu streams stdout ligne par ligne et tu affiches dans le panneau Codex.

5) Très important : ne lance pas codex.cmd (Windows) depuis Python

Sur Windows, beaucoup de CLIs Node exposent codex.cmd (script batch). Les batch sont pénibles à exécuter proprement via subprocess_exec sans shell.
La solution pro : exécuter Codex via node + l’entrypoint JS du package @openai/codex.

Dans le code ci-dessous, je lis node_modules/@openai/codex/package.json et je récupère la clé "bin" pour savoir quel JS lancer. C’est le plus stable (si OpenAI change l’arborescence interne, ton code tient).

6) Patch complet dans TON projet (Textual)

Tu as déjà un projet usbide Textual avec CODEX_HOME etc. Je te donne une version corrigée qui :

installe Codex via npm (dans .usbide/codex)

ajoute un panneau Codex (split logs en 2)

lance codex exec --json dans le panneau Codex

supporte USBIDE_CODEX_DEVICE_AUTH=1 pour codex login --device-auth

6.1 Remplacer usbide/runner.py par ceci
from __future__ import annotations

import asyncio
import json
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
    - encodage sortie: UTF-8 (errors='replace')

    Yield:
      - {'kind': 'line', 'text': '...', 'returncode': None}
      - {'kind': 'exit', 'text': 'exit <rc>', 'returncode': <rc>}
    """
    if not argv:
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
        yield {
            "kind": "line",
            "text": raw.decode("utf-8", errors="replace").rstrip("\n"),
            "returncode": None,
        }

    rc = await proc.wait()
    yield {"kind": "exit", "text": f"exit {rc}", "returncode": rc}


def windows_cmd_argv(command: str) -> list[str]:
    """Construit argv pour exécuter une commande via cmd.exe sur Windows."""
    comspec = os.environ.get("COMSPEC") or "cmd.exe"
    return [comspec, "/d", "/s", "/c", command]


def python_run_argv(script: Path) -> list[str]:
    """Commande pour exécuter un script python avec l'interpréteur courant."""
    return [sys.executable, str(script)]


# =============================================================================
# Outils Python (pip --prefix) : PyInstaller + outils dev
# =============================================================================

def tools_install_prefix(root_dir: Path) -> Path:
    return root_dir / ".usbide" / "tools"


def python_scripts_dir(prefix: Path) -> Path:
    """Dossier Scripts/bin d'un --prefix pip."""
    return prefix / ("Scripts" if os.name == "nt" else "bin")


def tools_env(root_dir: Path, base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = dict(base_env) if base_env is not None else os.environ.copy()
    bin_dir = python_scripts_dir(tools_install_prefix(root_dir))
    path_value = env.get("PATH", "")
    path_parts = path_value.split(os.pathsep) if path_value else []
    if str(bin_dir) not in path_parts:
        env["PATH"] = os.pathsep.join([str(bin_dir), *path_parts]) if path_parts else str(bin_dir)
    return env


def parse_tool_list(raw: str) -> list[str]:
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
    if not tool.strip():
        raise ValueError("tool ne doit pas être vide")
    search_env = env
    if root_dir is not None:
        search_env = tools_env(root_dir, env)
    return shutil.which(tool, path=search_env.get("PATH") if search_env else None) is not None


def pyinstaller_available(root_dir: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> bool:
    return tool_available("pyinstaller", root_dir=root_dir, env=env)


def pip_install_argv(
    prefix: Path,
    packages: Iterable[str],
    *,
    find_links: Optional[Path] = None,
    no_index: bool = False,
) -> list[str]:
    cleaned = [pkg.strip() for pkg in packages if pkg.strip()]
    if not cleaned:
        raise ValueError("packages ne doit pas être vide")
    argv = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--prefix",
        str(prefix),
    ]
    if no_index:
        argv.append("--no-index")
    if find_links is not None:
        argv.extend(["--find-links", str(find_links)])
    argv.extend(cleaned)
    return argv


def pyinstaller_install_argv(
    prefix: Path,
    *,
    find_links: Optional[Path] = None,
    no_index: bool = False,
) -> list[str]:
    return pip_install_argv(prefix, ["pyinstaller"], find_links=find_links, no_index=no_index)


def pyinstaller_build_argv(
    script: Path,
    dist_dir: Path,
    *,
    onefile: bool = False,
    work_dir: Optional[Path] = None,
    spec_dir: Optional[Path] = None,
) -> list[str]:
    if not script.name.strip():
        raise ValueError("script ne doit pas être vide")
    argv = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--distpath",
        str(dist_dir),
    ]
    if onefile:
        argv.remove("--onedir")
        argv.insert(1, "--onefile")
    if work_dir is not None:
        argv.extend(["--workpath", str(work_dir)])
    if spec_dir is not None:
        argv.extend(["--specpath", str(spec_dir)])
    argv.append(str(script))
    return argv


# =============================================================================
# Codex CLI officiel (npm: @openai/codex)
# =============================================================================

def codex_install_prefix(root_dir: Path) -> Path:
    """Préfixe npm portable pour Codex."""
    return root_dir / ".usbide" / "codex"


def codex_bin_dir(prefix: Path) -> Path:
    """Répertoire .bin npm."""
    return prefix / "node_modules" / ".bin"


def node_tools_dir(root_dir: Path) -> Path:
    """Dossier Node portable attendu."""
    return root_dir / "tools" / "node"


def node_executable(root_dir: Path, env: Optional[Dict[str, str]] = None) -> Optional[Path]:
    """Résout node (portable puis fallback PATH)."""
    candidates: list[Path] = []
    node_dir = node_tools_dir(root_dir)

    if os.name == "nt":
        candidates.append(node_dir / "node.exe")
    else:
        candidates.extend([node_dir / "bin" / "node", node_dir / "node"])

    search_path = (env or os.environ).get("PATH")
    which = shutil.which("node", path=search_path)
    if which:
        candidates.append(Path(which))

    for c in candidates:
        if c.exists():
            return c.resolve()
    return None


def npm_cli_js(root_dir: Path, node: Optional[Path] = None) -> Optional[Path]:
    """Chemin npm-cli.js (exécuter npm via node)."""
    node = node or node_executable(root_dir)
    if node is None:
        return None

    node_dir = node.parent
    candidate = node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if candidate.exists():
        return candidate.resolve()

    # Fallback permissif (node système)
    for alt in (
        node_dir.parent / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js",
        node_dir / ".." / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js",
    ):
        try:
            alt = alt.resolve()
        except Exception:
            continue
        if alt.exists():
            return alt
    return None


def codex_env(root_dir: Path, base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Préfixe PATH avec .bin Codex + Node portable (même si pas encore installés)."""
    env = dict(base_env) if base_env is not None else os.environ.copy()
    path_value = env.get("PATH", "")
    path_parts = path_value.split(os.pathsep) if path_value else []

    node_dir = node_tools_dir(root_dir)
    if str(node_dir) not in path_parts:
        path_parts.insert(0, str(node_dir))

    bin_dir = codex_bin_dir(codex_install_prefix(root_dir))
    if str(bin_dir) not in path_parts:
        path_parts.insert(0, str(bin_dir))

    env["PATH"] = os.pathsep.join(path_parts)
    return env


def codex_package_json(prefix: Path) -> Path:
    return prefix / "node_modules" / "@openai" / "codex" / "package.json"


def codex_entrypoint_js(prefix: Path) -> Optional[Path]:
    """Résout l'entrypoint CLI via la clé 'bin' du package.json."""
    pkg_json = codex_package_json(prefix)
    if not pkg_json.exists():
        return None
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
    except Exception:
        return None

    bin_field = data.get("bin")
    rel: Optional[str] = None
    if isinstance(bin_field, str):
        rel = bin_field
    elif isinstance(bin_field, dict):
        if isinstance(bin_field.get("codex"), str):
            rel = bin_field["codex"]
        else:
            for v in bin_field.values():
                if isinstance(v, str):
                    rel = v
                    break

    if not rel:
        return None

    entry = pkg_json.parent / rel
    return entry.resolve() if entry.exists() else None


def codex_cli_available(root_dir: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> bool:
    """Codex OK si:
    - portable (node + entrypoint) disponible, OU
    - codex dispo dans PATH (fallback)
    """
    if root_dir is not None:
        node = node_executable(root_dir, env=env)
        entry = codex_entrypoint_js(codex_install_prefix(root_dir))
        if node is not None and entry is not None:
            return True

    search_env = env
    if root_dir is not None:
        search_env = codex_env(root_dir, env)
    path = search_env.get("PATH") if search_env else None
    return shutil.which("codex", path=path) is not None


def _codex_base_argv(root_dir: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> list[str]:
    """Préfère node + entrypoint JS, sinon fallback 'codex'."""
    if root_dir is not None:
        node = node_executable(root_dir, env=env)
        entry = codex_entrypoint_js(codex_install_prefix(root_dir))
        if node is not None and entry is not None:
            return [str(node), str(entry)]
    return ["codex"]


def codex_login_argv(
    root_dir: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    *,
    device_auth: bool = False,
) -> list[str]:
    argv = [*_codex_base_argv(root_dir, env), "login"]
    if device_auth:
        argv.append("--device-auth")
    return argv


def codex_status_argv(root_dir: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> list[str]:
    return [*_codex_base_argv(root_dir, env), "login", "status"]


def codex_exec_argv(
    prompt: str,
    *,
    root_dir: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    json_output: bool = False,
    extra_args: Optional[Sequence[str]] = None,
) -> list[str]:
    """codex exec non-interactive. JSONL via --json."""
    if not prompt.strip():
        raise ValueError("prompt ne doit pas être vide")

    argv = [*_codex_base_argv(root_dir, env), "exec"]
    if json_output:
        argv.append("--json")
    if extra_args:
        argv.extend([a for a in extra_args if a.strip()])
    argv.append(prompt)
    return argv


def codex_install_argv(root_dir: Path, prefix: Path, package: str = "@openai/codex") -> list[str]:
    """Installe Codex via npm dans prefix (sur la clé)."""
    if not package.strip():
        raise ValueError("package ne doit pas être vide")

    node = node_executable(root_dir)
    npm = npm_cli_js(root_dir, node=node)
    if node is None or npm is None:
        raise FileNotFoundError(
            "Node portable introuvable. Place une distribution Node dans tools/node/ "
            "(node.exe + node_modules/npm/...)."
        )

    prefix.mkdir(parents=True, exist_ok=True)
    return [
        str(node),
        str(npm),
        "install",
        "--prefix",
        str(prefix),
        "--no-audit",
        "--no-fund",
        package,
    ]

6.2 Remplacer usbide/app.py par ceci (split logs + panneau Codex)
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.markup import escape as rich_escape
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DirectoryTree, Footer, Header, Input, RichLog, TextArea

from usbide.encoding import detect_text_encoding, is_probably_binary
from usbide.runner import (
    codex_bin_dir,
    codex_cli_available,
    codex_env,
    codex_exec_argv,
    codex_install_argv,
    codex_install_prefix,
    codex_login_argv,
    codex_status_argv,
    parse_tool_list,
    pip_install_argv,
    pyinstaller_available,
    pyinstaller_build_argv,
    pyinstaller_install_argv,
    python_run_argv,
    python_scripts_dir,
    stream_subprocess,
    tool_available,
    tools_env,
    tools_install_prefix,
    windows_cmd_argv,
)


@dataclass
class OpenFile:
    path: Path
    encoding: str
    dirty: bool = False


class USBIDEApp(App):
    CSS_PATH = "usbide.tcss"

    BINDINGS = [
        ("ctrl+s", "save", "Sauvegarder"),
        ("f5", "run", "Exécuter"),
        ("ctrl+l", "clear_log", "Effacer les journaux"),
        ("ctrl+r", "reload_tree", "Recharger l'arborescence"),
        ("ctrl+k", "codex_login", "Connexion Codex"),
        ("ctrl+t", "codex_check", "Vérifier Codex"),
        ("ctrl+i", "codex_install", "Installer Codex"),
        ("ctrl+d", "dev_tools", "Outils de dev"),
        ("ctrl+e", "build_exe", "Construire l'EXE"),
        ("ctrl+q", "quit", "Quitter"),
    ]

    def __init__(self, root_dir: Path) -> None:
        super().__init__()
        self.root_dir = root_dir.resolve()
        self.current: Optional[OpenFile] = None
        self._loading_editor: bool = False
        self._codex_install_attempted: bool = False
        self._pyinstaller_install_attempted: bool = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            tree = DirectoryTree(str(self.root_dir), id="tree")
            tree.border_title = "Fichiers"
            yield tree

            with Vertical(id="right"):
                editor = self._make_editor()
                editor.border_title = "Éditeur"
                yield editor

                # Split logs: Shell (gauche) / Codex (droite)
                with Horizontal(id="bottom"):
                    with Vertical(id="shell"):
                        cmd = Input(placeholder="> commande shell (Entrée)", id="cmd")
                        cmd.border_title = "Commande"
                        yield cmd

                        log = RichLog(id="log", markup=True)
                        log.border_title = "Journal"
                        yield log

                    with Vertical(id="codex"):
                        codex_cmd = Input(
                            placeholder="> Codex (Entrée) : lance `codex exec --json <prompt>`",
                            id="codex_cmd",
                        )
                        codex_cmd.border_title = "Codex"
                        yield codex_cmd

                        codex_log = RichLog(id="codex_log", markup=True)
                        codex_log.border_title = "Sortie Codex"
                        yield codex_log

        yield Footer()

    def _make_editor(self) -> TextArea:
        if hasattr(TextArea, "code_editor"):
            return TextArea.code_editor("", language=None, id="editor")  # type: ignore[attr-defined]
        return TextArea("", id="editor")

    def on_mount(self) -> None:
        self._ensure_portable_dirs()
        self._log_ui(
            f"[b]ValDev Pro v1[/b]\nRoot: {self.root_dir}\n"
            "Shell: champ 'Commande' • Codex: champ 'Codex' • Ctrl+K login • Ctrl+I install\n"
        )
        self._refresh_title()

    # ---------- logs ----------
    def _log_ui(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    def _log_output(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(rich_escape(msg))

    def _codex_log_ui(self, msg: str) -> None:
        self.query_one("#codex_log", RichLog).write(msg)

    def _codex_log_output(self, msg: str) -> None:
        self.query_one("#codex_log", RichLog).write(rich_escape(msg))

    # ---------- env portable ----------
    def _ensure_portable_dirs(self) -> None:
        for path in (
            self.root_dir / "cache" / "pip",
            self.root_dir / "cache" / "pycache",
            self.root_dir / "cache" / "npm",
            self.root_dir / "tmp",
            self.root_dir / "codex_home",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _portable_env(self, env: dict[str, str]) -> dict[str, str]:
        env["PIP_CACHE_DIR"] = str(self.root_dir / "cache" / "pip")
        env["PYTHONPYCACHEPREFIX"] = str(self.root_dir / "cache" / "pycache")
        env["TEMP"] = str(self.root_dir / "tmp")
        env["TMP"] = str(self.root_dir / "tmp")
        env["PYTHONNOUSERSITE"] = "1"

        env["CODEX_HOME"] = str(self.root_dir / "codex_home")

        env["NPM_CONFIG_CACHE"] = str(self.root_dir / "cache" / "npm")
        env["NPM_CONFIG_UPDATE_NOTIFIER"] = "false"
        return env

    def _codex_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env = self._portable_env(env)
        return codex_env(self.root_dir, env)

    def _tools_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env = self._portable_env(env)
        return tools_env(self.root_dir, env)

    def _wheelhouse_path(self) -> Optional[Path]:
        wheelhouse = self.root_dir / "tools" / "wheels"
        return wheelhouse if wheelhouse.is_dir() else None

    # ---------- UI title ----------
    def _refresh_title(self) -> None:
        if not self.current:
            self.title = "ValDev Pro v1"
            self.sub_title = str(self.root_dir)
            return
        dirty = " *" if self.current.dirty else ""
        self.title = f"ValDev Pro v1{dirty}"
        self.sub_title = f"{self.current.path}  ({self.current.encoding})"

    # ---------- tree ----------
    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path: Path = event.path
        if path.is_dir():
            return

        if is_probably_binary(path):
            self._log_ui(f"[yellow]Binaire/non texte ignoré:[/yellow] {path}")
            return

        encoding = detect_text_encoding(path)
        text = path.read_text(encoding=encoding)

        editor = self.query_one(TextArea)
        self._loading_editor = True
        editor.text = text
        self._loading_editor = False

        self.current = OpenFile(path=path, encoding=encoding, dirty=False)
        self._refresh_title()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._loading_editor or not self.current:
            return
        ta = getattr(event, "text_area", None) or getattr(event, "control", None)
        if getattr(ta, "id", None) != "editor":
            return
        self.current.dirty = True
        self._refresh_title()

    # ---------- inputs ----------
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "cmd":
            await self._run_shell(event)
        elif event.input.id == "codex_cmd":
            await self._run_codex(event)

    async def _run_shell(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        event.input.value = ""
        if not cmd:
            return
        self._log_ui(f"\n[b]$[/b] {rich_escape(cmd)}")
        argv = windows_cmd_argv(cmd) if os.name == "nt" else ["sh", "-lc", cmd]
        env = self._portable_env(os.environ.copy())

        async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
            if ev["kind"] == "line":
                self._log_output(ev["text"])
            else:
                self._log_ui(f"[dim]{ev['text']}[/dim]")

    async def _run_codex(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        event.input.value = ""
        if not prompt:
            return

        env = self._codex_env()
        if not codex_cli_available(self.root_dir, env):
            ok = await self._install_codex(force=False)
            if not ok:
                self._codex_log_ui("[red]Codex indisponible.[/red] (Ctrl+I pour installer)")
                return

        argv = codex_exec_argv(prompt, root_dir=self.root_dir, env=env, json_output=True)
        self._codex_log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
            if ev["kind"] != "line":
                self._codex_log_ui(f"[dim]{ev['text']}[/dim]")
                continue

            line = ev["text"].strip()
            if not line:
                continue

            # Sortie JSONL => on essaye de parser pour enrichir un peu l'affichage,
            # sinon on affiche la ligne brute.
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and isinstance(obj.get("type"), str):
                    self._codex_log_output(f"[{obj.get('type')}] {line}")
                else:
                    self._codex_log_output(line)
            except Exception:
                self._codex_log_output(line)

    # ---------- actions ----------
    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()
        self.query_one("#codex_log", RichLog).clear()
        self._log_ui("[dim]journaux effacés[/dim]")

    def action_reload_tree(self) -> None:
        self.query_one(DirectoryTree).reload()
        self._log_ui("[dim]arborescence rechargée[/dim]")

    def action_save(self) -> bool:
        if not self.current:
            self._log_ui("[yellow]Aucun fichier ouvert.[/yellow]")
            return False

        editor = self.query_one(TextArea)
        self.current.path.write_text(editor.text, encoding=self.current.encoding)
        self.current.dirty = False
        self._log_ui(f"[green]Sauvegardé[/green] {self.current.path}")
        self._refresh_title()
        return True

    async def action_run(self) -> None:
        if not self.current or self.current.path.suffix.lower() != ".py":
            self._log_ui("[yellow]Ouvre un fichier .py.[/yellow]")
            return
        if self.current.dirty:
            self.action_save()

        argv = python_run_argv(self.current.path)
        env = self._portable_env(os.environ.copy())
        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
            if ev["kind"] == "line":
                self._log_output(ev["text"])
            else:
                self._log_ui(f"[dim]{ev['text']}[/dim]")

    def _codex_device_auth_enabled(self) -> bool:
        return os.environ.get("USBIDE_CODEX_DEVICE_AUTH", "0").strip().lower() in {"1", "true", "yes", "on"}

    def _codex_auto_install_enabled(self) -> bool:
        return os.environ.get("USBIDE_CODEX_AUTO_INSTALL", "1").strip().lower() not in {"0", "false", "no", "off"}

    async def _install_codex(self, *, force: bool = False) -> bool:
        env = self._codex_env()
        if not force and codex_cli_available(self.root_dir, env):
            return True
        if not force and self._codex_install_attempted:
            return False
        if not force and not self._codex_auto_install_enabled():
            self._log_ui("[yellow]Auto-install Codex désactivé.[/yellow]")
            return False

        self._codex_install_attempted = True
        package = os.environ.get("USBIDE_CODEX_NPM_PACKAGE", "@openai/codex")
        prefix = codex_install_prefix(self.root_dir)
        bin_dir = codex_bin_dir(prefix)
        prefix.mkdir(parents=True, exist_ok=True)

        self._log_ui(f"[b]Installation Codex[/b] package={rich_escape(package)} prefix={rich_escape(str(prefix))}")

        try:
            argv = codex_install_argv(self.root_dir, prefix, package)
        except Exception as e:
            self._log_ui(f"[red]Impossible d'installer Codex:[/red] {e}")
            return False

        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")
        async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
            if ev["kind"] == "line":
                self._log_output(ev["text"])
            else:
                self._log_ui(f"[dim]{ev['text']}[/dim]")

        ok = codex_cli_available(self.root_dir, env)
        if ok:
            self._log_ui(f"[green]Codex installé.[/green] (.bin: {rich_escape(str(bin_dir))})")
        return ok

    async def action_codex_install(self) -> None:
        await self._install_codex(force=True)

    async def action_codex_login(self) -> None:
        env = self._codex_env()
        if not codex_cli_available(self.root_dir, env):
            ok = await self._install_codex(force=False)
            if not ok:
                self._log_ui("[red]Codex introuvable.[/red]")
                return

        self._log_ui("[b]Login Codex[/b] : navigateur/Device auth selon config.")
        argv = codex_login_argv(self.root_dir, env, device_auth=self._codex_device_auth_enabled())
        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
            if ev["kind"] == "line":
                self._log_output(ev["text"])
            else:
                self._log_ui(f"[dim]{ev['text']}[/dim]")

    async def action_codex_check(self) -> None:
        env = self._codex_env()
        if not codex_cli_available(self.root_dir, env):
            self._log_ui("[yellow]Codex non installé.[/yellow]")
            return
        argv = codex_status_argv(self.root_dir, env)
        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
            if ev["kind"] == "line":
                self._log_output(ev["text"])
            else:
                self._log_ui(f"[dim]{ev['text']}[/dim]")

    async def action_dev_tools(self) -> None:
        raw = os.environ.get("USBIDE_DEV_TOOLS", "ruff black mypy pytest")
        tools = parse_tool_list(raw)
        if not tools:
            self._log_ui("[yellow]Liste outils vide.[/yellow]")
            return

        env = self._tools_env()
        prefix = tools_install_prefix(self.root_dir)
        prefix.mkdir(parents=True, exist_ok=True)

        wheelhouse = self._wheelhouse_path()
        argv = pip_install_argv(prefix, tools, find_links=wheelhouse, no_index=wheelhouse is not None)
        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
            if ev["kind"] == "line":
                self._log_output(ev["text"])
            else:
                self._log_ui(f"[dim]{ev['text']}[/dim]")

    async def _install_pyinstaller(self, *, force: bool = False) -> bool:
        env = self._tools_env()
        if not force and pyinstaller_available(self.root_dir, env):
            return True
        if not force and self._pyinstaller_install_attempted:
            return False

        self._pyinstaller_install_attempted = True
        prefix = tools_install_prefix(self.root_dir)
        bin_dir = python_scripts_dir(prefix)
        prefix.mkdir(parents=True, exist_ok=True)

        wheelhouse = self._wheelhouse_path()
        argv = pyinstaller_install_argv(prefix, find_links=wheelhouse, no_index=wheelhouse is not None)
        self._log_ui(f"[b]Installation PyInstaller[/b] bin={rich_escape(str(bin_dir))}")
        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
            if ev["kind"] == "line":
                self._log_output(ev["text"])
            else:
                self._log_ui(f"[dim]{ev['text']}[/dim]")

        return pyinstaller_available(self.root_dir, env)

    async def action_build_exe(self) -> None:
        if not self.current or self.current.path.suffix.lower() != ".py":
            self._log_ui("[yellow]Ouvre un fichier .py.[/yellow]")
            return
        if self.current.dirty:
            self.action_save()

        env = self._tools_env()
        if not pyinstaller_available(self.root_dir, env):
            ok = await self._install_pyinstaller(force=False)
            if not ok:
                self._log_ui("[red]PyInstaller indisponible.[/red]")
                return

        dist_dir = self.root_dir / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        argv = pyinstaller_build_argv(self.current.path, dist_dir, onefile=False, work_dir=self.root_dir / "tmp")
        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
            if ev["kind"] == "line":
                self._log_output(ev["text"])
            else:
                self._log_ui(f"[dim]{ev['text']}[/dim]")

6.3 Mettre à jour usbide/usbide.tcss (nouveaux IDs)
Screen {
  background: $surface-darken-1;
  color: $text;
}

#main {
  height: 1fr;
  background: $surface;
  color: $text;
  padding: 1 1;
}

#tree {
  width: 34;
  border: heavy $primary;
  background: $panel;
  color: $text;
  padding: 1;
  margin: 0 1 0 0;
}

#right {
  width: 1fr;
  background: $surface;
}

#editor {
  height: 1fr;
  border: heavy $secondary;
  background: $surface;
  color: $text;
  padding: 1;
  margin: 0 0 1 0;
}

#bottom {
  height: 14;
}

#shell {
  width: 1fr;
  margin: 0 1 0 0;
}

#codex {
  width: 1fr;
}

#cmd {
  height: 3;
  border: heavy $accent;
  background: $panel;
  color: $text;
  padding: 0 1;
  margin: 0 0 1 0;
}

#codex_cmd {
  height: 3;
  border: heavy $primary;
  background: $panel;
  color: $text;
  padding: 0 1;
  margin: 0 0 1 0;
}

#log {
  height: 1fr;
  border: heavy $success;
  background: $panel;
  color: $text;
  padding: 1;
}

#codex_log {
  height: 1fr;
  border: heavy $secondary;
  background: $panel;
  color: $text;
  padding: 1;
}

Header {
  background: $primary-darken-1;
  color: $text;
  dock: top;
  padding: 0 1;
}

Footer {
  background: $primary-darken-2;
  color: $text;
  dock: bottom;
  padding: 0 1;
}

7) “Codex installé par défaut” (sans npm sur le PC)

Le meilleur workflow : tu pré-installes Codex sur ta clé sur ta machine à toi, puis tu livres la clé avec .usbide/codex/node_modules/... déjà rempli.

Script bootstrap (à créer : bootstrap_codex.bat à la racine de la clé)

Tu le lances 1 fois (sur ta machine dev), et après Codex est “natif” sur la clé.

@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "NODE=%ROOT%\tools\node\node.exe"
set "NPMCLI=%ROOT%\tools\node\node_modules\npm\bin\npm-cli.js"
set "PREFIX=%ROOT%\.usbide\codex"

if not exist "%NODE%" (
  echo [ERREUR] node.exe introuvable: "%NODE%"
  exit /b 1
)

if not exist "%NPMCLI%" (
  echo [ERREUR] npm-cli.js introuvable: "%NPMCLI%"
  exit /b 1
)

if not exist "%ROOT%\cache\npm" mkdir "%ROOT%\cache\npm"
if not exist "%PREFIX%" mkdir "%PREFIX%"

set "NPM_CONFIG_CACHE=%ROOT%\cache\npm"
set "NPM_CONFIG_UPDATE_NOTIFIER=false"

echo [INFO] Installation Codex dans "%PREFIX%"...
"%NODE%" "%NPMCLI%" install --prefix "%PREFIX%" --no-audit --no-fund @openai/codex@latest

echo [OK] Terminé.
endlocal


Ensuite, quand tu vas chez un client, aucune installation : l’app trouve Node dans tools/node et Codex déjà installé dans .usbide/codex.

8) Connexion (dans ton app)

Ctrl+K → lance codex login

si tu veux device auth : avant de lancer l’app, set :

USBIDE_CODEX_DEVICE_AUTH=1
et ça fera codex login --device-auth

Et grâce à CODEX_HOME=...\codex_home, la session reste sur ta clé.

9) Option “vraiment comme le terminal” (TUI Codex intégré) — plus compliqué

Si tu veux exactement l’UI interactive de Codex CLI (celle qui ressemble à un terminal), il faut une pseudo-console (PTY), surtout sur Windows (ConPTY).
C’est faisable, mais c’est un autre chantier (gestion des touches, redimensionnement, séquences ANSI, etc.). La stratégie codex exec --json est celle qui s’intègre proprement à une UI sans te battre contre le TTY.

10) Deux détails “pro” à ne pas zapper

Sécurité / confidentialité
Codex va potentiellement lire/envoyer du code (selon tes prompts et config). Ça se gère contractuellement avec tes clients. (À minima : prévenir, isoler les repos, éviter les secrets en clair.)

Mode dangereux
Le CLI a des options du style --yolo / bypass approvals (dans la doc CLI options). Ne les active pas “par défaut” dans un outil client, sauf si tu sais exactement pourquoi.

En résumé (ce que tu dois faire)

Embarquer Node portable dans tools/node/

Pré-installer @openai/codex dans .usbide/codex (script bootstrap)

Forcer CODEX_HOME vers USB_ROOT/codex_home

Dans ton app : lancer codex exec --json et streamer stdout vers un panneau “Codex” (code ci-dessus)

Ajouter un bouton/raccourci “login” qui lance codex login (ou --device-auth)