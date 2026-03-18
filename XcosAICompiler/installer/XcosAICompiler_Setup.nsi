  !define PRODUCT_NAME      "XcosAICompiler"
  !define PRODUCT_VERSION   "1.0-1"
  !define PRODUCT_PUBLISHER "XcosAICompiler Project"
  !define PRODUCT_URL       "https://github.com/yourusername/XcosAICompiler"
  !define SCILAB_TARGET_VER "2026.0.1"
  !define REGKEY_SCILAB     "SOFTWARE\Scilab\Scilab ${SCILAB_TARGET_VER}"
  !define REGKEY_UNINST     "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

  Unicode True
  SetCompressor /SOLID lzma

  !include "MUI2.nsh"
  !include "LogicLib.nsh"
  !include "FileFunc.nsh"
  !include "nsDialogs.nsh"

  Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
  OutFile "..\XcosAICompiler_Setup_${PRODUCT_VERSION}.exe"
  InstallDir ""
  InstallDirRegKey HKLM "${REGKEY_SCILAB}" "SciLab_Directory"
  RequestExecutionLevel admin

  !define MUI_ABORTWARNING
  !define MUI_WELCOMEPAGE_TITLE "Install XcosAICompiler for Scilab ${SCILAB_TARGET_VER}"
  !define MUI_WELCOMEPAGE_TEXT  "This installer deploys XcosAICompiler into your \
    Scilab installation.$\r$\n$\r$\nScilab ${SCILAB_TARGET_VER} must be installed \
    before proceeding.$\r$\n$\r$\nPython 3.8 or later must also be installed and \
    available on the system PATH."

  !insertmacro MUI_PAGE_WELCOME
  !insertmacro MUI_PAGE_LICENSE "..\LICENSE.txt"
  Page custom ScopePage_Create ScopePage_Leave
  !insertmacro MUI_PAGE_DIRECTORY
  !insertmacro MUI_PAGE_INSTFILES
  !insertmacro MUI_PAGE_FINISH

  !insertmacro MUI_UNPAGE_WELCOME
  !insertmacro MUI_UNPAGE_CONFIRM
  !insertmacro MUI_UNPAGE_INSTFILES
  !insertmacro MUI_UNPAGE_FINISH

  !insertmacro MUI_LANGUAGE "English"

  Var InstallMode
  Var ScilabExePath
  Var RadioAll
  Var RadioUser

  Function ScopePage_Create
    !insertmacro MUI_HEADER_TEXT "Installation Scope" \
      "Choose whether to install for all users or your account only."
    nsDialogs::Create 1018
    Pop $0
    ${NSD_CreateLabel}       0  0 100% 20u "Select installation scope:"
    ${NSD_CreateRadioButton} 10 28 100% 14u \
      "All Users — install to Scilab\contrib (requires admin)"
    Pop $RadioAll
    ${NSD_CreateRadioButton} 10 50 100% 14u \
      "Current User Only — install to %APPDATA%\Scilab\atoms"
    Pop $RadioUser
    ${NSD_SetState} $RadioAll ${BST_CHECKED}
    StrCpy $InstallMode "allusers"
    nsDialogs::Show
  FunctionEnd

  Function ScopePage_Leave
    ${NSD_GetState} $RadioAll $0
    ${If} $0 == ${BST_CHECKED}
      StrCpy $InstallMode "allusers"
    ${Else}
      StrCpy $InstallMode "user"
    ${EndIf}
  FunctionEnd

  Function .onInit
    ReadRegStr $R0 HKLM "${REGKEY_SCILAB}" "SciLab_Directory"
    ${If} $R0 == ""
      ReadRegStr $R0 HKCU "${REGKEY_SCILAB}" "SciLab_Directory"
    ${EndIf}
    ${If} $R0 == ""
      MessageBox MB_ICONSTOP|MB_OK "Scilab ${SCILAB_TARGET_VER} was not found."
      Abort
    ${EndIf}
    StrCpy $INSTDIR "$R0"
    ${If} ${FileExists} "$R0\bin\scilab.exe"
      StrCpy $ScilabExePath "$R0\bin\scilab.exe"
    ${Else}
      Abort
    ${EndIf}
  FunctionEnd

  Section "XcosAICompiler" SecMain
    SectionIn RO
    ${If} $InstallMode == "allusers"
      StrCpy $R1 "$INSTDIR\contrib\XcosAICompiler"
    ${Else}
      StrCpy $R1 "$APPDATA\Scilab\scilab-${SCILAB_TARGET_VER}\atoms\XcosAICompiler"
    ${EndIf}
    SetOutPath "$R1"
    File /oname=DESCRIPTION "..\DESCRIPTION"
    File /oname=CHANGES      "..\CHANGES"
    File /oname=LICENSE.txt  "..\LICENSE.txt"
    File /oname=builder.sce  "..\builder.sce"
    File /oname=loader.sce   "..\loader.sce"
    SetOutPath "$R1\macros"
    File "..\macros\*.sci"
    File "..\macros\buildnames.sce"
    SetOutPath "$R1\src\python"
    File "..\src\python\gemini_xcos_agent.py"
    File "..\src\python\requirements.txt"
    SetOutPath "$R1\etc"
    File "..\etc\module.start"
    File "..\etc\module.end"
    
    SetOutPath "$TEMP\XcosAIInstaller"
    FileOpen $9 "$TEMP\XcosAIInstaller\do_install.sce" w
    FileWrite $9 "MODULE_DIR = '$R1';" + "$\n"
    FileWrite $9 "cd(MODULE_DIR);" + "$\n"
    FileWrite $9 "if isdef('tbx_builder_macros') then" + "$\n"
    FileWrite $9 "  tbx_builder_macros(MODULE_DIR);" + "$\n"
    FileWrite $9 "else" + "$\n"
    FileWrite $9 "  genlib('XcosAICompilerlib', MODULE_DIR + '/macros/', %f, %t);" + "$\n"
    FileWrite $9 "end" + "$\n"
    FileWrite $9 "try; atomsAutoloadAdd('XcosAICompiler', MODULE_DIR); catch; end;" + "$\n"
    FileWrite $9 "exit;" + "$\n"
    FileClose $9
    ExecWait '"$ScilabExePath" -nw -f "$TEMP\XcosAIInstaller\do_install.sce"'
    
    WriteUninstaller "$R1\Uninstall_XcosAICompiler.exe"
    WriteRegStr  HKLM "${REGKEY_UNINST}" "DisplayName"     "${PRODUCT_NAME}"
    WriteRegStr  HKLM "${REGKEY_UNINST}" "UninstallString" '"$R1\Uninstall_XcosAICompiler.exe"'
    RMDir /r "$TEMP\XcosAIInstaller"
  SectionEnd

  Section "Uninstall"
    ReadRegStr $R1 HKLM "${REGKEY_UNINST}" "InstallLocation"
    RMDir /r "$R1"
    DeleteRegKey HKLM "${REGKEY_UNINST}"
  SectionEnd
