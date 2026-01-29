from pathlib import Path
import unittest

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
