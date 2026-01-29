import unittest

from usbide.runner import stream_subprocess


class TestStreamSubprocess(unittest.IsolatedAsyncioTestCase):
    async def test_argv_vide_declenche_erreur(self) -> None:
        # Une commande vide doit être rejetée pour éviter un subprocess invalide.
        with self.assertRaises(ValueError):
            async for _ in stream_subprocess([]):
                pass
