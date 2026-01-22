@echo off
setlocal EnableExtensions

REM --- racine (dossier usbide) ---
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

REM --- python portable attendu: adapte si besoin ---
REM ex: set "PY=%ROOT%\..\python\python.exe" si usbide est dans DEVKIT\usbide
set "PY=%ROOT%\..\python\python.exe"

if not exist "%PY%" (
  echo [ERREUR] Python portable introuvable: "%PY%"
  echo Edite ce fichier pour pointer vers ton python.exe sur la cle.
  pause
  exit /b 1
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_CACHE_DIR=%ROOT%\..\pip-cache"

cd /d "%ROOT%"
"%PY%" -m usbide --root "%ROOT%\..\workspace"
