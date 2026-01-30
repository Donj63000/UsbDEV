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

    # Ordre volontaire pour regrouper les actions d'execution avant les outils dev.
    BINDINGS = [
        ("ctrl+s", "save", "Sauvegarder"),
        ("f5", "run", "Executer"),
        ("ctrl+l", "clear_log", "Effacer les journaux"),
        ("ctrl+r", "reload_tree", "Recharger l'arborescence"),
        ("ctrl+k", "codex_login", "Connexion Codex"),
        ("ctrl+t", "codex_check", "Verifier Codex"),
        ("ctrl+i", "codex_install", "Installer Codex"),
        ("ctrl+e", "build_exe", "Construire l'EXE"),
        ("ctrl+d", "dev_tools", "Outils de dev"),
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
                editor.border_title = "Editeur"
                yield editor

                # Double journal: shell (gauche) / Codex (droite).
                with Horizontal(id="bottom"):
                    with Vertical(id="shell"):
                        cmd = Input(placeholder="> commande shell (Entree)", id="cmd")
                        cmd.border_title = "Commande"
                        yield cmd

                        log = RichLog(id="log", markup=True)
                        log.border_title = "Journal"
                        yield log

                    with Vertical(id="codex"):
                        codex_cmd = Input(
                            placeholder="> Codex (Entree) : lance `codex exec --json <prompt>`",
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
            "Shell: champ 'Commande' - Codex: champ 'Codex' - Ctrl+K login - Ctrl+I install\n"
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

        try:
            if is_probably_binary(path):
                self._log_ui(f"[yellow]Binaire/non texte ignore:[/yellow] {path}")
                return
        except OSError as exc:
            self._log_ui(f"[red]Acces fichier impossible:[/red] {path} ({exc})")
            return

        encoding = detect_text_encoding(path)
        try:
            text = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            text = path.read_text(encoding=encoding, errors="replace")
        except OSError as exc:
            self._log_ui(f"[red]Erreur ouverture:[/red] {path} ({exc})")
            return

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

        # Robustesse: on capture les erreurs de lancement pour eviter un crash UI.
        try:
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
        except FileNotFoundError as exc:
            # Cas typique: codex ou node introuvable dans le PATH.
            self._codex_log_ui(f"[red]Codex introuvable.[/red] {exc}")
        except Exception as exc:
            # Capture generique pour ne pas fermer l'application.
            self._codex_log_ui(f"[red]Erreur execution Codex:[/red] {exc}")

    # ---------- actions ----------
    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()
        self.query_one("#codex_log", RichLog).clear()
        self._log_ui("[dim]journaux effaces[/dim]")

    def action_reload_tree(self) -> None:
        self.query_one(DirectoryTree).reload()
        self._log_ui("[dim]arborescence rechargee[/dim]")

    def action_save(self) -> bool:
        if not self.current:
            self._log_ui("[yellow]Aucun fichier ouvert.[/yellow]")
            return False

        editor = self.query_one(TextArea)
        content = editor.text
        path = self.current.path
        encoding = self.current.encoding

        try:
            path.write_text(content, encoding=encoding)
            self.current.dirty = False
            self._log_ui(f"[green]Sauvegarde[/green] {path}")
            return True
        except UnicodeEncodeError:
            try:
                path.write_text(content, encoding="utf-8")
            except OSError as exc:
                self._log_ui(f"[red]Erreur sauvegarde (UTF-8):[/red] {path} ({exc})")
                return False
            self.current.encoding = "utf-8"
            self.current.dirty = False
            self._log_ui(f"[yellow]Sauvegarde en UTF-8 (fallback)[/yellow] {path}")
            return True
        except OSError as exc:
            self._log_ui(f"[red]Erreur sauvegarde:[/red] {path} ({exc})")
            return False
        finally:
            self._refresh_title()

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
            self._log_ui("[yellow]Auto-install Codex desactive.[/yellow]")
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
            self._log_ui(f"[green]Codex installe.[/green] (.bin: {rich_escape(str(bin_dir))})")
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
            self._log_ui("[yellow]Codex non installe.[/yellow]")
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

