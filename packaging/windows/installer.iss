#ifndef AppVersion
  #error AppVersion must be supplied by build-windows.ps1
#endif
#ifndef SourceRoot
  #error SourceRoot must be supplied
#endif
[Setup]
AppId={{3AF16E0B-66C4-49A5-9439-6E02879E3EA2}
AppName=MKV Audio Converter
AppVersion={#AppVersion}
AppPublisher=Fry747
AppPublisherURL=https://github.com/Fry747/mkv-audio-converter
DefaultDirName={localappdata}\Programs\MKV Audio Converter
DefaultGroupName=MKV Audio Converter
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible and not arm64
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#SourceRoot}\dist\windows
OutputBaseFilename=MKVAudioConverter-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#SourceRoot}\mkv_audio_converter\assets\icon.ico
LicenseFile={#SourceRoot}\LICENSE
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\MKVAudioConverter.exe
SetupLogging=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; Flags: unchecked

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceRoot}\dist\MKVAudioConverter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MKV Audio Converter"; Filename: "{app}\MKVAudioConverter.exe"; IconFilename: "{app}\MKVAudioConverter.exe"; AppUserModelID: "Fry747.MKVAudioConverter"
Name: "{group}\Deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MKV Audio Converter"; Filename: "{app}\MKVAudioConverter.exe"; IconFilename: "{app}\MKVAudioConverter.exe"; AppUserModelID: "Fry747.MKVAudioConverter"; Tasks: desktopicon

[Run]
Filename: "{app}\MKVAudioConverter.exe"; Description: "MKV Audio Converter starten"; Flags: nowait postinstall skipifsilent

; Media and separately downloaded tools in LocalAppData are deliberately not
; removed by the uninstaller. There is no recursive user-data deletion rule.
