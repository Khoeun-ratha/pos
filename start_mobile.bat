@echo off
rem Frontend 2: Flutter mobile app on a connected phone or a running emulator (start the server first)
rem The app starts with this PC's Wi-Fi address as the server, e.g. http://192.168.1.152:8000 (an emulator: 10.0.2.2).
cd /d "%~dp0mobile"
set "PC_IP="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1).IPv4Address.IPAddress"`) do set "PC_IP=%%i"
call flutter pub get
call flutter devices
if defined PC_IP (
  echo Server for the phone: http://%PC_IP%:8000
  call flutter run --dart-define=POS_SERVER=http://%PC_IP%:8000
) else (
  call flutter run
)
