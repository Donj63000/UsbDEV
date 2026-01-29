import os
import unittest
from pathlib import Path
from unittest.mock import patch

from usbide.runner import (
    codex_bin_dir,
    codex_cli_available,
    codex_env,
    codex_install_argv,
    codex_install_prefix,
    codex_login_argv,
    codex_status_argv,
    parse_tool_list,
    pip_install_argv,
    pyinstaller_available,
    pyinstaller_build_argv,
    pyinstaller_install_argv,
    stream_subprocess,
    tool_available,
    tools_env,
    tools_install_prefix,
)


class TestStreamSubprocess(unittest.IsolatedAsyncioTestCase):
    async def test_argv_vide_declenche_erreur(self) -> None:
        # Une commande vide doit être rejetée pour éviter un subprocess invalide.
        with self.assertRaises(ValueError):
            async for _ in stream_subprocess([]):
                pass


class TestCodexHelpers(unittest.TestCase):
    def test_codex_login_argv(self) -> None:
        # Vérifie la commande d'authentification attendue.
        argv = codex_login_argv()
        self.assertIn(argv[0], {"codex", "codex.cmd"})
        self.assertEqual(argv[1:], ["login"])

    def test_codex_status_argv(self) -> None:
        # Vérifie la commande de statut d'authentification attendue.
        argv = codex_status_argv()
        self.assertIn(argv[0], {"codex", "codex.cmd"})
        self.assertEqual(argv[1:], ["login", "status"])

    def test_codex_cli_available(self) -> None:
        # Le helper doit refléter la disponibilité du binaire.
        with patch("usbide.runner.shutil.which", return_value="/usr/bin/codex"):
            self.assertTrue(codex_cli_available())
        with patch("usbide.runner.shutil.which", return_value=None):
            self.assertFalse(codex_cli_available())

    def test_codex_cli_available_avec_env(self) -> None:
        # La disponibilité doit tenir compte du PATH fourni.
        root_dir = Path("/tmp/usbide")
        env = {"PATH": "/bin"}
        expected_bin = str(codex_bin_dir(codex_install_prefix(root_dir)))
        expected_path = os.pathsep.join([expected_bin, env["PATH"]])
        with patch("usbide.runner.shutil.which", return_value="/usr/bin/codex") as which:
            self.assertTrue(codex_cli_available(root_dir, env))
            self.assertEqual(which.call_args.kwargs.get("path"), expected_path)
            self.assertIn(which.call_args.args[0], {"codex", "codex.cmd"})

    def test_codex_env_prepend_path(self) -> None:
        # L'environnement Codex doit préfixer le PATH avec le binaire portable.
        root_dir = Path("/tmp/usbide")
        base_env = {"PATH": "/bin"}
        env = codex_env(root_dir, base_env)
        expected_bin = str(codex_bin_dir(codex_install_prefix(root_dir)))
        self.assertTrue(env["PATH"].startswith(expected_bin + os.pathsep))
        self.assertEqual(base_env["PATH"], "/bin")

    def test_codex_install_argv(self) -> None:
        # La commande pip doit cibler le préfixe portable.
        prefix = Path("/tmp/usbide/.usbide/codex")
        argv = codex_install_argv(prefix, "codex")
        self.assertIn("--prefix", argv)
        self.assertIn(str(prefix), argv)

    def test_codex_install_argv_rejecte_vide(self) -> None:
        # Un nom de package vide doit déclencher une erreur.
        with self.assertRaises(ValueError):
            codex_install_argv(Path("/tmp/usbide/.usbide/codex"), " ")


