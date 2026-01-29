from pathlib import Path
import unittest

from usbide.app import USBIDEApp


class TestThemeFrancais(unittest.TestCase):
    def test_bindings_sont_en_francais(self) -> None:
        # Vérifie que les libellés des raccourcis sont bien en français.
        expected_labels = [
            "Sauvegarder",
            "Exécuter",
            "Effacer le journal",
            "Recharger l'arborescence",
            "Connexion Codex",
            "Vérifier Codex",
            "Installer Codex",
            "Construire l'EXE",
            "Outils de dev",
            "Quitter",
        ]
        actual_labels = [label for _, _, label in USBIDEApp.BINDINGS]

        self.assertEqual(actual_labels, expected_labels)

    def test_theme_tcss_contient_les_sections_principales(self) -> None:
        # Garantit que le thème inclut les sections clés de l'UI.
        repo_root = Path(__file__).resolve().parents[1]
        css_path = repo_root / "usbide" / "usbide.tcss"
        css_text = css_path.read_text(encoding="utf-8")

        for selector in ("Screen", "#main", "#tree:focus", "#editor:focus", "#cmd:focus"):
            with self.subTest(selector=selector):
                self.assertIn(selector, css_text)
