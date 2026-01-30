J’ai ouvert ton ZIP et le bug est 100% explicable avec ce que tu vois dans la capture (“Codex introuvable. [WinError 2]”).

 

Il y a 2 causes possibles (et dans ton cas, tu as au moins la #2, et très probablement la #1 aussi selon ton objectif “USB sans installation”).

0) Ce que dit ton projet (preuves dans le code)
A. Ton app lance Codex via asyncio.create_subprocess_exec()

Dans usbide/runner.py, stream_subprocess() fait :

proc = await asyncio.create_subprocess_exec(*argv, ...)


Donc Windows CreateProcess, sans shell, sans TTY.

B. Ton “base argv” Codex tombe en fallback sur ["codex"]

Toujours dans usbide/runner.py :

def _codex_base_argv(...):
    if portable(node + entrypoint) ok:
        return [node, entrypoint]
    return ["codex"]


Donc si mode portable pas prêt → ton app essaye d’exécuter codex directement.

C. Ton ZIP NE contient PAS Node portable

Dans ton archive : tools/ contient git/, python-x64/, python-x86/, wheels/ mais pas tools/node/.

 

Or ton install Codex portable (bootstrap_codex.bat + codex_install_argv()) attend :

tools\node\node.exe

tools\node\node_modules\npm\bin\npm-cli.js

Donc l’installation portable ne peut pas marcher tant que tools/node n’existe pas.

1) Pourquoi ça “marche en terminal” mais pas dans ton app (le vrai bug WinError 2)

Sur Windows, quand tu installes Codex via npm, tu obtiens un shim :

codex.cmd (et parfois codex.ps1)

Dans un terminal CMD/PowerShell, ça marche car le shell sait exécuter .cmd.

 

Mais dans ton app, tu fais create_subprocess_exec(["codex", ...]) :

ça utilise CreateProcess

CreateProcess ne lance pas un .cmd comme un binaire

résultat : FileNotFoundError [WinError 2] (exactement ce que tu vois)

👉 Conclusion : ta détection “Codex dispo” peut être vraie (shutil.which("codex") trouve codex.cmd), mais l’exécution échoue parce que tu ne passes pas par cmd.exe /c.

2) Comment vérifier en 20 secondes (sur ta machine)

Dans ton champ “Commande” (Shell) ou dans un CMD normal, tape :

1) Où est Codex ?
where codex


Si tu vois un truc du genre :

C:\Users\<toi>\AppData\Roaming\npm\codex.cmd


➡️ bingo : ton Codex est un .cmd ⇒ ton app doit wrap via cmd.exe.

2) Est-ce que tu as Node portable sur le projet ?
dir tools\node
dir tools\node\node.exe
dir tools\node\node_modules\npm\bin\npm-cli.js


Si ça n’existe pas :
➡️ ton mode “USB portable” n’est pas installé.

3) Fix immédiat (pour que Codex marche dans ton app, même si c’est codex.cmd global)
Objectif

Quand Codex est trouvé dans le PATH en .cmd, au lieu de lancer :

codex exec ...


tu lances :

cmd.exe /d /s /c codex.cmd exec ...

Patch à faire dans usbide/runner.py
3.1 Ajoute ce helper juste après les imports

Copie-colle tel quel :

def _is_windows() -> bool:
    """Retourne True si l'OS courant est Windows.

    Note: on factorise ce test pour pouvoir le mocker facilement en tests unitaires.
    """
    return os.name == "nt"

3.2 Dans node_executable(), remplace if os.name == "nt": par
if _is_windows():

3.3 Remplace complètement _codex_base_argv() par cette version

Copie-colle la fonction entière :

