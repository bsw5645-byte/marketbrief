@echo off
setlocal
chcp 65001 >nul
set "BONG_PROBE_DIR=%~dp0"
set "BONG_PROBE_PY=%~dp0runtime\python.exe"
title BONG Caption Test
echo BONG - Oct 7 Korean caption test
echo No login, no GPT charge, no Telegram delivery.
echo.
if exist "%BONG_PROBE_PY%" goto packages
echo This test needs a dedicated Python installation in this folder.
echo Official source: https://www.python.org/
choice /C YN /N /M "Download and install Python here? [Y/N] "
if errorlevel 2 goto cancelled
powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $dest=Join-Path $env:BONG_PROBE_DIR 'python-setup.exe'; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.exe' -OutFile $dest; $sig=Get-AuthenticodeSignature -FilePath $dest; if($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation'){throw 'Official Python signature could not be verified. Installation stopped.'}"
if errorlevel 1 goto failed
start "" /wait "%~dp0python-setup.exe" /passive InstallAllUsers=0 TargetDir="%~dp0runtime" PrependPath=0 Include_launcher=0 Include_test=0 Shortcuts=0 AssociateFiles=0 Include_pip=1
if not exist "%BONG_PROBE_PY%" goto failed
:packages
echo Preparing caption test packages...
"%BONG_PROBE_PY%" -m pip --disable-pip-version-check install --no-warn-script-location "youtube-transcript-api==1.2.4" "requests==2.34.2"
if errorlevel 1 goto failed
echo.
"%BONG_PROBE_PY%" -X utf8 "%~dp0caption_probe.py"
set "BONG_PROBE_EXIT=%ERRORLEVEL%"
if exist "%~dp0BONG-test-result.txt" start "" notepad.exe "%~dp0BONG-test-result.txt"
echo.
echo Send the PASS / BLOCKED / ERROR result back to the chat.
pause
exit /b %BONG_PROBE_EXIT%
:cancelled
echo Installation cancelled. No test was run.
pause
exit /b 1
:failed
echo Setup failed. No automatic retry or security bypass will be attempted.
echo Copy the error shown above back to the chat.
pause
exit /b 1
