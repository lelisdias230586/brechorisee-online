from __future__ import annotations
import shutil, sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "BRECHORISEE_SERVIDOR" / "dados"
BACKUPS = BASE / "BRECHORISEE_SERVIDOR" / "backups"
DB = DATA / "brechorisee.db"

def backup(reason="manual"):
    DATA.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    if not DB.exists() or DB.stat().st_size == 0:
        print("Banco ainda nao encontrado:", DB)
        print("Use o sistema primeiro para criar dados.")
        return 1
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = BACKUPS / f"brechorisee_{ts}_{reason}.db"
    shutil.copy2(DB, dest)
    print("Backup criado com sucesso:")
    print(dest)
    return 0

def restore():
    BACKUPS.mkdir(parents=True, exist_ok=True)
    files = sorted(BACKUPS.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("Nenhum backup encontrado em:", BACKUPS)
        return 1
    print("Backups encontrados:")
    for i, f in enumerate(files[:30], 1):
        print(f"{i:02d}) {f.name}")
    choice = input("Digite o numero do backup para restaurar ou Enter para cancelar: ").strip()
    if not choice:
        print("Cancelado.")
        return 0
    try:
        idx = int(choice) - 1
        src = files[idx]
    except Exception:
        print("Opcao invalida.")
        return 1
    if DB.exists():
        backup("antes_restaurar")
    DATA.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, DB)
    print("Backup restaurado com sucesso:")
    print(src)
    print("Para aplicar, inicie o servidor novamente.")
    return 0

if __name__ == "__main__":
    op = (sys.argv[1] if len(sys.argv) > 1 else "backup").lower()
    raise SystemExit(restore() if op == "restore" else backup(op))
