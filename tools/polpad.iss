; Instalador do Polpad para Windows (Inno Setup 6).
;
; Gerado por: .venv\Scripts\python tools\build_exe.py --instalador
; que passa /DVersao, /DOrigem (pasta dist\Polpad do PyInstaller), /DIcone,
; /DLicenca, /DImagemGrande, /DImagemPequena e /O (pasta de saída).
;
; Páginas: boas-vindas, licença, opções, pronto para instalar, instalando e
; conclusão. Instala só para o usuário, sem administrador.
;
; O atualizador do Polpad roda este mesmo instalador em silêncio para
; atualizar ou voltar de versão:
;   Polpad-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
;                    /CLOSEAPPLICATIONS /LOG=... [/ATUALIZACAO]
; Com /ATUALIZACAO, o Polpad é reaberto ao terminar. Em silêncio, nenhuma
; opção é regravada: vale o que a pessoa escolheu depois, nas Configurações.

#ifndef Versao
  #define Versao "0.0.0"
#endif
#ifndef Origem
  #define Origem "..\dist\Polpad"
#endif
#ifndef Icone
  #define Icone "..\build\polpad.ico"
#endif
#ifndef Licenca
  #define Licenca "..\LICENSE"
#endif

[Setup]
AppId={{8F3C2A71-4D6B-4E9A-9C1E-2B7D5A0F3E64}
AppName=Polpad
AppVersion={#Versao}
AppVerName=Polpad {#Versao}
AppPublisher=Polpad
AppCopyright=Copyright (C) 2026 Gabriel Rezende Pires e Artur Morais Brasileiro
AppPublisherURL=https://github.com/gabriel-re-pires/polpad
AppSupportURL=https://github.com/gabriel-re-pires/polpad
VersionInfoVersion={#Versao}
DefaultDirName={localappdata}\Programs\Polpad
PrivilegesRequired=lowest
DisableWelcomePage=no
DisableDirPage=yes
DisableProgramGroupPage=yes
LicenseFile={#Licenca}
OutputBaseFilename=Polpad-Setup
SetupIconFile={#Icone}
#ifdef ImagemGrande
WizardImageFile={#ImagemGrande}
#endif
#ifdef ImagemPequena
WizardSmallImageFile={#ImagemPequena}
#endif
UninstallDisplayIcon={app}\Polpad.exe
UninstallDisplayName=Polpad
WizardStyle=modern
ShowLanguageDialog=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Fecha o Polpad aberto antes de trocar os arquivos; quem reabre é o [Run].
CloseApplications=yes
RestartApplications=no
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Messages]
WelcomeLabel1=Bem-vindo ao Polpad {#Versao}
WelcomeLabel2=Este assistente vai instalar o Polpad no seu computador.%n%nO Polpad configura as teclas, os perfis e o display do seu macropad.%n%nSe o Polpad estiver aberto, ele será fechado durante a instalação.
WizardSelectTasks=Opções
SelectTasksDesc=Escolha como o Polpad vai funcionar.
SelectTasksLabel2=Você pode mudar estas opções depois, nas Configurações do Polpad.
FinishedHeadingLabel=Polpad instalado
FinishedLabel=O Polpad foi instalado no seu computador.%n%nConecte o macropad pela USB para começar.
ClickFinish=Clique em Concluir para sair.

[Tasks]
Name: "iniciarcomwindows"; Description: "Iniciar o Polpad junto com o Windows (na bandeja)"
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; Flags: unchecked
Name: "avisarversao"; Description: "Avisar quando houver nova versão do Polpad"

[InstallDelete]
; Arquivos de outra versão não podem sobrar (atualizar e voltar de versão).
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Origem}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef ImagemDesinstalar
; Painel da tela de desinstalar: o desinstalador não tem as imagens do assistente.
Source: "{#ImagemDesinstalar}"; DestDir: "{app}"; DestName: "desinstalar.bmp"; Flags: ignoreversion
#endif

[Icons]
Name: "{autoprograms}\Polpad"; Filename: "{app}\Polpad.exe"
Name: "{autodesktop}\Polpad"; Filename: "{app}\Polpad.exe"; Tasks: desktopicon

[Registry]
; Iniciar com o Windows: o mesmo valor que o Polpad grava pelas
; Configurações. Só na instalação pelo assistente (não nas atualizações).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Polpad"; ValueData: """{app}\Polpad.exe"" --minimized"; Tasks: iniciarcomwindows; Check: not WizardSilent; Flags: uninsdeletevalue
; Se a pessoa ligou depois, pelas Configurações, a desinstalação também remove.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Polpad"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Polpad.exe"; Description: "Abrir o Polpad agora"; Flags: nowait postinstall skipifsilent
Filename: "https://github.com/gabriel-re-pires/polpad/releases/tag/v{#Versao}"; Description: "Ver as novidades da versão"; Flags: shellexec nowait postinstall skipifsilent unchecked
Filename: "{app}\Polpad.exe"; Flags: nowait; Check: EhAtualizacao

[Code]
function TemParametro(const Nome: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Nome) = 0 then
      Result := True;
end;

function EhAtualizacao: Boolean;
begin
  Result := TemParametro('/ATUALIZACAO');
end;

function SimNao(const Valor: Boolean): String;
begin
  if Valor then
    Result := 'true'
  else
    Result := 'false';
end;

{ Escolhas do assistente: o Polpad as aplica às Configurações ao abrir. }
procedure CurStepChanged(CurStep: TSetupStep);
var
  Pasta: String;
begin
  if (CurStep = ssPostInstall) and not WizardSilent then
  begin
    Pasta := ExpandConstant('{userappdata}\Polpad');
    ForceDirectories(Pasta);
    SaveStringToFile(Pasta + '\opcoes-do-instalador.json',
      '{"start_with_windows": ' + SimNao(WizardIsTaskSelected('iniciarcomwindows')) +
      ', "update_notify": ' + SimNao(WizardIsTaskSelected('avisarversao')) + '}',
      False);
  end;
end;

{ Tela de desinstalação. O Inno Setup sempre pergunta "Tem certeza?"; para
  não confirmar duas vezes, esta tela reabre o desinstalador em modo
  semiautomático (/SILENT: só o progresso), levando a escolha dos perfis. }
function InitializeUninstall: Boolean;
var
  Form: TSetupForm;
  Painel: TBitmapImage;
  Titulo, Texto, Dica: TNewStaticText;
  Caixa: TNewCheckBox;
  Remover, Cancelar: TNewButton;
  Imagem, Argumentos: String;
  Codigo, Esquerda, Largura: Integer;
begin
  Result := True;
  if UninstallSilent then
    Exit;
  Result := False;
  { Tamanho fixo: o painel do polvo à esquerda, o texto à direita. }
  Form := CreateCustomForm(ScaleX(560), ScaleY(260), False, False);
  try
    Form.Caption := 'Desinstalar o Polpad';
    Form.BorderStyle := bsDialog;
    Form.BorderIcons := [biSystemMenu];
    Form.Position := poScreenCenter;
    { Branco, como o conteúdo das páginas do instalador. }
    Form.Color := clWindow;

    Esquerda := 0;
    Imagem := ExpandConstant('{app}\desinstalar.bmp');
    if FileExists(Imagem) then
    begin
      Painel := TBitmapImage.Create(Form);
      Painel.Parent := Form;
      Painel.Left := 0;
      Painel.Top := 0;
      Painel.Width := ScaleX(150);
      Painel.Height := Form.ClientHeight;
      Painel.Stretch := True;
      Painel.Bitmap.LoadFromFile(Imagem);
      Esquerda := Painel.Width;
    end;
    Esquerda := Esquerda + ScaleX(24);
    Largura := Form.ClientWidth - Esquerda - ScaleX(24);

    Titulo := TNewStaticText.Create(Form);
    Titulo.Parent := Form;
    Titulo.Left := Esquerda;
    Titulo.Top := ScaleY(22);
    Titulo.Font.Style := [fsBold];
    Titulo.Font.Size := 12;
    Titulo.Caption := 'Desinstalar o Polpad';

    Texto := TNewStaticText.Create(Form);
    Texto.Parent := Form;
    Texto.Left := Esquerda;
    Texto.Top := ScaleY(56);
    Texto.Width := Largura;
    Texto.AutoSize := False;
    Texto.WordWrap := True;
    Texto.Height := ScaleY(48);
    Texto.Caption := 'O Polpad será removido deste computador: saem o programa, ' +
      'os atalhos e a inicialização com o Windows. Se ele estiver aberto, ' +
      'será fechado.';

    Caixa := TNewCheckBox.Create(Form);
    Caixa.Parent := Form;
    Caixa.Left := Esquerda;
    Caixa.Top := ScaleY(116);
    Caixa.Width := Largura;
    Caixa.Caption := 'Remover também meus perfis, ícones e configurações';
    Caixa.Checked := False;

    Dica := TNewStaticText.Create(Form);
    Dica.Parent := Form;
    Dica.Left := Esquerda + ScaleX(18);
    Dica.Top := ScaleY(138);
    Dica.Width := Largura - ScaleX(18);
    Dica.AutoSize := False;
    Dica.WordWrap := True;
    Dica.Height := ScaleY(32);
    Dica.Font.Color := clGrayText;
    Dica.Caption := 'Deixe desmarcado para encontrar seus perfis se instalar o Polpad de novo.';

    Cancelar := TNewButton.Create(Form);
    Cancelar.Parent := Form;
    Cancelar.Width := ScaleX(90);
    Cancelar.Height := ScaleY(28);
    Cancelar.Left := Form.ClientWidth - ScaleX(24) - Cancelar.Width;
    Cancelar.Top := Form.ClientHeight - ScaleY(22) - Cancelar.Height;
    Cancelar.Caption := 'Cancelar';
    Cancelar.ModalResult := mrCancel;
    Cancelar.Cancel := True;

    Remover := TNewButton.Create(Form);
    Remover.Parent := Form;
    Remover.Width := ScaleX(110);
    Remover.Height := ScaleY(28);
    Remover.Left := Cancelar.Left - ScaleX(10) - Remover.Width;
    Remover.Top := Cancelar.Top;
    Remover.Caption := 'Desinstalar';
    Remover.ModalResult := mrOk;
    Remover.Default := True;

    Form.ActiveControl := Cancelar;
    if Form.ShowModal = mrOk then
    begin
      Argumentos := '/SILENT /DOFORMULARIO';
      if Caixa.Checked then
        Argumentos := Argumentos + ' /PERFIS';
      Exec(ExpandConstant('{uninstallexe}'), Argumentos, '', SW_SHOW, ewNoWait, Codigo);
    end;
  finally
    Form.Free;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Codigo: Integer;
begin
  if CurUninstallStep = usUninstall then
    { Arquivos abertos não seriam removidos. }
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Polpad.exe', '', SW_HIDE,
      ewWaitUntilTerminated, Codigo);
  if (CurUninstallStep = usPostUninstall) and TemParametro('/PERFIS') then
    DelTree(ExpandConstant('{userappdata}\Polpad'), True, True, True);
  if (CurUninstallStep = usDone) and TemParametro('/DOFORMULARIO') then
    MsgBox('O Polpad foi removido do seu computador.', mbInformation, MB_OK);
end;
