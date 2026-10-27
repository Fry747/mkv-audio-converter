@echo off
setlocal
set "PYTHONUTF8=1"
pushd "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m mkv_audio_converter %*
) else (
  py -3 -m mkv_audio_converter %*
)
set "converter_exit=%errorlevel%"
popd
if not "%converter_exit%"=="0" pause
exit /b %converter_exit%
