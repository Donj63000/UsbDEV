@echo off
setlocal enabledelayedexpansion

REM Racine = dossier du .bat (portable quel que soit la lettre)
set "ROOT=%~dp0"
REM Normaliser sans trailing backslash
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

REM === Choisis ton Python portable ===
set "PY=%ROOT%\tools\python-x64\python.exe"

REM === Tout ce qui ecrit doit ecrire sur la cle ===
set "PIP_CACHE_DIR=%ROOT%\cache\pip"
set "PYTHONPYCACHEPREFIX=%ROOT%\cache\pycache"
set "TEMP=%ROOT%\tmp"
set "TMP=%ROOT%\tmp"
set "PYTHONNOUSERSITE=1"

REM === Codex CLI : forcer tout sur la cle ===
set "CODEX_HOME=%ROOT%\codex_home"

REM Assure dossiers
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%"
if not exist "%ROOT%\cache\pycache" mkdir "%ROOT%\cache\pycache"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%CODEX_HOME%" mkdir "%CODEX_HOME%"

REM PATH minimal
set "PATH=%ROOT%\tools\python-x64;%ROOT%\tools\python-x64\Scripts;%PATH%"

REM Lance l'IDE portable
"%PY%" -m usbide %*
endlocal
