; captioncast.iss
; Inno Setup Script for Captor Core
; How to use: 
; 1. Download and install Inno Setup (https://jrsoftware.org/isdownload.php).
; 2. Open this captioncast.iss file in Inno Setup.
; 3. Click "Build -> Compile" (or press Ctrl+F9).
; 4. The single installer executable (CaptorCoreSetup.exe) will be created in the "Output" folder.

[Setup]
AppName=Captor Core
AppVersion=1.0.1
AppPublisher=Captor Core Team
DefaultDirName={autopf}\Captor Core
DefaultGroupName=Captor Core
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=CaptorCoreSetup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
SetupIconFile=captor_core_icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\CaptorCore\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Captor Core"; Filename: "{app}\CaptorCore.exe"
Name: "{autodesktop}\Captor Core"; Filename: "{app}\CaptorCore.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CaptorCore.exe"; Description: "{cm:LaunchProgram,Captor Core}"; Flags: nowait postinstall skipifsilent runascurrentuser