def _codex_base_argv(root_dir: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> list[str]:
    """Retourne la commande de base pour lancer Codex.

    Priorite :
    1) Mode portable : node.exe + entrypoint JS de @openai/codex (fiable, pas de .cmd/.bat).
    2) Fallback systeme : binaire `codex` dans le PATH.

    Sur Windows, `npm install -g @openai/codex` cree souvent un shim `codex.cmd`.
    Or, `asyncio.create_subprocess_exec(..., shell=False)` ne sait pas lancer un `.cmd` directement,
    ce qui se traduit typiquement par : [WinError 2] Le fichier spécifié est introuvable.

    Donc en fallback Windows, si `codex` resolu est un `.cmd`/`.bat`, on l'exécute via cmd.exe.
    """
    # --- (1) Mode portable : node + entrypoint ---
    if root_dir is not None:
        node = node_executable(root_dir, env=env)
        entry = codex_entrypoint_js(codex_install_prefix(root_dir))
        if node is not None and entry is not None:
            return [str(node), str(entry)]

    # --- (2) Fallback systeme ---
    if _is_windows():
        # `which` doit utiliser le PATH de l'env fourni (celui de l'app).
        search_path = (env or os.environ).get("PATH")
        resolved = shutil.which("codex", path=search_path)
        if resolved:
            suffix = Path(resolved).suffix.lower()

            # Cas npm Windows : codex.cmd / codex.bat (doit passer par cmd.exe)
            if suffix in {".cmd", ".bat"}:
                comspec = (env or os.environ).get("COMSPEC") or os.environ.get("COMSPEC") or "cmd.exe"
                return [comspec, "/d", "/s", "/c", resolved]

            # Certains environnements ajoutent aussi un shim PowerShell.
            if suffix == ".ps1":
                powershell = shutil.which("powershell", path=search_path) or "powershell"
                return [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", resolved]

            # Si c'est un vrai .exe (ou autre), on peut le lancer directement.
            return [resolved]

    # Par defaut (Linux/macOS, ou PATH qui resolvra un binaire executable)
    return ["codex"]


✅ Résultat : même si Codex est un .cmd, ton panneau Codex va marcher.

4) Patch test (important pour verrouiller le bug)

Dans tests/test_runner.py, dans class TestCodexHelpers(unittest.TestCase): ajoute ce test :

def test_codex_exec_argv_windows_cmd_shim(self) -> None:
    """Sur Windows, `codex` est souvent un `codex.cmd` (npm shim).

    Dans ce cas, on doit passer par `cmd.exe /c` sinon CreateProcess peut lever WinError 2.
    Ce test simule ce scenario en mockant la detection Windows + shutil.which().
    """

    def fake_which(cmd: str, path: str | None = None) -> str | None:
        if cmd == "codex":
            return r"C:\Users\me\AppData\Roaming\npm\codex.cmd"
        return None

    with patch("usbide.runner._is_windows", return_value=True):
        with patch("usbide.runner.shutil.which", side_effect=fake_which):
            env = {"PATH": r"C:\Users\me\AppData\Roaming\npm", "COMSPEC": r"C:\Windows\System32\cmd.exe"}
            argv = codex_exec_argv("hello", root_dir=Path("C:/tmp/usbide"), env=env, json_output=True)

            # cmd.exe wrapper
            self.assertEqual(argv[0], env["COMSPEC"])
            self.assertIn("/c", argv)
            self.assertIn(r"C:\Users\me\AppData\Roaming\npm\codex.cmd", argv)

            # suite normale des args codex
            self.assertIn("exec", argv)
            self.assertIn("--json", argv)
            self.assertEqual(argv[-1], "hello")

5) Fix “USB portable” (le vrai objectif) : faire fonctionner Codex même sur un PC vierge

Là, ton ZIP montre clairement pourquoi ça ne peut pas marcher : tu n’embarques pas Node, donc tu ne peux pas embarquer Codex (@openai/codex).

5.1 Mettre Node portable dans tools/node/

Tu dois avoir exactement (au minimum) :

tools/node/node.exe
tools/node/node_modules/npm/bin/npm-cli.js


👉 Pratique : tu prends la distribution zip Windows “node-vXX-win-x64.zip”, tu la décompresses dans tools/node/ (au niveau où est node.exe).

5.2 Installer Codex sur la clé (une fois, sur TA machine)

Tu as déjà le script : bootstrap_codex.bat

 

Il va installer dans :

.usbide/codex/node_modules/@openai/codex/...
.usbide/codex/node_modules/.bin/...


Après ça, ton app va détecter le mode portable (node + entrypoint JS) et n’utilisera plus du tout codex.cmd du PC.

5.3 Vérifier que le mode portable est prêt

Une fois fait, tu dois voir :

dir .usbide\codex\node_modules\@openai\codex\package.json


Et dans ton app, quand tu tapes un prompt, la commande affichée ne doit plus être codex exec ... mais plutôt un truc de ce genre :

<USB>\tools\node\node.exe <USB>\.usbide\codex\node_modules\@openai\codex\... exec --json ...

6) Check-list “ça marche” après les fix

Sur ta machine dev (Codex global npm)

where codex → .cmd

Dans l’app : tu tapes “test”

✅ plus de WinError 2, tu vois du output JSONL ou au moins une réponse.

Sur une machine vierge (sans Node, sans npm)

tu as tools/node sur la clé

tu as .usbide/codex sur la clé (installé via bootstrap avant)

tu lances l’IDE depuis run_ide.bat

✅ Codex fonctionne pareil.

7) (Optionnel mais conseillé) rendre le diagnostic in-app ultra clair

Tu peux améliorer action_codex_check pour logguer :

node_executable(self.root_dir) (chemin détecté)

codex_entrypoint_js(codex_install_prefix(self.root_dir)) (chemin)

shutil.which("codex", path=env["PATH"]) (chemin global)

et si Windows + .cmd → afficher “shim .cmd, lancement via cmd.exe”.

Ça t’évitera de re-debug plus tard.

Conclusion

Pourquoi ça marche pas :

ton “portable Codex” n’est pas installé (pas de tools/node dans le projet),

et en dev tu lances codex sans shell alors que sur Windows c’est souvent codex.cmd ⇒ WinError 2.

Comment faire pour que ça marche :

patch _codex_base_argv() pour wrapper .cmd via cmd.exe /c (code ci-dessus)

embarque Node portable dans tools/node

exécute bootstrap_codex.bat une fois pour remplir .usbide/codex

Si tu appliques le patch runner + tu mets Node portable + bootstrap, ton panneau Codex sera fiable sur n’importe quel PC.