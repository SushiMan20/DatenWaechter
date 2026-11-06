# Baut das fertige Programm und den Installer auf einem Windows-PC.
# Voraussetzungen: Python 3.12 (python.org) und Inno Setup 6 (jrsoftware.org).
# Aufruf in PowerShell im Projektordner:  .\packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
python -m venv .venv-build
.\.venv-build\Scripts\python -m pip install --upgrade pip
.\.venv-build\Scripts\pip install ".[windows,gesichter,build]"
.\.venv-build\Scripts\pyinstaller --noconfirm --clean packaging\datenwaechter.spec --distpath dist --workpath build
$version = .\.venv-build\Scripts\python -c "import datenwaechter; print(datenwaechter.__version__)"
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" }
& $iscc "/DAppVersion=$version" packaging\installer.iss
Write-Host "Fertig: packaging\Output\Datenwaechter-Setup-$version.exe"
