@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "KEYSTORE=play_store_upload\brechorisee_upload.jks"
set "KEY_ALIAS=brechorisee_upload"
if not exist "%KEYSTORE%" (
  echo Chave nao encontrada: %KEYSTORE%
  echo Rode GERAR_AAB_GOOGLE_PLAY_WINDOWS.bat primeiro.
  pause
  exit /b 1
)
set /p STORE_PASS=Digite a senha da chave: 
keytool -list -v -keystore "%KEYSTORE%" -alias "%KEY_ALIAS%" -storepass "%STORE_PASS%" | findstr /C:"SHA256"
echo.
echo Use esse SHA-256 no Render:
echo BRECHORISEE_ANDROID_SHA256_FINGERPRINTS=COLE_AQUI
pause
