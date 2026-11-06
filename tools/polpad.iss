; Instalador do Polpad para Windows (Inno Setup 6).
;
; Gerado por: .venv\Scripts\python tools\build_exe.py --instalador
; que passa /DVersao, /DOrigem (pasta dist\Polpad do PyInstaller),
; /DIcone e /O (pasta de saída).
;
; Instala só para o usuário, sem administrador. O atualizador do Polpad roda
; este mesmo instalador em silêncio para atualizar ou voltar de versão:
;   Polpad-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
;                    /CLOSEAPPLICATIONS /LOG=... [/ATUALIZACAO]
; Com /ATUALIZACAO, o Polpad é reaberto ao terminar.

#ifndef Versao
  #define Versao "0.0.0"
#endif
#ifndef Origem
  #define Origem "..\dist\Polpad"
#endif
#ifndef Icone
  #define Icone "..\build\polpad.ico"
#endif

[Setup]
AppId={{8F3C2A71-4D6B-4E9A-9C1E-2B7D5A0F3E64}
AppName=Polpad
AppVersion={#Versao}
AppVerName=Polpad {#Versao}
AppPublisher=Polpad
AppPublisherURL=https://github.com/gabriel-re-pires/polpad
AppSupportURL=https://github.com/gabriel-re-pires/polpad
VersionInfoVersion={#Versao}
DefaultDirName={localappdata}\Programs\Polpad
PrivilegesRequired=lowest
DisableDirPage=yes
DisableProgramGroupPage=yes
OutputBaseFilename=Polpad-Setup
SetupIconFile={#Icone}
UninstallDisplayIcon={app}\Polpad.exe
UninstallDisplayName=Polpad
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Fecha o Polpad aberto antes de trocar os arquivos; quem reabre é o [Run].
CloseApplications=yes
RestartApplications=no
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; Flags: unchecked

[InstallDelete]
; Arquivos de outra versão não podem sobrar (atualizar e voltar de versão).
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Origem}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Polpad"; Filename: "{app}\Polpad.exe"
Name: "{autodesktop}\Polpad"; Filename: "{app}\Polpad.exe"; Tasks: desktopicon

[Registry]
; Iniciar com o Windows: o Polpad grava este valor; a desinstalação o remove.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Polpad"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Polpad.exe"; Description: "Abrir o Polpad"; Flags: nowait postinstall skipifsilent
Filename: "{app}\Polpad.exe"; Flags: nowait; Check: EhAtualizacao

[Code]
function EhAtualizacao: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/ATUALIZACAO') = 0 then
      Result := True;
end;
