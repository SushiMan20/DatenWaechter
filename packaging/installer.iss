; Installer für das fertige Windows-Programm (Inno Setup 6).
; Bauen: iscc /DAppVersion=1.5.0 packaging\installer.iss   (vorher PyInstaller ausführen)
; Installiert ohne Admin-Rechte nach %LOCALAPPDATA%\Programs\Datenwaechter.

#ifndef AppVersion
  #define AppVersion "1.5.0"
#endif

[Setup]
AppId={{6F1B2C8E-4B7D-4E59-9A3C-2D8E5F1A7C40}
AppName=Datenwächter
AppVersion={#AppVersion}
AppVerName=Datenwächter {#AppVersion}
AppPublisher=Datenwächter
DefaultDirName={localappdata}\Programs\Datenwaechter
DefaultGroupName=Datenwächter
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Datenwaechter-Setup-{#AppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\Datenwaechter.exe
UninstallDisplayName=Datenwächter
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "autostart"; Description: "Mit Windows starten (Schutz läuft im Infobereich)"; GroupDescription: "Zusätzlich:"
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop"; GroupDescription: "Zusätzlich:"; Flags: unchecked

[Files]
Source: "..\dist\Datenwaechter\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\extension\*"; DestDir: "{app}\Browser-Erweiterung"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\Datenwächter"; Filename: "{app}\Datenwaechter.exe"
Name: "{userprograms}\Datenwächter – Browser-Erweiterung (Ordner)"; Filename: "{app}\Browser-Erweiterung"
Name: "{userdesktop}\Datenwächter"; Filename: "{app}\Datenwaechter.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Datenwaechter"; ValueData: """{app}\Datenwaechter.exe"" --minimiert"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\datenwaechter-cli.exe"; Parameters: "browser-bruecke"; Flags: runhidden waituntilterminated; StatusMsg: "Verbindung zur Browser-Erweiterung einrichten …"
Filename: "{app}\Datenwaechter.exe"; Description: "Datenwächter jetzt starten"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/im Datenwaechter.exe /f"; Flags: runhidden; RunOnceId: "Beenden"
Filename: "{app}\datenwaechter-cli.exe"; Parameters: "browser-bruecke --entfernen"; Flags: runhidden; RunOnceId: "Bruecke"
