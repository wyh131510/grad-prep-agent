; ============================================================
; 毕业设计前期准备 Agent —— Inno Setup 安装脚本
; 前置：已运行 PyInstaller 生成 dist\GradPrepAgent\GradPrepAgent.exe
; 编译：iscc.exe installer\grad_prep_agent.iss  （或运行 打包.bat）
; ============================================================
#define MyAppName "毕业设计前期准备 Agent"
#define MyAppNameEn "GradPrepAgent"
#define MyAppVersion "1.0.0"
#define MyAppExeName "GradPrepAgent.exe"

[Setup]
AppId={{5A9F3D2B-8E1C-4F6A-9B7D-1C2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=GradPrepAgent
DefaultDirName={localappdata}\Programs\GradPrepAgent
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; 每用户安装：无需管理员权限，不写 Program Files（应用数据存 %LOCALAPPDATA%\GradPrepAgent）
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=GradPrepAgent_Setup
SetupIconFile=..\assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 安装前结束已运行实例
CloseApplications=yes

[Languages]
; 中文语言文件需单独下载（Inno Setup 6.5+ 才内置）：
; 打包.bat 会自动从 jsDelivr 下载到本目录；不存在则回退英文界面（不报错）
#ifexist "ChineseSimplified.isl"
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"

[Files]
Source: "..\dist\GradPrepAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; 开始菜单显式卸载入口
Name: "{autoprograms}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// 卸载时询问是否同时删除用户数据（文献库/设置/下载文件），避免留下残余；
// 静默卸载（如升级时旧版自动卸载）不弹窗、不删数据。
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if (CurUninstallStep = usUninstall) and (not UninstallSilent()) then
  begin
    DataDir := ExpandConstant('{localappdata}\GradPrepAgent');
    if DirExists(DataDir) then
    begin
      if MsgBox('是否同时删除用户数据（文献库、设置与下载的文献）？' + #13#10 + #13#10 +
                '数据目录：' + DataDir + #13#10#13#10 +
                '选「是」彻底清除；选「否」保留数据（重装后继续使用）。',
                mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
