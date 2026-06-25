from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"
APP_NAME = "brechorisee"
START_URL = "http://127.0.0.1:8000"


def run(cmd: list[str], **kwargs) -> None:
    print(">", " ".join(str(c) for c in cmd))
    subprocess.check_call(cmd, cwd=BASE_DIR, **kwargs)


def python_in_venv() -> Path:
    if platform.system().lower() == "windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def create_venv_and_install() -> None:
    if not VENV_DIR.exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    py = python_in_venv()
    run([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(py), "-m", "pip", "install", "-r", "requirements.txt"])


def create_windows_shortcut() -> None:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    target = BASE_DIR / "INICIAR_BRECHORISEE.bat"
    icon = BASE_DIR / "static" / "logo.ico"
    link = desktop / "brechorisee.lnk"
    ps = f"""
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut('{str(link)}')
$Shortcut.TargetPath = '{str(target)}'
$Shortcut.WorkingDirectory = '{str(BASE_DIR)}'
$Shortcut.IconLocation = '{str(icon)}'
$Shortcut.Description = 'Abrir sistema brechorisee'
$Shortcut.Save()
"""
    subprocess.check_call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps])
    print(f"Atalho criado em: {link}")


def create_linux_shortcut() -> None:
    desktop = Path.home() / "Desktop"
    applications = Path.home() / ".local" / "share" / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    icon = BASE_DIR / "static" / "logo.ico"
    starter = BASE_DIR / "iniciar_linux_mac.sh"
    content = f"""[Desktop Entry]
Type=Application
Name=brechorisee
Comment=Abrir sistema brechorisee
Exec=bash "{starter}"
Icon={icon}
Terminal=true
Categories=Office;Utility;
"""
    for folder in [desktop, applications]:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "brechorisee.desktop"
            path.write_text(content, encoding="utf-8")
            path.chmod(0o755)
            print(f"Atalho criado em: {path}")
        except Exception as exc:
            print(f"Não consegui criar atalho em {folder}: {exc}")


def create_macos_shortcut() -> None:
    desktop = Path.home() / "Desktop"
    command = desktop / "brechorisee.command"
    content = f"""#!/bin/bash
cd "{BASE_DIR}"
bash "./iniciar_linux_mac.sh"
"""
    command.write_text(content, encoding="utf-8")
    command.chmod(0o755)
    print(f"Atalho criado em: {command}")


def create_shortcut() -> None:
    system = platform.system().lower()
    try:
        if system == "windows":
            create_windows_shortcut()
        elif system == "darwin":
            create_macos_shortcut()
        else:
            create_linux_shortcut()
    except Exception as exc:
        print(f"Instalado, mas não consegui criar o atalho automaticamente: {exc}")


def main() -> None:
    print("Instalando brechorisee...")
    create_venv_and_install()
    create_shortcut()
    print("\nPronto! Para abrir, use o atalho criado ou execute:")
    if platform.system().lower() == "windows":
        print("  INICIAR_BRECHORISEE.bat")
    else:
        print("  ./iniciar_linux_mac.sh")
    print(f"Endereço no computador: {START_URL}")
    print("Para usar no celular, abra o sistema e entre em: http://127.0.0.1:8000/celular")


if __name__ == "__main__":
    main()
