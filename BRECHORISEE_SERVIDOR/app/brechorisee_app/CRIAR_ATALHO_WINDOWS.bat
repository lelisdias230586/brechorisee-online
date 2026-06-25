@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$WScriptShell = New-Object -ComObject WScript.Shell; $Shortcut = $WScriptShell.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\brechorisee.lnk'); $Shortcut.TargetPath = '%~dp0INICIAR_BRECHORISEE.bat'; $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.IconLocation = '%~dp0static\logo.ico'; $Shortcut.Description = 'Abrir sistema brechorisee'; $Shortcut.Save()"
echo Atalho criado na Area de Trabalho.
pause