class TestToolsHelpers(unittest.TestCase):
    def test_parse_tool_list(self) -> None:
        # La liste doit être nettoyée (séparateurs et doublons).
        tools = parse_tool_list("ruff, black  mypy, pytest ruff")
        self.assertEqual(tools, ["ruff", "black", "mypy", "pytest"])

    def test_tool_available_rejecte_vide(self) -> None:
        # Un nom d'outil vide doit déclencher une erreur.
        with self.assertRaises(ValueError):
            tool_available(" ")

    def test_tools_env_prepend_path(self) -> None:
        # L'environnement outils doit préfixer le PATH avec le binaire portable.
        root_dir = Path("/tmp/usbide")
        base_env = {"PATH": "/bin"}
        env = tools_env(root_dir, base_env)
        expected_bin = str(codex_bin_dir(tools_install_prefix(root_dir)))
        self.assertTrue(env["PATH"].startswith(expected_bin + os.pathsep))
        self.assertEqual(base_env["PATH"], "/bin")

    def test_pyinstaller_install_argv(self) -> None:
        # La commande pip doit cibler le préfixe outils.
        prefix = Path("/tmp/usbide/.usbide/tools")
        argv = pyinstaller_install_argv(prefix)
        self.assertIn("--prefix", argv)
        self.assertIn(str(prefix), argv)

    def test_pip_install_argv(self) -> None:
        # La commande pip doit inclure les packages demandés.
        prefix = Path("/tmp/usbide/.usbide/tools")
        argv = pip_install_argv(prefix, ["ruff", "black"])
        self.assertIn("--prefix", argv)
        self.assertIn(str(prefix), argv)
        self.assertIn("ruff", argv)
        self.assertIn("black", argv)

    def test_pip_install_argv_offline(self) -> None:
        # Le mode offline doit ajouter --no-index et --find-links.
        prefix = Path("/tmp/usbide/.usbide/tools")
        wheelhouse = Path("/tmp/usbide/tools/wheels")
        argv = pip_install_argv(prefix, ["ruff"], find_links=wheelhouse, no_index=True)
        self.assertIn("--no-index", argv)
        self.assertIn("--find-links", argv)
        self.assertIn(str(wheelhouse), argv)

    def test_pip_install_argv_rejecte_vide(self) -> None:
        # Une liste vide doit déclencher une erreur.
        with self.assertRaises(ValueError):
            pip_install_argv(Path("/tmp/usbide/.usbide/tools"), [" "])

    def test_pyinstaller_build_argv(self) -> None:
        # La commande PyInstaller doit inclure le script et le dist.
        script = Path("/tmp/usbide/app.py")
        dist_dir = Path("/tmp/usbide/dist")
        argv = pyinstaller_build_argv(script, dist_dir, onefile=True)
        self.assertIn(str(script), argv)
        self.assertIn(str(dist_dir), argv)
        self.assertIn("--onefile", argv)
        self.assertNotIn("--onedir", argv)

    def test_pyinstaller_build_argv_onedir_par_defaut(self) -> None:
        # Par défaut, on privilégie --onedir pour limiter les faux positifs AV.
        script = Path("/tmp/usbide/app.py")
        dist_dir = Path("/tmp/usbide/dist")
        argv = pyinstaller_build_argv(script, dist_dir)
        self.assertIn("--onedir", argv)

    def test_pyinstaller_build_argv_work_spec(self) -> None:
        # Les chemins work/spec doivent être inclus si fournis.
        script = Path("/tmp/usbide/app.py")
        dist_dir = Path("/tmp/usbide/dist")
        work_dir = Path("/tmp/usbide/build")
        spec_dir = Path("/tmp/usbide")
        argv = pyinstaller_build_argv(
            script,
            dist_dir,
            work_dir=work_dir,
            spec_dir=spec_dir,
        )
        self.assertIn("--workpath", argv)
        self.assertIn(str(work_dir), argv)
        self.assertIn("--specpath", argv)
        self.assertIn(str(spec_dir), argv)

    def test_pyinstaller_build_argv_rejecte_vide(self) -> None:
        # Un script vide doit déclencher une erreur.
        with self.assertRaises(ValueError):
            pyinstaller_build_argv(Path(""), Path("/tmp/usbide/dist"))

    def test_pyinstaller_available_avec_env(self) -> None:
        # La disponibilité doit tenir compte du PATH fourni.
        root_dir = Path("/tmp/usbide")
        env = {"PATH": "/bin"}
        expected_bin = str(codex_bin_dir(tools_install_prefix(root_dir)))
        expected_path = os.pathsep.join([expected_bin, env["PATH"]])
        with patch("usbide.runner.shutil.which", return_value="/usr/bin/pyinstaller") as which:
            self.assertTrue(pyinstaller_available(root_dir, env))
            which.assert_called_once_with("pyinstaller", path=expected_path)

    def test_tool_available_avec_env(self) -> None:
        # La disponibilité doit tenir compte du PATH fourni.
        root_dir = Path("/tmp/usbide")
        env = {"PATH": "/bin"}
        expected_bin = str(codex_bin_dir(tools_install_prefix(root_dir)))
        expected_path = os.pathsep.join([expected_bin, env["PATH"]])
        with patch("usbide.runner.shutil.which", return_value="/usr/bin/ruff") as which:
            self.assertTrue(tool_available("ruff", root_dir, env))
            which.assert_called_once_with("ruff", path=expected_path)
