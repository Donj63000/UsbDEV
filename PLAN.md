Les 6 trucs qui peuvent te bloquer chez les clients
2.1 Politiques IT (le vrai mur)

Beaucoup d’entreprises ont :

AppLocker / WDAC : bloque les exécutables non signés, ou ceux lancés depuis USB.

interdiction d’exécuter depuis un disque amovible

interdiction d’écrire dans certains dossiers

👉 Solution “pro” : signature de code (certificat) + procédure IT (whitelisting). Sinon tu auras des clients où ça ne passera pas.

2.2 Antivirus & SmartScreen (PyInstaller = souvent flag)

Les binaires “onefile” PyInstaller sont souvent suspects (extraction dans %TEMP%, packing).
👉 Stratégie :

préfère --onedir (un dossier) plutôt que --onefile

signe le binaire

garde un nom/éditeur stable

2.3 Compatibilité 32/64-bit

Un .exe packagé depuis un Python x64 ne tournera pas sur Windows 32-bit.
👉 Si tu veux être blindé : embarque un toolchain x64 et éventuellement x86 (rare en 2026 mais possible chez des vieux clients).

2.4 Dépendances Python avec extensions C

Si ton script utilise des libs qui nécessitent compilation (certains packages), tu vas tomber sur :

besoin de Visual Studio Build Tools

wheels manquants

timeouts / erreurs

👉 Solution : n’utiliser que des wheels pré-téléchargées (offline) et éviter les dépendances qui compilent sur place.

2.5 Codex en terminal : attention Windows

Si tu parles de Codex CLI officiel :

il se lance localement et peut lire/modifier/exécuter du code dans un dossier

mais Windows est “experimental” et OpenAI recommande souvent WSL pour la meilleure expérience

installer WSL = souvent admin + “pas zéro install”.

Donc si ton objectif est “je plug ma clé sur un PC client standard”, ne pars pas du principe que WSL/Node/VSBuildTools sont dispo.

2.6 Data / confidentialité + clé API

Codex/API = tu envoies potentiellement du code client vers OpenAI (à valider contractuellement).
Côté API :

par défaut des logs de monitoring d’abus peuvent être conservés jusqu’à 30 jours, et il existe des options type Zero Data Retention (soumis à éligibilité/approbation)

par défaut, les entrées/sorties API des offres business ne servent pas à entraîner les modèles, sauf opt-in

Côté sécurité clé :

ne jamais hardcoder

utiliser variables d’environnement / secret management

3) Architecture USB recommandée (portable, reproductible, propre)

Objectif : tout sur la clé, y compris caches, config, logs, wheels et builds.

USB:\
  UsbDev\
    run_ide.bat
    tools\
      python-x64\
      python-x86\          (optionnel)
      wheels\              (offline wheelhouse)
      pyinstaller\         (installé dans python-x64)
      git\                 (portable si besoin)
    workspace\
      client_A\
        src\
        requirements.txt
        build.bat
        app.spec
    cache\
      pip\
      pyinstaller\
    codex_home\            (si tu utilises Codex CLI)
    tmp\

4) Scripts concrets : launcher “zéro trace” (Windows)
4.1 run_ide.bat (point d’entrée)

détecte la lettre de la clé

force caches sur USB

prépare variables Codex (si utilisé)

lance ton IDE

@echo off
setlocal enabledelayedexpansion

REM Root = dossier du .bat (donc portable quel que soit le drive letter)
set "ROOT=%~dp0"
REM Normaliser sans trailing backslash
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

REM === Choisis ton Python portable ===
set "PY=%ROOT%\tools\python-x64\python.exe"

REM === Tout ce qui écrit doit écrire sur la clé ===
set "PIP_CACHE_DIR=%ROOT%\cache\pip"
set "PYTHONPYCACHEPREFIX=%ROOT%\cache\pycache"
set "TEMP=%ROOT%\tmp"
set "TMP=%ROOT%\tmp"
set "PYTHONNOUSERSITE=1"

REM === Si tu utilises Codex CLI officiel, force tout sur la clé ===
REM Codex peut stocker auth/config localement; on le redirige vers la clé
set "CODEX_HOME=%ROOT%\codex_home"

REM Exemple: si tu utilises l'API OpenAI via SDK (Python), la clé doit être en env var
REM set "OPENAI_API_KEY=..."
REM Idéal: ne pas stocker ici, mais demander au démarrage (voir plus bas).

REM Assure dossiers
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%"
if not exist "%ROOT%\cache\pycache" mkdir "%ROOT%\cache\pycache"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%CODEX_HOME%" mkdir "%CODEX_HOME%"

REM PATH minimal
set "PATH=%ROOT%\tools\python-x64;%ROOT%\tools\python-x64\Scripts;%PATH%"

REM Lance ton IDE (ex: python -m ton_app)
"%PY%" -m your_ide.main %*
endlocal

5) Dépendances offline (indispensable si tu veux “plug & work”)
5.1 Préparer un “wheelhouse” AVANT d’aller chez le client

Sur ta machine (avec Internet), tu fais :

pip download -r requirements.txt -d USB:\UsbDev\tools\wheels


Ensuite, chez le client (sans Internet), tu installes depuis wheels :

"%PY%" -m pip install --no-index --find-links "%ROOT%\tools\wheels" -r requirements.txt


👉 Ça t’évite :

pip qui télécharge

compilation

surprises réseau/proxy

6) Build .exe “sur place” (zéro install) : PyInstaller robuste
6.1 build.bat par projet (dans workspace\client_X\)

Important : force --distpath, --workpath, --specpath sur la clé.

