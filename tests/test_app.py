import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from usbide.app import OpenFile, USBIDEApp


class TestUSBIDEAppTitle(unittest.TestCase):
    def test_refresh_title_sans_fichier(self) -> None:
        # Le titre doit afficher le nom officiel et le chemin racine.
        # Utilise un dossier temporaire pour rester compatible Windows/Linux.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            app = USBIDEApp(root_dir=root_dir)
            app.current = None

            app._refresh_title()

            self.assertEqual(app.title, "ValDev Pro v1")
            self.assertEqual(app.sub_title, str(root_dir))

    def test_refresh_title_avec_fichier_dirty(self) -> None:
        # Le titre doit garder le branding et signaler les modifications.
        # Utilise un dossier temporaire pour rester compatible Windows/Linux.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            app = USBIDEApp(root_dir=root_dir)
            app.current = OpenFile(path=root_dir / "main.py", encoding="utf-8", dirty=True)

            app._refresh_title()

            self.assertEqual(app.title, "ValDev Pro v1 *")
            self.assertIn("main.py", app.sub_title)
            self.assertIn("utf-8", app.sub_title)


class TestUSBIDEAppSave(unittest.TestCase):
    def test_action_save_ok(self) -> None:
        # Une sauvegarde reussie doit retourner True et ecrire le contenu.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            path = root_dir / "note.txt"
            app = USBIDEApp(root_dir=root_dir)
            app.current = OpenFile(path=path, encoding="utf-8", dirty=True)
            fake_editor = MagicMock()
            fake_editor.text = "Bonjour"

            with patch.object(app, "query_one", return_value=fake_editor):
                self.assertTrue(app.action_save())

            self.assertEqual(path.read_text(encoding="utf-8"), "Bonjour")

    def test_action_save_fallback_utf8(self) -> None:
        # Un encodage incompatible doit declencher un fallback UTF-8.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            path = root_dir / "accent.txt"
            app = USBIDEApp(root_dir=root_dir)
            app.current = OpenFile(path=path, encoding="ascii", dirty=True)
            fake_editor = MagicMock()
            accent = "\u00e9"
            fake_editor.text = accent

            with patch.object(app, "query_one", return_value=fake_editor):
                self.assertTrue(app.action_save())

            self.assertEqual(path.read_text(encoding="utf-8"), accent)

    def test_action_save_oserror(self) -> None:
        # Une erreur d'ecriture doit retourner False.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            path = root_dir / "note.txt"
            app = USBIDEApp(root_dir=root_dir)
            app.current = OpenFile(path=path, encoding="utf-8", dirty=True)
            fake_editor = MagicMock()
            fake_editor.text = "Bonjour"

            with patch.object(app, "query_one", return_value=fake_editor):
                with patch.object(Path, "write_text", side_effect=OSError("boom")):
                    self.assertFalse(app.action_save())


class TestUSBIDEAppPortableEnv(unittest.TestCase):
    def test_portable_env_defauts(self) -> None:
        # Les variables doivent pointer vers des dossiers sur la cle.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            app = USBIDEApp(root_dir=root_dir)
            env = app._portable_env({"PATH": "X"})
            self.assertEqual(env["PIP_CACHE_DIR"], str(root_dir / "cache" / "pip"))
            self.assertEqual(env["PYTHONPYCACHEPREFIX"], str(root_dir / "cache" / "pycache"))
            self.assertEqual(env["TEMP"], str(root_dir / "tmp"))
            self.assertEqual(env["TMP"], str(root_dir / "tmp"))
            self.assertEqual(env["PYTHONNOUSERSITE"], "1")
            self.assertEqual(env["CODEX_HOME"], str(root_dir / "codex_home"))
            self.assertEqual(env["NPM_CONFIG_CACHE"], str(root_dir / "cache" / "npm"))
            self.assertEqual(env["NPM_CONFIG_UPDATE_NOTIFIER"], "false")

    def test_portable_env_ne_ecrase_pas(self) -> None:
        # Les variables doivent etre forcees sur la cle meme si deja definies.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            app = USBIDEApp(root_dir=root_dir)
            env = {
                "PIP_CACHE_DIR": "X",
                "PYTHONPYCACHEPREFIX": "Y",
                "TEMP": "Z",
                "TMP": "W",
                "PYTHONNOUSERSITE": "0",
                "CODEX_HOME": "C",
                "NPM_CONFIG_CACHE": "N",
                "NPM_CONFIG_UPDATE_NOTIFIER": "true",
            }
            result = app._portable_env(env)
            self.assertEqual(result["PIP_CACHE_DIR"], str(root_dir / "cache" / "pip"))
            self.assertEqual(result["PYTHONPYCACHEPREFIX"], str(root_dir / "cache" / "pycache"))
            self.assertEqual(result["TEMP"], str(root_dir / "tmp"))
            self.assertEqual(result["TMP"], str(root_dir / "tmp"))
            self.assertEqual(result["PYTHONNOUSERSITE"], "1")
            self.assertEqual(result["CODEX_HOME"], str(root_dir / "codex_home"))
            self.assertEqual(result["NPM_CONFIG_CACHE"], str(root_dir / "cache" / "npm"))
            self.assertEqual(result["NPM_CONFIG_UPDATE_NOTIFIER"], "false")

    def test_wheelhouse_path(self) -> None:
        # Le wheelhouse doit etre detecte quand le dossier existe.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            wheelhouse = root_dir / "tools" / "wheels"
            wheelhouse.mkdir(parents=True, exist_ok=True)
            app = USBIDEApp(root_dir=root_dir)
            self.assertEqual(app._wheelhouse_path(), wheelhouse)


