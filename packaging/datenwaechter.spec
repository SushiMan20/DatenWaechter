# PyInstaller-Rezept für das fertige Windows-Programm.
# Bauen:  pyinstaller --noconfirm --clean packaging/datenwaechter.spec
# Ergebnis: dist/Datenwaechter/ mit Datenwaechter.exe (Fenster) und datenwaechter-cli.exe (Konsole, Browser-Brücke)
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(SPECPATH, "app.ico")

datas = [(os.path.join(ROOT, "datenwaechter", n), "datenwaechter") for n in ("kategorien.json", "vornamen.txt")]
datas += collect_data_files("tkinterdnd2")                       # Drag & Drop (tkdnd)
datas += collect_data_files("cv2", includes=["data/haarcascade_*.xml"])   # Gesichtserkennung
datas += collect_data_files("pypdfium2_raw") + collect_data_files("pypdfium2")
datas += copy_metadata("keyring")                                 # keyring findet seine Speicher über Metadaten
binaries = collect_dynamic_libs("pypdfium2_raw")
try:   # UI-Automation-Schnittstelle schon beim Bauen erzeugen, damit das Programm sie nicht erst anlegen muss
    import comtypes.client
    comtypes.client.GetModule("UIAutomationCore.dll")
except Exception as e:  # noqa: BLE001
    print("Hinweis: UIAutomationCore nicht vorbereitet:", e)
hidden = (["pystray._win32", "keyring.backends.Windows", "win32timezone", "win32clipboard", "win32con"]
          + collect_submodules("winrt") + collect_submodules("datenwaechter") + collect_submodules("comtypes"))

a = Analysis(
    [os.path.join(SPECPATH, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["torch", "transformers", "gliner", "pytest", "matplotlib", "IPython", "pandas", "scipy"],
    noarchive=False,
)
pyz = PYZ(a.pure)

gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Datenwaechter", console=False, icon=ICON,
          version=None, upx=False)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="datenwaechter-cli", console=True, icon=ICON, upx=False)
coll = COLLECT(gui, cli, a.binaries, a.datas, name="Datenwaechter", upx=False)
