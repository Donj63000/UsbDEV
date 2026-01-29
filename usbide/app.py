from __future__ import annotations

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
    codex_install_argv,
    codex_install_prefix,
    codex_login_argv,
    codex_status_argv,
    parse_tool_list,
    pyinstaller_available,
    pyinstaller_build_argv,
    pyinstaller_install_argv,
    pip_install_argv,
    python_run_argv,
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
    """Mini IDE terminal portable (Textual).

    Objectif: fonctionner *portable* sur une clé USB.
    """

    CSS_PATH = "usbide.tcss"
    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("f5", "run", "Run"),
        ("ctrl+l", "clear_log", "Clear log"),
        ("ctrl+r", "reload_tree", "Reload tree"),
        ("ctrl+k", "codex_login", "Codex login"),
        ("ctrl+t", "codex_check", "Codex check"),
        ("ctrl+i", "codex_install", "Codex install"),
        ("ctrl+e", "build_exe", "Build EXE"),
        ("ctrl+d", "dev_tools", "Dev tools"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, root_dir: Path) -> None:
        super().__init__()
        self.root_dir = root_dir.resolve()
        self.current: Optional[OpenFile] = None
        self._loading_editor: bool = False  # évite de marquer dirty quand on charge un fichier
        self._codex_install_attempted: bool = False  # évite de répéter l'installation automatique
        self._pyinstaller_install_attempted: bool = False  # évite de répéter l'installation automatique

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            yield DirectoryTree(str(self.root_dir), id="tree")
            with Vertical(id="right"):
                yield self._make_editor()
                yield Input(placeholder="> commande shell (Entrée pour exécuter)", id="cmd")
                # markup=True pour nos messages; on escape la sortie externe
                yield RichLog(id="log", markup=True)
        yield Footer()

    def _make_editor(self) -> TextArea:
        """Crée l'éditeur avec fallback si `TextArea.code_editor` n'existe pas."""
        if hasattr(TextArea, "code_editor"):
            # Textual récent
            return TextArea.code_editor("", language=None, id="editor")  # type: ignore[attr-defined]

        # Fallback: TextArea standard
        editor = TextArea("", id="editor")
        # Quelques options si disponibles
        for attr, value in (
            ("show_line_numbers", True),
            ("tab_behavior", "indent"),
            ("soft_wrap", False),
        ):
            if hasattr(editor, attr):
                try:
                    setattr(editor, attr, value)
                except Exception:
                    pass
        return editor

    def on_mount(self) -> None:
        self._log_ui(
            f"[b]USBIDE[/b]\nRoot: {self.root_dir}\n"
            "Ctrl+S save • F5 run • Ctrl+R reload tree • Ctrl+L clear log • "
            "Ctrl+I install Codex • Ctrl+D dev tools • Ctrl+E build EXE • Ctrl+Q quit\n"
            "Astuce: utilise le champ `>` pour lancer des commandes shell (dir, git, etc.)."
        )
        self._refresh_title()

    # -------- logging helpers --------
    def _log_ui(self, msg: str) -> None:
        """Log interne: on autorise le markup Rich."""
        self.query_one(RichLog).write(msg)

    def _log_output(self, msg: str) -> None:
        """Log externe (sortie programme / shell): on escape pour éviter le markup accidentel."""
        self.query_one(RichLog).write(rich_escape(msg))

    # -------- UI helpers --------
    def _refresh_title(self) -> None:
        if not self.current:
            self.title = "USBIDE"
            self.sub_title = str(self.root_dir)
            return
        dirty = " *" if self.current.dirty else ""
        self.title = f"USBIDE{dirty}"
        self.sub_title = f"{self.current.path}  ({self.current.encoding})"

    def _codex_env(self) -> dict[str, str]:
        """Construit l'environnement (PATH + encodage) pour les commandes Codex."""
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return codex_env(self.root_dir, env)

    def _tools_env(self) -> dict[str, str]:
        """Construit l'environnement (PATH + encodage) pour les outils portables."""
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return tools_env(self.root_dir, env)

    def _codex_auto_install_enabled(self) -> bool:
        """Indique si l'installation automatique de Codex est autorisée."""
        value = os.environ.get("USBIDE_CODEX_AUTO_INSTALL", "1").strip().lower()
        return value not in {"0", "false", "no", "off"}

    def _dev_tools_list(self) -> list[str]:
        """Retourne la liste des outils dev à embarquer localement."""
        raw = os.environ.get("USBIDE_DEV_TOOLS", "ruff black mypy pytest")
        tools = parse_tool_list(raw)
        if not tools:
            # On avertit si la liste est vide pour éviter une installation silencieuse.
            self._log_ui(
                "[yellow]Liste d'outils dev vide.[/yellow] "
                "Définissez USBIDE_DEV_TOOLS pour configurer les outils."
            )
        return tools

    async def _install_dev_tools(self, *, force: bool = False) -> bool:
        """Installe les outils dev dans le préfixe portable si besoin."""
        tools = self._dev_tools_list()
        if not tools:
            return False

        env = self._tools_env()
        missing = [tool for tool in tools if not tool_available(tool, self.root_dir, env)]
        if not missing and not force:
            self._log_ui("[green]Outils dev déjà disponibles.[/green]")
            return True

        prefix = tools_install_prefix(self.root_dir)
        prefix.mkdir(parents=True, exist_ok=True)
        packages = tools if force else missing

        self._log_ui(
            "[b]Installation outils dev[/b] : "
            f"packages={rich_escape(' '.join(packages))} • "
            f"prefix={rich_escape(str(prefix))}"
        )

        try:
            argv = pip_install_argv(prefix, packages)
        except ValueError as e:
            self._log_ui(f"[red]Liste d'outils invalide:[/red] {e}")
            return False

        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        try:
            async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
                if ev["kind"] == "line":
                    self._log_output(ev["text"])
                else:
                    self._log_ui(f"[dim]{ev['text']}[/dim]")
        except Exception as e:
            self._log_ui(f"[red]Erreur installation outils dev:[/red] {e}")
            return False

        still_missing = [tool for tool in tools if not tool_available(tool, self.root_dir, env)]
        if still_missing:
            self._log_ui(
                "[yellow]Outils manquants après installation:[/yellow] "
                f"{rich_escape(' '.join(still_missing))}"
            )
            return False

        self._log_ui("[green]Outils dev installés.[/green]")
        return True

    async def _install_codex(self, *, force: bool = False) -> bool:
        """Installe Codex dans le préfixe portable si nécessaire."""
        env = self._codex_env()
        if not force and codex_cli_available(self.root_dir, env):
            return True
        if not force and self._codex_install_attempted:
            return False
        if not force and not self._codex_auto_install_enabled():
            self._log_ui(
                "[yellow]Installation automatique Codex désactivée.[/yellow] "
                "Définissez USBIDE_CODEX_AUTO_INSTALL=1 pour l'activer."
            )
            return False

        self._codex_install_attempted = True
        package = os.environ.get("USBIDE_CODEX_PIP_PACKAGE", "codex")
        prefix = codex_install_prefix(self.root_dir)
        bin_dir = codex_bin_dir(prefix)
        prefix.mkdir(parents=True, exist_ok=True)

        self._log_ui(
            "[b]Installation Codex[/b] : "
            f"package={rich_escape(package)} • prefix={rich_escape(str(prefix))}"
        )

        try:
            argv = codex_install_argv(prefix, package)
        except ValueError as e:
            self._log_ui(f"[red]Package Codex invalide:[/red] {e}")
            return False

        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        try:
            async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
                if ev["kind"] == "line":
                    self._log_output(ev["text"])
                else:
                    self._log_ui(f"[dim]{ev['text']}[/dim]")
        except Exception as e:
            self._log_ui(f"[red]Erreur installation Codex:[/red] {e}")
            return False

        if codex_cli_available(self.root_dir, env):
            self._log_ui(
                "[green]Codex installé.[/green] "
                f"Binaire attendu dans {rich_escape(str(bin_dir))}."
            )
            return True

        self._log_ui(
            "[yellow]Installation Codex terminée mais binaire non détecté.[/yellow] "
            "Vérifiez la connexion réseau ou le package configuré."
        )
        return False

    async def _install_pyinstaller(self, *, force: bool = False) -> bool:
        """Installe PyInstaller dans le préfixe portable si nécessaire."""
        env = self._tools_env()
        if not force and pyinstaller_available(self.root_dir, env):
            return True
        if not force and self._pyinstaller_install_attempted:
            return False

        self._pyinstaller_install_attempted = True
        prefix = tools_install_prefix(self.root_dir)
        bin_dir = codex_bin_dir(prefix)
        prefix.mkdir(parents=True, exist_ok=True)

        self._log_ui(
            "[b]Installation PyInstaller[/b] : "
            f"prefix={rich_escape(str(prefix))}"
        )

        argv = pyinstaller_install_argv(prefix)
        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        try:
            async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
                if ev["kind"] == "line":
                    self._log_output(ev["text"])
                else:
                    self._log_ui(f"[dim]{ev['text']}[/dim]")
        except Exception as e:
            self._log_ui(f"[red]Erreur installation PyInstaller:[/red] {e}")
            return False

        if pyinstaller_available(self.root_dir, env):
            self._log_ui(
                "[green]PyInstaller installé.[/green] "
                f"Binaire attendu dans {rich_escape(str(bin_dir))}."
            )
            return True

        self._log_ui(
            "[yellow]Installation PyInstaller terminée mais binaire non détecté.[/yellow] "
            "Vérifiez la connexion réseau ou le cache pip."
        )
        return False

    # -------- DirectoryTree events --------
    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path: Path = event.path

        if path.is_dir():
            return

        if is_probably_binary(path):
            self._log_ui(f"[yellow]Fichier binaire / non texte ignoré:[/yellow] {path}")
            return

        encoding = detect_text_encoding(path)
        try:
            text = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            text = path.read_text(encoding=encoding, errors="replace")
        except OSError as e:
            self._log_ui(f"[red]Erreur ouverture:[/red] {path} ({e})")
            return

        self.current = OpenFile(path=path, encoding=encoding, dirty=False)

        editor = self.query_one(TextArea)
        self._loading_editor = True
        try:
            editor.text = text
            # highlighting python si possible
            if hasattr(editor, "language"):
                editor.language = "python" if path.suffix.lower() == ".py" else None  # type: ignore[attr-defined]
        finally:
            self._loading_editor = False

        self._log_ui(f"[green]Ouvert[/green] {path}")
        self._refresh_title()

    def on_text_area_changed(self, event: object) -> None:
        """Marque dirty dès qu'on édite (robuste aux variations d'API)."""
        if self._loading_editor or not self.current:
            return

        # Selon la version, l'event expose `text_area` ou `control`
        ta = getattr(event, "text_area", None) or getattr(event, "control", None)
        if ta is None:
            return
        if getattr(ta, "id", None) != "editor":
            return

        self.current.dirty = True
        self._refresh_title()

    # -------- Input command --------
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "cmd":
            return
        cmd = event.value.strip()
        event.input.value = ""
        if not cmd:
            return

        self._log_ui(f"\n[b]$[/b] {rich_escape(cmd)}")

        argv = windows_cmd_argv(cmd) if os.name == "nt" else ["sh", "-lc", cmd]
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")

        try:
            async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
                if ev["kind"] == "line":
                    self._log_output(ev["text"])
                else:
                    self._log_ui(f"[dim]{ev['text']}[/dim]")
        except FileNotFoundError as e:
            self._log_ui(f"[red]Shell introuvable:[/red] {e}")
        except Exception as e:
            self._log_ui(f"[red]Erreur exécution commande:[/red] {e}")

    # -------- Actions --------
    def action_clear_log(self) -> None:
        self.query_one(RichLog).clear()
        self._log_ui("[dim]log cleared[/dim]")

    def action_reload_tree(self) -> None:
        self.query_one(DirectoryTree).reload()
        self._log_ui("[dim]tree reloaded[/dim]")

    def action_save(self) -> None:
        if not self.current:
            self._log_ui("[yellow]Aucun fichier ouvert.[/yellow]")
            return

        editor = self.query_one(TextArea)
        content = editor.text
        path = self.current.path
        encoding = self.current.encoding

        try:
            path.write_text(content, encoding=encoding)
            self.current.dirty = False
            self._log_ui(f"[green]Sauvegardé[/green] {path}")
        except UnicodeEncodeError:
            # fallback en utf-8
            path.write_text(content, encoding="utf-8")
            self.current.encoding = "utf-8"
            self.current.dirty = False
            self._log_ui(f"[yellow]Sauvegardé en UTF-8 (fallback)[/yellow] {path}")
        except OSError as e:
            self._log_ui(f"[red]Erreur sauvegarde:[/red] {path} ({e})")
        finally:
            self._refresh_title()

    async def action_run(self) -> None:
        if not self.current:
            self._log_ui("[yellow]Aucun fichier à exécuter.[/yellow]")
            return

        if self.current.path.suffix.lower() != ".py":
            self._log_ui("[yellow]Exécution supportée uniquement pour les fichiers .py[/yellow]")
            return

        # Sauver avant run
        if self.current.dirty:
            self.action_save()

        script = self.current.path
        argv = python_run_argv(script)

        # Affiche la commande (escape pour éviter markup cassé si chemin contient [])
        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")

        try:
            async for ev in stream_subprocess(argv, cwd=script.parent, env=env):
                if ev["kind"] == "line":
                    self._log_output(ev["text"])
                else:
                    self._log_ui(f"[dim]{ev['text']}[/dim]")
        except Exception as e:
            self._log_ui(f"[red]Erreur exécution:[/red] {e}")

    async def action_codex_login(self) -> None:
        """Lance l'authentification Codex via le CLI."""
        if not codex_cli_available(self.root_dir, self._codex_env()):
            installed = await self._install_codex(force=False)
            if not installed:
                self._log_ui(
                    "[red]CLI Codex introuvable.[/red] Installez-le puis relancez la commande."
                )
                return

        # Message utilisateur pour préciser le flux d'authentification.
        self._log_ui(
            "[b]Authentification Codex[/b] : une page ChatGPT peut s'ouvrir "
            "dans votre navigateur. Suivez les instructions affichées."
        )

        argv = codex_login_argv()
        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        env = self._codex_env()

        try:
            async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
                if ev["kind"] == "line":
                    self._log_output(ev["text"])
                else:
                    self._log_ui(f"[dim]{ev['text']}[/dim]")
        except FileNotFoundError as e:
            self._log_ui(f"[red]CLI Codex introuvable:[/red] {e}")
        except Exception as e:
            self._log_ui(f"[red]Erreur exécution Codex:[/red] {e}")

    async def action_codex_check(self) -> None:
        """Vérifie que Codex est utilisable (CLI présent + statut auth)."""
        if not codex_cli_available(self.root_dir, self._codex_env()):
            installed = await self._install_codex(force=False)
            if not installed:
                self._log_ui(
                    "[red]CLI Codex introuvable.[/red] Installez-le puis relancez la commande."
                )
                return

        self._log_ui("[b]Vérification Codex[/b] : contrôle du statut d'authentification.")

        argv = codex_status_argv()
        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        env = self._codex_env()

        exit_code: Optional[int] = None
        try:
            async for ev in stream_subprocess(argv, cwd=self.root_dir, env=env):
                if ev["kind"] == "line":
                    self._log_output(ev["text"])
                else:
                    exit_code = ev["returncode"]
                    # Message explicite pour aider l'utilisateur.
                    if exit_code == 0:
                        self._log_ui("[green]Codex prêt à l'emploi.[/green]")
                    else:
                        self._log_ui(
                            "[yellow]Codex semble non authentifié ou en erreur.[/yellow] "
                            "Relancez Ctrl+K pour vous connecter."
                        )
        except FileNotFoundError as e:
            self._log_ui(f"[red]CLI Codex introuvable:[/red] {e}")
        except Exception as e:
            self._log_ui(f"[red]Erreur vérification Codex:[/red] {e}")

    async def action_codex_install(self) -> None:
        """Installe ou met à jour Codex dans l'environnement portable."""
        await self._install_codex(force=True)

    async def action_dev_tools(self) -> None:
        """Installe les outils de dev localement si besoin."""
        await self._install_dev_tools(force=False)

    async def action_build_exe(self) -> None:
        """Construit un exécutable via PyInstaller pour le script courant."""
        if not self.current:
            self._log_ui("[yellow]Aucun fichier ouvert.[/yellow]")
            return

        if self.current.path.suffix.lower() != ".py":
            self._log_ui("[yellow]La génération d'exe nécessite un fichier .py[/yellow]")
            return

        # Sauver avant build.
        if self.current.dirty:
            self.action_save()

        if not pyinstaller_available(self.root_dir, self._tools_env()):
            installed = await self._install_pyinstaller(force=False)
            if not installed:
                self._log_ui(
                    "[red]PyInstaller introuvable.[/red] "
                    "Installez-le puis relancez la commande."
                )
                return

        script = self.current.path
        dist_dir = self.root_dir / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)

        try:
            argv = pyinstaller_build_argv(script, dist_dir, onefile=True)
        except ValueError as e:
            self._log_ui(f"[red]Script invalide:[/red] {e}")
            return

        self._log_ui(f"\n[b]$[/b] {rich_escape(' '.join(argv))}")

        env = self._tools_env()
        try:
            async for ev in stream_subprocess(argv, cwd=script.parent, env=env):
                if ev["kind"] == "line":
                    self._log_output(ev["text"])
                else:
                    self._log_ui(f"[dim]{ev['text']}[/dim]")
        except FileNotFoundError as e:
            self._log_ui(f"[red]PyInstaller introuvable:[/red] {e}")
        except Exception as e:
            self._log_ui(f"[red]Erreur build EXE:[/red] {e}")
