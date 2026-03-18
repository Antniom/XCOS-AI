@echo off
setlocal
where makensis >nul 2>&1
if %errorlevel%==0 ( set MAKENSIS=makensis & goto :build )
echo ERROR: makensis.exe not found.
pause & exit /b 1
:build
echo Building XcosAICompiler_Setup.exe...
%MAKENSIS% /V3 XcosAICompiler_Setup.nsi
pause
