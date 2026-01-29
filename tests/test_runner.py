import unittest
from unittest.mock import patch

from usbide.runner import codex_cli_available, codex_login_argv, stream_subprocess


class TestStreamSubprocess(unittest.IsolatedAsyncioTestCase):
    async def test_argv_vide_declenche_erreur(self) -> None:
        # Une commande vide doit être rejetée pour éviter un subprocess invalide.
        with self.assertRaises(ValueError):
            async for _ in stream_subprocess([]):
                pass


class TestCodexHelpers(unittest.TestCase):
    def test_codex_login_argv(self) -> None:
        # Vérifie la commande d'authentification attendue.
        self.assertEqual(codex_login_argv(), ["codex", "auth", "login"])

    def test_codex_cli_available(self) -> None:
        # Le helper doit refléter la disponibilité du binaire.
        with patch("usbide.runner.shutil.which", return_value="/usr/bin/codex"):
            self.assertTrue(codex_cli_available())
        with patch("usbide.runner.shutil.which", return_value=None):
            self.assertFalse(codex_cli_available())
