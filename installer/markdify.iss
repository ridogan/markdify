; Markdify — Windows kurulum sihirbazı (Inno Setup 6)
;
; Derlemek için:  installer\build.ps1
;
; Üretilen Markdify-Setup.exe kullanıcıya tek dosya olarak verilir. Sihirbaz
; uygulama dosyalarını kopyalar, ardından Python'u ve Python paketlerini kurar.
; Paketler (docling ~2 GB) kuruluma GÖMÜLMEZ: gömülü hâli 2,5 GB'lık bir
; yükleyici demek olurdu ve GitHub'ın 100 MB dosya sınırını da aşardı.

#define AppName "Markdify"
#define AppVersion "1.0.0"
#define AppPublisher "ridogan"
#define AppURL "https://github.com/ridogan/markdify"
#define AppExe "app.py"

[Setup]
AppId={{8F3A6C21-4B7E-4E5A-9D42-2C6E1B0A7F53}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

; ASCII güvenli varsayılan: docling-parse'ın C++ katmanı Türkçe karakterli
; yollarda PDF kaynaklarını açamıyor (bkz. README "Bilinen kısıt").
DefaultDirName=C:\Markdify
DirExistsWarning=no
DefaultGroupName={#AppName}
AllowNoIcons=yes

LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=Markdify-Setup-{#AppVersion}
SetupIconFile=..\assets\markdify.ico
UninstallDisplayIcon={app}\assets\markdify.ico
UninstallDisplayName={#AppName} {#AppVersion}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
tr.CreateDesktopIcon=Masaüstü kısayolu oluştur
tr.InstallingPython=Python kuruluyor (yaklaşık 30 MB)…
tr.CreatingVenv=Sanal ortam oluşturuluyor…
tr.InstallingPackages=Python paketleri kuruluyor (yaklaşık 2 GB) — bu adım internet hızınıza göre 10-30 dakika sürebilir…
tr.InstallingLibreOffice=LibreOffice kuruluyor (Word çizimleri için, isteğe bağlı)…
tr.NoPython=Python bulunamadı ve otomatik kurulum başarısız oldu.%n%nLütfen https://www.python.org/downloads/ adresinden Python 3.12 kurup kurulumu yeniden çalıştırın.
tr.PackagesFailed=Python paketleri kurulamadı.%n%nİnternet bağlantınızı kontrol edip kurulumu yeniden çalıştırın. Ayrıntılar:%n%1
tr.NonAsciiPath=Seçtiğiniz klasör yolu Türkçe veya ASCII dışı karakter içeriyor:%n%n%1%n%nBu yolda yüksek kaliteli PDF ayrıştırıcı çalışmaz; uygulama otomatik olarak yedek ayrıştırıcıya düşer (dönüşüm çalışır, tablo düzeni bir miktar bozulabilir).%n%nÖnerilen: C:\Markdify%n%nYine de bu klasöre kurulsun mu?
en.CreateDesktopIcon=Create a desktop shortcut
en.InstallingPython=Installing Python (about 30 MB)…
en.CreatingVenv=Creating virtual environment…
en.InstallingPackages=Installing Python packages (about 2 GB) — this may take 10-30 minutes…
en.InstallingLibreOffice=Installing LibreOffice (optional, for Word drawings)…
en.NoPython=Python was not found and could not be installed automatically.%n%nPlease install Python 3.12 from https://www.python.org/downloads/ and run setup again.
en.PackagesFailed=Failed to install Python packages.%n%nCheck your internet connection and run setup again. Details:%n%1
en.NonAsciiPath=The selected folder contains non-ASCII characters:%n%n%1%n%nThe high-quality PDF parser cannot run from this path; the app will fall back automatically.%n%nRecommended: C:\Markdify%n%nInstall here anyway?

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\app.py";             DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt";   DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE";            DestDir: "{app}"; Flags: ignoreversion
Source: "..\markdify\*.py";      DestDir: "{app}\markdify"; Flags: ignoreversion
Source: "..\assets\*";           DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";          Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\{#AppExe}"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\markdify.ico"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";   Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\{#AppExe}"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\markdify.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\{#AppExe}"""; WorkingDir: "{app}"; \
  Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Kurulumdan sonra üretilenler (sanal ortam, günlükler, ayarlar)
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\markdify\__pycache__"
Type: files;          Name: "{app}\settings.json"

[Code]
var
  PythonExe: String;

function IsAsciiPath(const Path: String): Boolean;
var
  I: Integer;
begin
  Result := True;
  for I := 1 to Length(Path) do
    if Ord(Path[I]) > 127 then
    begin
      Result := False;
      Exit;
    end;
end;

{ Kullanıcı ASCII dışı bir klasör seçerse uyar — sessizce bozuk kurulum olmasın. }
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
    if not IsAsciiPath(WizardDirValue) then
      Result := MsgBox(FmtMessage(CustomMessage('NonAsciiPath'), [WizardDirValue]),
                       mbConfirmation, MB_YESNO) = IDYES;
end;

{ Python'u KAYIT DEFTERİNDEN bulur.
  PATH'e güvenilemez: Windows, PATH'in başına Microsoft Store yönlendirme
  kısayolları koyar (WindowsApps\python.exe). Bunlar gerçek Python değildir,
  çalıştırıldığında "Python bulunamadı" yazıp Store'u açarlar. Ayrıca `py`
  başlatıcısı her kurulumda bulunmaz. Kayıt defterindeki PythonCore girdisi
  Python kurulumunun resmî ve güvenilir kaydıdır. }
function PythonFromRegistry(): String;
var
  Versions: array[0..5] of String;
  Roots: array[0..3] of Integer;
  I, J: Integer;
  Found: String;
begin
  Result := '';
  Versions[0] := '3.13'; Versions[1] := '3.12'; Versions[2] := '3.11';
  Versions[3] := '3.14'; Versions[4] := '3.10'; Versions[5] := '3.15';
  Roots[0] := HKCU; Roots[1] := HKLM; Roots[2] := HKLM64; Roots[3] := HKLM32;

  for I := 0 to 5 do
    for J := 0 to 3 do
      if RegQueryStringValue(Roots[J],
           'SOFTWARE\Python\PythonCore\' + Versions[I] + '\InstallPath',
           'ExecutablePath', Found) then
        if (Found <> '') and FileExists(Found) then
        begin
          Result := Found;
          Exit;
        end;
end;

function PythonFromKnownPaths(): String;
var
  Bases: array[0..3] of String;
  Versions: array[0..4] of String;
  I, J: Integer;
  Candidate: String;
begin
  Result := '';
  Bases[0] := ExpandConstant('{localappdata}\Programs\Python\Python');
  Bases[1] := 'C:\Python';
  Bases[2] := ExpandConstant('{commonpf}\Python');
  Bases[3] := ExpandConstant('{userpf}\Python\Python');
  Versions[0] := '313'; Versions[1] := '312'; Versions[2] := '311';
  Versions[3] := '314'; Versions[4] := '310';

  for I := 0 to 4 do
    for J := 0 to 3 do
    begin
      Candidate := Bases[J] + Versions[I] + '\python.exe';
      if FileExists(Candidate) then
      begin
        Result := Candidate;
        Exit;
      end;
    end;
end;

{ Bulunan yorumlayıcının gerçekten çalıştığını doğrular (Store kısayolu değil). }
function PythonWorks(const Exe: String): Boolean;
var
  ResultCode: Integer;
begin
  Result := (Exe <> '') and FileExists(Exe) and (Pos('WindowsApps', Exe) = 0)
            and Exec(Exe, '-c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"',
                     '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
            and (ResultCode = 0);
end;

function FindPython(): String;
var
  Candidate: String;
begin
  Candidate := PythonFromRegistry();
  if PythonWorks(Candidate) then
  begin
    Result := Candidate;
    Exit;
  end;

  Candidate := PythonFromKnownPaths();
  if PythonWorks(Candidate) then
  begin
    Result := Candidate;
    Exit;
  end;

  Result := '';
end;

function InstallPython(): Boolean;
var
  ResultCode: Integer;
begin
  WizardForm.StatusLabel.Caption := CustomMessage('InstallingPython');
  Result := Exec(ExpandConstant('{cmd}'),
    '/c winget install -e --id Python.Python.3.12 --accept-package-agreements ' +
    '--accept-source-agreements --disable-interactivity',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function RunPipSetup(): Boolean;
var
  ResultCode: Integer;
  AppDir, VenvPy, LogFile: String;
  LogText: AnsiString;
begin
  AppDir := ExpandConstant('{app}');
  VenvPy := AppDir + '\.venv\Scripts\python.exe';
  LogFile := ExpandConstant('{tmp}\pipsetup.log');

  WizardForm.StatusLabel.Caption := CustomMessage('CreatingVenv');
  if not Exec(PythonExe, '-m venv "' + AppDir + '\.venv"', AppDir,
              SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
  begin
    Result := False;
    Exit;
  end;

  WizardForm.StatusLabel.Caption := CustomMessage('InstallingPackages');
  Exec(VenvPy, '-m pip install --upgrade pip --quiet', AppDir,
       SW_HIDE, ewWaitUntilTerminated, ResultCode);

  Result := Exec(ExpandConstant('{cmd}'),
    '/c ""' + VenvPy + '" -m pip install -r "' + AppDir + '\requirements.txt" > "' +
    LogFile + '" 2>&1"', AppDir, SW_HIDE, ewWaitUntilTerminated, ResultCode)
    and (ResultCode = 0);

  if not Result then
  begin
    LogText := '';
    LoadStringFromFile(LogFile, LogText);
    { Kullanıcıya son satırları göster; tamamı çok uzun olur }
    if Length(LogText) > 600 then
      LogText := Copy(LogText, Length(LogText) - 600, 600);
    MsgBox(FmtMessage(CustomMessage('PackagesFailed'), [String(LogText)]), mbError, MB_OK);
  end;
end;

procedure InstallLibreOffice();
var
  ResultCode: Integer;
begin
  if FileExists('C:\Program Files\LibreOffice\program\soffice.exe') or
     FileExists('C:\Program Files (x86)\LibreOffice\program\soffice.exe') then
    Exit;

  WizardForm.StatusLabel.Caption := CustomMessage('InstallingLibreOffice');
  { Başarısız olması kurulumu bozmaz: LibreOffice isteğe bağlı bileşendir }
  Exec(ExpandConstant('{cmd}'),
    '/c winget install -e --id TheDocumentFoundation.LibreOffice ' +
    '--accept-package-agreements --accept-source-agreements --silent --disable-interactivity',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep <> ssPostInstall then
    Exit;

  PythonExe := FindPython();
  if PythonExe = '' then
  begin
    if InstallPython() then
      PythonExe := FindPython();
    if PythonExe = '' then
    begin
      MsgBox(CustomMessage('NoPython'), mbError, MB_OK);
      Exit;
    end;
  end;

  if RunPipSetup() then
    InstallLibreOffice();
end;
