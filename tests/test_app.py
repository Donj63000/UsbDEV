import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from usbide.app import OpenFile, USBIDEApp


class TestUSBIDEAppTitle(unittest.TestCase):
    def test_refresh_title_sans_fichier(self) -> None:
        # Le titre doit afficher le nom officiel et le chemin racine.
        root_dir = Path("/tmp/usbide")
        app = USBIDEApp(root_dir=root_dir)
        app.current = None

        app._refresh_title()

        self.assertEqual(app.title, "ValDev Pro v1")
        self.assertEqual(app.sub_title, str(root_dir))

    def test_refresh_title_avec_fichier_dirty(self) -> None:
        # Le titre doit garder le branding et signaler les modifications.
        root_dir = Path("/tmp/usbide")
        app = USBIDEApp(root_dir=root_dir)
        app.current = OpenFile(path=root_dir / "main.py", encoding="utf-8", dirty=True)

        app._refresh_title()

        self.assertEqual(app.title, "ValDev Pro v1 *")
        self.assertIn("main.py", app.sub_title)
        self.assertIn("utf-8", app.sub_title)


class TestUSBIDEAppSave(unittest.TestCase):
    def test_action_save_ok(self) -> None:
        # Une sauvegarde réussie doit retourner True et écrire le contenu.
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
        # Un encodage incompatible doit déclencher un fallback UTF-8.
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            path = root_dir / "accent.txt"
            app = USBIDEApp(root_dir=root_dir)
            app.current = OpenFile(path=path, encoding="ascii", dirty=True)
            fake_editor = MagicMock()
            fake_editor.text = "é"

            with patch.object(app, "query_one", return_value=fake_editor):
                self.assertTrue(app.action_save())

            self.assertEqual(path.read_text(encoding="utf-8"), "é")

    def test_action_save_oserror(self) -> None:
        # Une erreur d'écriture doit retourner False.
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
