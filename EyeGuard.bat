@echo off
rem Double-click to start EyeGuard. A small window lets you pick or make a profile.
title EyeGuard
cd /d "%~dp0"

set "PYTHON=py"
where py >nul 2>nul
if errorlevel 1 set "PYTHON=python"
call %PYTHON% --version >nul 2>nul
if errorlevel 1 goto no_python

call %PYTHON% eyeguard.py
if errorlevel 1 goto failed
exit /b 0

:no_python
echo.
echo  Python was not found on this computer.
echo.
echo  1. Install Python 3.10 or newer from https://www.python.org/downloads/
echo     and tick "Add python.exe to PATH" in the installer.
echo  2. Open a terminal in this folder and run:
echo         py -m pip install -r requirements-desktop.txt
echo  3. Double-click this file again.
echo.
pause
exit /b 1

:failed
echo.
echo  EyeGuard stopped with an error (see the message above).
echo  If it says a module is missing, open a terminal in this folder and run:
echo         py -m pip install -r requirements-desktop.txt
echo.
pause
exit /b 1
