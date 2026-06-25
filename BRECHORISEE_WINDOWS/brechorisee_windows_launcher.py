from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

APP_NAME = "BRECHORISEE"
BASE_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = BASE_DIR / "BRECHORISEE_SERVIDOR" / "app"
DATA_DIR = BASE_DIR / "BRECHORISEE_SERVIDOR" / "dados"
BACKUP_DIR = BASE_DIR / "BRECHORISEE_SERVIDOR" / "backups"
ENV_FILE = SERVER_DIR / ".env"
VENV_DIR = SERVER_DIR / ".venv"
PYTHON_EXE = VENV_DIR / "Scripts" / "python.exe"
PIP_EXE = VENV_DIR / "Scripts" / "pip.exe"
PORT = 8000
LOCAL_URL = f"http://127.0.0.1:{PORT}"

server_process: subprocess.Popen | None = None
auto_backup_running = False


def get_lan_ip() -> str:
    """Detecta o IP do notebook na rede Wi-Fi/LAN."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        host = socket.gethostname()
        for ip in socket.gethostbyname_ex(host)[2]:
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


def urls() -> dict[str, str]:
    ip = get_lan_ip()
    base = f"http://{ip}:{PORT}"
    return {
        "Sistema local": LOCAL_URL,
        "Sistema na rede": base,
        "Admin": base + "/admin",
        "Cliente": base + "/app/cliente",
        "Baixar APK": base + "/download/app-cliente.apk",
        "Página APK": base + "/apk",
    }


def ensure_env() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    (SERVER_DIR / "brechorisee_app" / "static" / "downloads").mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.write_text(
            f"""# BRECHORISEE - ÚNICO ARQUIVO DE CONFIGURAÇÃO
# Edite somente este arquivo quando precisar ajustar banco, Telegram, URL, senha/token ou app Android.

APP_ENV=local
BRECHORISEE_ENV=local
BRECHORISEE_STORE_NAME=BRECHORISEE
PUBLIC_BASE_URL=http://{get_lan_ip()}:{PORT}

# Banco local no notebook/servidor
BRECHORISEE_DB_PATH={str((DATA_DIR / "brechorisee.db").resolve()).replace("\\", "/")}

# Segurança local
BRECHORISEE_SECRET_KEY=troque-esta-chave-local
SECRET_KEY=troque-esta-chave-local
BRECHORISEE_SYNC_TOKEN=troque-token-sync-local
BRECHORISEE_ASSISTANT_TOKEN=troque-token-assistente-local

# Telegram
BRECHORISEE_TELEGRAM_SEND_REAL=0
BRECHORISEE_TELEGRAM_COMMANDS_ENABLED=0
TELEGRAM_BOT_TOKEN=COLOQUE_SEU_TOKEN_TELEGRAM_AQUI
TELEGRAM_ADMIN_CHAT_ID=COLOQUE_SEU_CHAT_ID_AQUI
TELEGRAM_ALLOWED_CHAT_IDS=COLOQUE_SEU_CHAT_ID_AQUI
TELEGRAM_WEBHOOK_SECRET=troque-webhook-local

# Android cliente
BRECHORISEE_ANDROID_SHA256_FINGERPRINTS=COLE_O_SHA256_DO_APP_CLIENTE_AQUI