class TestUSBIDEAppCodexFlags(unittest.TestCase):
    def test_codex_device_auth_enabled(self) -> None:
        # La variable d'environnement doit activer le device auth.
        app = USBIDEApp(root_dir=Path.cwd())
        with patch.dict(os.environ, {"USBIDE_CODEX_DEVICE_AUTH": "1"}, clear=True):
            self.assertTrue(app._codex_device_auth_enabled())
        with patch.dict(os.environ, {"USBIDE_CODEX_DEVICE_AUTH": "0"}, clear=True):
            self.assertFalse(app._codex_device_auth_enabled())

    def test_codex_auto_install_enabled(self) -> None:
        # La variable d'environnement doit activer ou desactiver l'auto-install.
        app = USBIDEApp(root_dir=Path.cwd())
        with patch.dict(os.environ, {"USBIDE_CODEX_AUTO_INSTALL": "0"}, clear=True):
            self.assertFalse(app._codex_auto_install_enabled())
        with patch.dict(os.environ, {"USBIDE_CODEX_AUTO_INSTALL": "1"}, clear=True):
            self.assertTrue(app._codex_auto_install_enabled())


class TestUSBIDEAppCodexRun(unittest.IsolatedAsyncioTestCase):
    async def test_run_codex_capture_erreur_lancement(self) -> None:
        # Verifie qu'une erreur de lancement Codex ne fait pas crasher l'UI.
        app = USBIDEApp(root_dir=Path.cwd())

        class DummyInput:
            def __init__(self) -> None:
                self.value = ""

        class DummyEvent:
            def __init__(self, value: str) -> None:
                self.value = value
                self.input = DummyInput()

        async def fake_stream(*_args, **_kwargs):
            # On force une erreur de lancement pour tester la robustesse.
            if False:
                yield  # pragma: no cover
            raise FileNotFoundError("codex missing")

        dummy_log = MagicMock()
        with (
            patch("usbide.app.codex_cli_available", return_value=True),
            patch("usbide.app.codex_exec_argv", return_value=["codex", "exec", "hello"]),
            patch("usbide.app.stream_subprocess", fake_stream),
            patch.object(app, "query_one", return_value=dummy_log),
        ):
            await app._run_codex(DummyEvent("hello"))

        # Le message d'erreur doit etre ecrit dans le panneau Codex.
        messages = [call.args[0] for call in dummy_log.write.call_args_list if call.args]
        self.assertTrue(any("Codex introuvable" in msg for msg in messages))


class TestUSBIDEAppBugLog(unittest.TestCase):
    def test_record_issue_cree_bug_md(self) -> None:
        # Un incident doit etre ajoute dans bug.md avec les champs essentiels.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            app = USBIDEApp(root_dir=root_dir)

            app._record_issue("erreur", "Erreur test", contexte="test_unitaire")

            contenu = (root_dir / "bug.md").read_text(encoding="utf-8")
            self.assertIn("niveau: erreur", contenu)
            self.assertIn("contexte: test_unitaire", contenu)
            self.assertIn("message: Erreur test", contenu)


class TestUSBIDEAppStreamLog(unittest.IsolatedAsyncioTestCase):
    async def test_stream_and_log_retour_nonzero(self) -> None:
        # Un exit code non nul doit etre consigne dans bug.md.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            app = USBIDEApp(root_dir=root_dir)

            async def fake_stream(*_args, **_kwargs):
                yield {"kind": "line", "text": "ok", "returncode": None}
                yield {"kind": "exit", "text": "exit 2", "returncode": 2}

            fake_log = MagicMock()
            output_lines: list[str] = []
            ui_lines: list[str] = []

            def output_log(text: str) -> None:
                output_lines.append(text)

            def ui_log(text: str) -> None:
                ui_lines.append(text)

            with (
                patch("usbide.app.stream_subprocess", fake_stream),
                patch.object(app, "query_one", return_value=fake_log),
            ):
                await app._stream_and_log(
                    ["cmd"],
                    cwd=root_dir,
                    env={},
                    output_log=output_log,
                    ui_log=ui_log,
                    contexte="test subprocess",
                )

            contenu = (root_dir / "bug.md").read_text(encoding="utf-8")
            self.assertIn("rc=2", contenu)