@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "USBROOT=%ROOT%\..\.."
for %%I in ("%USBROOT%") do set "USBROOT=%%~fI"

set "PY=%USBROOT%\tools\python-x64\python.exe"

set "PIP_CACHE_DIR=%USBROOT%\cache\pip"
set "PYTHONPYCACHEPREFIX=%USBROOT%\cache\pycache"
set "TEMP=%USBROOT%\tmp"
set "TMP=%USBROOT%\tmp"
set "PYTHONNOUSERSITE=1"

REM Optionnel: s'assure que pyinstaller est présent (offline)
"%PY%" -m pip install --no-index --find-links "%USBROOT%\tools\wheels" pyinstaller

REM Nettoyage des outputs
if exist "%ROOT%\dist" rmdir /s /q "%ROOT%\dist"
if exist "%ROOT%\build" rmdir /s /q "%ROOT%\build"

REM Build onedir (moins de faux positifs AV)
"%PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --distpath "%ROOT%\dist" ^
  --workpath "%ROOT%\build" ^
  --specpath "%ROOT%" ^
  "%ROOT%\app.spec"

echo Done. Output: %ROOT%\dist
endlocal

6.2 app.spec minimal (exemple)
# app.spec
# PyInstaller spec minimal, à adapter
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = []
# hiddenimports += collect_submodules("some_pkg")  # si import dynamique

a = Analysis(
    ["src/main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/*", "assets"),
        ("config/default.json", "config"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClientTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,   # False si tu veux GUI
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ClientTool",
)

7) Codex : comment rendre ça compatible “clé USB + PC client”
7.1 Si tu utilises Codex CLI officiel

Faits à connaître :

Le CLI peut lancer une UI terminale interactive et exécuter des commandes

Il stocke des transcriptions localement pour pouvoir “resume”

L’auth est cachée localement (fichier auth.json ou credential store) et tu peux contrôler où ça va

Windows est possible mais recommandé via WSL pour le meilleur setup

Implication : si tu veux “zéro trace sur le PC client”, tu dois forcer le stockage sur ta clé.

➡️ Dans ton %ROOT%\codex_home\config.toml (sur la clé), mets par exemple :

# Force credentials en fichier dans CODEX_HOME (donc sur la clé)
cli_auth_credentials_store = "file"


Le doc indique que le mode file stocke sous CODEX_HOME (par défaut ~/.codex) .

Et dans ton launcher, tu exportes :

set "CODEX_HOME=%ROOT%\codex_home"

7.2 Si tu veux éviter Codex CLI (recommandé pour “zéro install” sur Windows)

Tu peux intégrer Codex/Responses API directement dans ton mini IDE via le SDK Python OpenAI (juste une lib Python + HTTPS).
Le quickstart montre le pattern from openai import OpenAI puis client.responses.create(...) .

Exemple ultra-minimal (à intégrer dans ton IDE, pas un produit final) :

# codex_client_min.py
import os
from openai import OpenAI

def ask(prompt: str) -> str:
    # OPENAI_API_KEY doit être en env var (ne pas hardcoder)
    client = OpenAI()
    resp = client.responses.create(
        model="gpt-5",
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    )
    return resp.output_text

if __name__ == "__main__":
    print(ask("Écris un script Python qui ..."))


Et tu récupères la clé au runtime (sans l’écrire sur le PC) :

variable d’environnement temporaire dans le process

ou prompt getpass (mieux)

Les bonnes pratiques OpenAI poussent à ne pas exposer la clé dans le code et à utiliser des env vars .

8) “Preflight check” : script qui te dit en 10 secondes si ça va passer

Tu lances ça dès que tu arrives chez un client :

arch OS

droits d’écriture

exécution depuis USB

connectivité API (si besoin)

présence proxy (optionnel)

# preflight.py
import os
import platform
import socket
import tempfile
from pathlib import Path

def can_write(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test = path / ".__write_test__"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        return True
    except Exception:
        return False

def dns_ok(host="api.openai.com") -> bool:
    try:
        socket.gethostbyname(host)
        return True
    except Exception:
        return False

def main():
    root = Path(__file__).resolve().parent
    print("== Preflight ==")
    print("OS:", platform.platform())
    print("Arch:", platform.machine(), platform.architecture())
    print("USB root:", root)

    print("\n[Write tests]")
    print("Write USB cache:", can_write(root / "cache"))
    print("Write USB tmp:", can_write(root / "tmp"))
    print("Write tempdir:", can_write(Path(tempfile.gettempdir()) / "usbdev_test"))

    print("\n[Network]")
    print("DNS api.openai.com:", dns_ok())
    # Tu peux ajouter un HEAD HTTPS ici si autorisé (requests) + proxy detection

    print("\n[Env]")
    print("OPENAI_API_KEY set:", bool(os.environ.get("OPENAI_API_KEY")))
    print("HTTP_PROXY set:", bool(os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")))

if __name__ == "__main__":
    main()

9) Conclusion “terrain” (réponse directe à “tout est ok ?”)

Oui, ton workflow “je viens avec une clé, je code, je freeze en exe, je dépose sur le PC” est techniquement viable.

Non, ce n’est pas “ok partout” tant que tu n’as pas cadré :

IT policies (exécution depuis USB, whitelist, signature)

AV/SmartScreen (éviter onefile, signer)

dépendances (wheels offline, pas de compilation)

Codex sur Windows (Codex CLI = Windows expérimental + WSL souvent recommandé)

empreinte sur le PC (rediriger caches/config/logs sur la clé)

contrat data (code potentiellement envoyé à OpenAI; logs jusqu’à 30 jours par défaut côté API, options ZDR selon cas)