# Backup GitHub opcional. Para uso local, pode deixar desligado.
BRECHORISEE_GITHUB_DB_BACKUP=0
BRECHORISEE_GITHUB_REPO=
BRECHORISEE_GITHUB_TOKEN=
BRECHORISEE_GITHUB_DB_FILE=brechorisee.db
BRECHORISEE_GITHUB_BRANCH=main
BRECHORISEE_GITHUB_DB_BACKUP_INTERVAL_SECONDS=45
""",
            encoding="utf-8",
        )


def update_public_base_url() -> None:
    ensure_env()
    text = ENV_FILE.read_text(encoding="utf-8", errors="ignore")
    new_url = f"http://{get_lan_ip()}:{PORT}"
    if "PUBLIC_BASE_URL=" in text:
        text = "\n".join(
            (f"PUBLIC_BASE_URL={new_url}" if line.startswith("PUBLIC_BASE_URL=") else line)
            for line in text.splitlines()
        ) + "\n"
    else:
        text += f"\nPUBLIC_BASE_URL={new_url}\n"
    ENV_FILE.write_text(text, encoding="utf-8")


def run_cmd(cmd: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(
        cmd,
        cwd=str(cwd or BASE_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
    )
    return p.stdout


def run_bat(path: Path, log) -> None:
    if not path.exists():
        log(f"Script não encontrado: {path}\n")
        messagebox.showwarning(APP_NAME, f"Script não encontrado:\n{path}")
        return
    log(f"Executando: {path}\n")
    subprocess.Popen(["cmd", "/k", str(path)], cwd=str(path.parent))


def install_dependencies(log) -> None:
    ensure_env()
    if not PYTHON_EXE.exists():
        log("Criando ambiente Python local...\n")
        log(run_cmd([sys.executable, "-m", "venv", str(VENV_DIR)]))
    log("Atualizando pip...\n")
    log(run_cmd([str(PYTHON_EXE), "-m", "pip", "install", "--upgrade", "pip"]))
    log("Instalando dependências da BRECHORISEE...\n")
    req = SERVER_DIR / "requirements.txt"
    if req.exists():
        log(run_cmd([str(PIP_EXE), "install", "-r", str(req)], cwd=SERVER_DIR))
    else:
        log(run_cmd([str(PIP_EXE), "install", "fastapi", "uvicorn", "jinja2", "python-multipart", "python-dotenv", "requests", "httpx", "pillow", "qrcode[pil]"]))
    update_public_base_url()
    log("Instalação concluída.\n")


def make_backup(log, reason: str = "manual") -> Path | None:
    ensure_env()
    db = DATA_DIR / "brechorisee.db"
    if not db.exists() or db.stat().st_size == 0:
        log("Banco ainda não encontrado. Use o sistema primeiro para criar dados.\n")
        return None
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = BACKUP_DIR / f"brechorisee_{ts}_{reason}.db"
    shutil.copy2(db, dest)
    log(f"Backup criado:\n{dest}\n")
    return dest


def restore_backup(log) -> None:
    ensure_env()
    file = filedialog.askopenfilename(
        title="Escolha um backup .db da BRECHORISEE",
        initialdir=str(BACKUP_DIR),
        filetypes=[("Banco SQLite", "*.db"), ("Todos os arquivos", "*.*")],
    )
    if not file:
        return
    if server_process and server_process.poll() is None:
        messagebox.showwarning(APP_NAME, "Pare o servidor antes de restaurar um backup.")
        return
    db = DATA_DIR / "brechorisee.db"
    if db.exists():
        make_backup(log, "antes_restaurar")
    shutil.copy2(file, db)
    log(f"Backup restaurado para:\n{db}\n")
    messagebox.showinfo(APP_NAME, "Backup restaurado. Inicie o servidor novamente.")


def auto_backup_loop(log) -> None:
    global auto_backup_running
    if auto_backup_running:
        return
    auto_backup_running = True
    log("Backup automático ativado: a cada 10 minutos enquanto o painel estiver aberto.\n")
    while auto_backup_running:
        time.sleep(600)
        try:
            if server_process and server_process.poll() is None:
                make_backup(log, "auto")
        except Exception as exc:
            log(f"Falha no backup automático: {exc}\n")


def start_server(log) -> None:
    global server_process
    ensure_env()
    update_public_base_url()
    if server_process and server_process.poll() is None:
        log("Servidor já está rodando.\n")
        return
    if not PYTHON_EXE.exists():
        install_dependencies(log)
    env = os.environ.copy()
    env["BRECHORISEE_DB_PATH"] = str(DATA_DIR / "brechorisee.db")
    env["PUBLIC_BASE_URL"] = f"http://{get_lan_ip()}:{PORT}"
    env.setdefault("APP_ENV", "local")
    env.setdefault("BRECHORISEE_ENV", "local")
    env.setdefault("BRECHORISEE_STORE_NAME", "BRECHORISEE")
    cmd = [str(PYTHON_EXE), "-m", "uvicorn", "brechorisee_app.app:app", "--host", "0.0.0.0", "--port", str(PORT)]
    log(f"Iniciando servidor em {LOCAL_URL} ...\n")
    server_process = subprocess.Popen(
        cmd,
        cwd=str(SERVER_DIR),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def reader():
        assert server_process and server_process.stdout
        for line in server_process.stdout:
            log(line)

    threading.Thread(target=reader, daemon=True).start()
    threading.Thread(target=auto_backup_loop, args=(log,), daemon=True).start()
    time.sleep(2)
    show_links_text(log)
    webbrowser.open(LOCAL_URL)


def stop_server(log) -> None:
    global server_process
    if server_process and server_process.poll() is None:
        log("Criando backup antes de parar...\n")
        make_backup(log, "ao_parar")
        log("Parando servidor...\n")
        server_process.terminate()
        try:
            server_process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            server_process.kill()
        log("Servidor parado.\n")
    else:
        log("Servidor não está rodando.\n")


def publish_client_apk(log) -> None:
    candidates = [
        BASE_DIR / "BRECHORISEE_CLIENTE" / "android" / "BRECHORISEE_CLIENTE_RELEASE.apk",
        BASE_DIR / "BRECHORISEE_CLIENTE" / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk",
        BASE_DIR / "dist_brechorisee" / "BRECHORISEE_CLIENTE_SITE.apk",
        BASE_DIR / "BRECHORISEE_CLIENTE_SITE.apk",
    ]
    dest_dir = SERVER_DIR / "brechorisee_app" / "static" / "downloads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "BRECHORISEE_CLIENTE.apk"

    source = next((item for item in candidates if item.exists() and item.is_file() and item.stat().st_size > 0), None)
    if source is None:
        log("APK cliente não encontrado. Compile o app cliente primeiro ou copie o APK manualmente.\n")
        log(f"Destino esperado: {dest}\n")
        messagebox.showwarning(APP_NAME, "APK cliente não encontrado.")
        return

    shutil.copy2(source, dest)
    log(f"APK cliente publicado no servidor:\n{dest}\n")
    show_links_text(log)
    messagebox.showinfo(APP_NAME, "APK cliente publicado no servidor local.")


def show_links_text(log) -> None:
    u = urls()
    text = "\nLINKS DA BRECHORISEE NA SUA REDE:\n"
    for name, link in u.items():
        text += f"- {name}: {link}\n"
    text += "\nEnvie para as clientes: Cliente ou Página APK.\n"
    log(text)


def copy_links(root, log) -> None:
    text = "\n".join(f"{k}: {v}" for k, v in urls().items())
    root.clipboard_clear()
    root.clipboard_append(text)
    log("Links copiados para a área de transferência.\n")
    messagebox.showinfo(APP_NAME, "Links copiados.")


def show_qr(log) -> None:
    link = urls()["Página APK"]
    try:
        import qrcode
        from PIL import ImageTk
        img = qrcode.make(link).resize((320, 320))
        win = tk.Toplevel()
        win.title("BRECHORISEE - QR Code APK")
        tk.Label(win, text="Aponte a câmera para baixar o app cliente", font=("Arial", 12, "bold")).pack(pady=8)
        photo = ImageTk.PhotoImage(img)
        label = tk.Label(win, image=photo)
        label.image = photo
        label.pack(padx=16, pady=8)
        tk.Label(win, text=link, wraplength=420).pack(padx=16, pady=8)
        tk.Button(win, text="Abrir link", command=lambda: webbrowser.open(link)).pack(pady=8)
        log(f"QR Code exibido para: {link}\n")
    except Exception as exc:
        log(f"Não consegui gerar QR Code: {exc}\n")
        log(f"Link do APK: {link}\n")
        messagebox.showinfo(APP_NAME, f"Link do APK:\n{link}")


def open_env(log) -> None:
    ensure_env()
    subprocess.Popen(["notepad.exe", str(ENV_FILE)])


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(str(path))


def main() -> None:
    ensure_env()
    root = tk.Tk()
    root.title("Central BRECHORISEE")
    root.geometry("980x720")

    tk.Label(root, text="Central BRECHORISEE", font=("Arial", 20, "bold")).pack(pady=8)
    tk.Label(root, text="Um painel para instalar, iniciar, abrir, compilar, publicar APK, backup e QR Code.", font=("Arial", 10)).pack()

    logbox = scrolledtext.ScrolledText(root, height=22)
    logbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def log(text: str):
        logbox.insert(tk.END, text)
        logbox.see(tk.END)
        root.update_idletasks()

    def async_run(fn):
        threading.Thread(target=lambda: safe(fn), daemon=True).start()

    def safe(fn):
        try:
            fn(log)
        except Exception as exc:
            log(f"\nERRO: {exc}\n")
            messagebox.showerror(APP_NAME, str(exc))

    frame = tk.Frame(root)
    frame.pack(pady=8)

    buttons = [
        ("Instalar dependências", lambda: async_run(install_dependencies)),
        ("Iniciar servidor", lambda: async_run(start_server)),
        ("Parar servidor", lambda: async_run(stop_server)),
        ("Abrir sistema", lambda: webbrowser.open(LOCAL_URL)),
        ("Abrir Admin", lambda: webbrowser.open(LOCAL_URL + "/admin")),
        ("Abrir Cliente", lambda: webbrowser.open(LOCAL_URL + "/app/cliente")),
        ("Publicar APK Cliente", lambda: async_run(publish_client_apk)),
        ("QR Code APK", lambda: show_qr(log)),
        ("Copiar links", lambda: copy_links(root, log)),
        ("Backup agora", lambda: async_run(lambda lg: make_backup(lg, "manual"))),
        ("Restaurar backup", lambda: restore_backup(log)),
        ("Abrir pasta backups", lambda: open_folder(BACKUP_DIR)),
        ("Compilar Cliente Android", lambda: run_bat(BASE_DIR / "BRECHORISEE_CLIENTE" / "android" / "GERAR_PUBLICACAO_COMPLETA_WINDOWS.bat", log)),
        ("Compilar Admin Android", lambda: run_bat(BASE_DIR / "BRECHORISEE_ADMIN" / "android" / "COMPILAR_APK_WINDOWS.bat", log)),
        ("Abrir projetos iOS", lambda: open_folder(BASE_DIR / "BRECHORISEE_CLIENTE" / "ios")),
        ("Abrir .env único", lambda: open_env(log)),
        ("Abrir pasta do sistema", lambda: open_folder(BASE_DIR)),
        ("Ver links/IP", lambda: show_links_text(log)),
    ]

    for idx, (label, command) in enumerate(buttons):
        r, c = divmod(idx, 3)
        tk.Button(frame, text=label, width=27, height=2, command=command).grid(row=r, column=c, padx=5, pady=5)

    log("Pronto. Use 'Instalar dependências' uma vez e depois 'Iniciar servidor'.\n")
    log(f"Banco local: {DATA_DIR / 'brechorisee.db'}\n")
    log(f".env único: {ENV_FILE}\n")
    show_links_text(log)

    def on_close():
        global auto_backup_running
        auto_backup_running = False
        try:
            stop_server(log)
        finally:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
