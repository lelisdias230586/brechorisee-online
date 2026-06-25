@echo off
setlocal
echo.
echo Este arquivo libera a porta 8000 no Firewall do Windows para o app Android acessar o sistema local.
echo Pode ser necessario clicar com o botao direito e escolher "Executar como administrador".
echo.
net session >nul 2>nul
if not %errorlevel%==0 (
  echo ERRO: execute este arquivo como Administrador.
  pause
  exit /b 1
)
netsh advfirewall firewall add rule name="BRECHORISEE sistema local porta 8000" dir=in action=allow protocol=TCP localport=8000
echo.
echo Pronto. A porta 8000 foi liberada.
pause
