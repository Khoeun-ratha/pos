@echo off
rem Frontend 2: Flutter mobile app on a connected phone or a running emulator (start the server first)
cd /d "%~dp0mobile"
call flutter pub get
call flutter devices
call flutter run
