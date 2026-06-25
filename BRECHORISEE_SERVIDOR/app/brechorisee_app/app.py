from __future__ import annotations

import csv
import colorsys
import hashlib
import hmac
import html
import ipaddress
import secrets
import io
import json
import logging
import base64
import urllib.request
import urllib.error
import math
import os
import random
import re
import shutil
import socket
import sqlite3
import string
import unicodedata
import zipfile
import threading
import time
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import qrcode
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps, ImageDraw, ImageFont

try:
    import imageio.v2 as imageio
except Exception:
    imageio = None

try:
    import numpy as np
except Exception:
    np = None

APP_NAME = "brechorisee"
BASE_DIR = Path(__file__).resolve().parent


def load_local_env_file(path: Path | None = None) -> None:
    """Carrega brechorisee_app/.env sem depender de pacote externo.

    Variáveis já definidas pelo servidor/nuvem têm prioridade e não são sobrescritas.
    """
    env_path = path or (BASE_DIR / ".env")
    try:
        if not env_path.exists():
            return
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            os.environ[key] = value
    except Exception:
        logging.getLogger(APP_NAME).warning("Não foi possível carregar o arquivo .env local.", exc_info=True)


load_local_env_file(BASE_DIR / ".env")
load_local_env_file(BASE_DIR.parent / ".env")

def resolve_data_path(env_name: str, default_relative_name: str) -> Path:
    """Resolve caminhos persistentes sem depender da pasta em que o servidor foi iniciado."""
    raw_value = os.getenv(env_name, "").strip()
    if raw_value:
        candidate = Path(raw_value).expanduser()
        if not candidate.is_absolute():
            candidate = BASE_DIR / candidate
        return candidate
    render_disk = Path("/var/data")
    if render_disk.exists() and os.access(render_disk, os.W_OK):
        return render_disk / default_relative_name
    return BASE_DIR / default_relative_name


DB_PATH = resolve_data_path("BRECHORISEE_DB_PATH", "brechorisee.db")
STATIC_DIR = BASE_DIR / "static"
DOWNLOAD_DIR = STATIC_DIR / "downloads"
UPLOAD_DIR = STATIC_DIR / "uploads"
QR_DIR = STATIC_DIR / "qrcodes"
BACKUP_DIR = BASE_DIR / "backups"
GENERATED_MARKETING_DIR = STATIC_DIR / "generated" / "marketing"
LIVE_DIR = STATIC_DIR / "live"

PERSISTENT_DIR = Path(os.getenv("BRECHORISEE_PERSISTENT_DIR", "/var/data")).expanduser()


def _safe_persistent_symlink(link_path: Path, target_path: Path) -> Path:
    """Mantém arquivos grandes em disco persistente no Render sem quebrar /static/....

    Se o Render tiver um disco montado em /var/data, as pastas de uploads/live/qrcodes
    são guardadas lá. O caminho dentro de static vira um link simbólico, então as URLs
    antigas (/static/uploads/...) continuam funcionando.
    """
    try:
        if not (PERSISTENT_DIR.exists() and os.access(PERSISTENT_DIR, os.W_OK)):
            return link_path
        target_path.mkdir(parents=True, exist_ok=True)
        if link_path.is_symlink():
            return link_path
        if link_path.exists():
            # Copia o que já existe para o disco persistente antes de trocar por symlink.
            if link_path.is_dir():
                for item in link_path.iterdir():
                    dest = target_path / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    elif not dest.exists():
                        shutil.copy2(item, dest)
                shutil.rmtree(link_path)
            else:
                backup_name = target_path / link_path.name
                if not backup_name.exists():
                    shutil.copy2(link_path, backup_name)
                link_path.unlink()
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(target_path, target_is_directory=True)
        return link_path
    except Exception:
        logging.getLogger(APP_NAME).warning("Não foi possível preparar symlink persistente: %s -> %s", link_path, target_path, exc_info=True)
        return link_path


if os.getenv("BRECHORISEE_RENDER_PERSISTENCE", "1").strip().lower() not in {"0", "false", "nao", "não", "off"}:
    UPLOAD_DIR = _safe_persistent_symlink(UPLOAD_DIR, PERSISTENT_DIR / "uploads")
    QR_DIR = _safe_persistent_symlink(QR_DIR, PERSISTENT_DIR / "qrcodes")
    LIVE_DIR = _safe_persistent_symlink(LIVE_DIR, PERSISTENT_DIR / "live")
    GENERATED_MARKETING_DIR = _safe_persistent_symlink(GENERATED_MARKETING_DIR, PERSISTENT_DIR / "generated" / "marketing")
    BACKUP_DIR = _safe_persistent_symlink(BACKUP_DIR, PERSISTENT_DIR / "backups")


# Segurança e limites operacionais.
# Em produção, configure BRECHORISEE_SECRET_KEY com um valor longo e aleatório.
AUTH_COOKIE_NAME = "brechorisee_admin"
CUSTOMER_COOKIE_NAME = "brechorisee_cliente"
AUTH_SESSION_DAYS = int(os.getenv("BRECHORISEE_AUTH_SESSION_DAYS", "7"))
CUSTOMER_SESSION_DAYS = int(os.getenv("BRECHORISEE_CUSTOMER_SESSION_DAYS", "30"))
BRECHORISEE_ENV = os.getenv("BRECHORISEE_ENV", "development").strip().lower()
_SECRET_KEY_FROM_ENV = (os.getenv("BRECHORISEE_SECRET_KEY") or os.getenv("SECRET_KEY") or "").strip()
SECRET_KEY_CONFIGURED = bool(_SECRET_KEY_FROM_ENV)
if SECRET_KEY_CONFIGURED:
    BRECHORISEE_SECRET_KEY = _SECRET_KEY_FROM_ENV
elif BRECHORISEE_ENV in {"production", "prod"}:
    raise RuntimeError("Configure BRECHORISEE_SECRET_KEY ou SECRET_KEY em produção.")
else:
    # Fallback apenas para desenvolvimento local, para não quebrar testes/execução offline.
    BRECHORISEE_SECRET_KEY = hashlib.sha256(
        f"{APP_NAME}:{DB_PATH.resolve()}:development-only".encode("utf-8")
    ).hexdigest()
BRECHORISEE_SYNC_TOKEN = os.getenv("BRECHORISEE_SYNC_TOKEN", "").strip()
BRECHORISEE_ADMIN_RECOVERY_TOKEN = os.getenv("BRECHORISEE_ADMIN_RECOVERY_TOKEN", "").strip()
MAX_IMAGE_UPLOAD_BYTES = int(float(os.getenv("BRECHORISEE_MAX_IMAGE_MB", "12")) * 1024 * 1024)
# Fotos feitas no celular podem vir muito grandes. Mantemos boa qualidade,
# mas reduzimos dimensões para carregar rápido no site, PWA e apps WebView.
MAX_PRODUCT_IMAGE_SIDE = int(os.getenv("BRECHORISEE_MAX_PRODUCT_IMAGE_SIDE", "1600"))
IMAGE_SAVE_QUALITY = int(os.getenv("BRECHORISEE_IMAGE_SAVE_QUALITY", "86"))
MAX_MEDIA_UPLOAD_BYTES = int(float(os.getenv("BRECHORISEE_MAX_MEDIA_MB", "300")) * 1024 * 1024)
LIVE_RECOGNITION_MIN_SCORE = float(os.getenv("BRECHORISEE_LIVE_RECOGNITION_MIN_SCORE", "56"))
LIVE_RECOGNITION_ANDROID_MIN_SCORE = float(os.getenv("BRECHORISEE_LIVE_ANDROID_MIN_SCORE", "78"))
LIVE_RECOGNITION_ANDROID_GAP_SCORE = float(os.getenv("BRECHORISEE_LIVE_ANDROID_GAP_SCORE", "7"))
LIVE_RECOGNITION_MAX_PRODUCTS = int(os.getenv("BRECHORISEE_LIVE_RECOGNITION_MAX_PRODUCTS", "5"))
LIVE_CURRENT_STALE_SECONDS = int(os.getenv("BRECHORISEE_LIVE_CURRENT_STALE_SECONDS", "7"))
LIVE_REFERENCE_STALE_SECONDS = int(os.getenv("BRECHORISEE_LIVE_REFERENCE_STALE_SECONDS", "9"))
LIVE_AUTO_RECOGNITION_SECONDS = float(os.getenv("BRECHORISEE_LIVE_AUTO_RECOGNITION_SECONDS", "1.2"))
INSTAGRAM_ASSISTANT_MIN_SCORE = float(os.getenv("BRECHORISEE_INSTAGRAM_ASSISTANT_MIN_SCORE", "42"))
INSTAGRAM_ASSISTANT_STRONG_SCORE = float(os.getenv("BRECHORISEE_INSTAGRAM_ASSISTANT_STRONG_SCORE", "50"))
INSTAGRAM_ASSISTANT_MAX_MATCHES = int(os.getenv("BRECHORISEE_INSTAGRAM_ASSISTANT_MAX_MATCHES", "10"))
INSTAGRAM_ASSISTANT_DEBUG = os.getenv("BRECHORISEE_INSTAGRAM_ASSISTANT_DEBUG", "0").strip().lower() in {"1", "true", "yes", "sim"}

# Telegram: por padrão fica em modo seguro/simulado.
# Para envio real, configure TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID e BRECHORISEE_TELEGRAM_SEND_REAL=1.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
TELEGRAM_SEND_REAL = os.getenv("BRECHORISEE_TELEGRAM_SEND_REAL", "0").strip().lower() in {"1", "true", "sim", "yes", "on"}
TELEGRAM_NOTIFY_ORDERS = os.getenv("BRECHORISEE_TELEGRAM_NOTIFY_ORDERS", "1").strip().lower() not in {"0", "false", "nao", "não", "off"}
TELEGRAM_NOTIFY_LIVE = os.getenv("BRECHORISEE_TELEGRAM_NOTIFY_LIVE", "1").strip().lower() not in {"0", "false", "nao", "não", "off"}
TELEGRAM_NOTIFY_COMMENTS = os.getenv("BRECHORISEE_TELEGRAM_NOTIFY_COMMENTS", "1").strip().lower() not in {"0", "false", "nao", "não", "off"}
TELEGRAM_NOTIFY_RESERVATIONS = os.getenv("BRECHORISEE_TELEGRAM_NOTIFY_RESERVATIONS", "1").strip().lower() not in {"0", "false", "nao", "não", "off"}
TELEGRAM_NOTIFY_WAITLIST = os.getenv("BRECHORISEE_TELEGRAM_NOTIFY_WAITLIST", "1").strip().lower() not in {"0", "false", "nao", "não", "off"}
TELEGRAM_NOTIFY_PAYMENTS = os.getenv("BRECHORISEE_TELEGRAM_NOTIFY_PAYMENTS", "1").strip().lower() not in {"0", "false", "nao", "não", "off"}
TELEGRAM_COMMANDS_ENABLED = os.getenv("BRECHORISEE_TELEGRAM_COMMANDS_ENABLED", "1").strip().lower() not in {"0", "false", "nao", "não", "off"}
_TELEGRAM_ALLOWED_CHAT_IDS_RAW = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip() or TELEGRAM_ADMIN_CHAT_ID
TELEGRAM_ALLOWED_CHAT_IDS = {
    part.strip()
    for part in _TELEGRAM_ALLOWED_CHAT_IDS_RAW.replace(";", ",").split(",")
    if part.strip()
}
ASSISTANT_CONTROL_TOKEN = os.getenv("BRECHORISEE_ASSISTANT_TOKEN", os.getenv("BRECHORISEE_SYNC_TOKEN", "")).strip()

APP_VERSION = os.getenv("BRECHORISEE_VERSION", "4.9.6-oracle-vps")
SCHEMA_VERSION = os.getenv("BRECHORISEE_SCHEMA_VERSION", "2026_06_atendimento_bot_desejos_aquisicoes")
DB_BUSY_TIMEOUT_MS = int(os.getenv("BRECHORISEE_DB_BUSY_TIMEOUT_MS", "5000"))
DB_ENABLE_WAL = os.getenv("BRECHORISEE_DB_WAL", "1").strip().lower() not in {"0", "false", "nao", "não", "off"}

logging.basicConfig(
    level=os.getenv("BRECHORISEE_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("brechorisee")

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".3gp", ".avi"}
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/3gpp", "video/x-msvideo"}
IMAGE_EXT_BY_CONTENT_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
QR_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_MARKETING_DIR.mkdir(parents=True, exist_ok=True)
LIVE_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="BRECHORISEE", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/favicon.ico")
def favicon_ico() -> Response:
    path = BASE_DIR / "static" / "favicon.ico"
    if path.exists():
        return FileResponse(path, media_type="image/x-icon")
    return Response(status_code=204)


def money(value: Any) -> str:
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


templates.env.filters["money"] = money


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if fmt.endswith("%S") else text[:10], fmt)
        except Exception:
            pass
    return None


def days_between(start_value: Any, end_value: Any | None = None) -> int:
    start = parse_dt(start_value)
    end = parse_dt(end_value) if end_value else datetime.now()
    if not start:
        return 0
    return max(0, (end - start).days)


def date_br(value: Any) -> str:
    dt = parse_dt(value)
    return dt.strftime("%d/%m/%Y") if dt else "-"


templates.env.filters["date_br"] = date_br


DEFAULT_FORM_SUGGESTIONS: dict[str, list[str]] = {
    "title": [
        "Bolsa", "Calça", "Blusa", "Vestido", "Saia", "Short", "Macacão", "Jaqueta", "Casaco",
        "Camisa", "Camiseta", "Cropped", "Body", "Regata", "Top", "Kimono", "Conjunto", "Colete",
        "Blazer", "Moletom", "Cardigan", "Tricô", "Sapato", "Sandália", "Tênis", "Bota", "Rasteira",
        "Cinto", "Lenço", "Óculos", "Brinco", "Colar", "Pulseira",
    ],
    "category": [
        "Feminino", "Masculino", "Infantil", "Acessórios", "Calçados", "Bolsas", "Plus size",
        "Vintage", "Festa", "Praia", "Fitness", "Jeans",
    ],
    "garment_type": [
        "Bolsa", "Calça", "Blusa", "Vestido", "Saia", "Short", "Macacão", "Jaqueta", "Casaco",
        "Camisa", "Camiseta", "Cropped", "Body", "Regata", "Top", "Kimono", "Conjunto", "Colete",
        "Blazer", "Moletom", "Cardigan", "Tricô", "Sapato", "Sandália", "Tênis", "Bota", "Rasteira",
        "Cinto", "Lenço", "Óculos", "Bijuteria",
    ],
    "size": [
        "PP", "P", "M", "G", "GG", "XG", "Único", "34", "36", "38", "40", "42", "44", "46",
        "48", "50", "52", "P/M", "M/G", "Plus size",
    ],
    "brand": [
        "Sem marca", "Farm", "Zara", "C&A", "Renner", "Riachuelo", "Marisa", "Hering", "Colcci",
        "Le Lis Blanc", "Shoulder", "Animale", "Maria Filó", "Cantão", "Arezzo", "Schutz",
        "Santa Lolla", "Melissa", "Adidas", "Nike", "Puma", "Lacoste", "Forum", "Morena Rosa",
        "Lança Perfume", "Dudalina", "Youcom", "Shein",
    ],
    "color": [
        "Preto", "Branco", "Off white", "Bege", "Nude", "Marrom", "Caramelo", "Cinza", "Azul",
        "Azul-marinho", "Jeans", "Rosa", "Pink", "Verde", "Verde militar", "Vermelho", "Vinho",
        "Amarelo", "Mostarda", "Lilás", "Roxo", "Laranja", "Dourado", "Prata", "Estampado",
        "Colorido",
    ],
    "condition": [
        "Novo com etiqueta", "Novo sem etiqueta", "Seminovo", "Usado - bom", "Com detalhe",
    ],
    "season": [
        "Verão", "Inverno", "Meia estação", "Primavera", "Outono", "Festa", "Trabalho",
        "Casual", "Praia", "Academia", "Noite", "Dia a dia",
    ],
    "target_audience": [
        "Feminino", "Masculino", "Infantil", "Plus size", "Jovem", "Clássico", "Executivo",
        "Vintage", "Romântico", "Boho", "Minimalista", "Streetwear", "Festa", "Gestante",
    ],
    "style_tags": [
        "floral", "liso", "listrado", "poá", "animal print", "xadrez", "geométrico",
        "alfaiataria", "oversized", "cropped", "canelado", "renda", "bordado", "brilho",
        "paetê", "couro", "jeans", "linho", "viscose", "seda", "malha", "tricô",
        "cintura alta", "wide leg", "mom jeans", "skinny", "pantalona", "evasê",
        "midi", "longo", "curto", "com bojo", "sem bojo",
    ],
    "measurements": [
        "Busto 90 cm", "Cintura 72 cm", "Quadril 100 cm", "Comprimento 80 cm",
        "Manga 60 cm", "Entrepernas 72 cm", "Alça regulável", "Tamanho único",
    ],
    "characteristics": [
        "floral", "liso", "estampado", "listrado", "renda", "bordado", "botões",
        "zíper", "forrado", "transparência", "elástico", "amarrar", "manga curta",
        "manga longa", "decote V", "gola alta", "cintura alta", "sem avarias",
        "pequeno detalhe", "tecido leve", "tecido estruturado", "ótimo estado",
    ],
    "payment_method": [
        "Dinheiro", "Pix", "Cartão de débito", "Cartão de crédito", "Crédito parcelado",
        "Vale", "Troca",
    ],
    "customer": [
        "Cliente balcão", "Cliente Instagram", "Cliente WhatsApp", "Retirada loja",
    ],
    "notes": [
        "Consignação", "Repasse combinado", "Fornecedor prefere Pix", "Peças em ótimo estado",
        "Avisar antes de baixar preço",
    ],
    "phone": ["WhatsApp", "Telefone"],
    "instagram": ["@"],
    "email": ["@gmail.com", "@hotmail.com", "@outlook.com"],
}


def _merge_suggestions(*groups: Any, limit: int = 120) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        if not group:
            continue
        for item in group:
            text = str(item or "").strip()
            if not text:
                continue
            key = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
            if len(result) >= limit:
                return result
    return result


def get_form_suggestions() -> dict[str, list[str]]:
    suggestions = {key: list(values) for key, values in DEFAULT_FORM_SUGGESTIONS.items()}
    with get_db() as con:
        product_fields = {
            "title": "title",
            "category": "category",
            "garment_type": "garment_type",
            "size": "size",
            "brand": "brand",
            "color": "color",
            "condition": "condition",
            "season": "season",
            "target_audience": "target_audience",
            "style_tags": "style_tags",
            "measurements": "measurements",
            "characteristics": "characteristics",
            "code": "code",
        }
        for key, column in product_fields.items():
            rows = con.execute(
                f"SELECT DISTINCT {column} AS value FROM products WHERE {column} IS NOT NULL AND TRIM({column}) <> '' ORDER BY {column} LIMIT 250"
            ).fetchall()
            values: list[str] = []
            for row in rows:
                raw = str(row["value"] or "")
                # Campos de tags/características podem ter várias palavras separadas por vírgula.
                if key in {"style_tags", "characteristics", "season", "target_audience"}:
                    values.extend(part.strip() for part in raw.replace(";", ",").split(","))
                else:
                    values.append(raw)
            suggestions[key] = _merge_suggestions(suggestions.get(key, []), values)

        supplier_rows = con.execute("SELECT DISTINCT name FROM suppliers WHERE TRIM(name) <> '' ORDER BY name LIMIT 150").fetchall()
        suggestions["supplier"] = _merge_suggestions([row["name"] for row in supplier_rows])

        customer_rows = con.execute("SELECT DISTINCT customer FROM sales WHERE customer IS NOT NULL AND TRIM(customer) <> '' ORDER BY customer LIMIT 150").fetchall()
        suggestions["customer"] = _merge_suggestions(suggestions.get("customer", []), [row["customer"] for row in customer_rows])

    search_pool = _merge_suggestions(
        suggestions.get("code", []),
        suggestions.get("title", []),
        suggestions.get("garment_type", []),
        suggestions.get("brand", []),
        suggestions.get("color", []),
        suggestions.get("size", []),
        suggestions.get("style_tags", []),
        suggestions.get("characteristics", []),
        limit=180,
    )
    suggestions["q"] = search_pool
    suggestions["search"] = search_pool
    suggestions["cashierSearchInput"] = search_pool
    suggestions["codeInput"] = _merge_suggestions(suggestions.get("code", []), suggestions.get("title", []), suggestions.get("garment_type", []), limit=120)
    return suggestions


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_lan_ip() -> str:
    """Descobre um IP provável da rede local para acesso pelo celular."""
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
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"



def app_base_url(request: Request) -> str:
    """Base local para links clicáveis no celular/rede."""
    try:
        return str(request.base_url).rstrip("/")
    except Exception:
        return f"http://{get_lan_ip()}:8000"


def _url_host(value: str) -> str:
    """Extrai o host de uma URL, ignorando porta e credenciais."""
    try:
        parsed = urlparse(str(value or "").strip())
        return (parsed.hostname or "").strip().lower()
    except Exception:
        return ""


def _is_local_or_private_host(host: str) -> bool:
    """Detecta hosts que não devem ser divulgados para clientes externas."""
    host = (host or "").strip().lower().strip("[]")
    if not host:
        return True
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    if host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        # Inclui LAN, loopback, link-local e o bloco 100.64/10 usado por CGNAT/Tailscale.
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip in ipaddress.ip_network("100.64.0.0/10"))
    except Exception:
        return False


def _request_public_base_url(request: Request | None = None) -> str:
    """Monta a base pelo Host recebido.

    Essencial para túneis como localhost.run/lhr.life: mesmo que o .env tenha
    Tailscale, Render antigo ou IP local, links clicados pela cliente usam o
    domínio atual da requisição.
    """
    if request is None:
        return ""
    try:
        forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
        host = forwarded_host or (request.headers.get("host") or "").strip()
        if not host:
            return str(request.base_url).rstrip("/")
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
        # Túneis HTTPS muitas vezes chegam ao Uvicorn como HTTP interno, mas
        # com Host público. Para domínios públicos, preferimos HTTPS.
        host_only = host.split("@")[-1].split(":")[0].strip("[]").lower()
        if proto == "http" and not _is_local_or_private_host(host_only):
            proto = "https"
        return f"{proto}://{host}".rstrip("/")
    except Exception:
        try:
            return str(request.base_url).rstrip("/")
        except Exception:
            return ""


def _same_url_host(left: str, right: str) -> bool:
    lh = _url_host(left)
    rh = _url_host(right)
    return bool(lh and rh and lh == rh)


def _safe_same_origin_or_blank(configured_url: str, base: str, fallback_path: str) -> str:
    """Evita links antigos/stale como onrender quando a página veio por outro túnel."""
    configured_url = (configured_url or "").strip()
    base = (base or "").rstrip("/")
    if configured_url and (_same_url_host(configured_url, base) or _is_local_or_private_host(_url_host(base))):
        return configured_url
    return f"{base}{fallback_path}"


def product_deep_link(product_id: int | str = "", code: str = "") -> str:
    if product_id:
        return f"brechorisee://produto?id={product_id}"
    return f"brechorisee://produto?code={code}"


def product_public_link(product: sqlite3.Row | dict[str, Any], request: Request, source: str = "social") -> str:
    p = row_to_dict(product)
    code = p.get("code") or p.get("id") or ""
    return f"{app_base_url(request)}/vitrine/peca/{code}?origem={source}"


def instagram_profile_url(settings: dict[str, Any] | None = None) -> str:
    settings = settings or {}
    raw = str(settings.get("instagram") or "@brechorisee").strip()
    user = raw.replace("https://www.instagram.com/", "").replace("https://instagram.com/", "").strip("/").lstrip("@")
    return f"https://www.instagram.com/{user}" if user else "https://www.instagram.com/"





def brechorisee_validate_apk(path: Path) -> tuple[bool, str]:
    """Valida o APK antes de mostrar/servir para clientes.

    Bloqueia três problemas que causavam erro no celular:
    1. arquivo que não é APK de verdade ou download HTML renomeado;
    2. APK antigo cujo Manifest aponta para MainActivity, mas o classes.dex não tem a classe;
    3. APK release sem assinatura, comum quando se usa app-release-unsigned.apk.
    """
    try:
        if not path.exists() or not path.is_file():
            return False, "arquivo não encontrado"
        size = path.stat().st_size
        if size < 16 * 1024:
            return False, "arquivo muito pequeno para ser um APK válido"
        if not zipfile.is_zipfile(path):
            return False, "arquivo não é um APK/ZIP Android válido"

        expected_dex_markers = (
            b"Lcom/brechorisee/cliente/MainActivity;",
            b"com/brechorisee/cliente/MainActivity",
        )
        found_main_activity = False
        found_v1_signature = False

        with zipfile.ZipFile(path) as apk_zip:
            names = set(apk_zip.namelist())
            upper_names = {name.upper() for name in names}

            if "AndroidManifest.xml" not in names:
                return False, "APK sem AndroidManifest.xml"
            dex_names = [name for name in names if name.startswith("classes") and name.endswith(".dex")]
            if not dex_names:
                return False, "APK sem classes.dex"

            # Release/install via navegador precisa de APK assinado. O build unsigned instala com
            # erro "Como o pacote parece ser inválido". Como o projeto tem minSdk 23, o Gradle
            # gera assinatura v1 também quando a release está assinada corretamente.
            for name in upper_names:
                if name.startswith("META-INF/") and (name.endswith(".RSA") or name.endswith(".DSA") or name.endswith(".EC")):
                    found_v1_signature = True
                    break
            if not found_v1_signature:
                return False, "APK sem assinatura/certificado. Não use app-release-unsigned.apk. Gere pelo GERAR_APK_CLIENTE_FINAL_WINDOWS.bat ou use app-debug.apk assinado."

            for dex_name in dex_names:
                data = apk_zip.read(dex_name)
                if any(marker in data for marker in expected_dex_markers):
                    found_main_activity = True
                    break
            if not found_main_activity:
                return False, "APK antigo/incompatível: falta com.brechorisee.cliente.MainActivity no classes.dex. Compile e publique APK novo v4.8.9."

        return True, "ok"
    except Exception as exc:
        return False, f"erro ao validar APK: {exc}"


def brechorisee_customer_apk_path() -> Path:
    """Local do APK público do app cliente.

    O script GERAR_PUBLICACAO_COMPLETA_WINDOWS.bat copia o APK para:
    brechorisee_app/static/downloads/BRECHORISEE_CLIENTE.apk
    """
    custom_path = os.getenv("BRECHORISEE_CLIENT_APK_PATH", "").strip()
    if custom_path:
        return Path(custom_path)
    filename = os.getenv("BRECHORISEE_CLIENT_APK_FILENAME", "BRECHORISEE_CLIENTE.apk").strip() or "BRECHORISEE_CLIENTE.apk"
    return DOWNLOAD_DIR / filename


def brechorisee_customer_apk_info(request: Request | None = None) -> dict[str, Any]:
    base = get_public_server_url(request).rstrip("/")
    path = brechorisee_customer_apk_path()
    file_exists = path.exists() and path.is_file()
    valid, validation_message = brechorisee_validate_apk(path) if file_exists else (False, "arquivo não encontrado")
    size_bytes = path.stat().st_size if file_exists else 0
    size_mb = round(size_bytes / (1024 * 1024), 2) if size_bytes else 0
    updated_at = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if file_exists else ""
    return {
        "available": bool(file_exists and valid),
        "valid": bool(valid),
        "validation_message": validation_message,
        "filename": path.name,
        "path": str(path),
        "url": f"{base}/download/app-cliente.apk",
        "fallback_url": f"{base}/app/cliente",
        "size_bytes": int(size_bytes),
        "size_mb": size_mb,
        "updated_at": updated_at,
        "version": APP_VERSION,
    }



def brechorisee_admin_apk_path() -> Path:
    """Local do APK interno do app Admin.

    O Sistema BRECHORISEE publica o APK Admin em:
    brechorisee_app/static/downloads/BRECHORISEE_ADMIN.apk
    """
    custom_path = os.getenv("BRECHORISEE_ADMIN_APK_PATH", "").strip()
    if custom_path:
        return Path(custom_path)
    filename = os.getenv("BRECHORISEE_ADMIN_APK_FILENAME", "BRECHORISEE_ADMIN.apk").strip() or "BRECHORISEE_ADMIN.apk"
    return DOWNLOAD_DIR / filename


def brechorisee_admin_apk_info(request: Request | None = None) -> dict[str, Any]:
    base = get_public_server_url(request).rstrip("/")
    path = brechorisee_admin_apk_path()
    file_exists = path.exists() and path.is_file()
    valid, validation_message = brechorisee_validate_apk(path) if file_exists else (False, "arquivo não encontrado")
    size_bytes = path.stat().st_size if file_exists else 0
    size_mb = round(size_bytes / (1024 * 1024), 2) if size_bytes else 0
    updated_at = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if file_exists else ""
    return {
        "available": bool(file_exists and valid),
        "valid": bool(valid),
        "validation_message": validation_message,
        "filename": path.name,
        "path": str(path),
        "url": f"{base}/download/app-admin.apk",
        "fallback_url": f"{base}/admin",
        "size_bytes": int(size_bytes),
        "size_mb": size_mb,
        "updated_at": updated_at,
        "version": APP_VERSION,
    }

def brechorisee_customer_app_links(request: Request | None = None) -> dict[str, str]:
    """Links públicos para a cliente interagir com live/peça com ou sem app.

    Usa o host atual da requisição quando há túnel público, impedindo que botões
    de download apontem para domínio antigo salvo no .env.
    """
    base = get_public_server_url(request).rstrip("/")
    apk_info = brechorisee_customer_apk_info(request)
    google_play_url = os.getenv("BRECHORISEE_GOOGLE_PLAY_URL", "").strip()
    android_url = os.getenv("BRECHORISEE_ANDROID_APP_URL", "").strip()
    ios_url = os.getenv("BRECHORISEE_IOS_APP_URL", "").strip()
    configured_download = os.getenv("BRECHORISEE_CLIENT_APP_URL", "").strip() or os.getenv("BRECHORISEE_APP_DOWNLOAD_URL", "").strip()
    configured_apk = os.getenv("BRECHORISEE_CLIENT_APK_URL", "").strip()
    app_download_url = _safe_same_origin_or_blank(configured_download, base, "/app/cliente")
    direct_apk_url = _safe_same_origin_or_blank(configured_apk, base, "/download/app-cliente.apk")
    android_primary = android_url or google_play_url or direct_apk_url
    return {
        "base": base,
        "download": app_download_url,
        "apk": direct_apk_url,
        "google_play": google_play_url,
        "android": android_primary,
        "ios": ios_url or app_download_url,
        "customer_home": f"{base}{CUSTOMER_HOME_PATH}",
        "live_current": f"{base}/live/peca-atual",
        "live_companion": f"{base}/live/companion",
        "customer_live": f"{base}/cliente/live",
        "tutorial": f"{base}/cliente/tutorial",
        "tutorial_api": f"{base}/api/cliente/tutorial",
        "deep_live": "brechorisee://live-companion?abrir_instagram=1",
        "deep_tutorial": "brechorisee://tutorial",
    }


def brechorisee_customer_tutorial_payload(request: Request | None = None) -> dict[str, Any]:
    """Roteiro da animação/guia da cliente.

    A versão vem do .env; assim o tutorial mostra automaticamente a versão nova
    a cada atualização publicada no servidor/app.
    """
    version = os.getenv("BRECHORISEE_VERSION", "local")
    links = brechorisee_customer_app_links(request)
    return {
        "version": version,
        "updated_at": now_iso() if "now_iso" in globals() else datetime.now().isoformat(timespec="seconds"),
        "links": links,
        "steps": [
            {"icon": "📲", "title": "Baixe o app ou continue no site", "text": "Com o app você recebe alerta da live e reserva mais rápido. Sem app, use o link da bio ou o navegador."},
            {"icon": "🔔", "title": "Permita notificações", "text": "Quando a live começar, o BRECHORISEE avisa e abre o modo live para você acompanhar."},
            {"icon": "🎥", "title": "Entre na live pelo Instagram", "text": "Assista normalmente no Instagram. O BRECHORISEE fica como apoio para mostrar a peça atual."},
            {"icon": "👗", "title": "Veja a peça atual na tela", "text": "O app/site mostra foto, código, preço, tamanho, medidas e status em tempo quase real."},
            {"icon": "💖", "title": "Reserve ou entre na fila", "text": "Toque em Quero reservar. Se alguém chegou antes, você entra na fila de espera automaticamente."},
            {"icon": "🛍️", "title": "Acompanhe sua sacola", "text": "As peças da live ficam juntas em um carrinho por cliente para finalizar tudo de uma vez."},
            {"icon": "💳", "title": "Finalize com Pix, retirada ou entrega", "text": "Depois da live, confira o resumo, pague por Pix ou combine retirada/entrega com a loja."},
            {"icon": "✨", "title": "Veja repescagem e vitrine", "text": "Peças que não venderam podem aparecer na repescagem com link para comprar depois."},
            {"icon": "🌐", "title": "Sem app também funciona", "text": "Toda mensagem traz opção para baixar o app e também um link para continuar pelo navegador."},
        ],
    }


def brechorisee_customer_app_cta(request: Request | None = None, compact: bool = False) -> str:
    links = brechorisee_customer_app_links(request)
    if compact:
        return f"App BRECHORISEE: {links['download']} • Área da cliente: {links.get('customer_home') or links['download']} • Como usar: {links['tutorial']}"
    return "\n".join([
        "💖 Para reservar mais rápido nas próximas lives:",
        f"Baixe/abra o app BRECHORISEE: {links['download']}",
        f"Sem app, entre pela área da cliente: {links.get('customer_home') or links['download']}",
        f"Como usar app/site: {links['tutorial']}",
    ])


def product_social_text(
    product: sqlite3.Row | dict[str, Any],
    request: Request,
    question: str = "",
    channel: str = "whatsapp",
    payment_link: str = "",
    pix_text: str = "",
) -> str:
    p = row_to_dict(product)
    channel = (channel or "whatsapp").lower()
    base = app_base_url(request)
    local_link = f"{base}/abrir-peca?id={p.get('id')}&origem={channel}"
    public_link = product_public_link(p, request, source=channel)
    app_link = product_deep_link(p.get("id") or "", p.get("code") or "")
    photo_link = f"{base}/static/uploads/{p.get('image_filename')}" if p.get("image_filename") else ""
    question = (question or "").strip()
    if not question:
        if channel == "instagram":
            question = "Essa peça combina com seu estilo. Quer que eu reserve para você?"
        else:
            question = "Quer saber mais sobre essa peça?"

    lines = [
        "Oi! ✨",
        "",
        question,
        "",
        f"{p.get('title') or 'Peça'}",
        f"Código: {p.get('code') or '-'}",
        f"Preço: {money(p.get('sale_price'))}",
    ]
    if p.get("size"):
        lines.append(f"Tamanho: {p.get('size')}")
    if p.get("brand"):
        lines.append(f"Marca: {p.get('brand')}")
    if p.get("color"):
        lines.append(f"Cor: {p.get('color')}")
    if p.get("style_tags"):
        lines.append(f"Estilo: {p.get('style_tags')}")
    if p.get("characteristics"):
        lines.append(f"Detalhes: {p.get('characteristics')}")

    lines += ["", "Foto da peça:"]
    lines.append(photo_link or "sem foto cadastrada")

    if payment_link:
        lines += ["", "Pagamento/cartão:", payment_link]
    if pix_text:
        lines += ["", "Pix:", pix_text]

    lines += [
        "",
        "Ver peça:",
        public_link,
        "",
        "Abrir no app BRECHORISEE:",
        app_link,
    ]

    if channel == "instagram":
        lines += [
            "",
            "Se quiser, responda com: QUERO ESSA 💌",
            "Peça única: reserva sujeita à disponibilidade.",
        ]
    else:
        lines += [
            "",
            "Link local da peça:",
            local_link,
        ]

    # Toda mensagem de venda também oferece o caminho pelo app e pelo navegador.
    lines += ["", brechorisee_customer_app_cta(request)]
    return "\n".join(lines)


def product_share_text(product: sqlite3.Row | dict[str, Any], request: Request, question: str = "") -> str:
    return product_social_text(product, request, question=question, channel="whatsapp")


def similar_products_for_share(product: sqlite3.Row | dict[str, Any], limit: int = 6) -> list[sqlite3.Row]:
    p = row_to_dict(product)
    params: list[Any] = [p.get("id")]
    clauses = ["id <> ?", "status='disponivel'"]
    sub: list[str] = []
    for col in ("garment_type", "size", "color", "brand"):
        value = (p.get(col) or "").strip() if isinstance(p.get(col), str) else p.get(col)
        if value:
            sub.append(f"{col} = ?")
            params.append(value)
    if not sub:
        return []
    sql = f"""
        SELECT *
        FROM products
        WHERE {' AND '.join(clauses)} AND ({' OR '.join(sub)})
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(limit)
    with get_db() as con:
        return con.execute(sql, params).fetchall()


def public_product_payload(product: sqlite3.Row | dict[str, Any], request: Request) -> dict[str, Any]:
    p = row_to_dict(product)
    settings = get_store_settings() if "get_store_settings" in globals() else {}
    photo = f"{app_base_url(request)}/static/uploads/{p.get('image_filename')}" if p.get("image_filename") else ""
    public_link = product_public_link(p, request, "publico")
    whatsapp_text = product_social_text(p, request, question="Oi! Tenho interesse nessa peça. Ela ainda está disponível?", channel="whatsapp")
    phone = str(settings.get("whatsapp") or "").replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    wa_url = f"https://wa.me/55{phone}?text=" if phone and not phone.startswith("55") else f"https://wa.me/{phone}?text=" if phone else "https://wa.me/?text="
    return {
        "product": p,
        "settings": settings,
        "photo": photo,
        "public_link": public_link,
        "whatsapp_url": wa_url + quote_plus(whatsapp_text),
        "instagram_url": instagram_profile_url(settings),
    }


def get_db() -> sqlite3.Connection:
    """Abre conexão SQLite preparada para uso real em loja.

    As PRAGMAs abaixo reduzem travamentos em momentos de venda, live e upload,
    ativam integridade referencial e mantêm leitura/escrita mais estáveis.
    """
    con = sqlite3.connect(DB_PATH, timeout=max(1.0, DB_BUSY_TIMEOUT_MS / 1000))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute(f"PRAGMA busy_timeout = {max(1000, DB_BUSY_TIMEOUT_MS)}")
    if DB_ENABLE_WAL:
        try:
            con.execute("PRAGMA journal_mode = WAL")
            con.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.DatabaseError:
            logger.debug("SQLite WAL indisponível nesta conexão.", exc_info=True)
    return con


def ensure_column(con: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    table_exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)).fetchone()
    if not table_exists:
        return
    existing = {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with get_db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                instagram TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                category TEXT,
                garment_type TEXT,
                size TEXT,
                brand TEXT,
                color TEXT,
                condition TEXT,
                measurements TEXT,
                characteristics TEXT,
                cost_price REAL DEFAULT 0,
                sale_price REAL NOT NULL,
                supplier_id INTEGER,
                status TEXT NOT NULL DEFAULT 'disponivel',
                image_filename TEXT,
                image_hash TEXT,
                avg_r REAL,
                avg_g REAL,
                avg_b REAL,
                created_at TEXT NOT NULL,
                sold_at TEXT,
                style_tags TEXT,
                season TEXT,
                target_audience TEXT,
                trend_label TEXT,
                last_ai_score REAL,
                last_ai_notes TEXT,
                last_ai_at TEXT,
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            );

            CREATE TABLE IF NOT EXISTS product_attribute_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_name TEXT NOT NULL,
                value TEXT NOT NULL,
                usage_count INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(field_name, value)
            );

            CREATE INDEX IF NOT EXISTS idx_product_attribute_options_field
                ON product_attribute_options(field_name, usage_count DESC, value);

            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_code TEXT NOT NULL UNIQUE,
                customer TEXT,
                payment_method TEXT,
                discount REAL DEFAULT 0,
                total REAL NOT NULL,
                paid REAL DEFAULT 0,
                change_value REAL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (sale_id) REFERENCES sales(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS inventory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
            
            CREATE TABLE IF NOT EXISTS product_interest_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_product_interest_product ON product_interest_events(product_id);
            CREATE INDEX IF NOT EXISTS idx_product_interest_created ON product_interest_events(created_at);

            CREATE TABLE IF NOT EXISTS live_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'aberta',
                notes TEXT,
                created_at TEXT NOT NULL,
                ended_at TEXT,
                recap_created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS live_session_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_session_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                action TEXT NOT NULL DEFAULT 'reconhecida',
                status_snapshot TEXT,
                product_code TEXT,
                product_title TEXT,
                product_price REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_live_session_items_session ON live_session_items(live_session_id);
            CREATE INDEX IF NOT EXISTS idx_live_session_items_product ON live_session_items(product_id);

            CREATE TABLE IF NOT EXISTS live_ignored_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_session_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(live_session_id, product_id),
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS live_recap_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_session_id INTEGER NOT NULL,
                title TEXT,
                caption TEXT,
                item_ids TEXT,
                status TEXT NOT NULL DEFAULT 'rascunho',
                created_at TEXT NOT NULL,
                posted_at TEXT,
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id)
            );

            CREATE TABLE IF NOT EXISTS product_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                filename TEXT NOT NULL,
                original_filename TEXT,
                notes TEXT,
                image_hash TEXT,
                avg_r REAL,
                avg_g REAL,
                avg_b REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_product_media_product ON product_media(product_id);
            CREATE INDEX IF NOT EXISTS idx_product_media_hash ON product_media(image_hash);


            CREATE TABLE IF NOT EXISTS sync_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL UNIQUE,
                device_name TEXT,
                last_seen_at TEXT,
                last_sync_at TEXT,
                status TEXT DEFAULT 'ativo'
            );

            CREATE TABLE IF NOT EXISTS offline_sync_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                client_op_id TEXT,
                op_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente',
                payload TEXT,
                result TEXT,
                conflict_notes TEXT,
                created_at TEXT NOT NULL,
                processed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_offline_sync_device ON offline_sync_events(device_id);
            CREATE INDEX IF NOT EXISTS idx_offline_sync_status ON offline_sync_events(status);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_offline_sync_unique_op ON offline_sync_events(device_id, client_op_id);

            CREATE TABLE IF NOT EXISTS sync_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT NOT NULL DEFAULT 'cloud',
                op_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sync_outbox_status ON sync_outbox(status);
            CREATE INDEX IF NOT EXISTS idx_sync_outbox_target ON sync_outbox(target);


            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                instagram TEXT,
                email TEXT,
                birthday TEXT,
                measurements TEXT,
                preferences TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                customer_id INTEGER,
                customer_name TEXT,
                expires_at TEXT,
                status TEXT NOT NULL DEFAULT 'ativa',
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS wishlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                customer_name TEXT,
                query TEXT NOT NULL,
                size TEXT,
                brand TEXT,
                color TEXT,
                style TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                category TEXT,
                amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS product_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER,
                name TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            );

            CREATE TABLE IF NOT EXISTS supplier_settlements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER,
                description TEXT,
                amount REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pendente',
                paid_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            );

            CREATE TABLE IF NOT EXISTS returns_exchanges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER,
                product_id INTEGER,
                customer_name TEXT,
                reason TEXT,
                action TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sale_id) REFERENCES sales(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS app_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'atendente',
                pin TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'aberta',
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_audit_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id INTEGER NOT NULL,
                product_id INTEGER,
                code TEXT,
                status TEXT NOT NULL DEFAULT 'encontrado',
                created_at TEXT NOT NULL,
                FOREIGN KEY (audit_id) REFERENCES stock_audits(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                channel TEXT,
                status TEXT NOT NULL DEFAULT 'rascunho',
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS marketing_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                title TEXT,
                caption TEXT,
                hashtags TEXT,
                media_ids TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS store_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                store_name TEXT DEFAULT 'BRECHORISEE',
                whatsapp TEXT,
                instagram TEXT,
                exchange_policy TEXT,
                default_reservation_hours INTEGER DEFAULT 24,
                card_fee_percent REAL DEFAULT 0,
                desired_margin_percent REAL DEFAULT 50,
                created_at TEXT,
                updated_at TEXT
            );


            CREATE TABLE IF NOT EXISTS customer_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login_at TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_accounts_phone ON customer_accounts(phone);


            CREATE TABLE IF NOT EXISTS customer_notification_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_account_id INTEGER NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                channel_app INTEGER NOT NULL DEFAULT 1,
                channel_whatsapp INTEGER NOT NULL DEFAULT 0,
                frequency TEXT NOT NULL DEFAULT 'moderado',
                quiet_hours_start TEXT DEFAULT '21:00',
                quiet_hours_end TEXT DEFAULT '09:00',
                last_notified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id)
            );

            CREATE TABLE IF NOT EXISTS customer_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_account_id INTEGER NOT NULL,
                product_id INTEGER,
                notification_type TEXT NOT NULL DEFAULT 'nova_peca',
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                image_filename TEXT,
                action_url TEXT,
                status TEXT NOT NULL DEFAULT 'pendente',
                scheduled_at TEXT NOT NULL,
                sent_at TEXT,
                read_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_customer_notifications_account ON customer_notifications(customer_account_id, status, scheduled_at);
            CREATE INDEX IF NOT EXISTS idx_customer_notifications_product ON customer_notifications(product_id);

            CREATE TABLE IF NOT EXISTS admin_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL,
                last_login_at TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS auth_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_type TEXT NOT NULL,
                account_id INTEGER,
                action TEXT NOT NULL,
                ip TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'info',
                actor_type TEXT,
                actor_id TEXT,
                path TEXT,
                details TEXT,
                ip TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL
            );


            CREATE TABLE IF NOT EXISTS online_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_code TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL,
                customer_phone TEXT,
                customer_instagram TEXT,
                delivery_method TEXT DEFAULT 'retirada',
                address TEXT,
                delivery_lat REAL,
                delivery_lng REAL,
                delivery_maps_url TEXT,
                payment_method TEXT DEFAULT 'pix',
                pix_text TEXT,
                payment_link TEXT,
                subtotal REAL NOT NULL DEFAULT 0,
                discount REAL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'aguardando_pagamento',
                notes TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                paid_at TEXT,
                sale_id INTEGER,
                public_token TEXT,
                customer_account_id INTEGER,
                payment_status TEXT DEFAULT 'pendente',
                payment_confirmed_by TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS online_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                code TEXT,
                title TEXT,
                price REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'reservado',
                created_at TEXT NOT NULL,
                FOREIGN KEY (order_id) REFERENCES online_orders(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_online_orders_status ON online_orders(status);
            CREATE INDEX IF NOT EXISTS idx_online_order_items_order ON online_order_items(order_id);

            CREATE TABLE IF NOT EXISTS cash_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opened_by TEXT,
                opening_amount REAL DEFAULT 0,
                closing_amount REAL,
                expected_amount REAL,
                status TEXT NOT NULL DEFAULT 'aberto',
                notes TEXT,
                opened_at TEXT NOT NULL,
                closed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS cash_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                movement_type TEXT NOT NULL,
                description TEXT,
                amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT,
                sale_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES cash_sessions(id),
                FOREIGN KEY (sale_id) REFERENCES sales(id)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT,
                action TEXT NOT NULL,
                entity TEXT,
                entity_id TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS maintenance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                result TEXT,
                created_at TEXT NOT NULL
            );


            CREATE TABLE IF NOT EXISTS telegram_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                direction TEXT NOT NULL DEFAULT 'outbound',
                chat_id TEXT,
                username TEXT,
                text TEXT,
                command TEXT,
                payload TEXT,
                status TEXT NOT NULL DEFAULT 'pendente',
                related_type TEXT,
                related_id INTEGER,
                error TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_telegram_messages_created ON telegram_messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_telegram_messages_status ON telegram_messages(status);
            CREATE INDEX IF NOT EXISTS idx_telegram_messages_related ON telegram_messages(related_type, related_id);

            CREATE TABLE IF NOT EXISTS payment_proofs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL DEFAULT 'telegram',
                order_type TEXT,
                order_id INTEGER,
                customer_name TEXT,
                file_id TEXT,
                caption TEXT,
                status TEXT NOT NULL DEFAULT 'recebido',
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_payment_proofs_order ON payment_proofs(order_type, order_id);
            CREATE INDEX IF NOT EXISTS idx_payment_proofs_status ON payment_proofs(status);

            CREATE TABLE IF NOT EXISTS notebook_import_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL DEFAULT 'camera',
                image_filename TEXT,
                image_hash TEXT,
                ocr_engine TEXT,
                ocr_text TEXT,
                edited_text TEXT,
                parse_payload TEXT,
                status TEXT NOT NULL DEFAULT 'rascunho',
                confidence REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                applied_at TEXT
            );

            CREATE TABLE IF NOT EXISTS notebook_import_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                line_no INTEGER NOT NULL DEFAULT 0,
                entry_type TEXT NOT NULL DEFAULT 'unknown',
                customer_name TEXT,
                product_title TEXT,
                amount REAL,
                date_text TEXT,
                sale_group TEXT,
                raw_line TEXT,
                notes TEXT,
                confidence REAL DEFAULT 0,
                confirmed INTEGER NOT NULL DEFAULT 1,
                linked_product_id INTEGER,
                linked_sale_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (batch_id) REFERENCES notebook_import_batches(id),
                FOREIGN KEY (linked_product_id) REFERENCES products(id),
                FOREIGN KEY (linked_sale_id) REFERENCES sales(id)
            );

            CREATE TABLE IF NOT EXISTS whatsapp_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT,
                phone TEXT,
                delivery_type TEXT NOT NULL DEFAULT 'retirada',
                pickup_location TEXT,
                address TEXT,
                payment_method TEXT,
                payment_link TEXT,
                pix_key TEXT,
                pix_copy_paste TEXT,
                status TEXT NOT NULL DEFAULT 'aguardando_pagamento',
                reservation_expires_at TEXT,
                notes TEXT,
                total REAL NOT NULL DEFAULT 0,
                sale_id INTEGER,
                created_at TEXT NOT NULL,
                paid_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (sale_id) REFERENCES sales(id)
            );

            CREATE TABLE IF NOT EXISTS whatsapp_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                price REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (order_id) REFERENCES whatsapp_orders(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_whatsapp_orders_status ON whatsapp_orders(status);
            CREATE INDEX IF NOT EXISTS idx_whatsapp_order_items_order ON whatsapp_order_items(order_id);

            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                customer_name TEXT,
                phone TEXT,
                address TEXT,
                city TEXT,
                status TEXT NOT NULL DEFAULT 'pendente',
                scheduled_at TEXT,
                delivered_at TEXT,
                route_notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (sale_id) REFERENCES sales(id)
            );

            CREATE TABLE IF NOT EXISTS delivery_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                delivery_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente',
                delivered_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (delivery_id) REFERENCES deliveries(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_deliveries_sale ON deliveries(sale_id);
            CREATE INDEX IF NOT EXISTS idx_delivery_items_delivery ON delivery_items(delivery_id);
            """
        )

        # Migra bancos criados em versões anteriores sem apagar dados.
        ensure_column(con, "products", "style_tags", "TEXT")
        ensure_column(con, "products", "season", "TEXT")
        ensure_column(con, "products", "target_audience", "TEXT")
        ensure_column(con, "products", "trend_label", "TEXT")
        ensure_column(con, "products", "last_ai_score", "REAL")
        ensure_column(con, "products", "last_ai_notes", "TEXT")
        ensure_column(con, "products", "last_ai_at", "TEXT")
        ensure_column(con, "products", "sync_origin", "TEXT")
        ensure_column(con, "products", "cloud_synced_at", "TEXT")
        ensure_column(con, "products", "sync_updated_at", "TEXT")
        ensure_column(con, "products", "archived_at", "TEXT")
        ensure_column(con, "products", "deleted_at", "TEXT")
        ensure_column(con, "sales", "sync_origin", "TEXT")
        ensure_column(con, "sales", "cloud_synced_at", "TEXT")
        ensure_column(con, "customer_notifications", "match_score", "REAL")
        ensure_column(con, "customer_notifications", "ai_reason", "TEXT")
        ensure_column(con, "customer_notifications", "message_channel", "TEXT")
        ensure_column(con, "customer_notifications", "personalized", "INTEGER DEFAULT 0")
        ensure_column(con, "customer_notifications", "live_session_id", "INTEGER")
        ensure_column(con, "customer_accounts", "instagram", "TEXT")
        ensure_column(con, "customer_accounts", "style_preferences", "TEXT")
        ensure_column(con, "customer_accounts", "app_origin", "TEXT")
        ensure_column(con, "customers", "instagram", "TEXT")
        ensure_column(con, "customers", "preferences", "TEXT")
        ensure_column(con, "customers", "default_delivery_method", "TEXT")
        ensure_column(con, "customers", "address", "TEXT")
        ensure_column(con, "customers", "payment_method", "TEXT")
        ensure_column(con, "customers", "pix_text", "TEXT")
        ensure_column(con, "customers", "payment_link", "TEXT")
        ensure_column(con, "customers", "checkout_notes", "TEXT")
        ensure_column(con, "customers", "delivery_lat", "REAL")
        ensure_column(con, "customers", "delivery_lng", "REAL")
        ensure_column(con, "customers", "delivery_maps_url", "TEXT")

        ensure_column(con, "deliveries", "delivery_lat", "REAL")
        ensure_column(con, "deliveries", "delivery_lng", "REAL")
        ensure_column(con, "deliveries", "delivery_maps_url", "TEXT")
        ensure_column(con, "deliveries", "delivery_started_at", "TEXT")
        ensure_column(con, "deliveries", "delivery_eta_minutes", "INTEGER DEFAULT 35")
        ensure_column(con, "deliveries", "courier_lat", "REAL")
        ensure_column(con, "deliveries", "courier_lng", "REAL")
        ensure_column(con, "deliveries", "courier_maps_url", "TEXT")
        ensure_column(con, "deliveries", "tracking_updated_at", "TEXT")

        ensure_column(con, "online_orders", "delivery_lat", "REAL")
        ensure_column(con, "online_orders", "delivery_lng", "REAL")
        ensure_column(con, "online_orders", "delivery_maps_url", "TEXT")
        ensure_column(con, "online_orders", "delivery_started_at", "TEXT")
        ensure_column(con, "online_orders", "delivery_eta_minutes", "INTEGER DEFAULT 35")
        ensure_column(con, "online_orders", "courier_lat", "REAL")
        ensure_column(con, "online_orders", "courier_lng", "REAL")
        ensure_column(con, "online_orders", "courier_maps_url", "TEXT")
        ensure_column(con, "online_orders", "tracking_updated_at", "TEXT")
        ensure_column(con, "online_orders", "public_token", "TEXT")
        ensure_column(con, "online_orders", "customer_account_id", "INTEGER")
        ensure_column(con, "online_orders", "payment_status", "TEXT DEFAULT 'pendente'")
        ensure_column(con, "online_orders", "payment_confirmed_by", "TEXT")
        ensure_column(con, "online_orders", "updated_at", "TEXT")

        # Migração segura dos pedidos do WhatsApp.
        ensure_column(con, "whatsapp_orders", "pickup_location", "TEXT")
        ensure_column(con, "whatsapp_orders", "payment_link", "TEXT")
        ensure_column(con, "whatsapp_orders", "pix_key", "TEXT")
        ensure_column(con, "whatsapp_orders", "pix_copy_paste", "TEXT")
        ensure_column(con, "whatsapp_orders", "sale_id", "INTEGER")

        ensure_column(con, "telegram_messages", "related_type", "TEXT")
        ensure_column(con, "telegram_messages", "related_id", "INTEGER")
        ensure_column(con, "payment_proofs", "order_type", "TEXT")
        ensure_column(con, "payment_proofs", "order_id", "INTEGER")

        ensure_column(con, "live_sessions", "started_at", "TEXT")
        ensure_column(con, "live_sessions", "current_product_id", "INTEGER")
        ensure_column(con, "live_sessions", "current_product_set_at", "TEXT")
        ensure_column(con, "live_sessions", "current_product_source", "TEXT")
        ensure_column(con, "live_sessions", "current_product_event_id", "INTEGER")
        ensure_column(con, "live_sessions", "recording_filename", "TEXT")
        ensure_column(con, "live_sessions", "optimized_filename", "TEXT")
        ensure_column(con, "live_sessions", "snapshot_filename", "TEXT")
        ensure_column(con, "live_sessions", "ended_action", "TEXT")
        ensure_column(con, "live_sessions", "optimized_at", "TEXT")
        ensure_column(con, "live_sessions", "source_platform", "TEXT DEFAULT 'brechorisee'")
        ensure_column(con, "live_sessions", "instagram_live_url", "TEXT")
        ensure_column(con, "live_sessions", "brechorisee_watch_enabled", "INTEGER DEFAULT 1")
        ensure_column(con, "live_sessions", "instagram_control_started_at", "TEXT")
        ensure_column(con, "live_session_items", "second_offset", "REAL DEFAULT 0")
        ensure_column(con, "live_session_items", "clip_filename", "TEXT")
        ensure_column(con, "live_session_items", "clip_start_seconds", "REAL")
        ensure_column(con, "live_session_items", "clip_end_seconds", "REAL")
        ensure_column(con, "live_session_items", "clip_created_at", "TEXT")
        ensure_column(con, "live_session_items", "clip_notes", "TEXT")
        ensure_column(con, "live_reservation_queue", "customer_account_id", "INTEGER")
        ensure_column(con, "live_reservation_queue", "sale_id", "INTEGER")
        ensure_column(con, "live_customer_carts", "public_token", "TEXT")
        ensure_column(con, "live_customer_carts", "customer_account_id", "INTEGER")
        ensure_column(con, "sales", "customer_account_id", "INTEGER")
        ensure_column(con, "sales", "source", "TEXT")
        ensure_column(con, "sales", "source_ref_id", "INTEGER")
        ensure_column(con, "sales", "paid_at", "TEXT")

        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS live_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_session_id INTEGER NOT NULL,
                author_name TEXT,
                message TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'cliente',
                pinned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id)
            );

            CREATE TABLE IF NOT EXISTS live_reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_session_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                author_name TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id)
            );

            CREATE TABLE IF NOT EXISTS live_markers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_session_id INTEGER NOT NULL,
                product_id INTEGER,
                marker_type TEXT NOT NULL,
                label TEXT,
                second_offset REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS live_viewers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_session_id INTEGER NOT NULL,
                viewer_key TEXT NOT NULL,
                customer_account_id INTEGER,
                last_seen_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(live_session_id, viewer_key),
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_live_comments_session ON live_comments(live_session_id);
            CREATE INDEX IF NOT EXISTS idx_live_reactions_session ON live_reactions(live_session_id);
            CREATE INDEX IF NOT EXISTS idx_live_markers_session ON live_markers(live_session_id);
            CREATE INDEX IF NOT EXISTS idx_live_viewers_session ON live_viewers(live_session_id, last_seen_at);
            """
        )

        con.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_products_status_created ON products(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_products_code ON products(code);
            CREATE INDEX IF NOT EXISTS idx_products_title ON products(title);
            CREATE INDEX IF NOT EXISTS idx_products_deleted_archived ON products(deleted_at, archived_at);
            CREATE INDEX IF NOT EXISTS idx_sales_created_at ON sales(created_at);
            CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id);
            CREATE INDEX IF NOT EXISTS idx_sale_items_product ON sale_items(product_id);
            CREATE INDEX IF NOT EXISTS idx_inventory_events_product_created ON inventory_events(product_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_reservations_status_expires ON reservations(status, expires_at);
            CREATE INDEX IF NOT EXISTS idx_online_orders_status_created ON online_orders(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_live_sessions_status_started ON live_sessions(status, started_at);
            CREATE INDEX IF NOT EXISTS idx_live_items_session_action ON live_session_items(live_session_id, action);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_online_orders_public_token ON online_orders(public_token) WHERE public_token IS NOT NULL AND TRIM(public_token)<>'';
            CREATE INDEX IF NOT EXISTS idx_online_orders_customer_account ON online_orders(customer_account_id, created_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_accounts_email_unique ON admin_accounts(LOWER(email)) WHERE email IS NOT NULL AND TRIM(email)<>'';
            CREATE INDEX IF NOT EXISTS idx_security_events_created ON security_events(created_at, severity);
            CREATE INDEX IF NOT EXISTS idx_sales_source ON sales(source, source_ref_id);
            CREATE INDEX IF NOT EXISTS idx_notebook_imports_status ON notebook_import_batches(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_notebook_lines_batch ON notebook_import_lines(batch_id, line_no);
            CREATE INDEX IF NOT EXISTS idx_notebook_lines_sale ON notebook_import_lines(linked_sale_id);
            """
        )

        # Garante tokens públicos para pedidos/carrinhos antigos sem expor IDs sequenciais.
        try:
            for row in con.execute("SELECT id FROM online_orders WHERE public_token IS NULL OR TRIM(public_token)=''").fetchall():
                ensure_online_order_token(con, int(row["id"]))
        except Exception:
            logger.warning("Não foi possível completar migração de tokens públicos.", exc_info=True)

        count = con.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
        if count == 0:
            con.execute(
                "INSERT INTO suppliers(name, phone, instagram, notes, created_at) VALUES(?,?,?,?,?)",
                ("Consignação / Avulsa", "", "", "Fornecedor padrão para peças sem cadastro específico.", now_iso()),
            )

        if con.execute("SELECT COUNT(*) FROM store_settings").fetchone()[0] == 0:
            con.execute(
                "INSERT INTO store_settings(id, store_name, whatsapp, instagram, exchange_policy, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (1, "BRECHORISEE", "", "@brechorisee", "Trocas conforme política da loja. Peças únicas e previamente conferidas.", now_iso(), now_iso()),
            )

        seed_product_attribute_options(con)

        if con.execute("SELECT COUNT(*) FROM app_users").fetchone()[0] == 0:
            default_pin = os.getenv("BRECHORISEE_DEFAULT_PIN", "").strip()
            if not default_pin:
                default_pin = "".join(secrets.choice(string.digits) for _ in range(6))
            con.execute(
                "INSERT INTO app_users(name, role, pin, active, created_at) VALUES(?,?,?,?,?)",
                ("Administradora", "admin", default_pin, 1, now_iso()),
            )



ADMIN_ROUTE_PREFIXES = (
    "/products", "/suppliers", "/cashier", "/sales", "/recognize", "/reports", "/buscas-pecas",
    "/stock-history", "/ai", "/marketing", "/instagram-studio", "/clientes-inteligentes", "/gestao",
    "/profissional", "/backups", "/export", "/deliveries", "/whatsapp-vendas",
    "/notificacoes", "/ia-clientes", "/live", "/labels", "/loja-admin",
    "/sincronizacao", "/celular", "/android", "/usuarios", "/telegram", "/caderno", "/bot-risee", "/atendimento", "/desejos-aquisicoes",
    "/api/form-suggestions", "/api/product-by-code", "/api/products/search",
    "/api/generate-product-code", "/api/product-autofill", "/api/product-attribute-options", "/api/checkout", "/api/products",
    "/api/product-advice", "/api/reports", "/api/recognize", "/api/live",
    "/api/wishlist-matches", "/api/deliveries", "/api/ia-clientes",
    "/api/sync", "/api/android/sync", "/api/admin", "/api/telegram", "/api/caderno", "/api/bot-risee", "/api/buscas-pecas", "/api/desejos-aquisicoes",
)
PUBLIC_ROUTE_PREFIXES = (
    "/static", "/cliente", "/loja", "/online", "/site", "/instagram", "/vitrine/peca",
    "/live/peca-atual", "/live/companion", "/live/carrinho", "/app/cliente",
    "/api/public-live", "/api/live/peca-atual", "/api/live/companion", "/api/telegram/webhook", "/api/instagram-assistant",
    "/abrir-peca", "/service-worker.js", "/favicon.ico", "/api/cliente",
    "/api/server-info",
)
PUBLIC_RAW_PREFIXES = ("/p/",)
ADMIN_AUTH_PATHS = ("/admin-acesso", "/admin-acesso/criar", "/admin-acesso/login", "/admin-recuperar", "/admin-recuperar/salvar", "/admin-sair")
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}


def _path_matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def is_public_route(path: str) -> bool:
    return (
        path in ADMIN_AUTH_PATHS
        or any(_path_matches(path, prefix) for prefix in PUBLIC_ROUTE_PREFIXES)
        or any(path.startswith(prefix) for prefix in PUBLIC_RAW_PREFIXES)
    )


def is_admin_route(path: str) -> bool:
    if path == "/":
        return True
    if is_public_route(path):
        return False
    return any(_path_matches(path, prefix) for prefix in ADMIN_ROUTE_PREFIXES)


def _wants_json(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return request.url.path.startswith("/api/") or "application/json" in accept


def sync_token_is_valid(request: Request) -> bool:
    if not BRECHORISEE_SYNC_TOKEN:
        return False
    token = (request.headers.get("x-brechorisee-sync-token") or request.query_params.get("sync_token") or "").strip()
    return bool(token) and hmac.compare_digest(token, BRECHORISEE_SYNC_TOKEN)


def _admin_cookie_signature(account_id: int, expires: int) -> str:
    payload = f"{account_id}|{expires}"
    return hmac.new(BRECHORISEE_SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_admin_cookie_value(account_id: int, days: int = AUTH_SESSION_DAYS) -> str:
    expires = int(time.time()) + max(1, int(days)) * 24 * 60 * 60
    signature = _admin_cookie_signature(int(account_id), expires)
    return f"v1|{int(account_id)}|{expires}|{signature}"


def parse_admin_cookie_value(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        version, account_id_text, expires_text, signature = str(raw).split("|", 3)
        if version != "v1":
            return None
        account_id = int(account_id_text)
        expires = int(expires_text)
        if account_id < 1 or expires < int(time.time()):
            return None
        expected = _admin_cookie_signature(account_id, expires)
        if not hmac.compare_digest(signature, expected):
            return None
        return account_id
    except Exception:
        return None


def is_active_admin_account(account_id: int | None) -> bool:
    if not account_id:
        return False
    try:
        with get_db() as con:
            return bool(con.execute("SELECT 1 FROM admin_accounts WHERE id=? AND active=1", (int(account_id),)).fetchone())
    except Exception:
        return False


def _request_uses_https(request: Request | None) -> bool:
    if not request:
        return False
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").lower()
    return request.url.scheme == "https" or forwarded_proto == "https"


def set_admin_cookie(response: Response, account_id: int, request: Request | None = None) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        make_admin_cookie_value(account_id),
        max_age=AUTH_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=_request_uses_https(request),
        samesite="lax",
    )


def _customer_cookie_signature(account_id: int, expires: int) -> str:
    payload = f"cliente|{account_id}|{expires}"
    return hmac.new(BRECHORISEE_SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_customer_cookie_value(account_id: int, days: int = CUSTOMER_SESSION_DAYS) -> str:
    expires = int(time.time()) + max(1, int(days)) * 24 * 60 * 60
    signature = _customer_cookie_signature(int(account_id), expires)
    return f"v1|{int(account_id)}|{expires}|{signature}"


def parse_customer_cookie_value(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        version, account_id_text, expires_text, signature = str(raw).split("|", 3)
        if version != "v1":
            return None
        account_id = int(account_id_text)
        expires = int(expires_text)
        if account_id < 1 or expires < int(time.time()):
            return None
        expected = _customer_cookie_signature(account_id, expires)
        if not hmac.compare_digest(signature, expected):
            return None
        return account_id
    except Exception:
        return None


def set_customer_cookie(response: Response, account_id: int, request: Request | None = None) -> None:
    response.set_cookie(
        CUSTOMER_COOKIE_NAME,
        make_customer_cookie_value(account_id),
        max_age=CUSTOMER_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=_request_uses_https(request),
        samesite="lax",
    )


def check_login_rate_limit(request: Request) -> bool:
    """Limite simples em memória para reduzir força bruta no login admin."""
    key = request.client.host if request and request.client else "unknown"
    now = time.time()
    window = 10 * 60
    attempts = [ts for ts in _LOGIN_ATTEMPTS.get(key, []) if now - ts < window]
    if len(attempts) >= 10:
        _LOGIN_ATTEMPTS[key] = attempts
        return False
    attempts.append(now)
    _LOGIN_ATTEMPTS[key] = attempts
    return True


def reset_login_rate_limit(request: Request) -> None:
    key = request.client.host if request and request.client else "unknown"
    _LOGIN_ATTEMPTS.pop(key, None)


@app.middleware("http")
async def admin_access_guard(request: Request, call_next):
    path = str(request.url.path or "/")
    request_id = (request.headers.get("x-request-id") or secrets.token_hex(8)).strip()[:64]
    started_at = time.perf_counter()

    if is_admin_route(path):
        sync_api = path.startswith("/api/android/sync") or path.startswith("/api/sync")
        account_id = parse_admin_cookie_value(request.cookies.get(AUTH_COOKIE_NAME))
        if not (sync_api and sync_token_is_valid(request)) and not is_active_admin_account(account_id):
            if _wants_json(request):
                response = JSONResponse({"ok": False, "message": "Acesso administrativo obrigatório."}, status_code=401)
            else:
                next_url = quote_plus(str(request.url.path or "/"))
                response = RedirectResponse(url=f"/admin-acesso?next={next_url}", status_code=303)
            response.headers["X-Request-ID"] = request_id
            return response

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Falha inesperada em %s %s request_id=%s", request.method, path, request_id)
        raise

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    response.headers.setdefault("X-Request-ID", request_id)
    response.headers.setdefault("X-Response-Time-ms", str(elapsed_ms))
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
    if _request_uses_https(request):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if is_admin_route(path):
        response.headers.setdefault("Cache-Control", "no-store")
    return response



# ---------------------------------------------------------------------------
# Persistência grátis para Render Free sem Disk:
# backup/restore automático do SQLite em um repositório GitHub privado.
#
# Uso opcional para backup externo:
# BRECHORISEE_DB_PATH=/tmp/brechorisee.db
# BRECHORISEE_GITHUB_DB_BACKUP=1
# BRECHORISEE_GITHUB_TOKEN=COLE_TOKEN_GITHUB_AQUI
# BRECHORISEE_GITHUB_REPO=usuario/repositorio-privado-de-dados
# BRECHORISEE_GITHUB_DB_FILE=brechorisee.db
# ---------------------------------------------------------------------------

_GITHUB_DB_BACKUP_LOCK = threading.Lock()
_GITHUB_DB_BACKUP_RUNNING = False
_GITHUB_DB_LAST_BACKUP_AT = 0.0


def github_db_backup_enabled() -> bool:
    return os.getenv("BRECHORISEE_GITHUB_DB_BACKUP", "").strip().lower() in {"1", "true", "sim", "yes", "on"}


def github_db_config() -> dict[str, str]:
    return {
        "token": os.getenv("BRECHORISEE_GITHUB_TOKEN", "").strip(),
        "repo": os.getenv("BRECHORISEE_GITHUB_REPO", "").strip(),
        "path": os.getenv("BRECHORISEE_GITHUB_DB_FILE", "brechorisee.db").strip().lstrip("/") or "brechorisee.db",
        "branch": os.getenv("BRECHORISEE_GITHUB_BRANCH", "main").strip() or "main",
    }


def github_api_request(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | bytes]:
    cfg = github_db_config()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "BRECHORISEE",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return resp.status, json.loads(raw.decode("utf-8") or "{}")
            return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return exc.code, raw
    except Exception as exc:
        logger.warning("Falha ao comunicar com GitHub DB backup: %s", exc)
        return 0, {}


def github_db_contents_url() -> str:
    cfg = github_db_config()
    safe_path = quote_plus(cfg["path"]).replace("%2F", "/")
    return f"https://api.github.com/repos/{cfg['repo']}/contents/{safe_path}"


def github_db_download_if_needed(force: bool = False) -> bool:
    """Restaura o banco do GitHub para /tmp antes do init_db, quando configurado.

    Retorna True quando um banco foi baixado. Se não houver arquivo remoto ainda,
    o app segue criando um banco novo normalmente.
    """
    if not github_db_backup_enabled():
        return False
    cfg = github_db_config()
    if not cfg["token"] or not cfg["repo"]:
        logger.warning("BRECHORISEE_GITHUB_DB_BACKUP ativo, mas token/repo não foram configurados.")
        return False
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0 and not force:
        return False

    url = github_db_contents_url() + f"?ref={quote_plus(cfg['branch'])}"
    status, payload = github_api_request("GET", url)
    if status == 404:
        logger.info("Nenhum banco remoto encontrado no GitHub ainda; será criado no primeiro backup.")
        return False
    if status != 200 or not isinstance(payload, dict):
        logger.warning("Não foi possível baixar banco remoto do GitHub. Status=%s", status)
        return False

    content = str(payload.get("content") or "").replace("\n", "")
    if not content:
        logger.warning("Arquivo remoto do banco está vazio ou inválido.")
        return False
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DB_PATH.with_suffix(DB_PATH.suffix + ".download")
    tmp_path.write_bytes(base64.b64decode(content))
    tmp_path.replace(DB_PATH)
    logger.info("Banco BRECHORISEE restaurado do GitHub em %s", DB_PATH)
    return True


def github_db_backup_now(reason: str = "manual") -> bool:
    """Envia o SQLite atual para GitHub Contents API.

    Opcional para backup externo do banco SQLite.
    Use repositório privado para proteger os dados.
    """
    global _GITHUB_DB_BACKUP_RUNNING, _GITHUB_DB_LAST_BACKUP_AT
    if not github_db_backup_enabled():
        return False
    cfg = github_db_config()
    if not cfg["token"] or not cfg["repo"]:
        logger.warning("Backup GitHub ignorado: configure BRECHORISEE_GITHUB_TOKEN e BRECHORISEE_GITHUB_REPO.")
        return False
    if not DB_PATH.exists() or DB_PATH.stat().st_size <= 0:
        return False

    with _GITHUB_DB_BACKUP_LOCK:
        if _GITHUB_DB_BACKUP_RUNNING:
            return False
        _GITHUB_DB_BACKUP_RUNNING = True
    try:
        # Garante que mudanças em WAL sejam incorporadas antes de enviar o arquivo .db.
        try:
            with sqlite3.connect(DB_PATH, timeout=5) as con:
                con.execute("PRAGMA wal_checkpoint(FULL)")
        except Exception:
            pass

        db_bytes = DB_PATH.read_bytes()
        url = github_db_contents_url()
        status, current = github_api_request("GET", url + f"?ref={quote_plus(cfg['branch'])}")
        sha = current.get("sha") if status == 200 and isinstance(current, dict) else None
        if status not in {200, 404}:
            logger.warning("Backup GitHub não encontrou estado remoto. Status=%s", status)
            return False

        payload: dict[str, Any] = {
            "message": f"Backup banco BRECHORISEE ({reason})",
            "content": base64.b64encode(db_bytes).decode("ascii"),
            "branch": cfg["branch"],
        }
        if sha:
            payload["sha"] = sha
        put_status, put_payload = github_api_request("PUT", url, payload)
        if put_status in {200, 201}:
            _GITHUB_DB_LAST_BACKUP_AT = time.time()
            logger.info("Backup GitHub do banco BRECHORISEE concluído (%s).", reason)
            return True
        logger.warning("Falha no backup GitHub do banco. Status=%s Payload=%s", put_status, put_payload)
        return False
    finally:
        with _GITHUB_DB_BACKUP_LOCK:
            _GITHUB_DB_BACKUP_RUNNING = False


def schedule_github_db_backup(reason: str = "auto") -> None:
    if not github_db_backup_enabled():
        return
    min_interval = int(os.getenv("BRECHORISEE_GITHUB_DB_BACKUP_INTERVAL_SECONDS", "45") or "45")
    if time.time() - _GITHUB_DB_LAST_BACKUP_AT < max(10, min_interval):
        return
    threading.Thread(target=github_db_backup_now, kwargs={"reason": reason}, daemon=True).start()



@app.on_event("startup")
def startup_event() -> None:
    github_db_download_if_needed()
    init_db()
    init_live_central_schema()
    register_schema_version()
    if not SECRET_KEY_CONFIGURED:
        logger.warning("BRECHORISEE_SECRET_KEY não foi definido; configure uma chave aleatória antes de usar em produção.")
    start_auto_sync_worker()
    logger.info("BRECHORISEE %s iniciado em modo %s usando banco %s", APP_VERSION, BRECHORISEE_ENV, DB_PATH)

@app.middleware("http")
async def automatic_sync_tick(request: Request, call_next):
    response = await call_next(request)
    try:
        # Em servidor local, a sincronização roda automaticamente de tempos em tempos
        # e também após ações importantes sem exigir botão.
        path = str(request.url.path or "")
        if cloud_sync_url() and not path.startswith("/static") and not path.startswith("/api/android/sync"):
            if time.time() - _LAST_AUTO_SYNC_AT > max(30, AUTO_SYNC_INTERVAL_SECONDS):
                threading.Thread(target=run_auto_cloud_sync, kwargs={"force": True}, daemon=True).start()
    except Exception:
        pass
    try:
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and not str(request.url.path or "").startswith("/static"):
            schedule_github_db_backup(f"{request.method} {request.url.path}")
    except Exception:
        pass
    return response



def slugify(value: str) -> str:
    value = value.lower()
    value = re_sub = "".join(ch if ch.isalnum() else "-" for ch in value)
    value = "-".join(part for part in value.split("-") if part)
    return value[:60] or "peca"


FRUIT_CODE_WORDS = [
    "AMORA", "ACAI", "CACAU", "CAJU", "CEREJA", "FIGO", "GOIABA", "KIWI",
    "LARANJA", "LIMAO", "MACA", "MANGA", "MARACUJA", "MELAO", "MORANGO",
    "PESSEGO", "PITAYA", "TANGERINA", "UVA", "JABUTICABA"
]

PRINT_KEYWORDS = [
    ("FLORAL", ["floral", "flor", "flores"]),
    ("LISTRADO", ["listrado", "listra", "listras"]),
    ("POA", ["poa", "poá", "bolinha", "bolinhas"]),
    ("XADREZ", ["xadrez"]),
    ("ANIMAL", ["animal print", "animalprint", "onça", "onca", "zebra", "cobra", "leopardo"]),
    ("GEOMETRICO", ["geometrico", "geométrico"]),
    ("ABSTRATO", ["abstrato"]),
    ("TIEDYE", ["tie dye", "tie-dye"]),
    ("BORDADO", ["bordado", "bordada"]),
    ("RENDA", ["renda"]),
    ("CROCHE", ["croche", "crochê"]),
    ("JEANS", ["jeans", "denim"]),
    ("BRILHO", ["brilho", "paete", "paetê", "metalizado", "glitter"]),
    ("LISO", ["liso", "básico", "basico", "minimalista"]),
]

CODE_STOP_WORDS = {
    "A", "AS", "O", "OS", "E", "DE", "DA", "DO", "DAS", "DOS", "COM",
    "SEM", "PARA", "POR", "EM", "NA", "NO", "NAS", "NOS", "UM", "UMA",
    "PECA", "ROUPA", "BRECHO", "BRECHORISEE", "MODA"
}


def normalize_code_token(value: Any, default: str = "PECA", max_len: int = 14) -> str:
    """Transforma textos em código legível para etiqueta/QR."""
    text = str(value or "").strip()
    if not text:
        text = default
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.upper()
    text = "".join(ch if ch.isalnum() else "-" for ch in text)
    parts = [part for part in text.split("-") if part]
    token = "-".join(parts) or default
    token = token[:max_len].strip("-")
    return token or default


def single_code_word(value: Any, default: str = "", max_len: int = 18) -> str:
    """Extrai apenas um nome para o código: NOME-001."""
    token = normalize_code_token(value, default="", max_len=80)
    parts = [part for part in token.split("-") if part]
    for part in parts:
        clean = "".join(ch for ch in part if ch.isalnum())
        if clean and clean not in CODE_STOP_WORDS:
            return clean[:max_len]
    for part in parts:
        clean = "".join(ch for ch in part if ch.isalnum())
        if clean:
            return clean[:max_len]
    return default[:max_len] if default else ""


def choose_fruit_word(*values: Any) -> str:
    seed = "|".join(str(v or "") for v in values).strip().lower()
    if not seed:
        return random.choice(FRUIT_CODE_WORDS)
    total = sum((i + 1) * ord(ch) for i, ch in enumerate(seed))
    return FRUIT_CODE_WORDS[total % len(FRUIT_CODE_WORDS)]


def detect_print_code(*values: Any) -> str:
    text = " ".join(str(v or "") for v in values).lower()
    for label, keywords in PRINT_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return label
    if any(word in text for word in ["estampa", "estampado", "estampada"]):
        return "ESTAMPADO"
    return "LISO"


def choose_single_code_name(
    title: str = "",
    category: str = "",
    garment_type: str = "",
    color: str = "",
    brand: str = "",
    characteristics: str = "",
    style_tags: str = "",
) -> str:
    """Escolhe um único nome com base na peça.

    O código final sempre fica curto: NOME-001.
    O nome pode vir do tipo, estampa, marca, cor ou de uma fruta estilizada.
    """
    print_name = detect_print_code(title, characteristics, style_tags)

    # Prioridade prática para etiqueta: primeiro o nome/tipo da peça.
    # Assim, ao cadastrar "Bolsa" com categoria "Feminino", o código fica BOLSA-001,
    # e não FEMININO-001.
    candidates = [
        garment_type,
        title,
    ]
    if print_name != "LISO":
        candidates.append(print_name)
    candidates.extend([
        brand,
        color,
        style_tags,
        characteristics,
        category,
    ])

    for candidate in candidates:
        word = single_code_word(candidate)
        if word and len(word) >= 3:
            return word

    return choose_fruit_word(title, category, garment_type, color, brand, characteristics, style_tags)


def next_named_code(con: sqlite3.Connection, stem: str, start_at: int = 1) -> str:
    stem = single_code_word(stem, default="PECA")
    rows = con.execute("SELECT code FROM products WHERE code LIKE ?", (f"{stem}-%",)).fetchall()
    used: set[int] = set()
    for row in rows:
        code = row["code"]
        try:
            name, tail = str(code).rsplit("-", 1)
            if name == stem and tail.isdigit():
                used.add(int(tail))
        except Exception:
            pass

    seq = max(1, int(start_at or 1))
    while seq in used:
        seq += 1

    candidate = f"{stem}-{seq:03d}"
    while con.execute("SELECT 1 FROM products WHERE code=?", (candidate,)).fetchone():
        seq += 1
        candidate = f"{stem}-{seq:03d}"
    return candidate


def product_code_from_manual(raw_code: str, con: sqlite3.Connection) -> str:
    """Normaliza um código digitado para o padrão NOME-001."""
    normalized = normalize_code_token(raw_code, default="", max_len=50)
    parts = [part for part in normalized.split("-") if part]

    start_at = 1
    if parts and parts[-1].isdigit():
        start_at = int(parts[-1])
        parts = parts[:-1]

    stem = single_code_word("-".join(parts), default="")
    if not stem:
        stem = choose_fruit_word(raw_code)

    return next_named_code(con, stem, start_at=start_at)


def generate_product_code(
    title: str = "",
    category: str = "",
    garment_type: str = "",
    color: str = "",
    brand: str = "",
    characteristics: str = "",
    style_tags: str = "",
    con: sqlite3.Connection | None = None,
) -> str:
    """Gera código curto e fácil de falar: NOME-001.

    Ex.: VESTIDO-001, AMORA-002, FARM-003, FLORAL-004.
    """
    stem = choose_single_code_name(
        title=title,
        category=category,
        garment_type=garment_type,
        color=color,
        brand=brand,
        characteristics=characteristics,
        style_tags=style_tags,
    )

    if con is not None:
        return next_named_code(con, stem)

    with get_db() as local_con:
        return next_named_code(local_con, stem)


def product_code_has_meaningful_basis(
    title: str = "",
    category: str = "",
    garment_type: str = "",
    color: str = "",
    brand: str = "",
    characteristics: str = "",
    style_tags: str = "",
) -> bool:
    """Evita gerar códigos aleatórios/ruins antes de a peça ter alguma identificação real."""
    strong_values = [title, garment_type, brand]
    if any(strip_accents_lower(v) for v in strong_values):
        return True

    # Categoria/cor sozinhas são genéricas demais. Características só contam
    # quando há mais de uma pista ou quando parecem nome de peça/estampa real.
    weak_values = [category, color, characteristics, style_tags]
    filled_weak = [strip_accents_lower(v) for v in weak_values if strip_accents_lower(v)]
    if len(filled_weak) >= 2:
        return True
    if characteristics and any(word in strip_accents_lower(characteristics) for word in ["floral", "jeans", "renda", "listr", "poa", "animal"]):
        return True
    return False


def generate_product_code_preview(
    title: str = "",
    category: str = "",
    garment_type: str = "",
    color: str = "",
    brand: str = "",
    characteristics: str = "",
    style_tags: str = "",
) -> str:
    return generate_product_code(title, category, garment_type, color, brand, characteristics, style_tags)


def generate_sale_code() -> str:
    stamp = datetime.now().strftime("%y%m%d%H%M")
    suffix = "".join(random.choices(string.digits, k=3))
    return f"VENDA-{stamp}-{suffix}"


def generate_qr(code: str) -> str:
    img = qrcode.make(code)
    file_name = f"{code}.png"
    path = QR_DIR / file_name
    img.save(path)
    return file_name


def image_signature_from_image(img: Image.Image) -> tuple[str, tuple[float, float, float]]:
    """Gera assinatura visual local a partir de uma imagem PIL já recortada."""
    img = img.convert("RGB")
    small = img.resize((8, 8))
    gray = ImageOps.grayscale(small)
    pixels = list(gray.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= avg else "0" for p in pixels)

    # A cor média é calculada ignorando áreas quase pretas/brancas, que no Instagram
    # costumam ser barras laterais, cabeçalho, legenda ou botões do app.
    color_img = img.resize((32, 32))
    color_pixels = list(color_img.getdata())
    filtered = [
        (r, g, b) for r, g, b in color_pixels
        if not (r < 18 and g < 18 and b < 18)
        and not (r > 245 and g > 245 and b > 245)
    ]
    if not filtered:
        filtered = color_pixels
    r = sum(p[0] for p in filtered) / len(filtered)
    g = sum(p[1] for p in filtered) / len(filtered)
    b = sum(p[2] for p in filtered) / len(filtered)
    return bits, (float(r), float(g), float(b))


def image_signature(path: Path) -> tuple[str, tuple[float, float, float]]:
    """Gera uma assinatura visual simples para busca por similaridade.

    Usa hash médio em escala de cinza + cor média. É leve, local e não envia fotos
    para serviços externos.
    """
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        return image_signature_from_image(img)




# ------------------------------
# IA de cadastro de peças
# ------------------------------
AI_PRODUCT_FIELDS: tuple[str, ...] = (
    "title",
    "code",
    "category",
    "garment_type",
    "size",
    "brand",
    "color",
    "condition",
    "measurements",
    "characteristics",
    "style_tags",
    "season",
    "target_audience",
)

PRODUCT_OPTION_FIELDS: tuple[str, ...] = (
    "category",
    "garment_type",
    "size",
    "brand",
    "color",
    "condition",
    "season",
    "target_audience",
    "style_tags",
    "characteristics",
)

DEFAULT_PRODUCT_ATTRIBUTE_OPTIONS: dict[str, list[str]] = {
    "category": ["Feminino", "Masculino", "Infantil", "Acessórios", "Calçados", "Bolsas", "Casa"],
    "garment_type": [
        "Blusa", "Camisa", "Camiseta", "Calça", "Shorts", "Saia", "Vestido", "Macacão",
        "Jaqueta", "Casaco", "Tricô", "Lenço", "Cinto", "Bolsa", "Sapato", "Tênis",
    ],
    "size": ["PP", "P", "M", "G", "GG", "XG", "34", "36", "38", "40", "42", "44", "46", "Único"],
    "brand": ["Sem marca", "Farm", "Zara", "Renner", "C&A", "Riachuelo", "Shein", "Marisa"],
    # "Estampado" não é cor; é característica. Manter fora da lista de cores
    # evita que o preenchimento rápido coloque "Estampado" no campo errado.
    "color": [
        "Preto", "Branco", "Off-white", "Bege", "Nude", "Marrom", "Caramelo",
        "Azul", "Azul-marinho", "Jeans", "Verde", "Rosa", "Pink", "Vermelho",
        "Vinho", "Amarelo", "Mostarda", "Laranja", "Lilás", "Roxo", "Cinza",
        "Dourado", "Prata",
    ],
    "condition": ["Novo com etiqueta", "Novo sem etiqueta", "Seminovo", "Usado - bom", "Com detalhe"],
    "season": ["Verão", "Inverno", "Meia estação", "Festa", "Trabalho", "Casual", "Praia", "Noite"],
    "target_audience": ["Jovem", "Clássico", "Plus size", "Vintage", "Casual", "Elegante", "Infantil", "Unissex"],
    "style_tags": [
        "alfaiataria", "oversized", "floral", "vintage", "minimalista", "boho", "básico",
        "jeans", "tricô", "animal print", "liso", "estampado", "canelado", "renda",
    ],
    "characteristics": [
        "liso", "estampado", "floral", "listrado", "manga longa", "manga curta",
        "sem manga", "gola alta", "decote V", "elástico", "com bolso", "forrado",
        "transparência", "bordado", "renda", "botões", "zíper", "cintura alta",
    ],
}


GARMENT_SYNONYMS: dict[str, list[str]] = {
    "Saia": ["saia", "saias", "midi", "mini saia", "saia longa"],
    "Vestido": ["vestido", "vestidinho", "macaquinho vestido", "longuete"],
    "Blusa": ["blusa", "cropped", "regata", "body", "top"],
    "Camisa": ["camisa", "camisete", "social"],
    "Camiseta": ["camiseta", "t-shirt", "tee"],
    "Calça": ["calça", "pantalona", "skinny", "flare", "legging"],
    "Shorts": ["shorts", "bermuda", "short"],
    "Jaqueta": ["jaqueta", "jacket", "bomber"],
    "Casaco": ["casaco", "sobretudo", "cardigan", "blazer"],
    "Tricô": ["tricô", "tricot", "malha", "crochê", "croche"],
    "Lenço": ["lenço", "echarpe", "cachecol"],
    "Cinto": ["cinto"],
    "Bolsa": ["bolsa", "clutch", "necessaire"],
    "Sapato": ["sapato", "sandália", "sapatilha", "bota", "salto"],
    "Tênis": ["tênis", "tenis", "sneaker"],
}

CHARACTERISTIC_KEYWORDS: dict[str, list[str]] = {
    "floral": ["floral", "flores", "florido"],
    "listrado": ["listrado", "listras"],
    "poá": ["poá", "poa", "bolinha"],
    "animal print": ["animal", "onça", "oncinha", "zebra", "cobra"],
    "jeans": ["jeans", "denim"],
    "renda": ["renda"],
    "canelado": ["canelado"],
    "tricô": ["tricô", "tricot", "crochê", "croche"],
    "alfaiataria": ["alfaiataria", "social"],
    "manga longa": ["manga longa"],
    "manga curta": ["manga curta"],
    "sem manga": ["sem manga", "regata"],
    "cintura alta": ["cintura alta"],
    "elástico": ["elástico", "elastico"],
    "com bolso": ["bolso", "bolsos"],
    "zíper": ["zíper", "ziper"],
    "botões": ["botão", "botões", "botoes"],
}

SEASON_BY_GARMENT: dict[str, str] = {
    "Saia": "Casual",
    "Vestido": "Casual",
    "Blusa": "Casual",
    "Camisa": "Trabalho",
    "Camiseta": "Casual",
    "Calça": "Meia estação",
    "Shorts": "Verão",
    "Jaqueta": "Inverno",
    "Casaco": "Inverno",
    "Tricô": "Inverno",
    "Lenço": "Inverno",
    "Cinto": "Casual",
    "Bolsa": "Casual",
    "Sapato": "Casual",
    "Tênis": "Casual",
}


def normalize_option_value(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value[:80]


PSEUDO_COLOR_TO_CHARACTERISTIC: dict[str, str] = {
    "estampado": "estampado",
    "estampa": "estampado",
    "floral": "floral",
    "florido": "floral",
    "listrado": "listrado",
    "listras": "listrado",
    "poa": "poá",
    "poá": "poá",
    "bolinha": "poá",
    "animal print": "animal print",
    "onca": "animal print",
    "onça": "animal print",
    "xadrez": "xadrez",
    "colorido": "colorido",
}


COLOR_CANONICAL_MAP: dict[str, str] = {
    "off white": "Off-white",
    "offwhite": "Off-white",
    "off-white": "Off-white",
    "azul marinho": "Azul-marinho",
    "azul-marinho": "Azul-marinho",
    "lilas": "Lilás",
    "lilás": "Lilás",
    "cinza claro": "Cinza",
    "pink": "Pink",
}


JUNK_PRODUCT_TOKENS = {"", "e", "a", "o", "as", "os", "de", "da", "do", "ss", "s", "cm", "com", "cem"}


def canonicalize_product_token(value: str) -> str:
    raw = normalize_option_value(value)
    key = strip_accents_lower(raw)
    if key in {"jean", "jeang", "jens", "denin", "denim"}:
        return "jeans"
    if key in {"off white", "offwhite"}:
        return "off-white"
    return raw


def merge_clean_product_values(*values: Any) -> str:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        for part in split_option_values(str(value or "")):
            item = canonicalize_product_token(part)
            key = strip_accents_lower(item)
            if key in JUNK_PRODUCT_TOKENS:
                continue
            if len(key) <= 1:
                continue
            if key and key not in seen:
                seen.add(key)
                output.append(item)
    return ", ".join(output)


def split_color_pattern(value: str) -> tuple[str, str]:
    """Se o campo cor recebeu uma estampa/característica, move para característica."""
    raw = normalize_option_value(value)
    key = strip_accents_lower(raw)
    if not key:
        return "", ""
    if key in COLOR_CANONICAL_MAP:
        return COLOR_CANONICAL_MAP[key], ""
    if key in PSEUDO_COLOR_TO_CHARACTERISTIC:
        return "", PSEUDO_COLOR_TO_CHARACTERISTIC[key]
    return raw, ""


def sanitize_product_attribute_inputs(data: dict[str, Any]) -> dict[str, str]:
    """Corrige campos do cadastro antes de salvar/usar IA.

    Evita bugs vistos no vídeo:
    - "Estampado" entrando como cor.
    - tags/características duplicadas ou lixo de teclado.
    - campos genéricos ficando desorganizados ao salvar.
    """
    cleaned = {k: normalize_option_value(str(v or "")) for k, v in data.items()}
    color, moved_characteristic = split_color_pattern(cleaned.get("color", ""))
    cleaned["color"] = color
    cleaned["style_tags"] = merge_clean_product_values(cleaned.get("style_tags", ""))
    cleaned["characteristics"] = merge_clean_product_values(cleaned.get("characteristics", ""), moved_characteristic)
    cleaned["category"] = normalize_option_value(cleaned.get("category", ""))
    cleaned["garment_type"] = normalize_option_value(cleaned.get("garment_type", ""))
    cleaned["brand"] = normalize_option_value(cleaned.get("brand", ""))
    cleaned["season"] = normalize_option_value(cleaned.get("season", ""))
    cleaned["target_audience"] = normalize_option_value(cleaned.get("target_audience", ""))
    cleaned["condition"] = normalize_option_value(cleaned.get("condition", ""))
    cleaned["measurements"] = normalize_option_value(cleaned.get("measurements", ""))
    return cleaned


def sanitize_ai_product_suggestions(
    suggestions: dict[str, str],
    confidence: dict[str, float],
) -> tuple[dict[str, str], dict[str, float]]:
    suggestions = dict(suggestions or {})
    confidence = dict(confidence or {})
    if "color" in suggestions:
        color, moved = split_color_pattern(suggestions.get("color", ""))
        if moved:
            suggestions["characteristics"] = merge_clean_product_values(suggestions.get("characteristics", ""), moved)
            confidence["characteristics"] = max(float(confidence.get("characteristics", 0.0)), float(confidence.get("color", 0.0)), 0.74)
            suggestions.pop("color", None)
            confidence.pop("color", None)
        else:
            suggestions["color"] = color
    for multi in ("style_tags", "characteristics"):
        if multi in suggestions:
            suggestions[multi] = merge_clean_product_values(suggestions.get(multi, ""))
    suggestions = {k: normalize_option_value(v) for k, v in suggestions.items() if k in AI_PRODUCT_FIELDS and normalize_option_value(v)}
    confidence = {k: round(float(v), 2) for k, v in confidence.items() if k in suggestions}
    return suggestions, confidence


def split_option_values(value: str) -> list[str]:
    text = str(value or "").replace(";", ",").replace("|", ",")
    parts = [normalize_option_value(p) for p in text.split(",")]
    return [p for p in parts if p]


def remember_product_attribute_option(
    con: sqlite3.Connection,
    field_name: str,
    value: str,
    source: str = "manual",
) -> None:
    field_name = str(field_name or "").strip()
    if field_name not in PRODUCT_OPTION_FIELDS:
        return
    for item in split_option_values(value):
        con.execute(
            """
            INSERT INTO product_attribute_options(field_name, value, usage_count, source, created_at, updated_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(field_name, value) DO UPDATE SET
                usage_count = usage_count + 1,
                updated_at = excluded.updated_at
            """,
            (field_name, item, 1, source, now_iso(), now_iso()),
        )


def remember_product_attribute_options_from_form(con: sqlite3.Connection, data: dict[str, Any]) -> None:
    for field_name in PRODUCT_OPTION_FIELDS:
        remember_product_attribute_option(con, field_name, str(data.get(field_name) or ""), source="cadastro")


def seed_product_attribute_options(con: sqlite3.Connection) -> None:
    for field_name, values in DEFAULT_PRODUCT_ATTRIBUTE_OPTIONS.items():
        for value in values:
            remember_product_attribute_option(con, field_name, value, source="padrao")


def get_product_attribute_options(con: sqlite3.Connection | None = None, limit_per_field: int = 80) -> dict[str, list[str]]:
    close_con = False
    if con is None:
        con = get_db()
        close_con = True
    try:
        seed_product_attribute_options(con)
        result: dict[str, list[str]] = {field: [] for field in PRODUCT_OPTION_FIELDS}
        for field in PRODUCT_OPTION_FIELDS:
            rows = con.execute(
                """
                SELECT value
                FROM product_attribute_options
                WHERE field_name = ?
                ORDER BY usage_count DESC, updated_at DESC, value COLLATE NOCASE
                LIMIT ?
                """,
                (field, limit_per_field),
            ).fetchall()
            result[field] = [str(row["value"]) for row in rows if str(row["value"]).strip()]
        return result
    finally:
        if close_con:
            try:
                con.commit()
            except Exception:
                pass
            con.close()


def strip_accents_lower(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.lower().strip()


def infer_garment_from_text(text: str) -> tuple[str, float]:
    clean = strip_accents_lower(text)
    best = ""
    best_score = 0.0
    for garment, words in GARMENT_SYNONYMS.items():
        for word in words:
            w = strip_accents_lower(word)
            if re.search(rf"(^|\W){re.escape(w)}(\W|$)", clean):
                score = 0.94 if w == strip_accents_lower(garment) else 0.84
                if score > best_score:
                    best, best_score = garment, score
    return best, best_score


def infer_characteristics_from_text(text: str) -> list[str]:
    clean = strip_accents_lower(text)
    found: list[str] = []
    for label, words in CHARACTERISTIC_KEYWORDS.items():
        if any(strip_accents_lower(word) in clean for word in words):
            found.append(label)
    return found


def rgb_to_color_name(r: float, g: float, b: float) -> str:
    """Nome de cor conservador para cadastro por foto.

    Importante: "Estampado" não é cor; é característica. A versão anterior
    retornava "Estampado" quando a média da foto não encaixava em nenhuma cor,
    gerando preenchimento errado em peças off-white/bege, fotos de tela e vídeos
    do Instagram. Agora cores incertas retornam "Colorido" com baixa confiança,
    e o chamador decide se deve ou não sugerir.
    """
    mx, mn = max(r, g, b), min(r, g, b)
    brightness = (r + g + b) / 3
    saturation = mx - mn
    if mx < 45:
        return "Preto"
    if mn > 232 and saturation < 18:
        return "Branco"
    if brightness > 202 and saturation < 34:
        if r >= g >= b and (r - b) > 12:
            return "Off-white"
        if r > 190 and g > 178 and b > 145:
            return "Bege"
        return "Off-white"
    if saturation < 18:
        if mx > 170:
            return "Cinza claro"
        if mx > 90:
            return "Cinza"
        return "Preto"
    # tons terrosos/bege antes de amarelo/laranja
    if r > 145 and g > 110 and b < 105 and abs(r - g) < 80:
        return "Caramelo" if r > 170 and g > 120 else "Marrom"
    if r > 178 and g > 160 and b > 118 and r >= g >= b:
        return "Bege"
    if r > g + 35 and r > b + 35:
        return "Rosa" if b > 115 and g < 150 else "Vermelho"
    if g > r + 25 and g > b + 25:
        return "Verde"
    if b > r + 25 and b > g + 20:
        return "Azul"
    if r > 170 and g > 135 and b < 115:
        return "Amarelo"
    if r > 130 and b > 120 and g < 120:
        return "Roxo"
    return "Colorido"


def _color_confidence_from_profile(profile: dict[str, Any], has_typed_evidence: bool) -> float:
    """Confiança da cor inferida por foto.

    Fotos de galeria muitas vezes são prints/reels com fundo, textos e botões.
    A confiança cai quando a cor é genérica ou quando a área útil foi pequena.
    """
    color = str(profile.get("color") or "")
    selected_ratio = float(profile.get("selected_ratio") or 0)
    neutral_ratio = float(profile.get("neutral_light_ratio") or 0)
    saturated_ratio = float(profile.get("saturated_ratio") or 0)
    if color in {"Colorido", "Estampado"}:
        return 0.0 if not has_typed_evidence else 0.42
    if color in {"Branco", "Off-white", "Bege", "Cinza claro"} and neutral_ratio >= 0.28:
        return 0.70 if has_typed_evidence else 0.64
    if selected_ratio < 0.10 and saturated_ratio < 0.06:
        return 0.0
    return 0.68 if has_typed_evidence else 0.60


def image_visual_profile_from_bytes(raw: bytes) -> dict[str, Any]:
    """Extrai um perfil visual conservador da foto da peça.

    O objetivo não é "adivinhar tudo" pela foto: é sugerir somente o que tiver
    base visual suficiente. A rotina agora trata bem peças claras/off-white/bege
    e evita chamar textura, sombra ou print do Instagram de "estampado".
    """
    with Image.open(io.BytesIO(raw)) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((720, 720))
        sig, avg_full = image_signature_from_image(img)

        # Recorte central: normalmente a peça fica no centro da câmera/galeria.
        w, h = img.size
        margin_x = int(w * 0.10)
        margin_y = int(h * 0.08)
        crop = img.crop((margin_x, margin_y, max(margin_x + 1, w - margin_x), max(margin_y + 1, h - margin_y)))
        small = crop.resize((96, 96))
        pixels = list(small.getdata())

        usable = []
        neutral_light = []
        saturated = []
        very_dark_or_light = 0
        for r0, g0, b0 in pixels:
            mx, mn = max(r0, g0, b0), min(r0, g0, b0)
            brightness = (r0 + g0 + b0) / 3
            saturation = mx - mn
            if brightness > 250 or brightness < 10:
                very_dark_or_light += 1
                continue
            usable.append((r0, g0, b0))
            if 170 <= brightness <= 248 and saturation <= 34:
                neutral_light.append((r0, g0, b0))
            if saturation >= 42 and 45 <= brightness <= 235:
                saturated.append((r0, g0, b0))

        if not usable:
            usable = pixels

        neutral_light_ratio = len(neutral_light) / max(1, len(pixels))
        saturated_ratio = len(saturated) / max(1, len(pixels))
        selected_ratio = len(usable) / max(1, len(pixels))

        # Se a peça é clara/neutra, não jogue fora esses pixels; é o caso comum
        # de blusas, casacos, tricôs e crochês off-white.
        if neutral_light_ratio >= 0.26 and saturated_ratio < 0.18:
            selected = neutral_light
        elif len(saturated) >= max(80, int(len(pixels) * 0.08)):
            selected = saturated
        else:
            selected = usable

        r = sum(px[0] for px in selected) / max(1, len(selected))
        g = sum(px[1] for px in selected) / max(1, len(selected))
        b = sum(px[2] for px in selected) / max(1, len(selected))
        color = rgb_to_color_name(r, g, b)

        buckets = {
            (int(px[0] / 42), int(px[1] / 42), int(px[2] / 42))
            for px in usable
            if not (px[0] < 22 and px[1] < 22 and px[2] < 22)
            and not (px[0] > 245 and px[1] > 245 and px[2] > 245)
        }
        saturated_buckets = {
            (int(px[0] / 42), int(px[1] / 42), int(px[2] / 42))
            for px in saturated
        }
        hue_bins: list[int] = []
        for px in saturated:
            hr, hg, hb = px[0] / 255.0, px[1] / 255.0, px[2] / 255.0
            hue, sat, val = colorsys.rgb_to_hsv(hr, hg, hb)
            if sat >= 0.18 and val >= 0.20:
                hue_bins.append(int(hue * 12) % 12)
        hue_diversity = len(set(hue_bins))
        if hue_bins:
            dominant_hue_share = max(hue_bins.count(h) for h in set(hue_bins)) / len(hue_bins)
        else:
            dominant_hue_share = 1.0
        diversity = len(buckets)
        saturated_diversity = len(saturated_buckets)
        aspect = img.height / max(1, img.width)

        # Só marca "estampado" quando há variedade real de matizes. Textura
        # de malha/crochê, sombra, luz quente e print de vídeo não são estampa.
        pattern_hint = "estampado" if (
            saturated_ratio >= 0.22
            and saturated_diversity >= 12
            and diversity >= 28
            and hue_diversity >= 4
            and dominant_hue_share <= 0.55
            and neutral_light_ratio < 0.42
        ) else "liso"

        return {
            "image_hash": sig,
            "avg_r": r,
            "avg_g": g,
            "avg_b": b,
            "avg_full_r": avg_full[0],
            "avg_full_g": avg_full[1],
            "avg_full_b": avg_full[2],
            "color": color,
            "diversity": diversity,
            "saturated_diversity": saturated_diversity,
            "hue_diversity": hue_diversity,
            "dominant_hue_share": round(dominant_hue_share, 3),
            "aspect_ratio": aspect,
            "selected_ratio": round(selected_ratio, 3),
            "neutral_light_ratio": round(neutral_light_ratio, 3),
            "saturated_ratio": round(saturated_ratio, 3),
            "ignored_extreme_ratio": round(very_dark_or_light / max(1, len(pixels)), 3),
            "pattern_hint": pattern_hint,
        }


def similar_products_for_profile(
    con: sqlite3.Connection,
    image_hash: str,
    avg: tuple[float, float, float],
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT *
        FROM products
        WHERE image_hash IS NOT NULL
          AND avg_r IS NOT NULL
          AND deleted_at IS NULL
        ORDER BY id DESC
        LIMIT 300
        """
    ).fetchall()
    scored: list[tuple[float, sqlite3.Row]] = []
    for row in rows:
        try:
            hdist = hamming_distance(str(row["image_hash"]), image_hash)
            cd = color_distance((float(row["avg_r"]), float(row["avg_g"]), float(row["avg_b"])), avg)
            score = max(0.0, 100.0 - (hdist * 1.1) - (cd * 0.34))
            if score >= 48:
                scored.append((score, row))
        except Exception:
            continue
    scored.sort(key=lambda item: item[0], reverse=True)
    results: list[dict[str, Any]] = []
    for score, row in scored[:limit]:
        item = dict(row)
        item["match_score"] = round(score, 1)
        results.append(item)
    return results


def merge_unique_values(*values: Any) -> str:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        for item in split_option_values(str(value or "")):
            key = strip_accents_lower(item)
            if key and key not in seen:
                seen.add(key)
                output.append(item)
    return ", ".join(output)


def ai_product_autofill_suggestions(
    *,
    image_bytes: bytes | None = None,
    title: str = "",
    category: str = "",
    garment_type: str = "",
    color: str = "",
    brand: str = "",
    characteristics: str = "",
    style_tags: str = "",
) -> dict[str, Any]:
    typed_text = " ".join([title, category, garment_type, color, brand, characteristics, style_tags]).strip()
    has_typed_evidence = bool(strip_accents_lower(typed_text))
    suggestions: dict[str, str] = {}
    confidence: dict[str, float] = {}
    reasons: list[str] = []

    detected_garment, garment_score = infer_garment_from_text(typed_text)
    if detected_garment:
        suggestions["garment_type"] = detected_garment
        confidence["garment_type"] = garment_score
        if not title:
            suggestions["title"] = detected_garment
            confidence["title"] = 0.82
        reasons.append(f"Identifiquei o tipo pela descrição: {detected_garment}.")

    text_characteristics = infer_characteristics_from_text(typed_text)
    if text_characteristics:
        suggestions["characteristics"] = merge_unique_values(characteristics, ", ".join(text_characteristics))
        confidence["characteristics"] = max(confidence.get("characteristics", 0.0), 0.84)

    profile: dict[str, Any] | None = None
    similar: list[dict[str, Any]] = []
    strong_visual_match = False
    if image_bytes:
        try:
            profile = image_visual_profile_from_bytes(image_bytes)
            img_color = str(profile["color"])
            color_confidence = _color_confidence_from_profile(profile, has_typed_evidence)
            # Cor por foto é sugestão de apoio; não cria peça/código sozinha e não deve
            # preencher valores genéricos como Colorido/Estampado quando a foto é incerta.
            if not color and color_confidence >= 0.56:
                suggestions["color"] = img_color
                confidence["color"] = color_confidence
                reasons.append(f"A foto sugere cor {img_color}. Confirme visualmente antes de aplicar.")
            else:
                reasons.append("A foto não deu cor confiável suficiente para preencher automaticamente.")

            pattern_hint = str(profile.get("pattern_hint") or "").strip()
            if pattern_hint and pattern_hint != "liso":
                suggestions["characteristics"] = merge_unique_values(
                    suggestions.get("characteristics", characteristics),
                    pattern_hint,
                )
                confidence["characteristics"] = max(confidence.get("characteristics", 0.0), 0.60 if not has_typed_evidence else 0.70)
            else:
                reasons.append("Não marquei como estampado: a foto não mostrou estampa colorida com segurança.")
            with get_db() as con:
                similar = similar_products_for_profile(
                    con,
                    str(profile["image_hash"]),
                    (float(profile["avg_r"]), float(profile["avg_g"]), float(profile["avg_b"])),
                    limit=4,
                )
            if similar:
                best = similar[0]
                best_score = float(best.get("match_score") or 0)
                strong_visual_match = best_score >= 68
                reasons.append(f"Encontrei peça visualmente parecida: {best.get('title') or best.get('code')} ({best_score:.1f}%).")
                if strong_visual_match:
                    for field in ("category", "garment_type", "size", "brand", "season", "target_audience"):
                        if not suggestions.get(field) and best.get(field):
                            suggestions[field] = str(best.get(field))
                            confidence[field] = max(confidence.get(field, 0.0), min(0.86, best_score / 100))
                    suggestions["style_tags"] = merge_unique_values(style_tags, suggestions.get("style_tags"), best.get("style_tags"))
                    suggestions["characteristics"] = merge_unique_values(suggestions.get("characteristics"), best.get("characteristics"))
                    confidence["style_tags"] = max(confidence.get("style_tags", 0.0), min(0.78, best_score / 100))
                    confidence["characteristics"] = max(confidence.get("characteristics", 0.0), min(0.78, best_score / 100))
                else:
                    reasons.append("A semelhança visual não foi forte o bastante para preencher tipo, marca ou categoria automaticamente.")
        except Exception:
            logger.warning("Falha na IA local de foto da peça.", exc_info=True)

    garment = suggestions.get("garment_type") or garment_type
    if garment:
        suggestions.setdefault("category", "Acessórios" if garment in {"Lenço", "Cinto", "Bolsa"} else "Feminino")
        confidence.setdefault("category", 0.72)
        suggestions.setdefault("season", SEASON_BY_GARMENT.get(garment, "Casual"))
        confidence.setdefault("season", 0.68)
        suggestions.setdefault("target_audience", "Casual")
        confidence.setdefault("target_audience", 0.58)

    # Estado é padrão do formulário; só vira sugestão quando existe algum indício real.
    if (has_typed_evidence or detected_garment or strong_visual_match) and not suggestions.get("condition"):
        suggestions["condition"] = "Seminovo"
        confidence["condition"] = 0.55

    # Título amigável quando a administradora ainda não digitou e há tipo identificado.
    if not title and suggestions.get("garment_type"):
        suggestions["title"] = suggestions["garment_type"]
        confidence["title"] = max(confidence.get("title", 0.0), 0.80)

    # Código só é sugerido quando há base de identificação suficiente.
    has_code_basis = bool(
        suggestions.get("title")
        or title
        or suggestions.get("garment_type")
        or garment_type
        or (strong_visual_match and (suggestions.get("brand") or suggestions.get("category")))
    )
    if has_code_basis:
        code = generate_product_code_preview(
            title=suggestions.get("title") or title,
            category=suggestions.get("category") or category,
            garment_type=suggestions.get("garment_type") or garment_type,
            color=suggestions.get("color") or color,
            brand=suggestions.get("brand") or brand,
            characteristics=suggestions.get("characteristics") or characteristics,
            style_tags=suggestions.get("style_tags") or style_tags,
        )
        suggestions["code"] = code
        confidence["code"] = 0.9
    else:
        reasons.append("Não gerei código automático porque a imagem sozinha não identificou o tipo da peça com segurança.")

    # Remove sugestões vazias, limita aos campos conhecidos e não deixa estampa entrar como cor.
    suggestions, confidence = sanitize_ai_product_suggestions(suggestions, confidence)
    return {
        "suggestions": suggestions,
        "confidence": confidence,
        "auto_apply": {
            k: bool(confidence.get(k, 0) >= 0.76 and k not in {"code", "condition"})
            for k in suggestions
        },
        "reasons": reasons or ["Usei o nome, a foto e o histórico da loja para sugerir o cadastro."],
        "similar": [
            {
                "id": item.get("id"),
                "code": item.get("code"),
                "title": item.get("title"),
                "garment_type": item.get("garment_type"),
                "color": item.get("color"),
                "match_score": item.get("match_score"),
            }
            for item in similar
        ],
        "profile": profile or {},
    }


def _ratio_crop_box(width: int, height: int, left: float, top: float, right: float, bottom: float) -> tuple[int, int, int, int]:
    x1 = max(0, min(width - 1, int(round(width * left))))
    y1 = max(0, min(height - 1, int(round(height * top))))
    x2 = max(x1 + 1, min(width, int(round(width * right))))
    y2 = max(y1 + 1, min(height, int(round(height * bottom))))
    return x1, y1, x2, y2


def _trim_dark_side_margins(img: Image.Image, threshold: int = 28, min_keep_ratio: float = 0.42) -> Image.Image:
    """Remove faixas pretas laterais típicas de posts/reels verticais dentro do Instagram."""
    if img.width < 80 or img.height < 80:
        return img
    gray = ImageOps.grayscale(img.resize((min(img.width, 360), min(img.height, 720))))
    w, h = gray.size
    px = gray.load()
    col_means: list[float] = []
    for x in range(w):
        vals = [px[x, y] for y in range(h)]
        col_means.append(sum(vals) / len(vals))
    left = 0
    while left < w - 1 and col_means[left] < threshold:
        left += 1
    right = w - 1
    while right > left and col_means[right] < threshold:
        right -= 1
    if right <= left:
        return img
    # Evita cortar demais quando a peça é preta ou o fundo é escuro.
    keep_ratio = (right - left + 1) / w
    if keep_ratio < min_keep_ratio:
        return img
    scale_x = img.width / w
    x1 = max(0, int(left * scale_x))
    x2 = min(img.width, int((right + 1) * scale_x))
    if x2 - x1 < int(img.width * min_keep_ratio):
        return img
    return img.crop((x1, 0, x2, img.height))


def _trim_instagram_white_footer(img: Image.Image) -> Image.Image:
    """Corta rodapé branco de likes/legenda quando ele aparece dentro do recorte."""
    if img.width < 80 or img.height < 120:
        return img
    gray = ImageOps.grayscale(img.resize((min(img.width, 280), min(img.height, 720))))
    w, h = gray.size
    px = gray.load()
    cut = h
    # Procura, do fim para cima, um bloco muito claro e contínuo.
    for y in range(h - 1, int(h * 0.45), -1):
        row = [px[x, y] for x in range(w)]
        if sum(1 for v in row if v > 235) / w > 0.72:
            cut = y
        elif cut < h and y < cut - 10:
            break
    if cut < int(h * 0.92):
        scale_y = img.height / h
        return img.crop((0, 0, img.width, max(1, int(cut * scale_y))))
    return img


def instagram_screen_type_guess(width: int, height: int) -> str:
    if height >= width * 1.65:
        return "instagram_post_reels_story_vertical"
    if height > width:
        return "instagram_vertical"
    return "imagem_horizontal_ou_quadrada"


def instagram_screen_signature_variants(path: Path, live_focus: bool = False) -> list[dict[str, Any]]:
    """Gera várias assinaturas da mesma tela para reconhecer Post, Reels e Live.

    O Instagram mistura a peça com cabeçalho, legenda, botões e barras pretas. O
    reconhecimento antigo olhava a tela inteira; este modo também testa recortes
    prováveis da mídia e do corpo da peça.
    """
    variants: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, int]] = set()

    def add_variant(base_img: Image.Image, label: str, box: tuple[int, int, int, int], trim_sides: bool = True, trim_footer: bool = False) -> None:
        try:
            crop = base_img.crop(box)
            if trim_footer:
                crop = _trim_instagram_white_footer(crop)
            if trim_sides:
                crop = _trim_dark_side_margins(crop)
            if crop.width < 32 or crop.height < 32:
                return
            hsh, rgb = image_signature_from_image(crop)
            key = (hsh, crop.width, crop.height, int(sum(rgb)))
            if key in seen:
                return
            seen.add(key)
            variants.append({
                "label": label,
                "hash": hsh,
                "rgb": rgb,
                "box": [int(v) for v in box],
                "width": int(crop.width),
                "height": int(crop.height),
            })
        except Exception:
            return

    with Image.open(path) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGB")
        w, h = img.size
        kind = instagram_screen_type_guess(w, h)

        # Tela inteira fica como fallback para Post/Reels. Em live automática ela é evitada
        # para não reconhecer chão, botões ou cards antigos como peça atual.
        if not live_focus:
            add_variant(img, "tela_inteira", (0, 0, w, h), trim_sides=False, trim_footer=False)

        if live_focus:
            live_regions = [
                ("live_principal_sem_ui", (0.00, 0.05, 0.78, 0.82), True, False),
                ("live_centro_peca", (0.08, 0.08, 0.76, 0.76), True, False),
                ("live_dupla_esquerda", (0.00, 0.08, 0.52, 0.80), True, False),
                ("live_dupla_direita_segura", (0.38, 0.08, 0.78, 0.80), True, False),
                ("live_zoom_centro", (0.18, 0.12, 0.70, 0.70), True, False),
            ]
            for label, ratios, trim_sides, trim_footer in live_regions:
                add_variant(img, label, _ratio_crop_box(w, h, *ratios), trim_sides=trim_sides, trim_footer=trim_footer)

        # Recortes calibrados para Post/Reels do Instagram em celular vertical:
        # remove barra superior, botões inferiores e legenda; depois elimina barras pretas laterais.
        ratio_regions = [
            ("instagram_midia_post_reels", (0.00, 0.07, 1.00, 0.72), True, True),
            ("instagram_post_video_sem_legenda", (0.00, 0.10, 1.00, 0.69), True, True),
            ("instagram_reels_video", (0.00, 0.03, 1.00, 0.78), True, True),
            ("instagram_midia_centro", (0.08, 0.09, 0.92, 0.70), True, True),
            ("peca_corpo_inteiro", (0.16, 0.12, 0.84, 0.68), True, False),
            ("peca_centro_sem_ui", (0.22, 0.14, 0.78, 0.66), True, False),
            ("peca_zoom_superior", (0.18, 0.10, 0.82, 0.52), True, False),
            ("peca_zoom_inferior", (0.18, 0.32, 0.82, 0.72), True, False),
            ("quadrado_feed", (0.00, 0.08, 1.00, 0.58), True, True),
        ]
        for label, ratios, trim_sides, trim_footer in ratio_regions:
            box = _ratio_crop_box(w, h, *ratios)
            add_variant(img, label, box, trim_sides=trim_sides, trim_footer=trim_footer)

        # Reforço para prints exatamente como os enviados: vídeo central com laterais pretas.
        if h >= w * 1.55:
            precise_regions = [
                ("post_reels_area_arquivo_enviado", (0.13, 0.11, 0.87, 0.68), True, False),
                ("post_reels_area_visual", (0.14, 0.07, 0.86, 0.63), True, False),
                ("post_reels_lookbook_centro", (0.24, 0.08, 0.76, 0.67), True, False),
            ]
            for label, ratios, trim_sides, trim_footer in precise_regions:
                add_variant(img, label, _ratio_crop_box(w, h, *ratios), trim_sides=trim_sides, trim_footer=trim_footer)

    # Preferência: recortes de mídia antes da tela inteira.
    variants.sort(key=lambda v: 0 if str(v.get("label", "")).startswith(("live_", "instagram", "post_reels", "peca")) else 1)
    for v in variants:
        v["screen_type"] = kind
    return variants


def _safe_upload_ext(upload: UploadFile, allowed: set[str], fallback: str) -> str:
    ext = Path(upload.filename or "").suffix.lower()
    if ext in allowed:
        return ext
    content_type = (upload.content_type or "").lower().split(";", 1)[0].strip()
    if content_type in IMAGE_EXT_BY_CONTENT_TYPE:
        return IMAGE_EXT_BY_CONTENT_TYPE[content_type]
    return fallback


def _unique_upload_name(prefix: str, ext: str) -> str:
    return f"{slugify(prefix)}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}{ext}"


def _copy_upload_limited(upload: UploadFile, dest: Path, max_bytes: int) -> None:
    """Copia upload em blocos, impedindo arquivos enormes ou inesperados."""
    total = 0
    upload.file.seek(0)
    try:
        with dest.open("wb") as f:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="Arquivo muito grande para upload.")
                f.write(chunk)
    except Exception:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise


def _validate_saved_image(path: Path) -> None:
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            width, height = img.size
            if width < 1 or height < 1 or width * height > 50_000_000:
                raise ValueError("dimensões inválidas")
    except Exception:
        if path.exists():
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Imagem inválida ou corrompida.")


def _optimize_saved_image(path: Path) -> None:
    """Reduz fotos muito grandes sem cortar a peça.

    A correção é feita no arquivo salvo para deixar vitrine, PWA e WebView mais leves.
    A foto continua centralizada pelo CSS; aqui cuidamos do peso/dimensão física.
    """
    try:
        suffix = path.suffix.lower()
        with Image.open(path) as raw:
            img = ImageOps.exif_transpose(raw)
            if max(img.size) > MAX_PRODUCT_IMAGE_SIDE:
                img.thumbnail((MAX_PRODUCT_IMAGE_SIDE, MAX_PRODUCT_IMAGE_SIDE), Image.Resampling.LANCZOS)

            if suffix in {".jpg", ".jpeg"}:
                if img.mode not in {"RGB", "L"}:
                    img = img.convert("RGB")
                img.save(path, "JPEG", quality=IMAGE_SAVE_QUALITY, optimize=True, progressive=True)
            elif suffix == ".webp":
                if img.mode not in {"RGB", "RGBA"}:
                    img = img.convert("RGB")
                img.save(path, "WEBP", quality=IMAGE_SAVE_QUALITY, method=6)
            elif suffix == ".png":
                # Mantém transparência se existir; reduz dimensões e usa optimize.
                if img.mode not in {"RGB", "RGBA", "P", "LA", "L"}:
                    img = img.convert("RGB")
                img.save(path, "PNG", optimize=True)
    except Exception:
        # Otimização não deve impedir o cadastro se a imagem já foi validada.
        logging.warning("Não foi possível otimizar imagem enviada: %s", path, exc_info=True)


def save_upload(upload: UploadFile, prefix: str) -> str | None:
    """Salva uma imagem usada como foto principal ou foto de busca."""
    if not upload or not upload.filename:
        return None

    content_type = (upload.content_type or "").lower().split(";", 1)[0].strip()
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS and content_type not in IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Formato de imagem não permitido.")

    filename = _unique_upload_name(prefix, _safe_upload_ext(upload, ALLOWED_IMAGE_EXTS, ".jpg"))
    dest = UPLOAD_DIR / filename
    _copy_upload_limited(upload, dest, MAX_IMAGE_UPLOAD_BYTES)
    _validate_saved_image(dest)
    _optimize_saved_image(dest)
    _validate_saved_image(dest)
    return filename


def detect_media_type(upload: UploadFile) -> str:
    content_type = (upload.content_type or "").lower().split(";", 1)[0].strip()
    ext = Path(upload.filename or "").suffix.lower()
    if content_type.startswith("video/") or ext in ALLOWED_VIDEO_EXTS:
        return "video"
    return "image"


def save_media_upload(upload: UploadFile, prefix: str) -> tuple[str, str] | None:
    """Salva foto ou vídeo complementar da peça."""
    if not upload or not upload.filename:
        return None

    media_type = detect_media_type(upload)
    content_type = (upload.content_type or "").lower().split(";", 1)[0].strip()
    ext = Path(upload.filename or "").suffix.lower()

    if media_type == "video":
        if ext not in ALLOWED_VIDEO_EXTS and content_type not in VIDEO_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="Formato de vídeo não permitido.")
        final_ext = _safe_upload_ext(upload, ALLOWED_VIDEO_EXTS, ".mp4")
        max_bytes = MAX_MEDIA_UPLOAD_BYTES
    else:
        if ext not in ALLOWED_IMAGE_EXTS and content_type not in IMAGE_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="Formato de imagem não permitido.")
        final_ext = _safe_upload_ext(upload, ALLOWED_IMAGE_EXTS, ".jpg")
        max_bytes = MAX_IMAGE_UPLOAD_BYTES

    filename = _unique_upload_name(prefix, final_ext)
    dest = UPLOAD_DIR / filename
    _copy_upload_limited(upload, dest, max_bytes)
    if media_type == "image":
        _validate_saved_image(dest)
        _optimize_saved_image(dest)
        _validate_saved_image(dest)
    return filename, media_type


def insert_product_media(
    con: sqlite3.Connection,
    product_id: int,
    filename: str,
    media_type: str,
    original_filename: str = "",
    notes: str = "",
    image_hash: str | None = None,
    avg_r: float | None = None,
    avg_g: float | None = None,
    avg_b: float | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO product_media
        (product_id, media_type, filename, original_filename, notes, image_hash, avg_r, avg_g, avg_b, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (product_id, media_type, filename, original_filename, notes, image_hash, avg_r, avg_g, avg_b, now_iso()),
    )


def save_extra_media_files(
    con: sqlite3.Connection,
    product_id: int,
    files: list[UploadFile] | None,
    prefix: str,
    notes: str = "",
    can_set_main_image: bool = False,
) -> int:
    """Salva várias fotos/vídeos complementares.

    Fotos entram no reconhecimento visual. Vídeos ficam no histórico/galeria da peça
    e ajudam na pesquisa por nome do arquivo/observação.
    """
    saved_count = 0
    first_image_for_main: tuple[str, str, float, float, float] | None = None

    for upload in files or []:
        if not upload or not upload.filename:
            continue

        saved = save_media_upload(upload, prefix)
        if not saved:
            continue
        filename, media_type = saved

        image_hash = None
        avg_r = avg_g = avg_b = None
        if media_type == "image":
            try:
                image_hash, avg = image_signature(UPLOAD_DIR / filename)
                avg_r, avg_g, avg_b = avg
                if first_image_for_main is None:
                    first_image_for_main = (filename, image_hash, avg_r, avg_g, avg_b)
            except Exception:
                media_type = "arquivo"

        insert_product_media(
            con,
            product_id=product_id,
            filename=filename,
            media_type=media_type,
            original_filename=upload.filename or "",
            notes=notes,
            image_hash=image_hash,
            avg_r=avg_r,
            avg_g=avg_g,
            avg_b=avg_b,
        )
        saved_count += 1

    if can_set_main_image and first_image_for_main:
        filename, image_hash, avg_r, avg_g, avg_b = first_image_for_main
        con.execute(
            "UPDATE products SET image_filename=?, image_hash=?, avg_r=?, avg_g=?, avg_b=? WHERE id=?",
            (filename, image_hash, avg_r, avg_g, avg_b, product_id),
        )

    return saved_count


def hamming_distance(a: str, b: str) -> int:
    if not a or not b:
        return 64
    length = min(len(a), len(b))
    return sum(1 for i in range(length) if a[i] != b[i]) + abs(len(a) - len(b))


def score_signature(
    query_hash: str,
    query_rgb: tuple[float, float, float],
    image_hash: str | None,
    avg_r: float | None,
    avg_g: float | None,
    avg_b: float | None,
) -> float:
    visual_penalty = hamming_distance(query_hash, image_hash or "") / 64
    rgb = (avg_r or 0, avg_g or 0, avg_b or 0)
    color_distance = math.sqrt(sum((query_rgb[i] - rgb[i]) ** 2 for i in range(3))) / 441.67
    # Dá mais peso ao desenho/contraste, mas usa cor como desempate.
    penalty = (visual_penalty * 0.72) + (color_distance * 0.28)
    return max(0, round((1 - penalty) * 100, 1))


def recognition_score(query_hash: str, query_rgb: tuple[float, float, float], row: sqlite3.Row) -> float:
    return score_signature(
        query_hash,
        query_rgb,
        row["image_hash"] if "image_hash" in row.keys() else None,
        row["avg_r"] if "avg_r" in row.keys() else None,
        row["avg_g"] if "avg_g" in row.keys() else None,
        row["avg_b"] if "avg_b" in row.keys() else None,
    )


def recognize_product_matches(
    query_hash: str,
    query_rgb: tuple[float, float, float],
    limit: int = 8,
    status: str = "disponivel",
) -> list[dict[str, Any]]:
    """Compara a foto pesquisada com foto principal e todas as fotos complementares."""
    with get_db() as con:
        params: list[Any] = []
        where_status = ""
        normalized_status = (status or "disponivel").strip().lower()
        if normalized_status and normalized_status != "todos":
            if normalized_status in {"disponivel_reservado", "live_admin"}:
                where_status = " AND p.status IN ('disponivel','reservado')"
            else:
                where_status = " AND p.status = ?"
                params.append(status)

        rows = con.execute(
            f"""
            SELECT p.*, p.image_filename AS match_image_filename, p.image_hash AS match_image_hash,
                   p.avg_r AS match_avg_r, p.avg_g AS match_avg_g, p.avg_b AS match_avg_b,
                   'principal' AS match_source
            FROM products p
            WHERE p.image_hash IS NOT NULL{where_status}
            UNION ALL
            SELECT p.*, pm.filename AS match_image_filename, pm.image_hash AS match_image_hash,
                   pm.avg_r AS match_avg_r, pm.avg_g AS match_avg_g, pm.avg_b AS match_avg_b,
                   'complementar' AS match_source
            FROM products p
            JOIN product_media pm ON pm.product_id = p.id
            WHERE pm.image_hash IS NOT NULL{where_status}
            ORDER BY id DESC
            """,
            params + params,
        ).fetchall()

    best_by_product: dict[int, dict[str, Any]] = {}
    for row in rows:
        score = score_signature(
            query_hash,
            query_rgb,
            row["match_image_hash"],
            row["match_avg_r"],
            row["match_avg_g"],
            row["match_avg_b"],
        )
        product = dict(row)
        product["score"] = score
        product["match_source"] = row["match_source"]
        # Mostra no resultado a foto que mais pareceu, mesmo se for complementar.
        product["image_filename"] = row["match_image_filename"] or product.get("image_filename")
        current = best_by_product.get(product["id"])
        if current is None or score > current["score"]:
            best_by_product[product["id"]] = product

    results = list(best_by_product.values())
    results.sort(key=lambda p: p["score"], reverse=True)
    return results[:limit]


def recognize_product_matches_from_variants(
    variants: list[dict[str, Any]],
    limit: int = 8,
    status: str = "disponivel",
) -> list[dict[str, Any]]:
    """Compara várias assinaturas da mesma tela com foto principal e complementares.

    Usado no Assistente Instagram para Post/Reels/Live, onde a peça aparece dentro
    de uma captura de tela com barras, botões e legendas.
    """
    if not variants:
        return []
    with get_db() as con:
        params: list[Any] = []
        where_status = ""
        normalized_status = (status or "disponivel").strip().lower()
        if normalized_status and normalized_status != "todos":
            if normalized_status in {"disponivel_reservado", "live_admin"}:
                where_status = " AND p.status IN ('disponivel','reservado')"
            else:
                where_status = " AND p.status = ?"
                params.append(status)
        rows = con.execute(
            f"""
            SELECT p.*, p.image_filename AS match_image_filename, p.image_hash AS match_image_hash,
                   p.avg_r AS match_avg_r, p.avg_g AS match_avg_g, p.avg_b AS match_avg_b,
                   'principal' AS match_source
            FROM products p
            WHERE p.image_hash IS NOT NULL{where_status}
            UNION ALL
            SELECT p.*, pm.filename AS match_image_filename, pm.image_hash AS match_image_hash,
                   pm.avg_r AS match_avg_r, pm.avg_g AS match_avg_g, pm.avg_b AS match_avg_b,
                   'complementar' AS match_source
            FROM products p
            JOIN product_media pm ON pm.product_id = p.id
            WHERE pm.image_hash IS NOT NULL{where_status}
            ORDER BY id DESC
            """,
            params + params,
        ).fetchall()

    best_by_product: dict[int, dict[str, Any]] = {}
    for row in rows:
        best_score = -1.0
        best_variant: dict[str, Any] | None = None
        for variant in variants:
            score = score_signature(
                str(variant.get("hash") or ""),
                variant.get("rgb") or (0.0, 0.0, 0.0),
                row["match_image_hash"],
                row["match_avg_r"],
                row["match_avg_g"],
                row["match_avg_b"],
            )
            # Pequeno bônus para recortes próprios de Post/Reels, pois eles removem UI do Instagram.
            label = str(variant.get("label") or "")
            if label.startswith(("instagram", "post_reels", "peca")):
                score = min(100.0, score + 2.5)
            if score > best_score:
                best_score = score
                best_variant = variant
        product = dict(row)
        product["score"] = round(best_score, 1)
        product["match_source"] = row["match_source"]
        product["matched_screen_crop"] = (best_variant or {}).get("label") or ""
        product["screen_crop_box"] = (best_variant or {}).get("box") or []
        product["screen_crop_size"] = {
            "width": (best_variant or {}).get("width"),
            "height": (best_variant or {}).get("height"),
        }
        product["screen_type"] = (best_variant or {}).get("screen_type") or ""
        product["image_filename"] = row["match_image_filename"] or product.get("image_filename")
        current = best_by_product.get(product["id"])
        if current is None or product["score"] > current["score"]:
            best_by_product[product["id"]] = product

    results = list(best_by_product.values())
    results.sort(key=lambda p: p["score"], reverse=True)
    return results[:limit]


SEARCH_COLUMNS = [
    "code", "title", "category", "garment_type", "size", "brand", "color",
    "condition", "measurements", "characteristics", "style_tags", "season",
    "target_audience"
]


def split_search_terms(q: str) -> list[str]:
    text = (q or "").strip()
    if not text:
        return []
    return [term for term in text.replace(",", " ").split() if term]


def search_products_rows(q: str = "", status: str = "todos", limit: int | None = None) -> list[sqlite3.Row]:
    """Busca textual simples e rápida para celular, caixa e estoque.

    A busca aceita uma ou várias palavras. Ex.: "vestido preto p", "calça jeans",
    "BRE-2301" ou "zara couro". Cada palavra precisa aparecer em algum atributo
    da peça ou no nome da fornecedora.
    """
    terms = split_search_terms(q)
    normalized_status = (status or "todos").strip().lower()
    params: list[Any] = []
    where: list[str] = []

    for term in terms:
        like = f"%{term}%"
        column_checks = [f"COALESCE(p.{column}, '') LIKE ?" for column in SEARCH_COLUMNS]
        column_checks.append("COALESCE(s.name, '') LIKE ?")
        column_checks.append(
            "EXISTS (SELECT 1 FROM product_media pm WHERE pm.product_id = p.id "
            "AND (COALESCE(pm.notes, '') LIKE ? OR COALESCE(pm.original_filename, '') LIKE ? OR COALESCE(pm.filename, '') LIKE ?))"
        )
        where.append("(" + " OR ".join(column_checks) + ")")
        params.extend([like] * (len(column_checks) - 1))
        params.extend([like, like, like])

    if normalized_status != "todos":
        where.append("p.status = ?")
        params.append(normalized_status)

    sql = """
        SELECT p.*, s.name AS supplier_name,
               (SELECT COUNT(*) FROM product_media pm WHERE pm.product_id = p.id) AS media_count
        FROM products p
        LEFT JOIN suppliers s ON s.id = p.supplier_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)

    # Prioriza código exato, depois começo do código, depois cadastros recentes.
    sql += """
        ORDER BY
          CASE
            WHEN UPPER(p.code) = UPPER(?) THEN 0
            WHEN UPPER(p.code) LIKE UPPER(?) THEN 1
            ELSE 2
          END,
          p.id DESC
    """
    clean_q = (q or "").strip()
    params.extend([clean_q, f"{clean_q}%"])

    if limit is not None:
        safe_limit = max(1, min(int(limit), 80))
        sql += " LIMIT ?"
        params.append(safe_limit)

    with get_db() as con:
        return con.execute(sql, params).fetchall()



def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


def row_to_dict(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return dict(row) if not isinstance(row, dict) else row


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row["name"]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def row_has_column(row: sqlite3.Row | dict[str, Any] | None, column: str) -> bool:
    if not row:
        return False
    try:
        return column in row.keys()  # type: ignore[attr-defined]
    except Exception:
        try:
            return column in row
        except Exception:
            return False


def row_get(row: sqlite3.Row | dict[str, Any] | None, column: str, default: Any = None) -> Any:
    if not row_has_column(row, column):
        return default
    try:
        value = row[column]  # type: ignore[index]
    except Exception:
        value = default
    return default if value is None else value


def new_public_token(prefix: str = "") -> str:
    token = secrets.token_urlsafe(24).replace("-", "").replace("_", "")
    return (prefix + token)[:48]


def ensure_unique_public_token(con: sqlite3.Connection, table: str, column: str = "public_token", prefix: str = "") -> str:
    for _ in range(32):
        token = new_public_token(prefix)
        exists = con.execute(f"SELECT 1 FROM {table} WHERE {column}=? LIMIT 1", (token,)).fetchone()
        if not exists:
            return token
    return new_public_token(prefix + secrets.token_hex(4))


def validate_money_amount(value: Any, field_label: str, *, minimum: float = 0.0, allow_zero: bool = True) -> float:
    try:
        amount = float(value)
    except Exception:
        raise HTTPException(status_code=400, detail=f"{field_label} inválido.")
    if math.isnan(amount) or math.isinf(amount):
        raise HTTPException(status_code=400, detail=f"{field_label} inválido.")
    if amount < minimum or (not allow_zero and amount <= 0):
        raise HTTPException(status_code=400, detail=f"{field_label} deve ser {'maior que zero' if not allow_zero else 'maior ou igual a zero'}.")
    return round(amount, 2)


def log_security_event(
    con: sqlite3.Connection,
    event_type: str,
    severity: str = "info",
    actor_type: str = "",
    actor_id: Any = None,
    path: str = "",
    details: str = "",
    request: Request | None = None,
) -> None:
    try:
        if not path and request is not None:
            path = str(request.url.path or "")
        ip = request.client.host if request and request.client else ""
        user_agent = request.headers.get("user-agent", "")[:400] if request else ""
        con.execute(
            """
            INSERT INTO security_events(event_type, severity, actor_type, actor_id, path, details, ip, user_agent, created_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (event_type[:80], severity[:20], actor_type[:40], str(actor_id or ""), path[:240], details[:1000], ip[:80], user_agent, now_iso()),
        )
    except Exception:
        logger.debug("Falha ao registrar evento de segurança %s", event_type, exc_info=True)


def security_event(event_type: str, severity: str = "info", details: str = "", request: Request | None = None) -> None:
    try:
        with get_db() as con:
            log_security_event(con, event_type, severity=severity, path=str(request.url.path if request else ""), details=details, request=request)
    except Exception:
        logger.debug("Falha ao registrar evento de segurança.", exc_info=True)


def find_customer_account_id_for_identity(con: sqlite3.Connection, name: str = "", phone: str = "", email: str = "") -> int | None:
    phone_clean = normalize_phone(phone)
    email_key = normalize_text_key(email)
    if phone_clean:
        row = con.execute("SELECT id FROM customer_accounts WHERE phone=? AND active=1 ORDER BY id DESC LIMIT 1", (phone_clean,)).fetchone()
        if row:
            return int(row["id"])
    if email_key:
        rows = con.execute("SELECT id, email FROM customer_accounts WHERE active=1 AND COALESCE(email,'')<>'' ORDER BY id DESC LIMIT 20").fetchall()
        for row in rows:
            if normalize_text_key(row["email"]) == email_key:
                return int(row["id"])
    return None


def ensure_online_order_token(con: sqlite3.Connection, order_id: int) -> str:
    row = con.execute("SELECT id, public_token FROM online_orders WHERE id=?", (int(order_id),)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    token = str(row_get(row, "public_token", "") or "").strip()
    if not token:
        token = ensure_unique_public_token(con, "online_orders", "public_token", "ord_")
        con.execute("UPDATE online_orders SET public_token=? WHERE id=?", (token, int(order_id)))
    return token


def ensure_live_cart_token(con: sqlite3.Connection, cart_id: int) -> str:
    row = con.execute("SELECT id, public_token FROM live_customer_carts WHERE id=?", (int(cart_id),)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Carrinho não encontrado.")
    token = str(row_get(row, "public_token", "") or "").strip()
    if not token:
        token = ensure_unique_public_token(con, "live_customer_carts", "public_token", "cart_")
        con.execute("UPDATE live_customer_carts SET public_token=? WHERE id=?", (token, int(cart_id)))
    return token


def sale_already_linked(con: sqlite3.Connection, source: str, source_ref_id: int) -> sqlite3.Row | None:
    cols = table_columns(con, "sales")
    if "source" in cols and "source_ref_id" in cols:
        return con.execute("SELECT * FROM sales WHERE source=? AND source_ref_id=? LIMIT 1", (source, int(source_ref_id))).fetchone()
    return None


def create_sale_record(
    con: sqlite3.Connection,
    *,
    customer: str,
    payment_method: str,
    total: float,
    paid: float,
    discount: float = 0.0,
    customer_account_id: int | None = None,
    source: str = "",
    source_ref_id: int | None = None,
    created_at: str | None = None,
) -> tuple[int, str]:
    total = validate_money_amount(total, "Total da venda", minimum=0, allow_zero=True)
    paid = validate_money_amount(paid, "Valor pago", minimum=0, allow_zero=True)
    discount = validate_money_amount(discount, "Desconto", minimum=0, allow_zero=True)
    sale_code = generate_sale_code()
    columns = ["sale_code", "customer", "payment_method", "discount", "total", "paid", "change_value", "created_at"]
    values: list[Any] = [sale_code, customer, payment_method or "Online", discount, total, paid, max(0, paid - total), created_at or now_iso()]
    sales_cols = table_columns(con, "sales")
    optional_values = {
        "customer_account_id": customer_account_id,
        "source": source,
        "source_ref_id": source_ref_id,
        "paid_at": now_iso() if paid >= total else None,
    }
    for col, value in optional_values.items():
        if col in sales_cols:
            columns.append(col)
            values.append(value)
    placeholders = ",".join("?" for _ in columns)
    cur = con.execute(f"INSERT INTO sales({','.join(columns)}) VALUES({placeholders})", values)
    return int(cur.lastrowid), sale_code


def create_sale_for_online_order(con: sqlite3.Connection, order_id: int, source_label: str = "pedido_online") -> tuple[bool, str, int | None]:
    order = con.execute("SELECT * FROM online_orders WHERE id=?", (int(order_id),)).fetchone()
    if not order:
        return False, "Pedido online não encontrado.", None
    if row_get(order, "sale_id"):
        return True, f"Pedido {order['order_code']} já tem venda vinculada.", int(order["sale_id"])
    linked = sale_already_linked(con, "online_order", int(order_id))
    if linked:
        con.execute("UPDATE online_orders SET sale_id=?, status='pago', paid_at=COALESCE(paid_at, ?) WHERE id=?", (int(linked["id"]), now_iso(), int(order_id)))
        return True, f"Pedido {order['order_code']} já tinha venda vinculada.", int(linked["id"])
    items = con.execute(
        """
        SELECT oi.*, p.status AS product_status, p.sale_price
        FROM online_order_items oi
        JOIN products p ON p.id=oi.product_id
        WHERE oi.order_id=?
        """,
        (int(order_id),),
    ).fetchall()
    if not items:
        return False, "Pedido sem itens.", None
    blocked = [str(i["code"]) for i in items if i["product_status"] not in {"reservado", "disponivel"}]
    if blocked:
        con.execute("UPDATE online_orders SET status='conflito', tracking_updated_at=? WHERE id=?", (now_iso(), int(order_id)))
        return False, "Conflito: peça indisponível " + ", ".join(blocked), None
    total = validate_money_amount(row_get(order, "total", 0) or sum(safe_float(i["price"]) for i in items), "Total do pedido", minimum=0, allow_zero=True)
    customer_account_id = row_get(order, "customer_account_id") or find_customer_account_id_for_identity(con, order["customer_name"], order["customer_phone"], "")
    sale_id, sale_code = create_sale_record(
        con,
        customer=order["customer_name"],
        payment_method=order["payment_method"] or "Online",
        total=total,
        paid=total,
        discount=row_get(order, "discount", 0) or 0,
        customer_account_id=int(customer_account_id) if customer_account_id else None,
        source="online_order",
        source_ref_id=int(order_id),
    )
    sold_time = now_iso()
    for item in items:
        price = validate_money_amount(item["price"], f"Preço da peça {item['code']}", minimum=0, allow_zero=False)
        con.execute("INSERT INTO sale_items(sale_id, product_id, price) VALUES(?,?,?)", (sale_id, int(item["product_id"]), price))
        con.execute("UPDATE products SET status='vendido', sold_at=?, sync_updated_at=? WHERE id=?", (sold_time, sold_time, int(item["product_id"])))
        con.execute(
            "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
            (int(item["product_id"]), source_label, f"Pagamento confirmado no pedido {order['order_code']} / venda {sale_code}.", sold_time),
        )
        enqueue_product_cloud_sync(con, int(item["product_id"]), reason="sold_online")
    con.execute(
        "UPDATE online_orders SET status='pago', paid_at=COALESCE(paid_at, ?), sale_id=?, customer_account_id=COALESCE(customer_account_id, ?), tracking_updated_at=? WHERE id=?",
        (sold_time, sale_id, int(customer_account_id) if customer_account_id else None, sold_time, int(order_id)),
    )
    con.execute("UPDATE online_order_items SET status='vendido' WHERE order_id=?", (int(order_id),))
    enqueue_sale_cloud_sync(con, sale_id)
    return True, f"Pedido confirmado. Venda {sale_code} criada.", sale_id


def create_sale_for_live_reservation(con: sqlite3.Connection, reservation_id: int, source_label: str = "live_payment") -> tuple[bool, str, int | None]:
    reservation = con.execute(
        """
        SELECT r.*, p.code, p.title, p.sale_price, p.status AS product_status
        FROM live_reservation_queue r
        JOIN products p ON p.id=r.product_id
        WHERE r.id=?
        """,
        (int(reservation_id),),
    ).fetchone()
    if not reservation:
        return False, "Reserva não encontrada.", None
    if row_get(reservation, "sale_id"):
        return True, f"Reserva #{reservation_id} já tem venda vinculada.", int(reservation["sale_id"])
    linked = sale_already_linked(con, "live_reservation", int(reservation_id))
    if linked:
        con.execute("UPDATE live_reservation_queue SET sale_id=?, status='pago', paid_at=COALESCE(paid_at, ?), updated_at=? WHERE id=?", (int(linked["id"]), now_iso(), now_iso(), int(reservation_id)))
        return True, f"Reserva #{reservation_id} já tinha venda vinculada.", int(linked["id"])
    if reservation["product_status"] not in {"reservado", "disponivel"}:
        return False, f"Peça {reservation['code']} indisponível para venda.", None
    amount = validate_money_amount(reservation["sale_price"], f"Preço da peça {reservation['code']}", minimum=0, allow_zero=False)
    customer_account_id = row_get(reservation, "customer_account_id") or find_customer_account_id_for_identity(con, reservation["customer_name"], reservation["customer_phone"], "")
    sale_id, sale_code = create_sale_record(
        con,
        customer=reservation["customer_name"],
        payment_method="Pix/Live",
        total=amount,
        paid=amount,
        discount=0,
        customer_account_id=int(customer_account_id) if customer_account_id else None,
        source="live_reservation",
        source_ref_id=int(reservation_id),
    )
    paid_time = now_iso()
    con.execute("INSERT INTO sale_items(sale_id, product_id, price) VALUES(?,?,?)", (sale_id, int(reservation["product_id"]), amount))
    con.execute("UPDATE products SET status='vendido', sold_at=?, sync_updated_at=? WHERE id=?", (paid_time, paid_time, int(reservation["product_id"])))
    con.execute(
        "UPDATE live_reservation_queue SET status='pago', paid_at=COALESCE(paid_at, ?), sale_id=?, customer_account_id=COALESCE(customer_account_id, ?), updated_at=? WHERE id=?",
        (paid_time, sale_id, int(customer_account_id) if customer_account_id else None, paid_time, int(reservation_id)),
    )
    con.execute("UPDATE live_customer_cart_items SET status='pago', updated_at=? WHERE reservation_id=?", (paid_time, int(reservation_id)))
    con.execute("UPDATE live_queue_items SET status='vendida', updated_at=? WHERE live_session_id=? AND product_id=?", (paid_time, int(reservation["live_session_id"]), int(reservation["product_id"])))
    con.execute("INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)", (int(reservation["product_id"]), source_label, f"Venda {sale_code} criada a partir da reserva da live #{reservation['live_session_id']}.", paid_time))
    _live_insert_item(con, int(reservation["live_session_id"]), int(reservation["product_id"]), "vendida", f"Pagamento confirmado: {reservation['customer_name']} / venda {sale_code}.", 0)
    enqueue_product_cloud_sync(con, int(reservation["product_id"]), reason="sold_live")
    enqueue_sale_cloud_sync(con, sale_id)
    return True, f"Pagamento confirmado. Venda {sale_code} criada.", sale_id




# -----------------------------
# Importação inteligente do caderno por câmera
# -----------------------------

NOTEBOOK_IMPORT_CONFIDENCE_MIN_APPLY = float(os.getenv("BRECHORISEE_CADERNO_MIN_CONFIDENCE_APPLY", "0.35") or 0.35)
NOTEBOOK_MONEY_RE = re.compile(r"(?<![\d/])[-+]?\s*(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}(?![\d/])")
NOTEBOOK_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")


def notebook_clean_ocr_text(value: Any) -> str:
    """Normaliza OCR/anotação sem apagar o texto original de auditoria."""
    raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    replacements = {
        "R$": "R$",
        "—": "-",
        "–": "-",
        "−": "-",
        "，": ",",
        "‚": ",",
        "O,": "0,",
        "o,": "0,",
    }
    for old, new in replacements.items():
        raw = raw.replace(old, new)
    lines = []
    for line in raw.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def notebook_money_to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    negative = value.startswith("-") or value.startswith("−")
    value = value.replace("R$", "").replace(" ", "").replace("+", "").replace("-", "").replace("−", "")
    value = value.replace(".", "").replace(",", ".")
    try:
        amount = float(value)
        return -amount if negative else amount
    except Exception:
        return None


def notebook_parse_date_text(raw: str | None) -> str:
    """Converte data brasileira para YYYY-MM-DD quando possível; preserva vazio se incerto."""
    if not raw:
        return ""
    value = str(raw).strip().replace("-", "/")
    parts = value.split("/")
    if len(parts) != 3:
        return raw
    try:
        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2])
        if year < 100:
            year += 2000
        dt = datetime(year, month, day)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return raw


def notebook_line_without_amounts_and_dates(line: str) -> str:
    clean = NOTEBOOK_MONEY_RE.sub(" ", line)
    clean = NOTEBOOK_DATE_RE.sub(" ", clean)
    clean = re.sub(r"\([^)]{0,80}\)", " ", clean)
    clean = re.sub(r"[_•·]+", " ", clean)
    clean = re.sub(r"\s*[-=]+\s*", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" .:-")
    return clean.strip()


def notebook_detect_entry_type(line: str, amount: float | None) -> str:
    low = normalize_text_key(line)
    if not line.strip():
        return "blank"
    if "total" in low or "subtotal" in low:
        return "subtotal"
    if amount is not None and amount < 0:
        return "discount"
    if any(word in low for word in ["sinal", "entrada", "pago", "pagou", "pix", "cartao", "dinheiro"]):
        return "payment" if amount is not None else "note"
    if any(word in low for word in ["brinde", "troca", "devolucao", "pendente", "promocao", "promo", "nobuka"]):
        return "note" if amount is None else "sale_item"
    if amount is not None:
        return "sale_item"
    return "note"


def notebook_detect_customer(line: str, current_customer: str = "") -> str:
    low = normalize_text_key(line)
    amount_present = NOTEBOOK_MONEY_RE.search(line) is not None
    if amount_present:
        return current_customer
    # Ex.: Sandra (Nova compra), Maria - compra, Ana nova compra.
    if "compra" in low or "cliente" in low:
        candidate = re.split(r"\(|-|:", line, maxsplit=1)[0].strip(" .:-")
        if 2 <= len(candidate) <= 80 and not any(x in normalize_text_key(candidate) for x in ["nova", "mais", "total"]):
            return candidate
    # Primeira linha sem valor costuma ser nome da cliente no caderno.
    if not current_customer:
        candidate = notebook_line_without_amounts_and_dates(line)
        key = normalize_text_key(candidate)
        blocked = {"total", "subtotal", "promocao", "promo", "brinde", "data"}
        if 2 <= len(candidate) <= 80 and key not in blocked and not NOTEBOOK_DATE_RE.search(line):
            return candidate
    return current_customer


def notebook_parse_text(raw_text: str) -> dict[str, Any]:
    """Transforma texto reconhecido/revisado em linhas estruturadas e conservadoras.

    Nada é lançado diretamente no estoque/vendas sem conferência da administradora.
    """
    text_clean = notebook_clean_ocr_text(raw_text)
    lines = text_clean.split("\n") if text_clean else []
    entries: list[dict[str, Any]] = []
    current_customer = ""
    current_date = ""
    group_index = 1
    last_was_total = False

    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        dates = NOTEBOOK_DATE_RE.findall(line)
        if dates:
            # Em caderno de venda, datas ao lado do total costumam representar vencimento/fechamento.
            current_date = notebook_parse_date_text(dates[-1])

        before_customer = current_customer
        current_customer = notebook_detect_customer(line, current_customer)
        if current_customer != before_customer and entries:
            group_index += 1
            last_was_total = False

        money_matches = NOTEBOOK_MONEY_RE.findall(line)
        amount = notebook_money_to_float(money_matches[-1]) if money_matches else None
        entry_type = notebook_detect_entry_type(line, amount)
        title = ""
        confidence = 0.35

        if entry_type == "sale_item":
            title = notebook_line_without_amounts_and_dates(line)
            if title:
                confidence += 0.25
            if amount is not None:
                confidence += 0.25
            if current_customer:
                confidence += 0.10
        elif entry_type in {"subtotal", "discount", "payment"}:
            if amount is not None:
                confidence += 0.20
            if current_customer:
                confidence += 0.10
        else:
            title = notebook_line_without_amounts_and_dates(line)
            if title:
                confidence += 0.10

        if entry_type == "note" and current_customer and "compra" in normalize_text_key(line) and amount is None:
            # Cabeçalho de cliente; não aplica como venda.
            confidence = max(confidence, 0.6)

        group_key = f"{normalize_text_key(current_customer) or 'sem_cliente'}-{group_index}"
        entries.append({
            "line_no": idx,
            "raw_line": line,
            "entry_type": entry_type,
            "customer_name": current_customer,
            "product_title": title if entry_type == "sale_item" else "",
            "amount": amount,
            "date_text": current_date,
            "sale_group": group_key,
            "notes": "",
            "confidence": round(min(0.99, confidence), 2),
            "confirmed": 1 if entry_type in {"sale_item", "discount", "payment", "subtotal"} else 0,
        })

        if entry_type == "subtotal":
            last_was_total = True
            group_index += 1
        elif entry_type == "sale_item" and last_was_total:
            last_was_total = False

    totals = {
        "lines": len(entries),
        "sale_items": sum(1 for e in entries if e["entry_type"] == "sale_item"),
        "customers": len({e["customer_name"] for e in entries if e.get("customer_name")}),
        "gross_total": round(sum(float(e["amount"] or 0) for e in entries if e["entry_type"] == "sale_item" and (e.get("amount") or 0) > 0), 2),
        "discounts": round(abs(sum(float(e["amount"] or 0) for e in entries if e["entry_type"] == "discount" and (e.get("amount") or 0) < 0)), 2),
        "subtotals_seen": [float(e["amount"] or 0) for e in entries if e["entry_type"] == "subtotal" and e.get("amount") is not None],
    }
    totals["net_estimated"] = round(totals["gross_total"] - totals["discounts"], 2)
    avg_conf = (sum(float(e["confidence"] or 0) for e in entries) / len(entries)) if entries else 0
    return {
        "raw_text": raw_text or "",
        "clean_text": text_clean,
        "entries": entries,
        "summary": totals,
        "confidence": round(avg_conf, 2),
        "warnings": notebook_parse_warnings(entries, totals),
    }


def notebook_parse_warnings(entries: list[dict[str, Any]], totals: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not entries:
        warnings.append("Nenhuma linha foi reconhecida. Tire a foto mais próxima, com boa luz, ou cole o texto revisado.")
    if any(e["entry_type"] == "sale_item" and not e.get("customer_name") for e in entries):
        warnings.append("Há peças sem cliente identificado. Confira o nome da cliente antes de aplicar.")
    if any(e["entry_type"] == "sale_item" and not e.get("product_title") for e in entries):
        warnings.append("Há peças sem descrição clara.")
    if totals.get("subtotals_seen"):
        calculated = float(totals.get("net_estimated") or 0)
        nearest = min(totals["subtotals_seen"], key=lambda x: abs(float(x) - calculated))
        if abs(float(nearest) - calculated) > 1.50:
            warnings.append(f"O total calculado ({money(calculated)}) difere de subtotal anotado ({money(nearest)}). Confira desconto/parcelas.")
    return warnings


def notebook_try_ocr_image(image_path: Path) -> tuple[str, str, str]:
    """Executa OCR local opcional. Sem dependência instalada, mantém fluxo de conferência manual."""
    try:
        import pytesseract  # type: ignore
    except Exception:
        return "", "manual", "OCR automático indisponível neste servidor. Instale Tesseract + pytesseract ou use a conferência pelo texto."
    try:
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img)
        # Pré-processamento leve para melhorar caderno: escala, contraste, tons de cinza.
        max_side = 2200
        w, h = img.size
        if max(w, h) < 1500:
            scale = min(2.0, max_side / max(1, max(w, h)))
            img = img.resize((int(w * scale), int(h * scale)))
        img = ImageOps.grayscale(img)
        img = ImageOps.autocontrast(img)
        config = "--oem 3 --psm 6"
        try:
            text_out = pytesseract.image_to_string(img, lang="por+eng", config=config)
        except Exception:
            text_out = pytesseract.image_to_string(img, config=config)
        return notebook_clean_ocr_text(text_out), "pytesseract", ""
    except Exception as exc:
        return "", "ocr_error", f"OCR não conseguiu ler a imagem: {exc}"


def notebook_persist_import(
    con: sqlite3.Connection,
    *,
    image_filename: str = "",
    image_hash: str = "",
    ocr_engine: str = "manual",
    ocr_text: str = "",
    edited_text: str = "",
    parse_payload: dict[str, Any],
    source: str = "camera",
    notes: str = "",
) -> int:
    created_at = now_iso()
    status = "rascunho"
    cur = con.execute(
        """
        INSERT INTO notebook_import_batches
        (source, image_filename, image_hash, ocr_engine, ocr_text, edited_text, parse_payload, status, confidence, notes, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            source,
            image_filename,
            image_hash,
            ocr_engine,
            ocr_text,
            edited_text,
            json.dumps(parse_payload, ensure_ascii=False),
            status,
            float(parse_payload.get("confidence") or 0),
            notes,
            created_at,
            created_at,
        ),
    )
    batch_id = int(cur.lastrowid)
    notebook_replace_import_lines(con, batch_id, parse_payload)
    return batch_id


def notebook_replace_import_lines(con: sqlite3.Connection, batch_id: int, parse_payload: dict[str, Any]) -> None:
    con.execute("DELETE FROM notebook_import_lines WHERE batch_id=? AND linked_sale_id IS NULL", (int(batch_id),))
    now_value = now_iso()
    for entry in parse_payload.get("entries") or []:
        con.execute(
            """
            INSERT INTO notebook_import_lines
            (batch_id, line_no, entry_type, customer_name, product_title, amount, date_text, sale_group, raw_line, notes, confidence, confirmed, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                int(batch_id),
                int(entry.get("line_no") or 0),
                str(entry.get("entry_type") or "unknown")[:40],
                str(entry.get("customer_name") or "")[:160],
                str(entry.get("product_title") or "")[:240],
                entry.get("amount"),
                str(entry.get("date_text") or "")[:30],
                str(entry.get("sale_group") or "")[:120],
                str(entry.get("raw_line") or "")[:1000],
                str(entry.get("notes") or "")[:1000],
                float(entry.get("confidence") or 0),
                int(entry.get("confirmed") or 0),
                now_value,
                now_value,
            ),
        )


def notebook_get_import(con: sqlite3.Connection, batch_id: int) -> dict[str, Any]:
    batch = con.execute("SELECT * FROM notebook_import_batches WHERE id=?", (int(batch_id),)).fetchone()
    if not batch:
        raise HTTPException(status_code=404, detail="Importação do caderno não encontrada.")
    lines = con.execute(
        "SELECT * FROM notebook_import_lines WHERE batch_id=? ORDER BY line_no, id",
        (int(batch_id),),
    ).fetchall()
    payload = {}
    try:
        payload = json.loads(batch["parse_payload"] or "{}")
    except Exception:
        payload = {}
    return {"batch": batch, "lines": lines, "payload": payload}


def notebook_find_or_create_customer(con: sqlite3.Connection, name: str) -> int | None:
    name = (name or "").strip()
    if not name:
        return None
    key = normalize_text_key(name)
    for row in con.execute("SELECT id, name FROM customers ORDER BY id DESC LIMIT 500").fetchall():
        if normalize_text_key(row["name"]) == key:
            return int(row["id"])
    cur = con.execute(
        "INSERT INTO customers(name, notes, created_at) VALUES(?,?,?)",
        (name, "Criada pela importação do caderno por câmera.", now_iso()),
    )
    return int(cur.lastrowid)


def notebook_line_sale_date(line: sqlite3.Row, fallback: str | None = None) -> str:
    raw = row_get(line, "date_text", "") or fallback or ""
    parsed = notebook_parse_date_text(str(raw)) if raw else ""
    if parsed and re.match(r"^\d{4}-\d{2}-\d{2}$", parsed):
        return parsed + " 12:00:00"
    return now_iso()


def notebook_apply_import(con: sqlite3.Connection, batch_id: int, force: bool = False) -> dict[str, Any]:
    data = notebook_get_import(con, batch_id)
    batch = data["batch"]
    if batch["status"] == "aplicado" and not force:
        return {"ok": True, "message": "Esta importação já foi aplicada.", "created_sales": 0, "created_products": 0}
    lines = [r for r in data["lines"] if int(row_get(r, "confirmed", 0) or 0) == 1]
    sale_lines = [r for r in lines if row_get(r, "entry_type") == "sale_item" and row_get(r, "amount") is not None and float(row_get(r, "amount") or 0) > 0]
    if not sale_lines:
        raise HTTPException(status_code=400, detail="Nenhuma peça de venda confirmada para aplicar.")

    grouped: dict[str, list[sqlite3.Row]] = {}
    discounts_by_group: dict[str, float] = {}
    for line in lines:
        group = str(row_get(line, "sale_group", "") or "sem_grupo")
        if row_get(line, "entry_type") == "sale_item" and row_get(line, "amount") is not None and float(row_get(line, "amount") or 0) > 0:
            grouped.setdefault(group, []).append(line)
        elif row_get(line, "entry_type") == "discount" and row_get(line, "amount") is not None:
            discounts_by_group[group] = discounts_by_group.get(group, 0.0) + abs(float(row_get(line, "amount") or 0))

    created_sales = 0
    created_products = 0
    linked_line_ids: list[int] = []
    sale_ids: list[int] = []
    for group, items in grouped.items():
        if not items:
            continue
        customer_name = str(row_get(items[0], "customer_name", "") or "Cliente do caderno").strip() or "Cliente do caderno"
        customer_id = notebook_find_or_create_customer(con, customer_name)
        gross_total = sum(float(row_get(item, "amount") or 0) for item in items)
        discount = min(discounts_by_group.get(group, 0.0), gross_total)
        total = max(0.0, gross_total - discount)
        sale_date = notebook_line_sale_date(items[0])
        sale_id, sale_code = create_sale_record(
            con,
            customer=customer_name,
            payment_method="Caderno importado",
            total=total,
            paid=total,
            discount=discount,
            customer_account_id=None,
            source="notebook_import",
            source_ref_id=int(batch_id),
            created_at=sale_date,
        )
        sale_ids.append(sale_id)
        created_sales += 1

        for item in items:
            amount = validate_money_amount(row_get(item, "amount"), "Valor da peça importada do caderno", minimum=0, allow_zero=False)
            title = str(row_get(item, "product_title", "") or row_get(item, "raw_line", "") or "Peça importada do caderno").strip()
            title = title[:180] or "Peça importada do caderno"
            code = generate_product_code(title=title, category="Importado do caderno", garment_type="", color="", brand="", con=con)
            generate_qr(code)
            cur_prod = con.execute(
                """
                INSERT INTO products
                (code, title, category, garment_type, size, brand, color, condition, measurements,
                 characteristics, style_tags, season, target_audience, cost_price, sale_price, supplier_id,
                 status, image_filename, image_hash, avg_r, avg_g, avg_b, created_at, sold_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'vendido', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    title,
                    "Importado do caderno",
                    "",
                    "",
                    "",
                    "",
                    "Importada",
                    "",
                    f"Linha do caderno: {row_get(item, 'raw_line', '')}",
                    "caderno,importado,historico",
                    "",
                    "",
                    0.0,
                    amount,
                    1,
                    row_get(batch, "image_filename", "") or None,
                    row_get(batch, "image_hash", "") or None,
                    None,
                    None,
                    None,
                    sale_date,
                    sale_date,
                ),
            )
            product_id = int(cur_prod.lastrowid)
            con.execute("INSERT INTO sale_items(sale_id, product_id, price) VALUES(?,?,?)", (sale_id, product_id, amount))
            con.execute(
                "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                (product_id, "importacao_caderno", f"Peça histórica importada do caderno. Venda {sale_code}. Cliente {customer_name}.", sale_date),
            )
            con.execute(
                "UPDATE notebook_import_lines SET linked_product_id=?, linked_sale_id=?, updated_at=? WHERE id=?",
                (product_id, sale_id, now_iso(), int(row_get(item, "id"))),
            )
            linked_line_ids.append(int(row_get(item, "id")))
            created_products += 1
            enqueue_product_cloud_sync(con, product_id, reason="notebook_import")

        enqueue_sale_cloud_sync(con, sale_id)
        if customer_id:
            con.execute(
                "INSERT INTO audit_logs(user_name, action, entity, entity_id, details, created_at) VALUES(?,?,?,?,?,?)",
                ("sistema", "importacao_caderno_cliente", "customer", str(customer_id), f"Venda {sale_code} criada a partir do caderno.", now_iso()),
            )

    con.execute(
        "UPDATE notebook_import_batches SET status='aplicado', applied_at=?, updated_at=?, notes=COALESCE(notes,'') || ? WHERE id=?",
        (now_iso(), now_iso(), f"\nAplicado: {created_sales} venda(s), {created_products} peça(s).", int(batch_id)),
    )
    return {
        "ok": True,
        "message": f"Importação aplicada: {created_sales} venda(s) e {created_products} peça(s) históricas criadas.",
        "created_sales": created_sales,
        "created_products": created_products,
        "sale_ids": sale_ids,
        "line_ids": linked_line_ids,
    }


def notebook_summary(days: int = 30) -> dict[str, Any]:
    with get_db() as con:
        imports = con.execute("SELECT COUNT(*) AS c FROM notebook_import_batches WHERE created_at >= datetime('now', ?)", (f"-{int(days)} days",)).fetchone()["c"]
        pending = con.execute("SELECT COUNT(*) AS c FROM notebook_import_batches WHERE status!='aplicado'").fetchone()["c"]
        applied = con.execute("SELECT COUNT(*) AS c FROM notebook_import_batches WHERE status='aplicado' AND applied_at >= datetime('now', ?)", (f"-{int(days)} days",)).fetchone()["c"]
        value_row = con.execute(
            """
            SELECT COALESCE(SUM(si.price),0) AS total
            FROM sale_items si
            JOIN sales s ON s.id=si.sale_id
            WHERE s.source='notebook_import' AND s.created_at >= datetime('now', ?)
            """,
            (f"-{int(days)} days",),
        ).fetchone()
        recent = con.execute("SELECT * FROM notebook_import_batches ORDER BY id DESC LIMIT 12").fetchall()
    return {
        "days": days,
        "imports": int(imports or 0),
        "pending": int(pending or 0),
        "applied": int(applied or 0),
        "imported_sales_value": float(value_row["total"] or 0),
        "recent": recent,
    }


def telegram_mask_token(token: str | None = None) -> str:
    raw = (token if token is not None else TELEGRAM_BOT_TOKEN) or ""
    if not raw:
        return ""
    if len(raw) <= 12:
        return "***"
    return raw[:6] + "..." + raw[-4:]


def telegram_is_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID)


def telegram_chat_allowed(chat_id: str | int | None) -> bool:
    """Limita comandos do Telegram ao chat da administradora/equipe.

    Em produção, configure TELEGRAM_ADMIN_CHAT_ID ou TELEGRAM_ALLOWED_CHAT_IDS.
    Sem lista autorizada, comandos reais são bloqueados por segurança.
    """
    chat = str(chat_id or "").strip()
    if not chat:
        return False
    if not TELEGRAM_ALLOWED_CHAT_IDS:
        return BRECHORISEE_ENV not in {"production", "prod"}
    return chat in TELEGRAM_ALLOWED_CHAT_IDS


def telegram_html(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def telegram_public_url(path: str = "") -> str:
    base = get_public_server_url(None).rstrip("/")
    suffix = "/" + str(path or "").lstrip("/") if path else ""
    return base + suffix


def telegram_record_message(
    con: sqlite3.Connection,
    direction: str,
    text: str,
    chat_id: str = "",
    username: str = "",
    command: str = "",
    payload: dict[str, Any] | None = None,
    status: str = "pendente",
    related_type: str = "",
    related_id: int | None = None,
    error: str = "",
    sent_at: str | None = None,
) -> int:
    cur = con.execute(
        """
        INSERT INTO telegram_messages(direction, chat_id, username, text, command, payload, status, related_type, related_id, error, created_at, sent_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            direction,
            str(chat_id or ""),
            str(username or ""),
            str(text or "")[:3900],
            str(command or "")[:80],
            json.dumps(payload or {}, ensure_ascii=False),
            str(status or "pendente"),
            str(related_type or ""),
            int(related_id) if related_id else None,
            str(error or "")[:1000],
            now_iso(),
            sent_at,
        ),
    )
    return int(cur.lastrowid)


def telegram_send_admin_message(
    con: sqlite3.Connection,
    text: str,
    related_type: str = "",
    related_id: int | None = None,
    disable_notification: bool = False,
) -> dict[str, Any]:
    """Envia ou simula mensagem para a administradora no Telegram.

    Por segurança, o envio real só acontece quando:
    - TELEGRAM_BOT_TOKEN existe;
    - TELEGRAM_ADMIN_CHAT_ID existe;
    - BRECHORISEE_TELEGRAM_SEND_REAL=1.
    Sem isso, a mensagem fica registrada como "simulado" para teste local.
    """
    message = (text or "").strip()
    if not message:
        return {"ok": False, "status": "vazio", "message": "Mensagem vazia."}

    if not telegram_is_configured() or not TELEGRAM_SEND_REAL:
        msg_id = telegram_record_message(
            con,
            direction="outbound",
            chat_id=TELEGRAM_ADMIN_CHAT_ID,
            text=message,
            status="simulado",
            related_type=related_type,
            related_id=related_id,
            payload={"send_real": TELEGRAM_SEND_REAL, "configured": telegram_is_configured()},
        )
        return {"ok": True, "status": "simulado", "id": msg_id}

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = json.dumps(
        {
            "chat_id": TELEGRAM_ADMIN_CHAT_ID,
            "text": message[:3900],
            "parse_mode": "HTML",
            "disable_notification": bool(disable_notification),
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw else {}
        msg_id = telegram_record_message(
            con,
            direction="outbound",
            chat_id=TELEGRAM_ADMIN_CHAT_ID,
            text=message,
            status="enviado" if payload.get("ok") else "erro",
            related_type=related_type,
            related_id=related_id,
            payload=payload,
            sent_at=now_iso() if payload.get("ok") else None,
            error="" if payload.get("ok") else str(payload)[:1000],
        )
        return {"ok": bool(payload.get("ok")), "status": "enviado" if payload.get("ok") else "erro", "id": msg_id, "telegram": payload}
    except Exception as exc:
        msg_id = telegram_record_message(
            con,
            direction="outbound",
            chat_id=TELEGRAM_ADMIN_CHAT_ID,
            text=message,
            status="erro",
            related_type=related_type,
            related_id=related_id,
            error=str(exc),
        )
        logger.warning("Falha ao enviar Telegram: %s", exc)
        return {"ok": False, "status": "erro", "id": msg_id, "error": str(exc)}


def telegram_notify_admin(text: str, related_type: str = "", related_id: int | None = None) -> None:
    try:
        with get_db() as con:
            telegram_send_admin_message(con, text, related_type=related_type, related_id=related_id)
    except Exception as exc:
        logger.warning("Falha ao registrar/enviar notificação Telegram: %s", exc)


def telegram_order_summary(order: sqlite3.Row | dict[str, Any], items: list[sqlite3.Row | dict[str, Any]]) -> str:
    o = row_to_dict(order)
    rows = [row_to_dict(i) for i in items]
    total = safe_float(o.get("total"))
    if not total:
        total = sum(safe_float(i.get("price")) for i in rows)
    lines = [
        "🛍️ <b>Novo pedido BRECHORISEE</b>",
        f"Pedido: {o.get('order_code') or ('#' + str(o.get('id') or ''))}",
        f"Cliente: {o.get('customer_name') or '-'}",
        f"WhatsApp: {o.get('customer_phone') or '-'}",
        f"Instagram: {o.get('customer_instagram') or '-'}",
        f"Entrega: {o.get('delivery_method') or o.get('delivery_type') or '-'}",
        f"Pagamento: {o.get('payment_method') or '-'}",
        f"Total: {money(total)}",
    ]
    delivery_info = delivery_location_label(o)
    if delivery_info:
        lines += ["", "📍 Entrega/Google Maps:", delivery_info]
    elif o.get("address"):
        lines += ["", f"📍 Entrega: {o.get('address')}"]
    lines += [
        "",
        "Peças:",
    ]
    for item in rows:
        lines.append(f"• {item.get('code') or ''} — {item.get('title') or 'Peça'} — {money(item.get('price'))}")
    if o.get("notes"):
        lines += ["", f"Obs.: {o.get('notes')}"]
    lines += ["", "Comandos:", f"/pedido {o.get('id')} pago", f"/pedido {o.get('id')} cancelar"]
    return "\n".join(lines)


def telegram_live_reservation_summary(customer_name: str, customer_phone: str, product: sqlite3.Row | dict[str, Any], session_id: int, source: str = "live") -> str:
    p = row_to_dict(product)
    return "\n".join([
        "🔒 <b>Peça reservada</b>",
        f"Origem: {source}",
        f"Live: #{session_id}",
        f"Cliente: {customer_name or '-'}",
        f"WhatsApp: {customer_phone or '-'}",
        f"Peça: {p.get('code')} — {p.get('title')}",
        f"Valor: {money(p.get('sale_price'))}",
        "",
        "A peça saiu da vitrine/repescagem pública.",
    ])


def confirm_online_order_payment_by_id(order_id: int) -> tuple[bool, str, int | None]:
    with get_db() as con:
        ok, msg, sale_id = create_sale_for_online_order(con, int(order_id), source_label="venda_online_confirmada")
        if ok and sale_id:
            order = con.execute("SELECT * FROM online_orders WHERE id=?", (int(order_id),)).fetchone()
            if order:
                telegram_send_admin_message(con, f"✅ Pedido {order['order_code']} confirmado. Venda #{sale_id} criada/vinculada.", "online_order", int(order_id))
        return ok, msg, sale_id


def cancel_online_order_by_id(order_id: int) -> tuple[bool, str]:
    with get_db() as con:
        order = con.execute("SELECT * FROM online_orders WHERE id=?", (int(order_id),)).fetchone()
        if not order:
            return False, "Pedido online não encontrado."
        if order["status"] in {"pago", "entregue"}:
            return False, "Pedido já pago/entregue não pode ser cancelado por este comando."
        items = con.execute("SELECT * FROM online_order_items WHERE order_id=?", (int(order_id),)).fetchall()
        for item in items:
            p = con.execute("SELECT status FROM products WHERE id=?", (item["product_id"],)).fetchone()
            if p and p["status"] == "reservado":
                con.execute("UPDATE products SET status='disponivel', sync_updated_at=? WHERE id=?", (now_iso(), item["product_id"]))
                con.execute("UPDATE reservations SET status='cancelada' WHERE product_id=? AND status='ativa'", (item["product_id"],))
        con.execute("UPDATE online_orders SET status='cancelado' WHERE id=?", (int(order_id),))
        con.execute("UPDATE online_order_items SET status='cancelado' WHERE order_id=?", (int(order_id),))
        telegram_send_admin_message(con, f"❌ Pedido {order['order_code']} cancelado pelo Telegram. Peças reservadas voltaram para disponível.", "online_order", int(order_id))
    return True, "Pedido cancelado e reservas liberadas."


def telegram_status_text(con: sqlite3.Connection) -> str:
    statuses = {r["status"]: r["total"] for r in con.execute("SELECT status, COUNT(*) AS total FROM products GROUP BY status").fetchall()}
    open_orders = con.execute("SELECT COUNT(*) AS total FROM online_orders WHERE status IN ('aguardando_pagamento','separado','em_entrega')").fetchone()["total"]
    active_res = con.execute("SELECT COUNT(*) AS total FROM reservations WHERE status='ativa'").fetchone()["total"]
    live = con.execute("SELECT * FROM live_sessions ORDER BY id DESC LIMIT 1").fetchone()
    live_line = "sem live cadastrada"
    if live:
        live_line = f"live #{live['id']} {live['status']} — {live['title']}"
    return "\n".join([
        "📊 <b>Status BRECHORISEE</b>",
        f"Disponíveis: {statuses.get('disponivel', 0)}",
        f"Reservadas: {statuses.get('reservado', 0)}",
        f"Vendidas: {statuses.get('vendido', 0)}",
        f"Pedidos abertos: {open_orders}",
        f"Reservas ativas: {active_res}",
        f"Live: {live_line}",
    ])




def telegram_order_commands_text(order_id: int | None = None) -> str:
    target = str(order_id) if order_id else "ID"
    return "\n".join([
        "🛍️ Comandos de pedido BRECHORISEE",
        "",
        f"/pedido {target} — ver detalhes do pedido",
        f"/pedido {target} pago — confirmar Pix/pagamento",
        f"/pedido {target} cancelar — cancelar pedido e liberar peça",
        f"/pedido {target} entrega — marcar como em entrega",
        f"/pedido {target} entregue — marcar como entregue",
        "",
        "Outros:",
        "/pedidos — listar últimos pedidos",
        "/cliente NOME_OU_TELEFONE — buscar pedidos da cliente",
        "Envie foto com legenda 'pedido ID' para registrar comprovante.",
        "",
        "Exemplo:",
        "/pedido 1 pago",
    ])


def telegram_commands_help_text(section: str = "geral") -> str:
    section_key = re.sub(r"\s+", " ", (section or "geral").strip().lower().replace("/", ""))
    if section_key in {"pedido", "pedidos", "orders", "online"}:
        return telegram_order_commands_text()
    if section_key in {"live", "central", "ao vivo", "aovivo"}:
        return "\n".join([
            "🎛️ Comandos da live BRECHORISEE",
            "",
            "/painel — resumo da Central da Live",
            "/atual — peça atual",
            "/fila — próximas peças",
            "/proxima — mostrar próxima peça",
            "/addfila CODIGO — adicionar peça à fila",
            "/reservar NOME | TELEFONE — reservar peça atual",
            "/espera NOME — colocar cliente na fila de espera",
            "/vendida — marcar peça atual como vendida",
            "/pago NOME — confirmar pagamento da cliente",
            "/carrinho NOME — resumo/link do carrinho",
            "/resumo_live — relatório rápido da live",
            "",
            "Exemplos:",
            "/addfila CROPPED-001",
            "/reservar Maria | 48999999999",
            "/pago Maria",
        ])
    return "\n".join([
        "🤖 Comandos BRECHORISEE",
        "",
        "Ajuda:",
        "/comandos — mostra este menu",
        "/comandos live — comandos da Central da Live",
        "/comandos pedido — comandos de pedidos",
        "/status — resumo geral",
        "/ping — testar integração",
        "/chats — últimas conversas do Chat BRECHORISEE",
        "/responder ID mensagem — responder cliente no chat pelo Telegram",
        "/r ID mensagem — atalho para responder cliente",
        "",
        "Live:",
        "/painel",
        "/atual",
        "/fila",
        "/proxima",
        "/addfila CODIGO",
        "/reservar NOME | TELEFONE",
        "/espera NOME",
        "/vendida",
        "/pago NOME",
        "/carrinho NOME",
        "/resumo_live",
        "",
        "Pedidos:",
        "/pedidos",
        "/pedido ID",
        "/pedido ID pago",
        "/pedido ID cancelar",
        "/pedido ID entrega",
        "/pedido ID entregue",
        "/cliente NOME_OU_TELEFONE",
        "",
        "Comentários/comprovantes:",
        "/comentar TEXTO",
        "Envie foto com legenda 'pedido ID' para registrar comprovante.",
    ])

def telegram_process_text_command(text: str, chat_id: str = "", username: str = "") -> str:
    raw = (text or "").strip()
    low = raw.lower()
    with get_db() as con:
        telegram_record_message(con, "inbound", raw, chat_id=chat_id, username=username, command=low.split(" ")[0] if low else "", status="recebido")

        chat_reply_answer = telegram_try_chat_command(con, raw, low, chat_id=chat_id, username=username)
        if chat_reply_answer is not None:
            return chat_reply_answer

        if low in {"/start", "/ajuda", "ajuda", "menu", "/menu", "/help", "help", "/comandos", "comandos", "/brechorisee", "brechorisee"} or low.startswith("/comandos ") or low.startswith("comandos "):
            parts = raw.split(maxsplit=1)
            section = parts[1] if len(parts) > 1 else "geral"
            return telegram_commands_help_text(section)

        if low.startswith("/status") or low == "status":
            return telegram_status_text(con)

        if low.startswith("/pedidos") or low == "pedidos":
            rows = con.execute("SELECT * FROM online_orders ORDER BY id DESC LIMIT 8").fetchall()
            if not rows:
                return "Nenhum pedido online encontrado."
            lines = ["🛍️ Últimos pedidos:"]
            for o in rows:
                lines.append(f"#{o['id']} {o['order_code']} — {o['customer_name']} — {money(o['total'])} — {o['status']}")
            return "\n".join(lines)

        if low.startswith("/reservas") or low == "reservas":
            rows = con.execute(
                """
                SELECT r.*, p.code, p.title, p.sale_price
                FROM reservations r
                JOIN products p ON p.id=r.product_id
                WHERE r.status='ativa'
                ORDER BY r.id DESC LIMIT 10
                """
            ).fetchall()
            if not rows:
                return "Nenhuma reserva ativa."
            lines = ["🔒 Reservas ativas:"]
            for r in rows:
                lines.append(f"#{r['id']} {r['code']} — {r['title']} — {r['customer_name'] or '-'} — {money(r['sale_price'])}")
            return "\n".join(lines)

        if low in {"/live", "live"} or low.startswith("/live "):
            live = con.execute("SELECT * FROM live_sessions ORDER BY id DESC LIMIT 1").fetchone()
            if not live:
                return "Nenhuma live cadastrada."
            viewers = live_viewer_count(con, int(live["id"]))
            return f"🎥 Live #{live['id']} — {live['title']} — {live['status']} — {viewers} cliente(s) assistindo."


        live_central_answer = telegram_try_live_central_command(con, raw, low, chat_id=chat_id, username=username)
        if live_central_answer is not None:
            return live_central_answer

        if low.startswith("/ping"):
            return "✅ Telegram conectado ao BRECHORISEE. Mensagem recebida pelo app e resposta gerada."

        if low in {"/pedido", "pedido"} or re.fullmatch(r"/?pedido\s+(ajuda|comandos|help)", low):
            return telegram_order_commands_text()

        m_order_help = re.fullmatch(r"/?pedido\s+(\d+)\s+(ajuda|comandos|help)", low)
        if m_order_help:
            return telegram_order_commands_text(int(m_order_help.group(1)))

        if re.fullmatch(r"/?pedido\s+(pago|confirmar|cancelar|cancelado|entrega|entregue|separado)", low):
            return telegram_order_commands_text()

        m_detail = re.search(r"/?pedido\s+(\d+)\s*$", low)
        if m_detail:
            order_id = int(m_detail.group(1))
            o = con.execute("SELECT * FROM online_orders WHERE id=?", (order_id,)).fetchone()
            if not o:
                return "Pedido não encontrado."
            items = con.execute("SELECT * FROM online_order_items WHERE order_id=?", (order_id,)).fetchall()
            lines = [f"🛍️ Pedido #{o['id']} {o['order_code']}", f"Cliente: {o['customer_name']} — {o['customer_phone'] or '-'}", f"Status: {o['status']}", f"Total: {money(o['total'])}"]
            loc = delivery_location_label(o)
            if loc:
                lines += ["📍 Entrega/Google Maps:", loc]
            lines.append("Peças:")
            for it in items:
                lines.append(f"• {it['code']} — {it['title']} — {money(it['price'])} — {it['status']}")
            lines += ["", f"Comandos: /pedido {order_id} pago | /pedido {order_id} cancelar | /pedido {order_id} entrega | /pedido {order_id} entregue"]
            return "\n".join(lines)

        m_delivery = re.search(r"/?pedido\s+(\d+)\s+(entrega|entregue|separado)", low)
        if m_delivery:
            order_id = int(m_delivery.group(1))
            action = m_delivery.group(2)
            new_status = "em_entrega" if action == "entrega" else action
            o = con.execute("SELECT * FROM online_orders WHERE id=?", (order_id,)).fetchone()
            if not o:
                return "Pedido não encontrado."
            con.execute("UPDATE online_orders SET status=? WHERE id=?", (new_status, order_id))
            telegram_send_admin_message(con, f"📦 Pedido {o['order_code']} atualizado pelo Telegram: {new_status}.", "online_order", order_id)
            return f"✅ Pedido {o['order_code']} atualizado para {new_status}."

        if low.startswith("/cliente "):
            term = raw.split(" ", 1)[1].strip()
            like = "%" + term.replace("%", "") + "%"
            rows = con.execute("""
                SELECT * FROM online_orders
                WHERE customer_phone LIKE ? OR customer_name LIKE ? OR customer_instagram LIKE ?
                ORDER BY id DESC LIMIT 8
            """, (like, like, like)).fetchall()
            if not rows:
                return "Nenhum pedido encontrado para esta cliente."
            lines = ["👤 Pedidos da cliente:"]
            for o in rows:
                lines.append(f"#{o['id']} {o['order_code']} — {o['customer_name']} — {money(o['total'])} — {o['status']}")
            return "\n".join(lines)


    m = re.search(r"/?pedido\s+(\d+)\s+(pago|confirmar|cancelar|cancelado)", low)
    if m:
        order_id = int(m.group(1))
        action = m.group(2)
        if action in {"pago", "confirmar"}:
            ok, msg, _sale_id = confirm_online_order_payment_by_id(order_id)
            return ("✅ " if ok else "⚠️ ") + msg
        ok, msg = cancel_online_order_by_id(order_id)
        return ("✅ " if ok else "⚠️ ") + msg

    if low.startswith("/comentar ") or low.startswith("comentar "):
        message = raw.split(" ", 1)[1].strip() if " " in raw else ""
        if not message:
            return "Mensagem vazia."
        with get_db() as con:
            live = con.execute("SELECT * FROM live_sessions WHERE status='ao_vivo' ORDER BY id DESC LIMIT 1").fetchone()
            if not live:
                return "Não há live ao vivo para receber o comentário."
            con.execute(
                "INSERT INTO live_comments(live_session_id, author_name, message, source, created_at) VALUES(?,?,?,?,?)",
                (int(live["id"]), username or "Telegram/Admin", message[:220], "telegram_admin", now_iso()),
            )
        return "Comentário enviado para a live/admin."

    return "Comando não reconhecido. Envie /ajuda."


def telegram_register_payment_proof(payload: dict[str, Any]) -> str:
    message = payload.get("message") or payload.get("edited_message") or {}
    chat = message.get("chat") or {}
    username = chat.get("username") or message.get("from", {}).get("username") or ""
    chat_id = str(chat.get("id") or "")
    caption = str(message.get("caption") or "")
    photos = message.get("photo") or []
    file_id = ""
    if photos:
        file_id = str(sorted(photos, key=lambda p: int(p.get("file_size") or 0))[-1].get("file_id") or "")
    document = message.get("document") or {}
    if not file_id and document:
        file_id = str(document.get("file_id") or "")

    m = re.search(r"(?:pedido|order|#)\s*[:#-]?\s*(\d+)", caption.lower())
    order_id = int(m.group(1)) if m else None
    order_type = "online_order" if order_id else ""
    with get_db() as con:
        con.execute(
            """
            INSERT INTO payment_proofs(source, order_type, order_id, customer_name, file_id, caption, status, notes, created_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            ("telegram", order_type, order_id, username, file_id, caption, "recebido", "Comprovante recebido pelo Telegram.", now_iso()),
        )
        telegram_record_message(con, "inbound", caption or "[comprovante sem legenda]", chat_id=chat_id, username=username, command="comprovante", payload=payload, status="recebido", related_type=order_type, related_id=order_id)
        if order_id:
            telegram_send_admin_message(con, f"🧾 Comprovante recebido no Telegram para pedido #{order_id}. Confira antes de confirmar pagamento.", order_type, order_id)
    return f"Comprovante recebido para pedido #{order_id}." if order_id else "Comprovante recebido. Inclua 'pedido ID' na legenda para vincular automaticamente."


def load_ai_config() -> dict[str, Any]:
    path = BASE_DIR / "ai_config.json"
    default = {
        "trend_keywords": [
            "alfaiataria", "linho", "jeans", "wide leg", "cropped", "básica",
            "vintage", "oversized", "couro", "satinado", "renda", "metalizado",
            "floral", "midi", "camisa", "calça reta"
        ],
        "attention_keywords": [
            "avaria", "mancha", "bolinha", "desbotado", "rasgo", "ajuste",
            "defeito", "muito usado"
        ],
        "slow_stock_days": 90,
        "old_stock_days": 180
    }
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            default.update({k: v for k, v in loaded.items() if v is not None})
        except Exception:
            pass
    return default


def product_text(product: sqlite3.Row | dict[str, Any]) -> str:
    p = row_to_dict(product)
    parts = [
        p.get("title"), p.get("category"), p.get("garment_type"), p.get("size"),
        p.get("brand"), p.get("color"), p.get("condition"), p.get("characteristics"),
        p.get("style_tags"), p.get("season"), p.get("target_audience")
    ]
    return " ".join(str(part or "") for part in parts).lower()


def average_days_to_sale(con: sqlite3.Connection, product: sqlite3.Row | dict[str, Any]) -> tuple[int, float | None]:
    p = row_to_dict(product)
    garment_type = (p.get("garment_type") or "").strip()
    category = (p.get("category") or "").strip()
    params: list[Any] = []
    where = ["status='vendido'", "sold_at IS NOT NULL"]
    if garment_type:
        where.append("garment_type = ?")
        params.append(garment_type)
    elif category:
        where.append("category = ?")
        params.append(category)
    else:
        where.append("1=0")

    rows = con.execute(
        f"SELECT created_at, sold_at FROM products WHERE {' AND '.join(where)} ORDER BY sold_at DESC LIMIT 60",
        params,
    ).fetchall()
    durations = [days_between(r["created_at"], r["sold_at"]) for r in rows]
    if not durations:
        return 0, None
    return len(durations), round(sum(durations) / len(durations), 1)


def local_fashion_ai(product: sqlite3.Row | dict[str, Any], con: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Análise local: usa histórico interno, tempo de estoque e palavras configuráveis.

    Não consulta tendências da internet. O arquivo ai_config.json permite atualizar
    manualmente as palavras que a loja considera tendência ou ponto de atenção.
    """
    close_con = False
    if con is None:
        con = get_db()
        close_con = True

    try:
        p = row_to_dict(product)
        config = load_ai_config()
        text = product_text(p)
        age_days = days_between(p.get("created_at"), p.get("sold_at") if p.get("status") == "vendido" else None)
        cost = safe_float(p.get("cost_price"))
        price = safe_float(p.get("sale_price"))
        margin_pct = ((price - cost) / price * 100) if price else 0

        score = 50.0
        reasons: list[str] = []
        actions: list[str] = []

        sold_count, avg_sale_days = average_days_to_sale(con, p)
        if sold_count:
            score += min(18, sold_count * 3)
            reasons.append(f"{sold_count} peça(s) parecida(s) já venderam no histórico.")
            if avg_sale_days is not None:
                if avg_sale_days <= 30:
                    score += 15
                    reasons.append(f"Giro parecido rápido: média de {avg_sale_days} dias para vender.")
                elif avg_sale_days <= 60:
                    score += 8
                    reasons.append(f"Giro parecido saudável: média de {avg_sale_days} dias.")
                elif avg_sale_days >= 120:
                    score -= 10
                    reasons.append(f"Giro parecido lento: média de {avg_sale_days} dias.")
        else:
            reasons.append("Ainda não há histórico suficiente de peças parecidas.")

        trend_hits = [kw for kw in config.get("trend_keywords", []) if str(kw).lower() in text]
        attention_hits = [kw for kw in config.get("attention_keywords", []) if str(kw).lower() in text]
        if trend_hits:
            score += min(14, len(trend_hits) * 3.5)
            reasons.append("Combina com palavras de tendência configuradas: " + ", ".join(trend_hits[:6]) + ".")
        if attention_hits:
            score -= min(18, len(attention_hits) * 4)
            reasons.append("Possui pontos de atenção: " + ", ".join(attention_hits[:6]) + ".")

        slow_days = int(config.get("slow_stock_days", 90) or 90)
        old_days = int(config.get("old_stock_days", 180) or 180)
        if p.get("status") != "vendido":
            if age_days >= old_days:
                score -= 25
                reasons.append(f"Está há {age_days} dias em estoque, acima do limite antigo de {old_days} dias.")
                actions.append("Avaliar promoção, troca de vitrine, nova foto e postagem com look completo.")
            elif age_days >= slow_days:
                score -= 12
                reasons.append(f"Está há {age_days} dias em estoque, acima do alerta de {slow_days} dias.")
                actions.append("Testar desconto leve, repostagem e mudança de exposição.")
            elif age_days <= 14:
                score += 4
                reasons.append("Peça recém-cadastrada, boa para testar destaque inicial.")
        else:
            if age_days <= 30:
                score += 10
                reasons.append(f"Vendeu rápido: {age_days} dias em estoque.")
            elif age_days >= old_days:
                score -= 8
                reasons.append(f"Levou {age_days} dias para vender.")

        if margin_pct >= 55:
            score += 5
            reasons.append(f"Margem estimada alta: {margin_pct:.0f}%.")
        elif 0 < margin_pct < 25:
            score -= 6
            reasons.append(f"Margem estimada baixa: {margin_pct:.0f}%.")

        score = max(0, min(100, round(score, 1)))
        if score >= 78:
            label = "tendência forte no brechorisee"
            actions.append("Destacar em vitrine, provador, redes sociais e montar look completo.")
        elif score >= 62:
            label = "boa aposta"
            actions.append("Manter bem exposta e acompanhar procura nos próximos dias.")
        elif score >= 45:
            label = "neutra / em observação"
            actions.append("Acompanhar giro e comparar com peças parecidas.")
        else:
            label = "atenção: risco de estoque parado"
            actions.append("Rever preço, foto, descrição, vitrine ou fazer campanha de liquidação.")

        if p.get("status") != "vendido" and age_days >= old_days and score < 50:
            label = "possivelmente fora do momento"
            actions.append("Considerar promoção mais forte ou devolução/repasse, se a política da fornecedora permitir.")

        return {
            "score": score,
            "label": label,
            "age_days": age_days,
            "margin_pct": round(margin_pct, 1),
            "sold_count_similar": sold_count,
            "avg_sale_days_similar": avg_sale_days,
            "trend_hits": trend_hits,
            "attention_hits": attention_hits,
            "reasons": reasons[:8],
            "actions": list(dict.fromkeys(actions))[:6],
            "updated_at": now_iso(),
        }
    finally:
        if close_con:
            con.close()


def ai_summary() -> dict[str, Any]:
    with get_db() as con:
        available = con.execute("SELECT * FROM products WHERE status!='vendido' ORDER BY created_at DESC").fetchall()
        sold = con.execute("SELECT * FROM products WHERE status='vendido' ORDER BY sold_at DESC LIMIT 50").fetchall()
        scored = [(local_fashion_ai(row, con), row) for row in available]
        scored.sort(key=lambda pair: pair[0]["score"], reverse=True)
        trending = [{"ai": ai, "product": row} for ai, row in scored[:8]]
        slow = [{"ai": ai, "product": row} for ai, row in sorted(scored, key=lambda pair: pair[0]["age_days"], reverse=True)[:10]]
        sold_fast = []
        for row in sold:
            age = days_between(row["created_at"], row["sold_at"])
            if age <= 45:
                sold_fast.append({"product": row, "age_days": age})
        return {"trending": trending, "slow": slow, "sold_fast": sold_fast[:8], "config": load_ai_config()}



def report_payload(days: int = 30) -> dict[str, Any]:
    """Relatórios completos para o painel de gráficos.

    Usa somente o banco local: vendas, itens vendidos, produtos, fornecedoras e clientes
    digitados no caixa.
    """
    days = max(7, min(1825, int(days or 30)))
    start_date = (datetime.now() - timedelta(days=days - 1)).date()
    labels = [(start_date + timedelta(days=i)).isoformat() for i in range(days)]

    with get_db() as con:
        sales_rows = con.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, COALESCE(SUM(total),0) AS total, COUNT(*) AS qty,
                   COALESCE(SUM(discount),0) AS discount_total,
                   COALESCE(AVG(total),0) AS avg_ticket
            FROM sales
            WHERE substr(created_at, 1, 10) >= ?
            GROUP BY day
            """,
            (start_date.isoformat(),),
        ).fetchall()

        purchase_rows = con.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, COALESCE(SUM(cost_price),0) AS total, COUNT(*) AS qty
            FROM products
            WHERE substr(created_at, 1, 10) >= ?
            GROUP BY day
            """,
            (start_date.isoformat(),),
        ).fetchall()

        status_rows = con.execute("SELECT status, COUNT(*) AS qty FROM products GROUP BY status").fetchall()

        top_sales = con.execute(
            """
            SELECT COALESCE(NULLIF(p.garment_type,''), NULLIF(p.category,''), 'Sem tipo') AS label,
                   COALESCE(SUM(si.price),0) AS total,
                   COUNT(*) AS qty,
                   COALESCE(SUM(si.price - COALESCE(p.cost_price,0)),0) AS margin
            FROM sale_items si
            JOIN products p ON p.id = si.product_id
            JOIN sales s ON s.id = si.sale_id
            WHERE substr(s.created_at, 1, 10) >= ?
            GROUP BY label
            ORDER BY total DESC
            LIMIT 12
            """,
            (start_date.isoformat(),),
        ).fetchall()

        supplier_rows = con.execute(
            """
            SELECT COALESCE(s.name, 'Sem fornecedora') AS supplier,
                   COUNT(p.id) AS entries,
                   COALESCE(SUM(p.cost_price),0) AS cost_total,
                   COALESCE(SUM(CASE WHEN p.status='vendido' THEN p.sale_price ELSE 0 END),0) AS sold_total
            FROM products p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE substr(p.created_at, 1, 10) >= ?
            GROUP BY supplier
            ORDER BY entries DESC, cost_total DESC
            LIMIT 12
            """,
            (start_date.isoformat(),),
        ).fetchall()

        monthly_sales = con.execute(
            """
            SELECT substr(created_at, 1, 7) AS month,
                   COALESCE(SUM(total),0) AS total,
                   COUNT(*) AS sales_qty,
                   COALESCE(AVG(total),0) AS avg_ticket
            FROM sales
            GROUP BY month
            ORDER BY month
            LIMIT 36
            """
        ).fetchall()

        payment_methods = con.execute(
            """
            SELECT COALESCE(NULLIF(payment_method,''), 'Não informado') AS label,
                   COALESCE(SUM(total),0) AS total,
                   COUNT(*) AS qty
            FROM sales
            WHERE substr(created_at, 1, 10) >= ?
            GROUP BY label
            ORDER BY total DESC
            LIMIT 12
            """,
            (start_date.isoformat(),),
        ).fetchall()

        top_customers = con.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(customer),''), 'Cliente balcão') AS customer,
                   COALESCE(SUM(total),0) AS total,
                   COUNT(*) AS purchases,
                   COALESCE(AVG(total),0) AS avg_ticket
            FROM sales
            WHERE substr(created_at, 1, 10) >= ?
            GROUP BY customer
            ORDER BY total DESC, purchases DESC
            LIMIT 15
            """,
            (start_date.isoformat(),),
        ).fetchall()

        customer_preferences = con.execute(
            """
            SELECT customer, preference, qty, total FROM (
              SELECT COALESCE(NULLIF(TRIM(s.customer),''), 'Cliente balcão') AS customer,
                     COALESCE(NULLIF(p.style_tags,''), NULLIF(p.garment_type,''), NULLIF(p.category,''), 'Sem estilo') AS preference,
                     COUNT(*) AS qty,
                     COALESCE(SUM(si.price),0) AS total,
                     ROW_NUMBER() OVER (
                       PARTITION BY COALESCE(NULLIF(TRIM(s.customer),''), 'Cliente balcão')
                       ORDER BY COUNT(*) DESC, COALESCE(SUM(si.price),0) DESC
                     ) AS rn
              FROM sales s
              JOIN sale_items si ON si.sale_id = s.id
              JOIN products p ON p.id = si.product_id
              WHERE substr(s.created_at, 1, 10) >= ?
              GROUP BY customer, preference
            )
            WHERE rn <= 3
            ORDER BY customer, rn
            LIMIT 60
            """,
            (start_date.isoformat(),),
        ).fetchall()

        portfolio_category = con.execute(
            """
            SELECT COALESCE(NULLIF(category,''), 'Sem categoria') AS label,
                   COUNT(*) AS qty,
                   COALESCE(SUM(sale_price),0) AS value_total,
                   COALESCE(SUM(cost_price),0) AS cost_total
            FROM products
            WHERE status='disponivel'
            GROUP BY label
            ORDER BY qty DESC, value_total DESC
            LIMIT 12
            """
        ).fetchall()

        portfolio_brand = con.execute(
            """
            SELECT COALESCE(NULLIF(brand,''), 'Sem marca') AS label,
                   COUNT(*) AS qty,
                   COALESCE(SUM(sale_price),0) AS value_total
            FROM products
            WHERE status='disponivel'
            GROUP BY label
            ORDER BY qty DESC, value_total DESC
            LIMIT 12
            """
        ).fetchall()

        portfolio_color = con.execute(
            """
            SELECT COALESCE(NULLIF(color,''), 'Sem cor') AS label,
                   COUNT(*) AS qty,
                   COALESCE(SUM(sale_price),0) AS value_total
            FROM products
            WHERE status='disponivel'
            GROUP BY label
            ORDER BY qty DESC, value_total DESC
            LIMIT 12
            """
        ).fetchall()

        portfolio_size = con.execute(
            """
            SELECT COALESCE(NULLIF(size,''), 'Sem tamanho') AS label,
                   COUNT(*) AS qty,
                   COALESCE(SUM(sale_price),0) AS value_total
            FROM products
            WHERE status='disponivel'
            GROUP BY label
            ORDER BY qty DESC, value_total DESC
            LIMIT 12
            """
        ).fetchall()

        day_of_week = con.execute(
            """
            SELECT CASE strftime('%w', created_at)
                     WHEN '0' THEN 'Domingo'
                     WHEN '1' THEN 'Segunda'
                     WHEN '2' THEN 'Terça'
                     WHEN '3' THEN 'Quarta'
                     WHEN '4' THEN 'Quinta'
                     WHEN '5' THEN 'Sexta'
                     ELSE 'Sábado'
                   END AS label,
                   COALESCE(SUM(total),0) AS total,
                   COUNT(*) AS qty
            FROM sales
            WHERE substr(created_at, 1, 10) >= ?
            GROUP BY strftime('%w', created_at)
            ORDER BY strftime('%w', created_at)
            """,
            (start_date.isoformat(),),
        ).fetchall()

        hour_sales = con.execute(
            """
            SELECT substr(created_at, 12, 2) || 'h' AS label,
                   COALESCE(SUM(total),0) AS total,
                   COUNT(*) AS qty
            FROM sales
            WHERE substr(created_at, 1, 10) >= ?
            GROUP BY substr(created_at, 12, 2)
            ORDER BY label
            """,
            (start_date.isoformat(),),
        ).fetchall()

        products = con.execute("SELECT * FROM products ORDER BY created_at DESC").fetchall()

        cashier_summary = con.execute(
            """
            SELECT COALESCE(SUM(total),0) AS total,
                   COALESCE(SUM(discount),0) AS discounts,
                   COALESCE(AVG(total),0) AS avg_ticket,
                   COUNT(*) AS sales_qty
            FROM sales
            WHERE substr(created_at, 1, 10) >= ?
            """,
            (start_date.isoformat(),),
        ).fetchone()

        items_summary = con.execute(
            """
            SELECT COUNT(*) AS items_sold,
                   COALESCE(SUM(si.price),0) AS items_total,
                   COALESCE(SUM(si.price - COALESCE(p.cost_price,0)),0) AS gross_margin
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            JOIN products p ON p.id = si.product_id
            WHERE substr(s.created_at, 1, 10) >= ?
            """,
            (start_date.isoformat(),),
        ).fetchone()

    sales_map = {row["day"]: {"total": float(row["total"] or 0), "qty": int(row["qty"] or 0), "discount_total": float(row["discount_total"] or 0), "avg_ticket": float(row["avg_ticket"] or 0)} for row in sales_rows}
    purchase_map = {row["day"]: {"total": float(row["total"] or 0), "qty": int(row["qty"] or 0)} for row in purchase_rows}

    age_buckets = {"0-30 dias": 0, "31-60 dias": 0, "61-90 dias": 0, "91-180 dias": 0, "+180 dias": 0}
    stock_history = []
    total_stock_value = 0.0
    total_stock_cost = 0.0
    for p in products:
        age = days_between(p["created_at"], p["sold_at"] if p["status"] == "vendido" else None)
        if p["status"] != "vendido":
            total_stock_value += float(p["sale_price"] or 0)
            total_stock_cost += float(p["cost_price"] or 0)
            if age <= 30:
                age_buckets["0-30 dias"] += 1
            elif age <= 60:
                age_buckets["31-60 dias"] += 1
            elif age <= 90:
                age_buckets["61-90 dias"] += 1
            elif age <= 180:
                age_buckets["91-180 dias"] += 1
            else:
                age_buckets["+180 dias"] += 1
        stock_history.append({
            "id": p["id"],
            "code": p["code"],
            "title": p["title"],
            "status": p["status"],
            "created_at": p["created_at"],
            "sold_at": p["sold_at"],
            "age_days": age,
            "sale_price": float(p["sale_price"] or 0),
            "cost_price": float(p["cost_price"] or 0),
            "garment_type": p["garment_type"] or p["category"] or "-",
            "brand": p["brand"] or "-",
            "color": p["color"] or "-",
            "size": p["size"] or "-",
            "style_tags": p["style_tags"] or "-",
        })

    cashier = dict(cashier_summary) if cashier_summary else {}
    item_sum = dict(items_summary) if items_summary else {}
    sales_total = float(cashier.get("total") or 0)
    gross_margin = float(item_sum.get("gross_margin") or 0)

    return {
        "labels": labels,
        "sales": [sales_map.get(day, {"total": 0, "qty": 0, "discount_total": 0, "avg_ticket": 0}) for day in labels],
        "purchases": [purchase_map.get(day, {"total": 0, "qty": 0}) for day in labels],
        "status": [dict(row) for row in status_rows],
        "top_sales": [dict(row) for row in top_sales],
        "suppliers": [dict(row) for row in supplier_rows],
        "age_buckets": age_buckets,
        "stock_history": sorted(stock_history, key=lambda item: item["age_days"], reverse=True),
        "monthly_sales": [dict(row) for row in monthly_sales],
        "payment_methods": [dict(row) for row in payment_methods],
        "top_customers": [dict(row) for row in top_customers],
        "customer_preferences": [dict(row) for row in customer_preferences],
        "portfolio_category": [dict(row) for row in portfolio_category],
        "portfolio_brand": [dict(row) for row in portfolio_brand],
        "portfolio_color": [dict(row) for row in portfolio_color],
        "portfolio_size": [dict(row) for row in portfolio_size],
        "day_of_week": [dict(row) for row in day_of_week],
        "hour_sales": [dict(row) for row in hour_sales],
        "cashier_summary": {
            "total": sales_total,
            "discounts": float(cashier.get("discounts") or 0),
            "avg_ticket": float(cashier.get("avg_ticket") or 0),
            "sales_qty": int(cashier.get("sales_qty") or 0),
            "items_sold": int(item_sum.get("items_sold") or 0),
            "items_total": float(item_sum.get("items_total") or 0),
            "gross_margin": gross_margin,
            "gross_margin_pct": round((gross_margin / sales_total * 100), 1) if sales_total else 0,
            "stock_value": total_stock_value,
            "stock_cost": total_stock_cost,
        },
    }


def get_stats() -> dict[str, Any]:
    with get_db() as con:
        total_active = con.execute("SELECT COUNT(*) FROM products WHERE status='disponivel'").fetchone()[0]
        total_reserved = con.execute("SELECT COUNT(*) FROM products WHERE status='reservado'").fetchone()[0]
        total_sold = con.execute("SELECT COUNT(*) FROM products WHERE status='vendido'").fetchone()[0]
        stock_value = con.execute("SELECT COALESCE(SUM(sale_price),0) FROM products WHERE status!='vendido'").fetchone()[0]
        stock_cost = con.execute("SELECT COALESCE(SUM(cost_price),0) FROM products WHERE status!='vendido'").fetchone()[0]
        sales_total = con.execute("SELECT COALESCE(SUM(total),0) FROM sales").fetchone()[0]
        today = datetime.now().strftime("%Y-%m-%d")
        sales_today = con.execute("SELECT COALESCE(SUM(total),0) FROM sales WHERE created_at LIKE ?", (f"{today}%",)).fetchone()[0]
        purchases_today = con.execute("SELECT COALESCE(SUM(cost_price),0) FROM products WHERE created_at LIKE ?", (f"{today}%",)).fetchone()[0]
        entries_today = con.execute("SELECT COUNT(*) FROM products WHERE created_at LIKE ?", (f"{today}%",)).fetchone()[0]
        slow_stock = con.execute(
            "SELECT COUNT(*) FROM products WHERE status!='vendido' AND julianday('now') - julianday(created_at) >= 90"
        ).fetchone()[0]
        latest = con.execute(
            """
            SELECT p.*, s.name AS supplier_name
            FROM products p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.status != 'vendido'
            ORDER BY p.id DESC
            LIMIT 6
            """
        ).fetchall()

    return {
        "total_active": total_active,
        "total_reserved": total_reserved,
        "total_sold": total_sold,
        "stock_value": stock_value,
        "stock_cost": stock_cost,
        "stock_margin": stock_value - stock_cost,
        "sales_total": sales_total,
        "sales_today": sales_today,
        "purchases_today": purchases_today,
        "entries_today": entries_today,
        "slow_stock": slow_stock,
        "latest": latest,
    }






def _marketing_font(size: int, bold: bool = False):
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _center_crop_image(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert('RGB')
        return ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> list[str]:
    words = (text or '').split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = current + ' ' + word
        bbox = draw.textbbox((0, 0), trial, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines



def auto_marketing_seal(product: dict[str, Any], requested: str = "auto") -> str:
    requested = (requested or "auto").strip().upper()
    if requested and requested != "AUTO":
        return requested[:22]
    status = str(product.get("status") or "").lower()
    if status == "vendido":
        return "VENDIDO"
    if status == "reservado":
        return "RESERVADO"
    created = product.get("created_at")
    age = days_between(created) if created else 0
    text = product_text(product)
    if age <= 14:
        return "NOVO"
    if product.get("trend_label") or any(word in text for word in ["tendencia", "tendência", "wide leg", "linho", "alfaiataria", "metalizado"]):
        return "TENDÊNCIA"
    if safe_float(product.get("sale_price")) < 50:
        return "ACHADINHO"
    return "PEÇA ÚNICA"


MARKETING_STYLES: dict[str, dict[str, tuple[int, int, int, int] | str]] = {
    "minimalista": {
        "panel": (255, 252, 248, 218),
        "title": (116, 51, 38, 255),
        "subtitle": (75, 55, 51, 255),
        "accent": (168, 77, 58, 255),
    },
    "chic": {
        "panel": (248, 240, 231, 225),
        "title": (45, 29, 27, 255),
        "subtitle": (88, 68, 61, 255),
        "accent": (45, 29, 27, 255),
    },
    "promocao": {
        "panel": (255, 245, 226, 232),
        "title": (129, 56, 28, 255),
        "subtitle": (75, 55, 51, 255),
        "accent": (197, 86, 38, 255),
    },
    "luxo": {
        "panel": (39, 29, 27, 225),
        "title": (255, 249, 237, 255),
        "subtitle": (243, 220, 194, 255),
        "accent": (243, 220, 194, 255),
    },
}

def _draw_marketing_overlay(
    base: Image.Image,
    product: dict[str, Any],
    title: str,
    subtitle: str = '',
    footer: str = 'BRECHORISEE • Moda Circular',
    template_style: str = 'minimalista',
    seal: str = '',
) -> Image.Image:
    img = base.copy().convert('RGBA')
    w, h = img.size
    style = MARKETING_STYLES.get((template_style or 'minimalista').lower(), MARKETING_STYLES['minimalista'])
    panel_color = style['panel']  # type: ignore[index]
    title_color = style['title']  # type: ignore[index]
    subtitle_color = style['subtitle']  # type: ignore[index]
    accent_color = style['accent']  # type: ignore[index]

    overlay = Image.new('RGBA', img.size, (0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    panel_h = int(h * 0.28)
    if template_style == 'luxo':
        draw.rectangle((0, h - panel_h - 45, w, h), fill=(0, 0, 0, 65))
    draw.rounded_rectangle((30, h - panel_h - 30, w - 30, h - 30), radius=30, fill=panel_color)

    font_title = _marketing_font(max(34, w // 20), bold=True)
    font_sub = _marketing_font(max(24, w // 34), bold=False)
    font_footer = _marketing_font(max(18, w // 50), bold=True)
    font_badge = _marketing_font(max(20, w // 44), bold=True)
    text_draw = ImageDraw.Draw(overlay)

    # Selo superior
    if seal:
        seal_text = seal.upper()[:24]
        bbox = text_draw.textbbox((0, 0), seal_text, font=font_badge)
        bw = bbox[2] - bbox[0] + 38
        bh = bbox[3] - bbox[1] + 24
        bx, by = 34, 34
        draw.rounded_rectangle((bx, by, bx + bw, by + bh), radius=999, fill=accent_color)
        fill = (255, 255, 255, 255) if template_style != 'luxo' else (39, 29, 27, 255)
        text_draw.text((bx + 19, by + 11), seal_text, font=font_badge, fill=fill)

    y = h - panel_h
    x = 60
    max_text_w = w - 120
    for line in _wrap_text(text_draw, title, font_title, max_text_w)[:3]:
        text_draw.text((x, y), line, font=font_title, fill=title_color)
        bbox = text_draw.textbbox((x, y), line, font=font_title)
        y = bbox[3] + 6
    if subtitle:
        for line in _wrap_text(text_draw, subtitle, font_sub, max_text_w)[:3]:
            text_draw.text((x, y), line, font=font_sub, fill=subtitle_color)
            bbox = text_draw.textbbox((x, y), line, font=font_sub)
            y = bbox[3] + 4
    text_draw.text((x, h - 78), footer, font=font_footer, fill=accent_color)

    # assinatura discreta
    circle_r = max(34, w // 22)
    cx, cy = w - 72, 70
    draw.ellipse((cx-circle_r, cy-circle_r, cx+circle_r, cy+circle_r), outline=accent_color, width=max(3, w // 180))
    mark_font = _marketing_font(max(18, w // 48), bold=True)
    text_draw.text((cx-circle_r+16, cy-12), "BR", font=mark_font, fill=accent_color)

    return Image.alpha_composite(img, overlay).convert('RGB')

def _make_placeholder(size: tuple[int, int], title: str) -> Image.Image:
    img = Image.new('RGB', size, (247, 228, 217))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((20, 20, size[0]-20, size[1]-20), radius=28, outline=(168, 77, 58), width=3)
    font = _marketing_font(max(30, size[0] // 18), bold=True)
    lines = _wrap_text(draw, title or 'BRECHORISEE', font, size[0]-120)
    total_h = 0
    line_boxes = []
    for line in lines[:3]:
        bbox = draw.textbbox((0,0), line, font=font)
        line_boxes.append((line, bbox))
        total_h += (bbox[3]-bbox[1]) + 10
    y = (size[1]-total_h)//2
    for line, bbox in line_boxes:
        tw = bbox[2]-bbox[0]
        draw.text(((size[0]-tw)//2, y), line, font=font, fill=(116, 51, 38))
        y += (bbox[3]-bbox[1]) + 10
    return img


def render_post_image(product: dict[str, Any], media: list[dict[str, Any]], caption: str, content_type: str = 'post', template_style: str = 'minimalista', seal: str = '') -> str:
    size = (1080, 1350)
    if content_type == 'story':
        size = (1080, 1920)
    title = product.get('title') or 'Peça'
    subtitle = f"{money(product.get('sale_price'))} • {product.get('brand') or 'Sem marca'}"
    hero = next((m for m in media if m.get('media_type') == 'image' and m.get('filename')), None)
    if hero:
        base = _center_crop_image(UPLOAD_DIR / hero['filename'], size)
    else:
        base = _make_placeholder(size, title)
    final = _draw_marketing_overlay(base, product, title, subtitle, template_style=template_style, seal=seal)
    file_name = f"{slugify(product.get('code') or title)}-{content_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    final.save(GENERATED_MARKETING_DIR / file_name, quality=95)
    return f"/static/generated/marketing/{file_name}"


def _frame_from_video(video_path: Path, target_size: tuple[int, int], sample_every: int = 8, max_frames: int = 36) -> list[Image.Image]:
    if imageio is None:
        return []
    frames: list[Image.Image] = []
    try:
        reader = imageio.get_reader(str(video_path))
        count = 0
        for idx, frame in enumerate(reader):
            if idx % max(1, sample_every) != 0:
                continue
            pil = Image.fromarray(frame).convert('RGB')
            pil = ImageOps.fit(pil, target_size, method=Image.Resampling.LANCZOS)
            frames.append(pil)
            count += 1
            if count >= max_frames:
                break
        reader.close()
    except Exception:
        return []
    return frames


def render_reel_video(product: dict[str, Any], media: list[dict[str, Any]], template_style: str = 'minimalista', seal: str = '', duration_mode: str = 'medio', quality_mode: str = 'alta') -> str | None:
    if imageio is None:
        return None
    profile = generation_profile(duration_mode, quality_mode)
    size = profile['size']
    fps = profile['fps']
    image_hold = fps * profile['image_secs']
    frames: list[Image.Image] = []
    title = product.get('title') or 'Peça'
    subtitle = f"{money(product.get('sale_price'))} • {product.get('brand') or 'Sem marca'}"

    for item in media:
        mtype = item.get('media_type')
        filename = item.get('filename')
        if not filename:
            continue
        path = UPLOAD_DIR / filename
        if mtype == 'image' and path.exists():
            base = _center_crop_image(path, size)
            slide = _draw_marketing_overlay(base, product, title, subtitle, footer='Peça única • Chame no direct', template_style=template_style, seal=seal)
            frames.extend([slide.copy() for _ in range(image_hold)])
        elif mtype == 'video' and path.exists():
            video_frames = _frame_from_video(path, size, sample_every=profile['sample_every'], max_frames=profile['max_video_frames'])
            if video_frames:
                for vf in video_frames:
                    slide = _draw_marketing_overlay(vf, product, title, subtitle, footer='Vídeo da peça • BRECHORISEE', template_style=template_style, seal=seal)
                    frames.append(slide)
            else:
                placeholder = _make_placeholder(size, 'Vídeo da peça')
                slide = _draw_marketing_overlay(placeholder, product, title, subtitle, footer='Vídeo • BRECHORISEE', template_style=template_style, seal=seal)
                frames.extend([slide.copy() for _ in range(image_hold)])

    if not frames:
        placeholder = _make_placeholder(size, title)
        slide = _draw_marketing_overlay(placeholder, product, title, subtitle, footer='BRECHORISEE', template_style=template_style, seal=seal)
        frames.extend([slide.copy() for _ in range(image_hold)])

    end_slide = _make_placeholder(size, 'Chame no direct')
    end_slide = _draw_marketing_overlay(end_slide, product, 'Disponível no BRECHORISEE', subtitle, footer='Moda circular com estilo', template_style=template_style, seal=seal)
    frames.extend([end_slide.copy() for _ in range(fps * 2)])

    file_name = f"{slugify(product.get('code') or title)}-reel-{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
    output_path = GENERATED_MARKETING_DIR / file_name
    try:
        writer = imageio.get_writer(str(output_path), fps=fps, codec='libx264', quality=profile['quality'], macro_block_size=None)
        for frame in frames:
            writer.append_data(np.array(frame) if np is not None else frame)
        writer.close()
        return f"/static/generated/marketing/{file_name}"
    except Exception:
        try:
            writer.close()
        except Exception:
            pass
        return None


def render_carousel_slides(product: dict[str, Any], media: list[dict[str, Any]], template_style: str = 'minimalista', seal: str = '') -> list[str]:
    urls: list[str] = []
    size = (1080, 1350)
    title = product.get('title') or 'Peça'
    subtitle = f"{money(product.get('sale_price'))} • {product.get('brand') or 'Sem marca'}"
    chosen = [m for m in media if m.get('media_type') == 'image'][:6]
    if not chosen:
        return []
    for idx, item in enumerate(chosen, start=1):
        path = UPLOAD_DIR / item['filename']
        if not path.exists():
            continue
        base = _center_crop_image(path, size)
        footer = f"Slide {idx} • BRECHORISEE"
        final = _draw_marketing_overlay(base, product, title, subtitle, footer=footer, template_style=template_style, seal=seal)
        file_name = f"{slugify(product.get('code') or title)}-carrossel-{idx}-{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        final.save(GENERATED_MARKETING_DIR / file_name, quality=95)
        urls.append(f"/static/generated/marketing/{file_name}")
    return urls


def get_product_with_media(product_id: int) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    with get_db() as con:
        product = con.execute(
            """
            SELECT p.*, s.name AS supplier_name
            FROM products p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.id = ?
            """,
            (product_id,),
        ).fetchone()
        media = con.execute(
            "SELECT * FROM product_media WHERE product_id=? ORDER BY CASE WHEN notes='Foto principal' THEN 0 ELSE 1 END, id DESC",
            (product_id,),
        ).fetchall()
    return product, media


def marketing_hashtags(product: sqlite3.Row | dict[str, Any]) -> list[str]:
    p = row_to_dict(product)
    tags = [
        'brechorisee', 'modacircular', 'brecho', 'brechoonline', 'achadinhos',
        'sustentabilidade', 'pecaunica'
    ]
    extra = [p.get('garment_type'), p.get('brand'), p.get('color'), p.get('style_tags'), p.get('season')]
    for item in extra:
        for part in str(item or '').replace(';', ',').split(','):
            clean = unicodedata.normalize('NFKD', part).encode('ascii', 'ignore').decode('ascii')
            clean = ''.join(ch for ch in clean if ch.isalnum())
            if clean:
                tags.append(clean.lower())
    seen = set()
    result = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            result.append('#' + tag)
        if len(result) >= 14:
            break
    return result




def build_narration_text(product: sqlite3.Row | dict[str, Any], custom_text: str = '', content_type: str = 'reel') -> str:
    p = row_to_dict(product)
    garment = p.get('garment_type') or p.get('title') or 'peça'
    brand = p.get('brand') or 'sem marca'
    size = p.get('size') or 'tamanho único'
    color = p.get('color') or ''
    price = money(p.get('sale_price'))
    mood = (custom_text or '').strip()
    intro = f"Apresentando {p.get('title') or garment}, disponível no BRECHORISEE."
    body = f"Uma {garment.lower()} {color.lower() if color else ''} da marca {brand}, no tamanho {size}.".replace('  ', ' ')
    fit = 'Uma peça única de moda circular, com estilo e personalidade.'
    if mood:
        fit = mood
    ending = f"Valor {price}. Se você gostou, chama no direct para reservar."
    return ' '.join(part.strip() for part in [intro, body, fit, ending] if part.strip())


def suggest_music_prompts(product: sqlite3.Row | dict[str, Any], template_style: str = 'minimalista', music_mode: str = 'viral') -> list[str]:
    p = row_to_dict(product)
    base = [
        'Pesquisar na biblioteca do Instagram: viral fashion',
        'Pesquisar na biblioteca do Instagram: trend aesthetic',
        'Pesquisar na biblioteca do Instagram: chic outfit',
    ]
    garment = str(p.get('garment_type') or p.get('title') or '').lower()
    style_tags = str(p.get('style_tags') or '').lower()
    if 'bolsa' in garment or 'acessor' in garment:
        base.append('Pesquisar: elegant accessory trend')
    if 'vestido' in garment or 'festa' in style_tags:
        base.append('Pesquisar: glamour viral')
    if 'jeans' in garment or 'street' in style_tags:
        base.append('Pesquisar: streetwear viral beat')
    if template_style == 'luxo':
        base.append('Pesquisar: luxury chic trend')
    if music_mode == 'animada':
        base.append('Pesquisar: upbeat viral')
    elif music_mode == 'elegante':
        base.append('Pesquisar: classy fashion')
    elif music_mode == 'romantica':
        base.append('Pesquisar: soft romantic trend')
    seen = []
    for item in base:
        if item not in seen:
            seen.append(item)
    return seen[:6]


def generation_profile(duration_mode: str = 'medio', quality_mode: str = 'alta') -> dict[str, Any]:
    duration_mode = (duration_mode or 'medio').strip().lower()
    quality_mode = (quality_mode or 'alta').strip().lower()
    image_secs = {'curto': 2, 'medio': 3, 'longo': 4}.get(duration_mode, 3)
    max_video_frames = {'curto': 18, 'medio': 36, 'longo': 60}.get(duration_mode, 36)
    sample_every = {'curto': 12, 'medio': 8, 'longo': 6}.get(duration_mode, 8)
    size = {'alta': (720, 1280), 'maxima': (1080, 1920)}.get(quality_mode, (720, 1280))
    fps = {'alta': 18, 'maxima': 24}.get(quality_mode, 18)
    quality = {'alta': 8, 'maxima': 9}.get(quality_mode, 8)
    return {
        'duration_mode': duration_mode,
        'quality_mode': quality_mode,
        'image_secs': image_secs,
        'max_video_frames': max_video_frames,
        'sample_every': sample_every,
        'size': size,
        'fps': fps,
        'quality': quality,
        'duration_label': {'curto': 'Curto', 'medio': 'Médio', 'longo': 'Longo'}.get(duration_mode, 'Médio'),
        'quality_label': {'alta': 'Alta', 'maxima': 'Máxima'}.get(quality_mode, 'Alta'),
    }


def build_marketing_content(product: sqlite3.Row | dict[str, Any], media: list[sqlite3.Row | dict[str, Any]], custom_text: str = '', content_type: str = 'post', template_style: str = 'minimalista', seal: str = 'auto', duration_mode: str = 'medio', quality_mode: str = 'alta', audio_mode: str = 'narracao', music_mode: str = 'viral') -> dict[str, Any]:
    p = row_to_dict(product)
    media_dicts = [row_to_dict(m) for m in media]
    content_type = (content_type or 'post').strip().lower()
    template_style = (template_style or 'minimalista').strip().lower()
    seal_text = auto_marketing_seal(p, seal)
    profile = generation_profile(duration_mode, quality_mode)
    label_map = {'post': 'Post', 'carrossel': 'Carrossel', 'reel': 'Reel', 'story': 'Story'}
    format_label = label_map.get(content_type, 'Post')

    garment = p.get('garment_type') or p.get('title') or 'Peça'
    brand = p.get('brand') or 'Sem marca'
    size = p.get('size') or 'único'
    color = p.get('color') or ''
    price = money(p.get('sale_price'))
    status_line = 'Peça única disponível no BRECHORISEE ✨'

    base_text = (custom_text or '').strip()
    if not base_text:
        base_text = f"{garment} {color.lower() if color else ''} com ótimo potencial para compor looks lindos e conscientes.".strip()

    caption_lines = [
        status_line,
        '',
        base_text,
        '',
        f"Tipo: {garment}",
        f"Marca: {brand}",
        f"Tamanho: {size}",
    ]
    if color:
        caption_lines.append(f"Cor: {color}")
    caption_lines.append(f"Preço: {price}")
    caption_lines += [
        '',
        'Chame no direct para reservar 💌',
    ]
    hashtags = marketing_hashtags(p)
    full_caption = '\n'.join(caption_lines + ['', ' '.join(hashtags)])

    overlay_text = [
        p.get('title') or garment,
        price,
        'Peça única • BRECHORISEE'
    ]

    reel_script = [
        'Cena 1: capa com a melhor foto da peça e o logo BRECHORISEE.',
        'Cena 2: mostrar frente/caimento da peça.',
        'Cena 3: mostrar detalhes, textura, estampa ou etiqueta.',
        f"Cena 4: encerrar com preço ({price}) e chamada para direct.",
    ]
    if any(m.get('media_type') == 'video' for m in media_dicts):
        reel_script.insert(2, 'Aproveitar o vídeo selecionado para mostrar movimento e caimento.')
    if audio_mode == 'narracao':
        reel_script.append('Adicionar narração apresentando a peça com voz suave e clara.')
    elif audio_mode == 'narracao_musica':
        reel_script.append('Usar narração principal e, na postagem final, aplicar música viral em volume baixo no Instagram.')

    narration_text = build_narration_text(p, custom_text=base_text, content_type=content_type)
    music_suggestions = suggest_music_prompts(p, template_style=template_style, music_mode=music_mode)

    return {
        'content_type': content_type,
        'format_label': format_label,
        'template_style': template_style,
        'seal': seal_text,
        'duration_mode': profile['duration_mode'],
        'duration_label': profile['duration_label'],
        'quality_mode': profile['quality_mode'],
        'quality_label': profile['quality_label'],
        'audio_mode': audio_mode,
        'music_mode': music_mode,
        'title': p.get('title') or garment,
        'overlay_text': overlay_text,
        'caption': '\n'.join(caption_lines),
        'hashtags': ' '.join(hashtags),
        'full_caption': full_caption,
        'cta': 'Chame no direct',
        'narration_text': narration_text,
        'music_suggestions': music_suggestions,
        'reel_script': reel_script,
        'media': media_dicts,
        'product': p,
    }


def load_marketing_drafts(limit: int = 12) -> list[sqlite3.Row]:
    with get_db() as con:
        return con.execute(
            """
            SELECT d.*, p.title AS product_title, p.code AS product_code
            FROM marketing_drafts d
            JOIN products p ON p.id = d.product_id
            ORDER BY d.id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()




def delivery_maps_links(address: str = "", city: str = "") -> dict[str, str]:
    full = " ".join(part.strip() for part in [address or "", city or ""] if part and part.strip())
    q = quote_plus(full)
    if not q:
        return {"google_maps": "", "waze": ""}
    return {
        "google_maps": f"https://www.google.com/maps/search/?api=1&query={q}",
        "waze": f"https://waze.com/ul?q={q}&navigate=yes",
    }


def delivery_status_label(status: str) -> str:
    return {
        "pendente": "Pendente",
        "separado": "Separado",
        "rota": "Em rota",
        "entregue": "Entregue",
        "cancelada": "Cancelada",
        "cliente_ausente": "Cliente ausente",
    }.get((status or "").lower(), status or "Pendente")


def delivery_items_for_sale(con: sqlite3.Connection, sale_id: int) -> list[sqlite3.Row]:
    return con.execute(
        """
        SELECT p.*
        FROM sale_items si
        JOIN products p ON p.id = si.product_id
        WHERE si.sale_id=?
        ORDER BY p.title
        """,
        (sale_id,),
    ).fetchall()


def hydrate_delivery(row: sqlite3.Row, con: sqlite3.Connection) -> dict[str, Any]:
    d = dict(row)
    d["maps"] = delivery_maps_links(d.get("address") or "", d.get("city") or "")
    if d.get("delivery_maps_url"):
        d["maps"]["google_maps"] = d.get("delivery_maps_url") or d["maps"].get("google_maps", "")
    d["tracking"] = delivery_tracking_payload(d)
    d["status_label"] = delivery_status_label(d.get("status") or "")
    d["items"] = con.execute(
        """
        SELECT di.*, p.code, p.title, p.image_filename, p.size, p.color, p.brand
        FROM delivery_items di
        JOIN products p ON p.id = di.product_id
        WHERE di.delivery_id=?
        ORDER BY di.id
        """,
        (d["id"],),
    ).fetchall()
    return d


def deliveries_summary_payload() -> dict[str, Any]:
    with get_db() as con:
        rows = con.execute("SELECT status, COUNT(*) AS qty FROM deliveries GROUP BY status").fetchall()
        cards = {row["status"]: row["qty"] for row in rows}
        today = datetime.now().strftime("%Y-%m-%d")
        pending_today = con.execute(
            "SELECT COUNT(*) FROM deliveries WHERE status <> 'entregue' AND COALESCE(scheduled_at,'') LIKE ?",
            (f"{today}%",),
        ).fetchone()[0]
    return {
        "pendente": cards.get("pendente", 0),
        "separado": cards.get("separado", 0),
        "rota": cards.get("rota", 0),
        "cliente_ausente": cards.get("cliente_ausente", 0),
        "entregue": cards.get("entregue", 0),
        "cancelada": cards.get("cancelada", 0),
        "hoje": pending_today,
    }




WHATSAPP_ORDER_STATUSES = {
    "orcamento_enviado": "Orçamento enviado",
    "aguardando_pagamento": "Aguardando pagamento",
    "pago": "Pago",
    "separado": "Separado",
    "em_entrega": "Em entrega",
    "cliente_ausente": "Cliente ausente",
    "entregue": "Entregue",
    "cancelado": "Cancelado",
}


def normalize_phone_for_whatsapp(phone: str) -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if digits and not digits.startswith("55") and len(digits) in {10, 11}:
        digits = "55" + digits
    return digits


def full_static_url(request: Request, filename: str | None) -> str:
    if not filename:
        return ""
    # Usa o host atual quando possível; no app Android geralmente é o IP do computador.
    base = str(request.base_url).rstrip("/")
    return f"{base}/static/uploads/{filename}"


def maps_search_url(address: str) -> str:
    query = quote_plus(address or "")
    return f"https://www.google.com/maps/search/?api=1&query={query}" if query else ""


def whatsapp_order_label(status: str) -> str:
    return WHATSAPP_ORDER_STATUSES.get(status or "", status or "-")


templates.env.filters["whatsapp_order_label"] = whatsapp_order_label


def load_whatsapp_order(order_id: int) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    with get_db() as con:
        order = con.execute("SELECT * FROM whatsapp_orders WHERE id=?", (order_id,)).fetchone()
        items = con.execute(
            """
            SELECT woi.*, p.code, p.title, p.image_filename, p.garment_type, p.size, p.color, p.brand, p.status AS product_status
            FROM whatsapp_order_items woi
            JOIN products p ON p.id = woi.product_id
            WHERE woi.order_id=?
            ORDER BY woi.id
            """,
            (order_id,),
        ).fetchall()
    return order, items


def build_whatsapp_order_message(request: Request, order: sqlite3.Row | dict[str, Any], items: list[sqlite3.Row | dict[str, Any]]) -> str:
    o = row_to_dict(order)
    rows = [row_to_dict(i) for i in items]
    total = sum(safe_float(item.get("price")) for item in rows) or safe_float(o.get("total"))
    customer = o.get("customer_name") or "cliente"
    lines = [
        f"Oi, {customer}! ✨",
        "",
        "Seu pedido no BRECHORISEE ficou assim:",
        "",
    ]
    for idx, item in enumerate(rows, start=1):
        desc = f"{idx}. {item.get('code')} - {item.get('title') or item.get('garment_type') or 'Peça'}"
        details = []
        if item.get("size"):
            details.append(f"tam. {item.get('size')}")
        if item.get("color"):
            details.append(str(item.get("color")))
        if item.get("brand"):
            details.append(str(item.get("brand")))
        if details:
            desc += " (" + " • ".join(details) + ")"
        desc += f" - {money(item.get('price'))}"
        lines.append(desc)

    lines += ["", f"Total: {money(total)}", ""]

    payment_method = (o.get("payment_method") or "").strip()
    if payment_method:
        lines.append(f"Pagamento: {payment_method}")

    if o.get("pix_copy_paste"):
        lines += ["", "Pix copia e cola:", str(o.get("pix_copy_paste"))]
    elif o.get("pix_key"):
        lines += ["", f"Chave Pix: {o.get('pix_key')}"]

    if o.get("payment_link"):
        lines += ["", "Cartão/link InfinitePay:", str(o.get("payment_link"))]

    if o.get("delivery_type") == "entrega":
        lines += ["", "Entrega:", str(o.get("address") or "Endereço a confirmar")]
    else:
        pickup = o.get("pickup_location") or "Retirada na loja BRECHORISEE."
        lines += ["", "Retirada:", pickup]
        murl = maps_search_url(pickup)
        if murl:
            lines.append(f"Localização: {murl}")

    photo_lines = []
    for item in rows:
        url = full_static_url(request, item.get("image_filename"))
        if url:
            photo_lines.append(f"{item.get('code')}: {url}")
    if photo_lines:
        lines += ["", "Fotos das peças:"]
        lines.extend(photo_lines)

    if o.get("reservation_expires_at"):
        lines += ["", f"Reserva válida até: {date_br(o.get('reservation_expires_at'))}"]

    lines += ["", "Após o pagamento, envie o comprovante por aqui para confirmarmos sua compra 💌"]
    return "\n".join(lines)


def whatsapp_order_to_sale(order_id: int) -> tuple[bool, str, int | None]:
    with get_db() as con:
        order = con.execute("SELECT * FROM whatsapp_orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            return False, "Pedido não encontrado.", None
        if order["sale_id"]:
            return True, "Pagamento já confirmado.", order["sale_id"]
        if order["status"] == "cancelado":
            return False, "Pedido cancelado.", None

        items = con.execute(
            """
            SELECT woi.*, p.status AS product_status, p.code
            FROM whatsapp_order_items woi
            JOIN products p ON p.id = woi.product_id
            WHERE woi.order_id=?
            """,
            (order_id,),
        ).fetchall()
        if not items:
            return False, "Pedido sem peças.", None

        blocked = [i["code"] for i in items if i["product_status"] not in {"disponivel", "reservado"}]
        if blocked:
            return False, "Algumas peças não estão disponíveis/reservadas: " + ", ".join(blocked), None

        total = sum(float(i["price"] or 0) for i in items)
        sale_code = generate_sale_code()
        cur = con.execute(
            "INSERT INTO sales(sale_code, customer, payment_method, discount, total, paid, change_value, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (sale_code, order["customer_name"], order["payment_method"] or "WhatsApp", 0, total, total, 0, now_iso()),
        )
        sale_id = cur.lastrowid
        sold_time = now_iso()
        for item in items:
            con.execute(
                "INSERT INTO sale_items(sale_id, product_id, price) VALUES(?,?,?)",
                (sale_id, item["product_id"], item["price"]),
            )
            con.execute("UPDATE products SET status='vendido', sold_at=? WHERE id=?", (sold_time, item["product_id"]))
            con.execute(
                "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                (item["product_id"], "venda_whatsapp", f"Pagamento confirmado no pedido WhatsApp #{order_id}. Peça retirada do estoque disponível.", sold_time),
            )
        con.execute(
            "UPDATE whatsapp_orders SET status='pago', sale_id=?, paid_at=?, updated_at=? WHERE id=?",
            (sale_id, sold_time, sold_time, order_id),
        )
    return True, f"Pagamento confirmado. Venda {sale_code} criada.", sale_id





DEFAULT_CLOUD_URL = "https://brechorisee-online.onrender.com"

AUTO_SYNC_INTERVAL_SECONDS = int(os.getenv("AUTO_SYNC_INTERVAL_SECONDS", "60") or "60")
_AUTO_SYNC_LOCK = threading.Lock()
_LAST_AUTO_SYNC_AT = 0.0
_LAST_AUTO_SYNC_RESULT: dict[str, Any] = {"ok": None, "message": "Sincronização automática ainda não executada."}



def cloud_sync_url() -> str:
    """Endereço da nuvem usado pelo sistema local para publicar a vitrine.

    No Render/nuvem, fica vazio por padrão para evitar que a nuvem tente sincronizar com ela mesma.
    No computador/local, usa CLOUD_SYNC_URL se existir; senão usa o endereço padrão da vitrine criada.
    """
    configured = os.getenv("CLOUD_SYNC_URL", "").strip().rstrip("/")
    if configured:
        return configured
    if os.getenv("APP_ENV", "").lower() == "production":
        return ""
    return DEFAULT_CLOUD_URL


def is_cloud_sync_enabled(request: Request | None = None) -> bool:
    url = cloud_sync_url()
    if not url:
        return False
    # Evita publicar em si mesmo.
    try:
        if request is not None and str(request.base_url).rstrip("/") == url:
            return False
    except Exception:
        pass
    return True


def _file_to_base64(filename: str | None) -> str:
    if not filename:
        return ""
    path = UPLOAD_DIR / filename
    if not path.exists() or not path.is_file():
        return ""
    try:
        data = path.read_bytes()
        # Limite para evitar travar internet ruim. Fotos grandes podem ser reenviadas manualmente depois.
        if len(data) > 8 * 1024 * 1024:
            return ""
        return base64.b64encode(data).decode("ascii")
    except Exception:
        return ""


def _save_base64_image(image_b64: str, prefix: str, original_filename: str = "") -> tuple[str | None, str | None, float | None, float | None, float | None]:
    if not image_b64:
        return None, None, None, None, None
    try:
        raw = base64.b64decode(image_b64.encode("ascii"), validate=False)
    except Exception:
        return None, None, None, None, None
    if not raw:
        return None, None, None, None, None
    ext = Path(original_filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        ext = ".jpg"
    filename = _unique_upload_name(prefix or "sync", ext)
    dest = UPLOAD_DIR / filename
    try:
        dest.write_bytes(raw)
        image_hash, avg = image_signature(dest)
        return filename, image_hash, avg[0], avg[1], avg[2]
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        return None, None, None, None, None


def product_sync_payload(con: sqlite3.Connection, product_id: int, include_image: bool = True) -> dict[str, Any]:
    row = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not row:
        return {}
    payload = dict(row)
    payload["source_product_id"] = product_id
    payload["image_base64"] = _file_to_base64(row["image_filename"]) if include_image else ""
    payload["image_original_filename"] = row["image_filename"] or ""
    return payload


def enqueue_cloud_operation(con: sqlite3.Connection, op_type: str, payload: dict[str, Any]) -> int:
    cur = con.execute(
        "INSERT INTO sync_outbox(target, op_type, payload, status, attempts, created_at) VALUES(?,?,?,?,?,?)",
        ("cloud", op_type, json.dumps(payload or {}, ensure_ascii=False), "pendente", 0, now_iso()),
    )
    return int(cur.lastrowid)


def enqueue_product_cloud_sync(con: sqlite3.Connection, product_id: int, reason: str = "product_upsert") -> None:
    payload = product_sync_payload(con, product_id, include_image=True)
    if not payload:
        return
    payload["sync_reason"] = reason
    enqueue_cloud_operation(con, "upsert_product", payload)


def enqueue_sale_cloud_sync(con: sqlite3.Connection, sale_id: int) -> None:
    sale = con.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    if not sale:
        return
    items = con.execute(
        """
        SELECT p.code, p.title, p.sale_price, p.id AS product_id
        FROM sale_items si
        JOIN products p ON p.id = si.product_id
        WHERE si.sale_id=?
        """,
        (sale_id,),
    ).fetchall()
    payload = dict(sale)
    payload["source_sale_id"] = sale_id
    payload["codes"] = [row["code"] for row in items]
    payload["items"] = [dict(row) for row in items]
    enqueue_cloud_operation(con, "upsert_sale", payload)


def _sync_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"User-Agent": "BRECHORISEE-Sync/1.0"}
    if extra:
        headers.update(extra)
    if BRECHORISEE_SYNC_TOKEN:
        headers["X-Brechorisee-Sync-Token"] = BRECHORISEE_SYNC_TOKEN
    return headers


def _http_json(url: str, payload: dict[str, Any], timeout: int = 18) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=_sync_headers({"Content-Type": "application/json"}),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except Exception:
        return {"ok": False, "message": body[:500]}



def _outbox_has_pending_product(con: sqlite3.Connection, code: str) -> bool:
    rows = con.execute(
        "SELECT payload FROM sync_outbox WHERE target='cloud' AND op_type='upsert_product' AND status IN ('pendente','erro') ORDER BY id DESC LIMIT 80"
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
            if normalize_code_token(payload.get("code") or "", default="", max_len=50) == code:
                return True
        except Exception:
            continue
    return False


def _outbox_has_pending_sale(con: sqlite3.Connection, sale_code: str) -> bool:
    rows = con.execute(
        "SELECT payload FROM sync_outbox WHERE target='cloud' AND op_type='upsert_sale' AND status IN ('pendente','erro') ORDER BY id DESC LIMIT 80"
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
            if str(payload.get("sale_code") or "") == sale_code:
                return True
        except Exception:
            continue
    return False


def enqueue_unsynced_local_state(max_products: int = 300, max_sales: int = 100) -> dict[str, Any]:
    """Coloca automaticamente na fila tudo que existe localmente e ainda não foi para a nuvem.

    Não depende de botão. Usa código da peça e código da venda como referência para evitar duplicar.
    """
    if not cloud_sync_url():
        return {"products": 0, "sales": 0, "message": "Nuvem não configurada."}

    queued_products = queued_sales = 0
    with get_db() as con:
        product_rows = con.execute(
            """
            SELECT id, code FROM products
            WHERE code IS NOT NULL AND TRIM(code) <> ''
              AND (cloud_synced_at IS NULL OR cloud_synced_at='' OR COALESCE(sync_updated_at, created_at) > cloud_synced_at)
            ORDER BY id ASC
            LIMIT ?
            """,
            (max(1, min(int(max_products or 300), 1000)),),
        ).fetchall()
        for row in product_rows:
            code = normalize_code_token(row["code"], default="", max_len=50)
            if not code or _outbox_has_pending_product(con, code):
                continue
            enqueue_product_cloud_sync(con, int(row["id"]), reason="auto_local_state")
            queued_products += 1

        sale_rows = con.execute(
            """
            SELECT id, sale_code FROM sales
            WHERE sale_code IS NOT NULL AND TRIM(sale_code) <> ''
              AND (cloud_synced_at IS NULL OR cloud_synced_at='')
            ORDER BY id ASC
            LIMIT ?
            """,
            (max(1, min(int(max_sales or 100), 500)),),
        ).fetchall()
        for row in sale_rows:
            sale_code = str(row["sale_code"] or "")
            if not sale_code or _outbox_has_pending_sale(con, sale_code):
                continue
            enqueue_sale_cloud_sync(con, int(row["id"]))
            queued_sales += 1

    return {"products": queued_products, "sales": queued_sales}


def mark_local_product_cloud_synced(code: str) -> None:
    if not code:
        return
    with get_db() as con:
        con.execute(
            "UPDATE products SET cloud_synced_at=?, sync_updated_at=COALESCE(sync_updated_at, ?) WHERE code=?",
            (now_iso(), now_iso(), code),
        )


def mark_local_sale_cloud_synced(sale_code: str) -> None:
    if not sale_code:
        return
    with get_db() as con:
        con.execute("UPDATE sales SET cloud_synced_at=? WHERE sale_code=?", (now_iso(), sale_code))


def push_outbox_to_cloud(max_items: int = 80, request: Request | None = None) -> dict[str, Any]:
    url = cloud_sync_url()
    if not url:
        return {"ok": False, "message": "CLOUD_SYNC_URL não configurado neste ambiente."}
    if request is not None and str(request.base_url).rstrip("/") == url:
        return {"ok": True, "message": "Ambiente já é a nuvem; nada para publicar."}

    with get_db() as con:
        rows = con.execute(
            "SELECT * FROM sync_outbox WHERE target='cloud' AND status IN ('pendente','erro') ORDER BY id ASC LIMIT ?",
            (max(1, min(int(max_items or 80), 300)),),
        ).fetchall()

    if not rows:
        return {"ok": True, "message": "Nenhuma pendência para publicar.", "sent": 0, "failed": 0}

    operations = []
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        operations.append({
            "id": f"local-outbox-{row['id']}",
            "type": row["op_type"],
            "payload": payload,
        })

    try:
        response = _http_json(
            f"{url}/api/android/sync/push",
            {
                "device_id": f"local-{socket.gethostname()}",
                "device_name": "BRECHORISEE local/computador",
                "operations": operations,
            },
            timeout=30,
        )
    except Exception as exc:
        with get_db() as con:
            for row in rows:
                con.execute(
                    "UPDATE sync_outbox SET status='erro', attempts=attempts+1, last_error=? WHERE id=?",
                    (str(exc)[:500], row["id"]),
                )
        return {"ok": False, "message": f"Nuvem indisponível: {exc}", "sent": 0, "failed": len(rows)}

    results = response.get("results") or []
    by_id = {str(r.get("client_op_id") or ""): r for r in results if isinstance(r, dict)}
    sent = failed = conflicts = 0
    with get_db() as con:
        for row in rows:
            key = f"local-outbox-{row['id']}"
            res = by_id.get(key, {})
            status = str(res.get("status") or "")
            if status == "sincronizado":
                sent += 1
                con.execute(
                    "UPDATE sync_outbox SET status='sincronizado', sent_at=?, attempts=attempts+1, last_error=NULL WHERE id=?",
                    (now_iso(), row["id"]),
                )
                try:
                    payload = json.loads(row["payload"] or "{}")
                    if row["op_type"] == "upsert_product":
                        con.execute(
                            "UPDATE products SET cloud_synced_at=?, sync_updated_at=COALESCE(sync_updated_at, ?) WHERE code=?",
                            (now_iso(), now_iso(), normalize_code_token(payload.get("code") or "", default="", max_len=50)),
                        )
                    elif row["op_type"] == "upsert_sale":
                        con.execute(
                            "UPDATE sales SET cloud_synced_at=? WHERE sale_code=?",
                            (now_iso(), str(payload.get("sale_code") or "")),
                        )
                except Exception:
                    pass
            elif status == "conflito":
                conflicts += 1
                con.execute(
                    "UPDATE sync_outbox SET status='conflito', sent_at=?, attempts=attempts+1, last_error=? WHERE id=?",
                    (now_iso(), json.dumps(res, ensure_ascii=False)[:500], row["id"]),
                )
            else:
                failed += 1
                con.execute(
                    "UPDATE sync_outbox SET status='erro', attempts=attempts+1, last_error=? WHERE id=?",
                    (json.dumps(res or response, ensure_ascii=False)[:500], row["id"]),
                )
    return {"ok": failed == 0, "message": response.get("message") or "Publicação enviada.", "sent": sent, "failed": failed, "conflicts": conflicts, "cloud_url": url}


def import_cloud_bootstrap(limit: int = 2000) -> dict[str, Any]:
    url = cloud_sync_url()
    if not url:
        return {"ok": False, "message": "CLOUD_SYNC_URL não configurado."}
    try:
        req_url = f"{url}/api/android/sync/bootstrap?device_id=local-import&limit={int(limit or 2000)}"
        req = urllib.request.Request(req_url, headers=_sync_headers())
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"ok": False, "message": f"Não consegui ler a nuvem: {exc}"}

    products = data.get("products") or []
    imported = updated = 0
    conflicts = 0
    skipped = 0
    with get_db() as con:
        for product in products:
            if not isinstance(product, dict):
                skipped += 1
                continue
            code = _offline_safe_text(product.get("code"), 80)
            if not code:
                skipped += 1
                continue
            existing = con.execute("SELECT * FROM products WHERE code=?", (code,)).fetchone()
            if existing:
                # Se a nuvem marcou vendido/reservado, o local acompanha para não revender.
                con.execute(
                    """
                    UPDATE products SET status=?, sold_at=COALESCE(?, sold_at), cloud_synced_at=?, sync_origin=COALESCE(sync_origin, 'cloud')
                    WHERE code=?
                    """,
                    (_offline_safe_text(product.get("status") or existing["status"], 40), product.get("sold_at"), now_iso(), code),
                )
                updated += 1
            else:
                result = _process_offline_product(con, product)
                if result.get("ok"):
                    imported += 1
                else:
                    conflicts += 1
    return {
        "ok": True,
        "imported": imported,
        "updated": updated,
        "conflicts": conflicts,
        "skipped": skipped,
        "cloud_products": len(products),
        "cloud_url": url,
        "message": f"Nuvem lida: {len(products)} peça(s); importadas: {imported}; atualizadas: {updated}; conflitos: {conflicts}."
    }


def run_full_cloud_sync(request: Request | None = None) -> dict[str, Any]:
    """Sincronização real automática local ⇄ nuvem.

    Ordem segura:
    1. Puxa a nuvem para o local, para respeitar vendas/status feitos online.
    2. Coloca na fila peças/vendas locais ainda não publicadas.
    3. Envia a fila para a nuvem.
    4. Puxa novamente para confirmar status final.
    """
    pull_before = import_cloud_bootstrap()
    queued = enqueue_unsynced_local_state()
    push = push_outbox_to_cloud(request=request)
    pull_after = import_cloud_bootstrap()
    ok = bool(push.get("ok")) and bool(pull_before.get("ok")) and bool(pull_after.get("ok"))
    return {"ok": ok, "queued": queued, "push": push, "pull_before": pull_before, "pull_after": pull_after, "mode": "automatico"}



def run_auto_cloud_sync(force: bool = False) -> dict[str, Any]:
    """Executa sincronização automática com trava para não rodar duas vezes ao mesmo tempo."""
    global _LAST_AUTO_SYNC_AT, _LAST_AUTO_SYNC_RESULT
    if not cloud_sync_url():
        return {"ok": False, "message": "Nuvem não configurada neste ambiente."}
    now_ts = time.time()
    if not force and now_ts - _LAST_AUTO_SYNC_AT < max(20, AUTO_SYNC_INTERVAL_SECONDS):
        return _LAST_AUTO_SYNC_RESULT
    if not _AUTO_SYNC_LOCK.acquire(blocking=False):
        return {"ok": True, "message": "Sincronização automática já em andamento."}
    try:
        _LAST_AUTO_SYNC_AT = time.time()
        result = run_full_cloud_sync()
        result["automatic"] = True
        result["at"] = now_iso()
        _LAST_AUTO_SYNC_RESULT = result
        return result
    except Exception as exc:
        _LAST_AUTO_SYNC_RESULT = {"ok": False, "message": str(exc), "automatic": True, "at": now_iso()}
        return _LAST_AUTO_SYNC_RESULT
    finally:
        try:
            _AUTO_SYNC_LOCK.release()
        except Exception:
            pass


def start_auto_sync_worker() -> None:
    if not cloud_sync_url():
        return

    def _worker() -> None:
        # Pequena espera para o servidor terminar de subir.
        time.sleep(8)
        while True:
            try:
                run_auto_cloud_sync(force=True)
            except Exception:
                pass
            time.sleep(max(30, AUTO_SYNC_INTERVAL_SECONDS))

    t = threading.Thread(target=_worker, name="brechorisee-auto-sync", daemon=True)
    t.start()


def local_product_total() -> int:
    try:
        with get_db() as con:
            return int(con.execute("SELECT COUNT(*) FROM products").fetchone()[0])
    except Exception:
        return 0


def local_available_product_total() -> int:
    try:
        with get_db() as con:
            return int(con.execute("SELECT COUNT(*) FROM products WHERE status='disponivel'").fetchone()[0])
    except Exception:
        return 0


def auto_sync_if_local_empty(reason: str = "empty_local") -> dict[str, Any]:
    """Garante que um computador local vazio puxe a nuvem antes de mostrar a vitrine.

    Isso corrige o caso comum: a nuvem tem peças, mas o servidor local recém-atualizado
    ainda não recebeu nenhuma peça.
    """
    if not cloud_sync_url():
        return {"ok": False, "message": "Nuvem não configurada."}
    if local_product_total() == 0:
        result = run_auto_cloud_sync(force=True)
        result["trigger"] = reason
        return result
    return {"ok": True, "message": "Local já possui produtos.", "trigger": reason}


def get_public_server_url(request: Request | None = None) -> str:
    """URL pública usada em links do Telegram, WhatsApp, app e páginas externas.

    Correção v4.8.6:
    - quando a requisição chega por um túnel público (localhost.run/lhr.life,
      Cloudflare, domínio próprio etc.), usa automaticamente o domínio atual;
    - evita reaproveitar link antigo do .env, como Render/onrender, quando a
      cliente está navegando por outro host;
    - sem requisição, usa PUBLIC_BASE_URL/BRECHORISEE_PUBLIC_BASE_URL se houver.
    """
    request_base = _request_public_base_url(request)
    request_host = _url_host(request_base)
    if request_base and not _is_local_or_private_host(request_host):
        return request_base.rstrip("/")

    configured = (
        os.getenv("PUBLIC_BASE_URL", "")
        or os.getenv("BRECHORISEE_PUBLIC_BASE_URL", "")
        or os.getenv("BRECHORISEE_PUBLIC_URL", "")
        or os.getenv("RENDER_EXTERNAL_URL", "")
    ).strip().rstrip("/")
    if configured:
        return configured

    if request_base:
        return request_base.rstrip("/")

    return f"http://{get_lan_ip()}:8000"

def _offline_safe_text(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _ensure_sync_device(con: sqlite3.Connection, device_id: str, device_name: str = "") -> None:
    device_id = _offline_safe_text(device_id or "android", 120) or "android"
    device_name = _offline_safe_text(device_name, 120)
    con.execute(
        """
        INSERT INTO sync_devices(device_id, device_name, last_seen_at, last_sync_at, status)
        VALUES(?,?,?,?, 'ativo')
        ON CONFLICT(device_id) DO UPDATE SET
          device_name=excluded.device_name,
          last_seen_at=excluded.last_seen_at,
          last_sync_at=excluded.last_sync_at,
          status='ativo'
        """,
        (device_id, device_name, now_iso(), now_iso()),
    )


def _record_sync_event(
    con: sqlite3.Connection,
    device_id: str,
    client_op_id: str,
    op_type: str,
    status: str,
    payload: dict[str, Any],
    result: dict[str, Any] | None = None,
    conflict_notes: str = "",
) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO offline_sync_events
        (device_id, client_op_id, op_type, status, payload, result, conflict_notes, created_at, processed_at)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            _offline_safe_text(device_id, 120),
            _offline_safe_text(client_op_id, 160),
            _offline_safe_text(op_type, 80),
            _offline_safe_text(status, 40),
            json.dumps(payload or {}, ensure_ascii=False),
            json.dumps(result or {}, ensure_ascii=False),
            _offline_safe_text(conflict_notes, 1000),
            now_iso(),
            now_iso(),
        ),
    )


def _process_offline_product(con: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    """Cria ou atualiza uma peça vindo do Android/local/nuvem.

    Regra de sincronização:
    - O código da peça é a chave principal entre os sistemas.
    - Se já existe o mesmo código, atualiza atributos e status.
    - Se não existe, cria.
    - Se vier imagem em base64, salva foto principal também.
    """
    title = _offline_safe_text(payload.get("title") or payload.get("nome") or "Peça sincronizada", 160)
    category = _offline_safe_text(payload.get("category") or payload.get("categoria"), 120)
    garment_type = _offline_safe_text(payload.get("garment_type") or payload.get("tipo") or title, 120)
    size = _offline_safe_text(payload.get("size") or payload.get("tamanho"), 80)
    brand = _offline_safe_text(payload.get("brand") or payload.get("marca"), 120)
    color = _offline_safe_text(payload.get("color") or payload.get("cor"), 120)
    condition = _offline_safe_text(payload.get("condition") or payload.get("estado") or "Seminovo", 120)
    characteristics = _offline_safe_text(payload.get("characteristics") or payload.get("caracteristicas"), 500)
    measurements = _offline_safe_text(payload.get("measurements") or payload.get("medidas"), 300)
    style_tags = _offline_safe_text(payload.get("style_tags") or payload.get("estilo"), 300)
    season = _offline_safe_text(payload.get("season") or payload.get("estacao"), 120)
    target_audience = _offline_safe_text(payload.get("target_audience") or payload.get("publico"), 120)
    status = _offline_safe_text(payload.get("status") or "disponivel", 40)
    if status not in {"disponivel", "reservado", "vendido", "arquivado"}:
        status = "disponivel"
    try:
        sale_price = validate_money_amount(payload.get("sale_price") or payload.get("preco") or 0, "Preço de venda sincronizado", minimum=0, allow_zero=False)
        cost_price = validate_money_amount(payload.get("cost_price") or payload.get("custo") or 0, "Preço de custo sincronizado", minimum=0, allow_zero=True)
    except HTTPException as exc:
        return {"ok": False, "conflict": True, "message": str(exc.detail)}
    supplier_id = int(payload.get("supplier_id") or 1)

    raw_code = _offline_safe_text(payload.get("code") or payload.get("codigo"), 80)
    if raw_code:
        # Em sincronização, preserva o código para a peça ser a mesma nos três sistemas.
        code = normalize_code_token(raw_code, default="PECA", max_len=50)
    else:
        code = generate_product_code(
            title=title, category=category, garment_type=garment_type,
            color=color, brand=brand, characteristics=characteristics, style_tags=style_tags, con=con
        )

    existing = con.execute("SELECT * FROM products WHERE code=?", (code,)).fetchone()

    image_filename = existing["image_filename"] if existing else None
    image_hash = existing["image_hash"] if existing else None
    avg_r = existing["avg_r"] if existing else None
    avg_g = existing["avg_g"] if existing else None
    avg_b = existing["avg_b"] if existing else None

    image_b64 = _offline_safe_text(payload.get("image_base64"), limit=20_000_000)
    if image_b64 and not image_filename:
        saved_name, saved_hash, saved_r, saved_g, saved_b = _save_base64_image(
            image_b64,
            prefix=code or title,
            original_filename=_offline_safe_text(payload.get("image_original_filename") or payload.get("image_filename"), 200),
        )
        if saved_name:
            image_filename, image_hash, avg_r, avg_g, avg_b = saved_name, saved_hash, saved_r, saved_g, saved_b

    generate_qr(code)

    if existing:
        con.execute(
            """
            UPDATE products
            SET title=?, category=?, garment_type=?, size=?, brand=?, color=?, condition=?,
                measurements=?, characteristics=?, style_tags=?, season=?, target_audience=?,
                cost_price=?, sale_price=?, supplier_id=?, status=?,
                image_filename=COALESCE(?, image_filename),
                image_hash=COALESCE(?, image_hash),
                avg_r=COALESCE(?, avg_r),
                avg_g=COALESCE(?, avg_g),
                avg_b=COALESCE(?, avg_b),
                sold_at=CASE WHEN ?='vendido' THEN COALESCE(?, sold_at) ELSE sold_at END,
                cloud_synced_at=?, sync_updated_at=?
            WHERE id=?
            """,
            (
                title, category, garment_type, size, brand, color, condition,
                measurements, characteristics, style_tags, season, target_audience,
                cost_price, sale_price, supplier_id, status,
                image_filename, image_hash, avg_r, avg_g, avg_b,
                status, payload.get("sold_at") or now_iso(),
                now_iso(), now_iso(), existing["id"],
            ),
        )
        product_id = existing["id"]
        action = "updated"
    else:
        cur = con.execute(
            """
            INSERT INTO products
            (code, title, category, garment_type, size, brand, color, condition, measurements,
             characteristics, style_tags, season, target_audience, cost_price, sale_price, supplier_id,
             status, image_filename, image_hash, avg_r, avg_g, avg_b, created_at, sold_at, sync_origin, cloud_synced_at, sync_updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code, title, category, garment_type, size, brand, color, condition,
                measurements, characteristics, style_tags, season, target_audience,
                cost_price, sale_price, supplier_id, status,
                image_filename, image_hash, avg_r, avg_g, avg_b,
                payload.get("created_at") or now_iso(),
                payload.get("sold_at") if status == "vendido" else None,
                _offline_safe_text(payload.get("sync_origin") or "sync", 40),
                now_iso(),
                now_iso(),
            ),
        )
        product_id = cur.lastrowid
        action = "created"

    if image_filename:
        media_exists = con.execute("SELECT 1 FROM product_media WHERE product_id=? AND filename=?", (product_id, image_filename)).fetchone()
        if not media_exists:
            insert_product_media(
                con,
                product_id=product_id,
                filename=image_filename,
                media_type="image",
                original_filename=_offline_safe_text(payload.get("image_original_filename") or image_filename, 200),
                notes="Foto principal sincronizada",
                image_hash=image_hash,
                avg_r=avg_r,
                avg_g=avg_g,
                avg_b=avg_b,
            )

    con.execute(
        "INSERT INTO inventory_events(product_id, event_type, source, notes, created_at) VALUES(?,?,?,?,?)",
        (product_id, "sync", "sincronizacao", f"Peça {action} por sincronização.", now_iso()),
    )
    return {"ok": True, "product_id": product_id, "code": code, "action": action}

def _process_offline_customer(con: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    name = _offline_safe_text(payload.get("name") or payload.get("nome") or payload.get("customer") or "Cliente offline", 160)
    phone = _offline_safe_text(payload.get("phone") or payload.get("whatsapp") or payload.get("telefone"), 80)
    existing = None
    if phone:
        existing = con.execute("SELECT * FROM customers WHERE phone=?", (phone,)).fetchone()
    if existing:
        con.execute(
            "UPDATE customers SET name=?, instagram=?, email=?, measurements=?, preferences=?, notes=? WHERE id=?",
            (
                name,
                _offline_safe_text(payload.get("instagram"), 120),
                _offline_safe_text(payload.get("email"), 160),
                _offline_safe_text(payload.get("measurements") or payload.get("medidas"), 300),
                _offline_safe_text(payload.get("preferences") or payload.get("preferencias"), 500),
                _offline_safe_text(payload.get("notes") or payload.get("observacoes"), 500),
                existing["id"],
            ),
        )
        return {"ok": True, "customer_id": existing["id"], "updated": True}
    cur = con.execute(
        """
        INSERT INTO customers(name, phone, instagram, email, birthday, measurements, preferences, notes, created_at)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            name, phone,
            _offline_safe_text(payload.get("instagram"), 120),
            _offline_safe_text(payload.get("email"), 160),
            _offline_safe_text(payload.get("birthday") or payload.get("aniversario"), 40),
            _offline_safe_text(payload.get("measurements") or payload.get("medidas"), 300),
            _offline_safe_text(payload.get("preferences") or payload.get("preferencias"), 500),
            _offline_safe_text(payload.get("notes") or payload.get("observacoes"), 500),
            now_iso(),
        ),
    )
    return {"ok": True, "customer_id": cur.lastrowid, "created": True}


def _process_offline_sale(con: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    raw_codes = payload.get("codes") or payload.get("codigos") or []
    if isinstance(raw_codes, str):
        raw_codes = [part.strip() for part in raw_codes.replace("\n", ",").split(",") if part.strip()]
    codes = [normalize_code_token(c, default="", max_len=50) for c in raw_codes if str(c).strip()]
    codes = [c for c in codes if c]
    if not codes:
        return {"ok": False, "conflict": True, "message": "Venda sem códigos."}

    sale_code = _offline_safe_text(payload.get("sale_code") or payload.get("codigo_venda"), 120)
    if sale_code:
        existing_sale = con.execute("SELECT * FROM sales WHERE sale_code=?", (sale_code,)).fetchone()
        if existing_sale:
            return {"ok": True, "sale_id": existing_sale["id"], "sale_code": sale_code, "already_exists": True, "sold_codes": codes}

    placeholders = ",".join("?" for _ in codes)
    products = con.execute(f"SELECT * FROM products WHERE code IN ({placeholders})", codes).fetchall()
    found = {p["code"]: p for p in products}
    missing = [c for c in codes if c not in found]
    unavailable = [c for c, p in found.items() if p["status"] not in {"disponivel", "reservado"}]
    if missing or unavailable:
        return {
            "ok": False,
            "conflict": True,
            "message": "Conflito de estoque na sincronização da venda.",
            "missing": missing,
            "unavailable": unavailable,
        }

    try:
        discount = validate_money_amount(payload.get("discount") or payload.get("desconto") or 0, "Desconto sincronizado", minimum=0, allow_zero=True)
        paid = validate_money_amount(payload.get("paid") or payload.get("pago") or payload.get("total") or 0, "Pago sincronizado", minimum=0, allow_zero=True)
        prices = [validate_money_amount(p["sale_price"], f"Preço sincronizado da peça {p['code']}", minimum=0, allow_zero=False) for p in products]
    except HTTPException as exc:
        return {"ok": False, "conflict": True, "message": str(exc.detail)}
    customer = _offline_safe_text(payload.get("customer") or payload.get("cliente"), 160)
    payment_method = _offline_safe_text(payload.get("payment_method") or payload.get("pagamento") or "Sincronizado", 120)
    subtotal = round(sum(prices), 2)
    total = safe_float(payload.get("total"), -1)
    if total < 0:
        total = round(subtotal - discount, 2)
    try:
        total = validate_money_amount(total, "Total sincronizado", minimum=0, allow_zero=True)
    except HTTPException as exc:
        return {"ok": False, "conflict": True, "message": str(exc.detail)}
    if discount > subtotal:
        return {"ok": False, "conflict": True, "message": "Desconto sincronizado maior que subtotal."}
    change_value = max(0, paid - total)
    sale_code = sale_code or generate_sale_code()

    cur = con.execute(
        "INSERT INTO sales(sale_code, customer, payment_method, discount, total, paid, change_value, created_at, sync_origin, cloud_synced_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (sale_code, customer, payment_method, discount, total, paid, change_value, payload.get("created_at") or now_iso(), "sync", now_iso()),
    )
    sale_id = cur.lastrowid
    sold_time = payload.get("sold_at") or now_iso()
    for p, price in zip(products, prices):
        con.execute("INSERT INTO sale_items(sale_id, product_id, price) VALUES(?,?,?)", (sale_id, p["id"], price))
        con.execute("UPDATE products SET status='vendido', sold_at=?, cloud_synced_at=?, sync_updated_at=? WHERE id=?", (sold_time, now_iso(), now_iso(), p["id"]))
        con.execute(
            "INSERT INTO inventory_events(product_id, event_type, source, notes, created_at) VALUES(?,?,?,?,?)",
            (p["id"], "venda_sync", "sincronizacao", f"Venda sincronizada: {sale_code}. Peça removida da vitrine/estoque disponível.", sold_time),
        )

    return {"ok": True, "sale_id": sale_id, "sale_code": sale_code, "total": total, "sold_codes": codes}

def _process_offline_reservation(con: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    code = _offline_safe_text(payload.get("code") or payload.get("codigo"), 80).upper()
    product = con.execute("SELECT * FROM products WHERE code=?", (code,)).fetchone() if code else None
    if not product:
        return {"ok": False, "conflict": True, "message": "Peça da reserva não encontrada.", "code": code}
    if product["status"] != "disponivel":
        return {"ok": False, "conflict": True, "message": "Peça não está disponível para reserva.", "code": code, "status": product["status"]}
    customer_name = _offline_safe_text(payload.get("customer") or payload.get("cliente"), 160)
    expires_at = _offline_safe_text(payload.get("expires_at") or payload.get("prazo"), 40)
    con.execute(
        "INSERT INTO reservations(product_id, customer_name, expires_at, status, notes, created_at) VALUES(?,?,?,?,?,?)",
        (product["id"], customer_name, expires_at, "ativa", _offline_safe_text(payload.get("notes") or payload.get("observacoes"), 500), now_iso()),
    )
    con.execute("UPDATE products SET status='reservado' WHERE id=?", (product["id"],))
    return {"ok": True, "product_id": product["id"], "code": code, "status": "reservado"}


def _process_generic_offline_op(con: sqlite3.Connection, op_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    # Para mensagens, entregas, interesse e anotações, mantém histórico sincronizado
    # sem arriscar alterar estoque automaticamente.
    return {"ok": True, "stored": True, "message": f"Operação {op_type} recebida e registrada para histórico."}


def process_offline_operation(con: sqlite3.Connection, op: dict[str, Any], device_id: str) -> dict[str, Any]:
    op_type = _offline_safe_text(op.get("type") or op.get("op_type") or "note", 80)
    client_op_id = _offline_safe_text(op.get("id") or op.get("client_op_id") or f"{device_id}-{datetime.now().timestamp()}", 160)
    payload = op.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {"value": payload}

    already = con.execute(
        "SELECT result, status FROM offline_sync_events WHERE device_id=? AND client_op_id=?",
        (device_id, client_op_id),
    ).fetchone()
    if already and already["status"] in {"sincronizado", "conflito"}:
        try:
            return {"client_op_id": client_op_id, "op_type": op_type, "status": already["status"], "result": json.loads(already["result"] or "{}")}
        except Exception:
            return {"client_op_id": client_op_id, "op_type": op_type, "status": already["status"], "result": {}}

    try:
        if op_type in {"create_product", "product", "cadastro_peca", "upsert_product", "publicar_peca"}:
            result = _process_offline_product(con, payload)
        elif op_type in {"create_customer", "customer", "cliente"}:
            result = _process_offline_customer(con, payload)
        elif op_type in {"create_sale", "sale", "venda", "offline_sale", "upsert_sale"}:
            result = _process_offline_sale(con, payload)
        elif op_type in {"reserve_product", "reservation", "reserva"}:
            result = _process_offline_reservation(con, payload)
        else:
            result = _process_generic_offline_op(con, op_type, payload)

        status = "conflito" if result.get("conflict") else "sincronizado"
        _record_sync_event(con, device_id, client_op_id, op_type, status, payload, result, result.get("message", ""))
        return {"client_op_id": client_op_id, "op_type": op_type, "status": status, "result": result}
    except Exception as exc:
        result = {"ok": False, "message": str(exc)}
        _record_sync_event(con, device_id, client_op_id, op_type, "erro", payload, result, str(exc))
        return {"client_op_id": client_op_id, "op_type": op_type, "status": "erro", "result": result}



def register_schema_version() -> None:
    """Registra a versão lógica do schema sem depender de ferramenta externa.

    O projeto ainda usa SQLite, mas esta tabela cria um ponto de controle para
    futuras migrações formais. O comando é idempotente e seguro em banco novo ou
    banco já existente.
    """
    try:
        with get_db() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES(?,?,?)",
                (SCHEMA_VERSION, "Base profissional: publicação limpa, backup e operação segura.", now_iso()),
            )
    except Exception:
        logger.warning("Não foi possível registrar a versão do schema.", exc_info=True)


def current_schema_version() -> dict[str, Any]:
    try:
        with get_db() as con:
            row = con.execute(
                "SELECT version, description, applied_at FROM schema_migrations ORDER BY applied_at DESC, version DESC LIMIT 1"
            ).fetchone()
            if row:
                return {"version": row["version"], "description": row["description"], "applied_at": row["applied_at"]}
    except Exception:
        pass
    return {"version": SCHEMA_VERSION, "description": "schema_migrations ainda não inicializada", "applied_at": None}



def _safe_count(con: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
    try:
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(con.execute(sql, params).fetchone()[0])
    except Exception:
        return 0


def _latest_backup_info() -> dict[str, Any] | None:
    try:
        backups = sorted(
            [p for p in BACKUP_DIR.glob("backup-brechorisee-*.zip") if p.is_file()],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not backups:
            return None
        latest = backups[0]
        return {
            "filename": latest.name,
            "size_bytes": latest.stat().st_size,
            "created_at": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(timespec="seconds"),
        }
    except Exception:
        return None


def operational_status_snapshot(include_private: bool = False) -> dict[str, Any]:
    db_ok = False
    db_message = "indisponível"
    quick_check = "not_run"
    counts: dict[str, int] = {}
    try:
        with get_db() as con:
            con.execute("SELECT 1").fetchone()
            quick_check = str(con.execute("PRAGMA quick_check").fetchone()[0])
            db_ok = quick_check.lower() == "ok"
            db_message = "ok" if db_ok else quick_check
            counts = {
                "products": _safe_count(con, "products", "deleted_at IS NULL"),
                "available_products": _safe_count(con, "products", "status='disponivel' AND deleted_at IS NULL"),
                "sales": _safe_count(con, "sales"),
                "customers": _safe_count(con, "customers"),
                "online_orders_open": _safe_count(con, "online_orders", "status NOT IN ('entregue','cancelado')"),
                "sync_pending": _safe_count(con, "sync_outbox", "status='pendente'"),
                "live_active": _safe_count(con, "live_sessions", "status='ativa'"),
            }
    except Exception as exc:
        logger.warning("Healthcheck do banco falhou: %s", exc)
        db_message = str(exc)[:180]

    disk = shutil.disk_usage(str(BASE_DIR))
    payload: dict[str, Any] = {
        "ok": db_ok,
        "app": APP_NAME,
        "version": APP_VERSION,
        "environment": BRECHORISEE_ENV,
        "time": now_iso(),
        "database": {
            "ok": db_ok,
            "message": db_message,
            "quick_check": quick_check,
            "wal_enabled": DB_ENABLE_WAL,
            "schema": current_schema_version(),
        },
        "storage": {
            "free_mb": round(disk.free / (1024 * 1024), 1),
            "total_mb": round(disk.total / (1024 * 1024), 1),
        },
        "backup": _latest_backup_info(),
        "counts": counts,
    }
    if include_private:
        payload["paths"] = {
            "base_dir": str(BASE_DIR),
            "db_path": str(DB_PATH),
            "upload_dir": str(UPLOAD_DIR),
            "backup_dir": str(BACKUP_DIR),
        }
        payload["limits"] = {
            "image_mb": round(MAX_IMAGE_UPLOAD_BYTES / (1024 * 1024), 1),
            "media_mb": round(MAX_MEDIA_UPLOAD_BYTES / (1024 * 1024), 1),
            "auth_session_days": AUTH_SESSION_DAYS,
            "customer_session_days": CUSTOMER_SESSION_DAYS,
        }
    return payload


@app.get("/healthz")
def healthz() -> JSONResponse:
    status = operational_status_snapshot(include_private=False)
    public_payload = {
        "ok": bool(status["ok"]),
        "app": status["app"],
        "version": status["version"],
        "time": status["time"],
        "database": {"ok": bool(status["database"]["ok"])},
    }
    return JSONResponse(public_payload, status_code=200 if public_payload["ok"] else 503)


@app.get("/readyz")
def readyz() -> JSONResponse:
    """Pronto para receber tráfego: banco íntegro e storage com folga mínima."""
    status = operational_status_snapshot(include_private=False)
    storage_ok = float(status.get("storage", {}).get("free_mb") or 0) >= 50
    ready = bool(status["ok"]) and storage_ok
    payload = {
        "ok": ready,
        "app": status["app"],
        "version": status["version"],
        "time": status["time"],
        "database": {"ok": bool(status["database"]["ok"]), "schema": status["database"].get("schema")},
        "storage": {"ok": storage_ok, "free_mb": status.get("storage", {}).get("free_mb")},
    }
    return JSONResponse(payload, status_code=200 if ready else 503)


@app.get("/api/admin/operational-status")
def api_admin_operational_status() -> JSONResponse:
    status = operational_status_snapshot(include_private=True)
    return JSONResponse(status, status_code=200 if status["ok"] else 503)


@app.get("/sincronizacao", response_class=HTMLResponse)
def sync_page(request: Request) -> Response:
    # Ao abrir a tela, força uma sincronização completa para que o status mostrado
    # seja real. Continua automático; não depende de botão manual.
    page_sync_result = run_auto_cloud_sync(force=True) if cloud_sync_url() else {"ok": False, "message": "Nuvem não configurada."}
    with get_db() as con:
        devices = con.execute("SELECT * FROM sync_devices ORDER BY last_seen_at DESC").fetchall()
        events = con.execute("SELECT * FROM offline_sync_events ORDER BY id DESC LIMIT 200").fetchall()
        rows = con.execute("SELECT status, COUNT(*) AS total FROM offline_sync_events GROUP BY status").fetchall()
        outbox_rows = con.execute("SELECT status, COUNT(*) AS total FROM sync_outbox GROUP BY status").fetchall()
        outbox_events = con.execute("SELECT * FROM sync_outbox ORDER BY id DESC LIMIT 120").fetchall()
    counts = {row["status"]: row["total"] for row in rows}
    outbox_counts = {row["status"]: row["total"] for row in outbox_rows}
    return templates.TemplateResponse(
        "sync.html",
        {
            "request": request,
            "devices": devices,
            "events": events,
            "counts": counts,
            "outbox_counts": outbox_counts,
            "outbox_events": outbox_events,
            "cloud_url": cloud_sync_url(),
            "last_auto_sync": page_sync_result or _LAST_AUTO_SYNC_RESULT,
            "auto_interval": AUTO_SYNC_INTERVAL_SECONDS,
            "local_product_total": local_product_total(),
            "local_available_product_total": local_available_product_total(),
            "active": "sync",
        },
    )


@app.post("/sincronizacao/cloud/run")
def sync_cloud_run(request: Request) -> Response:
    result = run_full_cloud_sync(request=request)
    # Guarda um evento de auditoria simples para aparecer no histórico.
    try:
        audit("sync_cloud_run", "sync", "cloud", json.dumps(result, ensure_ascii=False)[:900])
    except Exception:
        pass
    return RedirectResponse(url="/sincronizacao", status_code=303)


@app.post("/api/sync/cloud/run")
def api_sync_cloud_run(request: Request) -> JSONResponse:
    return JSONResponse(run_full_cloud_sync(request=request))


@app.get("/api/sync/cloud/status")
def api_sync_cloud_status() -> JSONResponse:
    with get_db() as con:
        rows = con.execute("SELECT status, COUNT(*) AS total FROM sync_outbox GROUP BY status").fetchall()
    return JSONResponse({"ok": True, "cloud_url": cloud_sync_url(), "outbox": {row["status"]: row["total"] for row in rows}})



@app.get("/service-worker.js")
def service_worker() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "js" / "service-worker.js", media_type="application/javascript")


@app.get("/api/server-info")
def api_server_info() -> JSONResponse:
    ip = get_lan_ip()
    return JSONResponse({
        "ok": True,
        "local_url": "http://127.0.0.1:8000",
        "phone_url": f"http://{ip}:8000",
        "ip": ip,
        "camera_note": "Fotos pelo celular usam o seletor/câmera do aparelho. O app Android acessa este servidor local e usa o mesmo banco SQLite do computador.",
        "android_url": f"http://{ip}:8000/android",
        "database": "local_sqlite_no_computador",
    })




@app.get("/api/android/sync/bootstrap")
def api_android_sync_bootstrap(request: Request, device_id: str = "android", limit: int = 500) -> JSONResponse:
    with get_db() as con:
        _ensure_sync_device(con, device_id)
        products = con.execute(
            """
            SELECT id, code, title, category, garment_type, size, brand, color, condition,
                   sale_price, cost_price, status, image_filename, created_at, sold_at,
                   style_tags, season, target_audience, characteristics
            FROM products
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(10, min(int(limit or 500), 2000)),),
        ).fetchall()
        customers = con.execute(
            "SELECT id, name, phone, instagram, email, measurements, preferences, notes, created_at FROM customers ORDER BY id DESC LIMIT 1000"
        ).fetchall()
        pending = con.execute(
            "SELECT id, client_op_id, op_type, status, conflict_notes, created_at, processed_at FROM offline_sync_events WHERE device_id=? ORDER BY id DESC LIMIT 200",
            (device_id,),
        ).fetchall()
    return JSONResponse({
        "ok": True,
        "mode": "online",
        "server_time": now_iso(),
        "base_url": get_public_server_url(request),
        "products": [dict(row) for row in products],
        "customers": [dict(row) for row in customers],
        "sync_events": [dict(row) for row in pending],
        "message": "Dados principais enviados para cache offline do Android."
    })


@app.post("/api/android/sync/push")
async def api_android_sync_push(request: Request) -> JSONResponse:
    data = await request.json()
    device_id = _offline_safe_text(data.get("device_id") or "android", 120)
    device_name = _offline_safe_text(data.get("device_name") or "BRECHORISEE Android", 120)
    operations = data.get("operations") or []
    if not isinstance(operations, list):
        return JSONResponse({"ok": False, "message": "operations precisa ser uma lista."}, status_code=400)

    results: list[dict[str, Any]] = []
    with get_db() as con:
        _ensure_sync_device(con, device_id, device_name)
        for op in operations[:300]:
            if isinstance(op, dict):
                results.append(process_offline_operation(con, op, device_id))
        con.execute("UPDATE sync_devices SET last_sync_at=?, last_seen_at=? WHERE device_id=?", (now_iso(), now_iso(), device_id))

    summary = {
        "sincronizado": sum(1 for r in results if r.get("status") == "sincronizado"),
        "conflito": sum(1 for r in results if r.get("status") == "conflito"),
        "erro": sum(1 for r in results if r.get("status") == "erro"),
    }
    return JSONResponse({"ok": True, "server_time": now_iso(), "summary": summary, "results": results})


@app.get("/api/android/sync/status")
def api_android_sync_status(device_id: str = "android") -> JSONResponse:
    with get_db() as con:
        device = con.execute("SELECT * FROM sync_devices WHERE device_id=?", (device_id,)).fetchone()
        rows = con.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM offline_sync_events
            WHERE device_id=?
            GROUP BY status
            """,
            (device_id,),
        ).fetchall()
    return JSONResponse({
        "ok": True,
        "device": dict(device) if device else None,
        "counts": {row["status"]: row["total"] for row in rows},
    })


@app.get("/api/form-suggestions")
def api_form_suggestions() -> JSONResponse:
    """Sugestões para preencher rápido no celular, usando listas padrão + histórico local."""
    return JSONResponse({"ok": True, "suggestions": get_form_suggestions()})


@app.get("/celular", response_class=HTMLResponse)
def mobile_setup(request: Request) -> Response:
    ip = get_lan_ip()
    return templates.TemplateResponse(
        "mobile_setup.html",
        {
            "request": request,
            "active": "mobile",
            "ip": ip,
            "phone_url": f"http://{ip}:8000",
            "local_url": "http://127.0.0.1:8000",
        },
    )


@app.get("/android", response_class=HTMLResponse)
def android_setup(request: Request) -> Response:
    ip = get_lan_ip()
    return templates.TemplateResponse(
        "android.html",
        {
            "request": request,
            "active": "android",
            "ip": ip,
            "phone_url": f"http://{ip}:8000",
            "local_url": "http://127.0.0.1:8000",
            "db_path": str(DB_PATH),
        },
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> Response:
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": get_stats(), "active": "dashboard"})


@app.get("/products", response_class=HTMLResponse)
def products(request: Request, q: str = "", status: str = "disponivel") -> Response:
    auto_sync_if_local_empty("products_page")
    rows = search_products_rows(q=q, status=status, limit=None)
    return templates.TemplateResponse(
        "products.html",
        {"request": request, "products": rows, "q": q, "status": status, "active": "products"},
    )


@app.get("/products/new", response_class=HTMLResponse)
def new_product_form(request: Request) -> Response:
    with get_db() as con:
        suppliers = con.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    return templates.TemplateResponse(
        "product_form.html",
        {
            "request": request,
            "suppliers": suppliers,
            "active": "products",
            "product": None,
            "generated_code": "",
            "attribute_options": get_product_attribute_options(),
        },
    )


@app.post("/products/new")
def create_product(
    request: Request,
    title: str = Form(...),
    code: str = Form(""),
    auto_code: str = Form("1"),
    category: str = Form(""),
    garment_type: str = Form(""),
    size: str = Form(""),
    brand: str = Form(""),
    color: str = Form(""),
    condition: str = Form(""),
    measurements: str = Form(""),
    characteristics: str = Form(""),
    style_tags: str = Form(""),
    season: str = Form(""),
    target_audience: str = Form(""),
    cost_price: float = Form(0),
    sale_price: float = Form(...),
    supplier_id: int = Form(1),
    image: UploadFile = File(None),
    media_files: list[UploadFile] | None = File(None),
    media_notes: str = Form(""),
) -> Response:
    title = (title or "").strip()
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Informe um título válido para a peça.")
    sanitized_fields = sanitize_product_attribute_inputs({
        "category": category,
        "garment_type": garment_type,
        "size": size,
        "brand": brand,
        "color": color,
        "condition": condition,
        "measurements": measurements,
        "characteristics": characteristics,
        "style_tags": style_tags,
        "season": season,
        "target_audience": target_audience,
    })
    category = sanitized_fields.get("category", category)
    garment_type = sanitized_fields.get("garment_type", garment_type)
    size = sanitized_fields.get("size", size)
    brand = sanitized_fields.get("brand", brand)
    color = sanitized_fields.get("color", color)
    condition = sanitized_fields.get("condition", condition)
    measurements = sanitized_fields.get("measurements", measurements)
    characteristics = sanitized_fields.get("characteristics", characteristics)
    style_tags = sanitized_fields.get("style_tags", style_tags)
    season = sanitized_fields.get("season", season)
    target_audience = sanitized_fields.get("target_audience", target_audience)
    cost_price = validate_money_amount(cost_price, "Preço de custo", minimum=0, allow_zero=True)
    sale_price = validate_money_amount(sale_price, "Preço de venda", minimum=0, allow_zero=False)
    if cost_price and sale_price < cost_price:
        logger.info("Peça cadastrada com venda abaixo do custo: %s custo=%s venda=%s", title, cost_price, sale_price)
    code_is_auto = str(auto_code or "1") != "0"
    raw_code = (code or "").strip().upper()
    prefix = slugify(title)
    filename = save_upload(image, prefix) if image else None
    image_hash = None
    avg_r = avg_g = avg_b = None
    if filename:
        image_hash, avg = image_signature(UPLOAD_DIR / filename)
        avg_r, avg_g, avg_b = avg

    try:
        with get_db() as con:
            if code_is_auto or not raw_code:
                code = generate_product_code(
                    title=title,
                    category=category,
                    garment_type=garment_type,
                    color=color,
                    brand=brand,
                    characteristics=characteristics,
                    style_tags=style_tags,
                    con=con,
                )
            else:
                code = product_code_from_manual(raw_code, con)
            generate_qr(code)

            cur = con.execute(
                """
                INSERT INTO products
                (code, title, category, garment_type, size, brand, color, condition, measurements,
                 characteristics, style_tags, season, target_audience, cost_price, sale_price, supplier_id,
                 status, image_filename, image_hash, avg_r, avg_g, avg_b, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'disponivel', ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    title,
                    category,
                    garment_type,
                    size,
                    brand,
                    color,
                    condition,
                    measurements,
                    characteristics,
                    style_tags,
                    season,
                    target_audience,
                    cost_price,
                    sale_price,
                    supplier_id,
                    filename,
                    image_hash,
                    avg_r,
                    avg_g,
                    avg_b,
                    now_iso(),
                ),
            )
            product_id = cur.lastrowid
            if filename:
                insert_product_media(
                    con,
                    product_id=product_id,
                    filename=filename,
                    media_type="image",
                    original_filename=image.filename if image else "",
                    notes="Foto principal",
                    image_hash=image_hash,
                    avg_r=avg_r,
                    avg_g=avg_g,
                    avg_b=avg_b,
                )

            extra_count = save_extra_media_files(
                con,
                product_id=product_id,
                files=media_files,
                prefix=prefix,
                notes=media_notes,
                can_set_main_image=(filename is None),
            )
            notes_text = "Peça cadastrada no estoque."
            if filename or extra_count:
                notes_text += f" Arquivos salvos: {int(bool(filename)) + extra_count}."
            con.execute(
                "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                (product_id, "entrada", notes_text, now_iso()),
            )
            remember_product_attribute_options_from_form(con, {
                "category": category,
                "garment_type": garment_type,
                "size": size,
                "brand": brand,
                "color": color,
                "condition": condition,
                "measurements": measurements,
                "characteristics": characteristics,
                "style_tags": style_tags,
                "season": season,
                "target_audience": target_audience,
            })

            enqueue_product_cloud_sync(con, product_id, reason="created")
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Código já existe. Use outro código.")

    try:
        if is_cloud_sync_enabled(request):
            threading.Thread(target=run_auto_cloud_sync, kwargs={"force": True}, daemon=True).start()
    except Exception:
        pass

    return RedirectResponse(url="/products", status_code=303)


@app.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: int) -> Response:
    with get_db() as con:
        product = con.execute(
            """
            SELECT p.*, s.name AS supplier_name, s.phone AS supplier_phone, s.instagram AS supplier_instagram
            FROM products p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.id = ?
            """,
            (product_id,),
        ).fetchone()
        media = con.execute(
            "SELECT * FROM product_media WHERE product_id=? ORDER BY id DESC",
            (product_id,),
        ).fetchall()
    if not product:
        raise HTTPException(status_code=404, detail="Peça não encontrada.")
    ai = local_fashion_ai(product)
    share_text = product_share_text(product, request)
    instagram_share_text = product_social_text(product, request, channel="instagram")
    share_local_url = f"{app_base_url(request)}/abrir-peca?id={product['id']}"
    share_public_url = product_public_link(product, request, source="produto")
    share_app_url = product_deep_link(product["id"], product["code"])
    share_photo_url = f"{app_base_url(request)}/static/uploads/{product['image_filename']}" if product["image_filename"] else ""
    settings = get_store_settings()
    similar_products = similar_products_for_share(product, limit=6)
    return templates.TemplateResponse(
        "product_detail.html",
        {
            "request": request,
            "product": product,
            "media": media,
            "ai": ai,
            "active": "products",
            "share_text": share_text,
            "instagram_share_text": instagram_share_text,
            "share_local_url": share_local_url,
            "share_public_url": share_public_url,
            "share_app_url": share_app_url,
            "share_photo_url": share_photo_url,
            "instagram_profile_url": instagram_profile_url(settings),
            "similar_products": similar_products,
        },
    )


@app.post("/products/{product_id}/status")
def update_product_status(request: Request, product_id: int, status: str = Form(...)) -> Response:
    if status not in {"disponivel", "reservado", "vendido", "arquivado"}:
        raise HTTPException(status_code=400, detail="Status inválido.")
    with get_db() as con:
        con.execute(
            "UPDATE products SET status=?, sold_at=CASE WHEN ?=\'vendido\' THEN ? ELSE sold_at END, archived_at=CASE WHEN ?=\'arquivado\' THEN ? ELSE archived_at END WHERE id=?",
            (status, status, now_iso(), status, now_iso(), product_id),
        )
        con.execute(
            "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
            (product_id, "status", f"Status alterado para {status}.", now_iso()),
        )
        enqueue_product_cloud_sync(con, product_id, reason=f"status_{status}")
    try:
        if is_cloud_sync_enabled(request):
            threading.Thread(target=run_auto_cloud_sync, kwargs={"force": True}, daemon=True).start()
    except Exception:
        pass
    return RedirectResponse(url=f"/products/{product_id}", status_code=303)




@app.post("/products/{product_id}/archive")
def archive_product(request: Request, product_id: int) -> Response:
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Peça não encontrada.")
        con.execute(
            "UPDATE products SET status='arquivado', archived_at=?, sync_updated_at=? WHERE id=?",
            (now_iso(), now_iso(), product_id),
        )
        con.execute(
            "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
            (product_id, "arquivado", "Peça arquivada. Saiu da vitrine, busca e live, mas ficou preservada no histórico.", now_iso()),
        )
        enqueue_product_cloud_sync(con, product_id, reason="arquivado")
    try:
        if is_cloud_sync_enabled(request):
            threading.Thread(target=run_auto_cloud_sync, kwargs={"force": True}, daemon=True).start()
    except Exception:
        pass
    return RedirectResponse(url=f"/products/{product_id}", status_code=303)


@app.post("/products/{product_id}/restore")
def restore_product(request: Request, product_id: int) -> Response:
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Peça não encontrada.")
        con.execute(
            "UPDATE products SET status='disponivel', archived_at=NULL, sync_updated_at=? WHERE id=?",
            (now_iso(), product_id),
        )
        con.execute(
            "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
            (product_id, "restaurado", "Peça restaurada para disponível.", now_iso()),
        )
        enqueue_product_cloud_sync(con, product_id, reason="restaurado")
    try:
        if is_cloud_sync_enabled(request):
            threading.Thread(target=run_auto_cloud_sync, kwargs={"force": True}, daemon=True).start()
    except Exception:
        pass
    return RedirectResponse(url=f"/products/{product_id}", status_code=303)


@app.post("/products/{product_id}/delete")
def delete_product_permanently(product_id: int, confirm_text: str = Form("")) -> Response:
    if (confirm_text or "").strip().upper() != "EXCLUIR":
        raise HTTPException(status_code=400, detail="Digite EXCLUIR para confirmar a exclusão definitiva.")
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Peça não encontrada.")
        media = con.execute("SELECT * FROM product_media WHERE product_id=?", (product_id,)).fetchall()
        # Remove arquivos locais quando existirem. Se estiver na nuvem/armazenamento externo, só remove o registro.
        filenames = []
        if product["image_filename"]:
            filenames.append(product["image_filename"])
        filenames.extend([m["filename"] for m in media if m["filename"]])
        for filename in set(filenames):
            try:
                path = UPLOAD_DIR / filename
                if path.exists() and path.is_file():
                    path.unlink()
            except Exception:
                pass
        try:
            qr = QR_DIR / f"{product['code']}.png"
            if qr.exists():
                qr.unlink()
        except Exception:
            pass
        con.execute("DELETE FROM product_media WHERE product_id=?", (product_id,))
        con.execute("DELETE FROM product_interest_events WHERE product_id=?", (product_id,))
        con.execute("DELETE FROM live_ignored_products WHERE product_id=?", (product_id,))
        con.execute("DELETE FROM live_session_items WHERE product_id=?", (product_id,))
        con.execute("DELETE FROM inventory_events WHERE product_id=?", (product_id,))
        con.execute("DELETE FROM products WHERE id=?", (product_id,))
    return RedirectResponse(url="/products", status_code=303)


@app.post("/products/{product_id}/media")
def add_product_media(
    request: Request,
    product_id: int,
    media_files: list[UploadFile] | None = File(None),
    media_notes: str = Form(""),
) -> Response:
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Peça não encontrada.")

        saved_count = save_extra_media_files(
            con,
            product_id=product_id,
            files=media_files,
            prefix=product["code"] or product["title"],
            notes=media_notes,
            can_set_main_image=not bool(product["image_filename"]),
        )
        if saved_count:
            con.execute(
                "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                (product_id, "midia", f"{saved_count} foto(s)/vídeo(s) complementar(es) adicionados.", now_iso()),
            )
            enqueue_product_cloud_sync(con, product_id, reason="media_added")
    try:
        if is_cloud_sync_enabled(request):
            threading.Thread(target=run_auto_cloud_sync, kwargs={"force": True}, daemon=True).start()
    except Exception:
        pass
    return RedirectResponse(url=f"/products/{product_id}", status_code=303)




@app.get("/abrir-peca")
def open_product_from_link(id: int | None = None, code: str = "", origem: str = "whatsapp") -> Response:
    with get_db() as con:
        product = None
        if id:
            product = con.execute("SELECT * FROM products WHERE id=?", (id,)).fetchone()
        if not product and code:
            product = con.execute("SELECT * FROM products WHERE UPPER(code)=UPPER(?)", (code.strip(),)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Peça não encontrada.")
        con.execute(
            "INSERT INTO product_interest_events(product_id, event_type, source, notes, created_at) VALUES(?,?,?,?,?)",
            (product["id"], "link_aberto", origem or "whatsapp", "Link da peça aberto por mensagem.", now_iso()),
        )
    code = product["code"] or str(product["id"])
    return RedirectResponse(url=f"/loja/produto/{code}?origem={origem}", status_code=303)


@app.get("/p/{code}")
def open_product_short_link(code: str, origem: str = "whatsapp") -> Response:
    return open_product_from_link(id=None, code=code, origem=origem)




def find_similar_products(product: sqlite3.Row | dict[str, Any], limit: int = 6) -> list[sqlite3.Row]:
    p = row_to_dict(product)
    with get_db() as con:
        clauses = ["status='disponivel'", "id <> ?"]
        params: list[Any] = [p.get("id")]
        sub: list[str] = []
        for col in ["garment_type", "category", "size", "brand", "color", "style_tags"]:
            value = str(p.get(col) or "").strip()
            if value:
                sub.append(f"COALESCE({col}, '') LIKE ?")
                params.append(f"%{value.split(',')[0].strip()}%")
        if not sub:
            sub.append("1=1")
        sql = f"""
            SELECT *
            FROM products
            WHERE {' AND '.join(clauses)} AND ({' OR '.join(sub)})
            ORDER BY id DESC
            LIMIT ?
        """
        params.append(max(1, min(int(limit), 20)))
        return con.execute(sql, params).fetchall()



def hash_password(password: str, salt: str | None = None) -> str:
    """Hash simples com salt para senhas do portal."""
    salt = salt or secrets.token_hex(16)
    raw = (password or "").encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", raw, salt.encode("utf-8"), 160000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash or "$" not in stored_hash:
        return False
    try:
        salt, digest = stored_hash.split("$", 1)
        return hmac.compare_digest(hash_password(password, salt).split("$", 1)[1], digest)
    except Exception:
        return False


def customer_from_request(request: Request) -> sqlite3.Row | None:
    account_id = parse_customer_cookie_value(request.cookies.get(CUSTOMER_COOKIE_NAME))
    if not account_id:
        return None
    with get_db() as con:
        return con.execute("SELECT * FROM customer_accounts WHERE id=? AND active=1", (account_id,)).fetchone()


def admin_from_request(request: Request) -> sqlite3.Row | None:
    account_id = parse_admin_cookie_value(request.cookies.get(AUTH_COOKIE_NAME))
    if not account_id:
        return None
    with get_db() as con:
        return con.execute("SELECT * FROM admin_accounts WHERE id=? AND active=1", (account_id,)).fetchone()


def has_admin_account() -> bool:
    with get_db() as con:
        return bool(con.execute("SELECT 1 FROM admin_accounts WHERE active=1 LIMIT 1").fetchone())


def auth_log(account_type: str, account_id: int | None, action: str, request: Request | None = None) -> None:
    try:
        ip = request.client.host if request and request.client else ""
        with get_db() as con:
            con.execute(
                "INSERT INTO auth_events(account_type, account_id, action, ip, created_at) VALUES(?,?,?,?,?)",
                (account_type, account_id, action, ip, now_iso()),
            )
    except Exception:
        pass



def normalize_phone(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalize_text_key(value: str | None) -> str:
    return unicodedata.normalize("NFKD", str(value or "").strip().lower()).encode("ascii", "ignore").decode("ascii")


def admin_recovery_allowed(request: Request, token: str = "") -> bool:
    """Permite recuperar/criar senha admin sem login apenas com token configurado.

    Em produção, configure BRECHORISEE_ADMIN_RECOVERY_TOKEN no Render e use o
    mesmo valor uma única vez na tela /admin-recuperar. Sem token, a recuperação
    fica liberada apenas em ambiente local de desenvolvimento.
    """
    configured = BRECHORISEE_ADMIN_RECOVERY_TOKEN
    provided = (token or request.query_params.get("token") or "").strip()
    if configured:
        return bool(provided) and hmac.compare_digest(provided, configured)
    host = (request.client.host if request and request.client else "") or ""
    local_host = host in {"127.0.0.1", "::1", "localhost"} or host.startswith("192.168.") or host.startswith("10.")
    return BRECHORISEE_ENV != "production" and local_host


def safe_next_url(value: str | None, fallback: str = "/") -> str:
    value = str(value or "").strip()
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


CUSTOMER_HOME_PATH = "/cliente/inicio"


def customer_safe_next_url(value: str | None, fallback: str = CUSTOMER_HOME_PATH) -> str:
    """Destino seguro depois de login/cadastro da cliente.

    Regra v4.8.7:
    - Login/cadastro nunca joga a cliente direto na live.
    - Links de live/download continuam existindo, mas após autenticar a cliente cai na
      área inicial e decide tocar em "Entrar na live".
    - Mantém bloqueio contra URLs externas e caminhos administrativos.
    """
    value = safe_next_url(value, fallback)
    blocked_prefixes = (
        "/live",
        "/cliente/live",
        "/cliente/live-opcoes",
        "/cliente/live-companion",
        "/app/cliente",
        "/download",
        "/apk",
        "/app-cliente.apk",
        "/admin",
        "/cashier",
        "/products",
        "/sales",
        "/reports",
        "/gestao",
        "/professional",
        "/profissional",
    )
    lower = value.lower()
    if lower == "/cliente":
        return fallback
    if any(lower == p or lower.startswith(p + "/") for p in blocked_prefixes):
        return fallback
    return value


def find_or_create_customer_for_account(con: sqlite3.Connection, name: str, phone: str, email: str = "") -> int | None:
    phone_clean = "".join(ch for ch in str(phone or "") if ch.isdigit())
    customer = None
    if phone_clean:
        customer = con.execute("SELECT id FROM customers WHERE REPLACE(REPLACE(REPLACE(REPLACE(phone,' ',''),'(',''),')',''),'-','') LIKE ?", (f"%{phone_clean[-8:]}" if len(phone_clean) >= 8 else phone_clean,)).fetchone()
    if customer:
        return int(customer["id"])
    cur = con.execute(
        "INSERT INTO customers(name, phone, email, created_at) VALUES(?,?,?,?)",
        (name, phone, email, now_iso()),
    )
    return int(cur.lastrowid)


def customer_recommendations(account: sqlite3.Row | None, limit: int = 12) -> list[sqlite3.Row]:
    """Sugere peças disponíveis usando histórico/preferências simples da cliente."""
    if not account:
        return loja_rows(limit=limit)
    name = account["name"]
    phone = account["phone"] or ""
    terms: list[str] = []
    with get_db() as con:
        rows = con.execute(
            """
            SELECT p.garment_type, p.size, p.color, p.brand, p.style_tags
            FROM sales s
            JOIN sale_items si ON si.sale_id=s.id
            JOIN products p ON p.id=si.product_id
            WHERE (LOWER(s.customer)=LOWER(?) OR COALESCE(s.customer,'') LIKE ?)
            ORDER BY s.id DESC LIMIT 30
            """,
            (name, f"%{phone[-8:] if phone else name}%"),
        ).fetchall()
        for r in rows:
            for key in ("garment_type", "size", "color", "brand", "style_tags"):
                value = str(r[key] or "").strip()
                if value:
                    terms.append(value.split(",")[0].strip())
    q = " ".join(terms[:4])
    return loja_rows(q=q, limit=limit) if q else loja_rows(limit=limit)



def online_order_code() -> str:
    stamp = datetime.now().strftime("%y%m%d%H%M")
    suffix = "".join(random.choices(string.digits, k=3))
    return f"ONLINE-{stamp}-{suffix}"


def loja_rows(q: str = "", category: str = "", limit: int = 80) -> list[sqlite3.Row]:
    terms = split_search_terms(q)
    where = ["p.status='disponivel'"]
    params: list[Any] = []
    if category:
        where.append("(p.category LIKE ? OR p.garment_type LIKE ? OR p.style_tags LIKE ?)")
        params.extend([f"%{category}%"] * 3)
    for term in terms:
        like = f"%{term}%"
        where.append("(" + " OR ".join([f"COALESCE(p.{col}, '') LIKE ?" for col in SEARCH_COLUMNS]) + ")")
        params.extend([like] * len(SEARCH_COLUMNS))
    sql = """
        SELECT p.*, 
          (SELECT COUNT(*) FROM product_media pm WHERE pm.product_id=p.id) AS media_count
        FROM products p
        WHERE """ + " AND ".join(where) + """
        ORDER BY p.id DESC
        LIMIT ?
    """
    params.append(max(1, min(int(limit), 160)))
    with get_db() as con:
        return con.execute(sql, params).fetchall()


def online_order_status_label(status: str) -> str:
    return {
        "aguardando_pagamento": "Aguardando pagamento",
        "pago": "Pago",
        "separado": "Separado",
        "em_entrega": "Em entrega",
        "cliente_ausente": "Cliente ausente",
        "entregue": "Entregue",
        "cancelado": "Cancelado",
        "conflito": "Conflito",
    }.get(status or "", status or "-")


def load_online_order(order_id: int) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    with get_db() as con:
        order = con.execute("SELECT * FROM online_orders WHERE id=?", (int(order_id),)).fetchone()
        if not order:
            return None, []
        items = con.execute(
            """
            SELECT oi.*, p.image_filename, p.size, p.brand, p.color, p.status AS product_status
            FROM online_order_items oi
            JOIN products p ON p.id=oi.product_id
            WHERE oi.order_id=?
            ORDER BY oi.id
            """,
            (int(order_id),),
        ).fetchall()
    return order, items


def load_online_order_public(order_token: str, request: Request | None = None) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    token = str(order_token or "").strip()
    with get_db() as con:
        order = None
        if token:
            order = con.execute("SELECT * FROM online_orders WHERE public_token=? LIMIT 1", (token,)).fetchone()
        if not order and token.isdigit():
            # Compatibilidade segura: ID antigo só abre para admin logada ou para a própria cliente logada.
            legacy = con.execute("SELECT * FROM online_orders WHERE id=?", (int(token),)).fetchone()
            admin_ok = bool(request and admin_from_request(request))
            customer_ok = False
            if legacy and request:
                account = customer_from_request(request)
                if account:
                    same_account = row_get(legacy, "customer_account_id") and int(row_get(legacy, "customer_account_id")) == int(account["id"])
                    same_phone = normalize_phone(row_get(legacy, "customer_phone", "")) and normalize_phone(row_get(legacy, "customer_phone", "")) == normalize_phone(account["phone"])
                    customer_ok = bool(same_account or same_phone)
            if legacy and (admin_ok or customer_ok):
                token_value = ensure_online_order_token(con, int(legacy["id"]))
                order = con.execute("SELECT * FROM online_orders WHERE public_token=? LIMIT 1", (token_value,)).fetchone()
            elif legacy:
                log_security_event(con, "legacy_order_id_public_blocked", severity="warning", path="/loja/pedido", details=f"order_id={token}", request=request)
        if not order:
            return None, []
        items = con.execute(
            """
            SELECT oi.*, p.image_filename, p.size, p.brand, p.color, p.status AS product_status
            FROM online_order_items oi
            JOIN products p ON p.id=oi.product_id
            WHERE oi.order_id=?
            ORDER BY oi.id
            """,
            (int(order["id"]),),
        ).fetchall()
    return order, items




def build_google_maps_url(address: str = "", lat: str | float | None = None, lng: str | float | None = None, raw_url: str = "") -> str:
    """Cria link seguro do Google Maps para entrega.

    Preferência:
    1. link informado/capturado pela cliente;
    2. latitude/longitude capturada pelo navegador;
    3. endereço digitado.
    """
    raw = str(raw_url or "").strip()
    if raw.startswith(("https://www.google.", "https://maps.google.", "https://goo.gl/maps", "https://maps.app.goo.gl")):
        return raw
    lat_s = str(lat or "").strip().replace(",", ".")
    lng_s = str(lng or "").strip().replace(",", ".")
    try:
        if lat_s and lng_s:
            lat_f = float(lat_s)
            lng_f = float(lng_s)
            if -90 <= lat_f <= 90 and -180 <= lng_f <= 180:
                return f"https://www.google.com/maps?q={lat_f:.7f},{lng_f:.7f}"
    except Exception:
        pass
    addr = str(address or "").strip()
    if addr:
        return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(addr)
    return ""


def build_waze_url(address: str = "", lat: str | float | None = None, lng: str | float | None = None, raw_url: str = "") -> str:
    """Cria link seguro do Waze para o destino da entrega."""
    lat_s = str(lat or "").strip().replace(",", ".")
    lng_s = str(lng or "").strip().replace(",", ".")
    try:
        if lat_s and lng_s:
            lat_f = float(lat_s)
            lng_f = float(lng_s)
            if -90 <= lat_f <= 90 and -180 <= lng_f <= 180:
                return f"https://waze.com/ul?ll={lat_f:.7f}%2C{lng_f:.7f}&navigate=yes"
    except Exception:
        pass
    raw = str(raw_url or "").strip()
    if raw.startswith(("https://waze.com/", "https://www.waze.com/")):
        return raw
    addr = str(address or "").strip()
    if addr:
        return "https://waze.com/ul?q=" + quote_plus(addr) + "&navigate=yes"
    return ""


def delivery_tracking_payload(delivery: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
    """Resumo visual de aproximação da entrega usado no app Cliente e no app Admin.

    O cálculo é conservador: não rastreia a loja em tempo real sem consentimento.
    Mostra o progresso do pedido a partir do status marcado pela administração e
    usa o link/localização informada pela cliente para abrir Maps/Waze.
    """
    d = row_to_dict(delivery or {})
    raw_status = str(d.get("status") or "").lower()
    method = str(d.get("delivery_method") or "entrega").lower()
    is_delivery = method == "entrega" or bool(d.get("address") or d.get("delivery_maps_url") or d.get("delivery_lat"))
    if not is_delivery:
        return {"enabled": False, "progress": 0, "stage": "Retirada", "eta": "", "message": "", "maps_url": "", "waze_url": ""}

    normalized = {
        "aguardando_pagamento": "pendente",
        "pago": "separado",
        "separado": "separado",
        "em_entrega": "rota",
        "rota": "rota",
        "cliente_ausente": "cliente_ausente",
        "entregue": "entregue",
        "cancelado": "cancelada",
        "cancelada": "cancelada",
        "conflito": "pendente",
    }.get(raw_status, raw_status or "pendente")

    progress_map = {
        "pendente": 18,
        "separado": 42,
        "rota": 78,
        "cliente_ausente": 82,
        "entregue": 100,
        "cancelada": 0,
    }
    stage_map = {
        "pendente": "Pedido recebido",
        "separado": "Peças separadas",
        "rota": "Estamos chegando",
        "cliente_ausente": "Tentativa de entrega",
        "entregue": "Entregue",
        "cancelada": "Cancelada",
    }
    message_map = {
        "pendente": "A loja recebeu o pedido e vai preparar a entrega.",
        "separado": "Seu pedido foi separado. Quando sair para entrega, a aproximação ficará ativa.",
        "rota": "Entrega em andamento. Acompanhe pelo mapa ou pelo WhatsApp.",
        "cliente_ausente": "A loja tentou entregar e vai combinar nova tentativa.",
        "entregue": "Entrega concluída. Obrigado por comprar no BRECHORISEE.",
        "cancelada": "Entrega cancelada.",
    }

    address_parts = [str(d.get("address") or "").strip(), str(d.get("city") or "").strip()]
    full_address = " ".join(p for p in address_parts if p)
    maps_url = build_google_maps_url(full_address, d.get("delivery_lat"), d.get("delivery_lng"), d.get("delivery_maps_url") or "")
    waze_url = build_waze_url(full_address, d.get("delivery_lat"), d.get("delivery_lng"), d.get("delivery_maps_url") or "")
    courier_maps_url = build_google_maps_url("", d.get("courier_lat"), d.get("courier_lng"), d.get("courier_maps_url") or "")

    try:
        eta_min = int(d.get("delivery_eta_minutes") or 35)
    except Exception:
        eta_min = 35
    eta_min = max(5, min(180, eta_min))
    if normalized == "entregue":
        eta = "Entregue"
    elif normalized == "cliente_ausente":
        eta = "Nova tentativa a combinar"
    elif normalized == "rota":
        eta = f"Chegará em aproximadamente {eta_min} min"
    elif normalized == "separado":
        eta = "Saída prevista em breve"
    else:
        eta = "Aguardando separação"

    return {
        "enabled": True,
        "status": normalized,
        "progress": progress_map.get(normalized, 18),
        "stage": stage_map.get(normalized, "Pedido recebido"),
        "message": message_map.get(normalized, "Acompanhe a entrega pelo BRECHORISEE."),
        "eta": eta,
        "eta_minutes": eta_min,
        "maps_url": maps_url,
        "waze_url": waze_url,
        "courier_maps_url": courier_maps_url,
        "address": full_address,
        "updated_at": d.get("tracking_updated_at") or d.get("updated_at") or d.get("created_at") or "",
        "started_at": d.get("delivery_started_at") or "",
        "route_notes": d.get("route_notes") or d.get("notes") or "",
    }


def delivery_location_label(order: sqlite3.Row | dict[str, Any]) -> str:
    o = row_to_dict(order)
    if o.get("delivery_method") != "entrega":
        return ""
    parts = []
    if o.get("address"):
        parts.append(str(o.get("address")))
    if o.get("delivery_maps_url"):
        parts.append(str(o.get("delivery_maps_url")))
    elif o.get("delivery_lat") and o.get("delivery_lng"):
        parts.append(build_google_maps_url(lat=o.get("delivery_lat"), lng=o.get("delivery_lng")))
    return "\n".join([p for p in parts if p])


def online_order_message(order: sqlite3.Row | dict[str, Any], items: list[sqlite3.Row | dict[str, Any]], request: Request) -> str:
    o = row_to_dict(order)
    settings = get_store_settings()
    lines = [
        f"Oi, {o.get('customer_name') or 'cliente'}! ✨",
        "",
        "Seu pedido self-service no BRECHORISEE ficou assim:",
        "",
    ]
    for idx, item in enumerate(items, start=1):
        it = row_to_dict(item)
        lines.append(f"{idx}. {it.get('title')} ({it.get('code')}) - {money(it.get('price'))}")
        if it.get("image_filename"):
            lines.append(f"Foto: {app_base_url(request)}/static/uploads/{it.get('image_filename')}")
    lines += ["", f"Total: {money(o.get('total'))}", ""]
    if o.get("payment_method") == "pix" or o.get("pix_text"):
        pix = o.get("pix_text") or settings.get("pix_text") or settings.get("pix_key") or ""
        lines.append(f"Pix: {pix or 'solicite a chave Pix'}")
    if o.get("payment_method") in {"cartao", "misto"} or o.get("payment_link"):
        lines.append(f"Cartão/InfinitePay: {o.get('payment_link') or settings.get('infinitepay_link') or 'solicite o link'}")
    if o.get("delivery_method") == "retirada":
        location = settings.get("pickup_location") or settings.get("address") or ""
        if location:
            lines += ["", f"Retirada/localização: {location}"]
    elif o.get("delivery_method") == "entrega":
        delivery_info = delivery_location_label(o)
        if delivery_info:
            lines += ["", "Entrega/local pelo Google Maps:", delivery_info]
        else:
            lines += ["", "Entrega: combinar endereço/localização com a cliente."]
    lines += [
        "",
        "Após o pagamento, envie o comprovante por aqui para confirmarmos sua compra 💌",
        f"Acompanhar pedido: {app_base_url(request)}/loja/pedido/{o.get('id')}",
    ]
    return "\n".join(lines)



@app.get("/vitrine/peca/{code}", response_class=HTMLResponse)
def public_product_page(request: Request, code: str, origem: str = "instagram") -> Response:
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE UPPER(code)=UPPER(?) OR CAST(id AS TEXT)=?", (code.strip(), code.strip())).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Peça não encontrada.")
        con.execute(
            "INSERT INTO product_interest_events(product_id, event_type, source, notes, created_at) VALUES(?,?,?,?,?)",
            (product["id"], "vitrine_aberta", origem or "instagram", "Vitrine pública da peça aberta.", now_iso()),
        )
    payload = public_product_payload(product, request)
    return templates.TemplateResponse("public_product.html", {"request": request, **payload})


@app.get("/api/products/{product_id}/share")
def api_product_share(product_id: int, request: Request, question: str = "", channel: str = "whatsapp", payment_link: str = "", pix_text: str = "") -> JSONResponse:
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        return JSONResponse({"ok": False, "message": "Peça não encontrada."}, status_code=404)
    message = product_social_text(product, request, question=question, channel=channel, payment_link=payment_link, pix_text=pix_text)
    settings = get_store_settings()
    return JSONResponse({
        "ok": True,
        "message": message,
        "channel": channel,
        "app_link": product_deep_link(product["id"], product["code"]),
        "local_link": f"{app_base_url(request)}/abrir-peca?id={product['id']}&origem={channel}",
        "public_link": product_public_link(product, request, source=channel),
        "photo_link": f"{app_base_url(request)}/static/uploads/{product['image_filename']}" if product["image_filename"] else "",
        "instagram_profile_url": instagram_profile_url(settings),
    })


@app.get("/suppliers", response_class=HTMLResponse)
def suppliers_page(request: Request) -> Response:
    with get_db() as con:
        suppliers = con.execute(
            """
            SELECT s.*, COUNT(p.id) AS items_count
            FROM suppliers s
            LEFT JOIN products p ON p.supplier_id = s.id
            GROUP BY s.id
            ORDER BY s.name
            """
        ).fetchall()
    return templates.TemplateResponse("suppliers.html", {"request": request, "suppliers": suppliers, "active": "suppliers"})


@app.post("/suppliers")
def create_supplier(
    name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    instagram: str = Form(""),
    notes: str = Form(""),
) -> Response:
    with get_db() as con:
        con.execute(
            "INSERT INTO suppliers(name, phone, email, instagram, notes, created_at) VALUES(?,?,?,?,?,?)",
            (name, phone, email, instagram, notes, now_iso()),
        )
    return RedirectResponse(url="/suppliers", status_code=303)


@app.get("/cashier", response_class=HTMLResponse)
def cashier(request: Request) -> Response:
    return templates.TemplateResponse("cashier.html", {"request": request, "active": "cashier"})


@app.get("/api/product-by-code")
def api_product_by_code(code: str) -> JSONResponse:
    code = code.strip().upper()
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE code=?", (code,)).fetchone()
    if not product:
        return JSONResponse({"ok": False, "message": "Peça não encontrada."}, status_code=404)
    return JSONResponse({"ok": True, "product": dict(product)})


@app.get("/api/products/search")
def api_products_search(q: str = "", status: str = "disponivel", limit: int = 20) -> JSONResponse:
    q = (q or "").strip()
    if not q:
        return JSONResponse({"ok": True, "q": q, "results": []})
    rows = search_products_rows(q=q, status=status, limit=limit)
    return JSONResponse({"ok": True, "q": q, "results": [dict(row) for row in rows]})



@app.get("/api/product-attribute-options")
def api_product_attribute_options() -> JSONResponse:
    with get_db() as con:
        options = get_product_attribute_options(con)
    return JSONResponse({"ok": True, "options": options})


@app.post("/api/product-attribute-options")
async def api_save_product_attribute_option(request: Request) -> JSONResponse:
    try:
        data = await request.json()
    except Exception:
        data = {}
    field_name = str(data.get("field_name") or "").strip()
    value = normalize_option_value(str(data.get("value") or ""))
    if field_name not in PRODUCT_OPTION_FIELDS or not value:
        return JSONResponse({"ok": False, "message": "Campo ou valor inválido."}, status_code=400)
    with get_db() as con:
        remember_product_attribute_option(con, field_name, value, source="digitado")
        options = get_product_attribute_options(con)
    return JSONResponse({"ok": True, "options": options, "field_name": field_name, "value": value})


def product_autofill_safe_fallback_payload(
    *,
    title: str = "",
    category: str = "",
    garment_type: str = "",
    brand: str = "",
    color: str = "",
    characteristics: str = "",
    style_tags: str = "",
    message: str = "",
) -> dict[str, Any]:
    """Fallback local: quando a análise completa falha, ainda devolve JSON estável.

    Isso evita que o app Android/WebView mostre erro genérico e permite continuar
    o cadastro pelo que foi digitado.
    """
    suggestions: dict[str, str] = {}
    confidence: dict[str, float] = {}
    typed_text = " ".join([title, category, garment_type, brand, color, characteristics, style_tags]).strip()
    detected_garment, garment_score = infer_garment_from_text(typed_text)
    if detected_garment and not garment_type:
        suggestions["garment_type"] = detected_garment
        confidence["garment_type"] = max(0.78, garment_score)
    if detected_garment and not title:
        suggestions["title"] = detected_garment
        confidence["title"] = 0.78
    text_characteristics = infer_characteristics_from_text(typed_text)
    if text_characteristics and not characteristics:
        suggestions["characteristics"] = ", ".join(text_characteristics)
        confidence["characteristics"] = 0.76
    garment = suggestions.get("garment_type") or garment_type
    if garment:
        suggestions.setdefault("category", "Acessórios" if garment in {"Lenço", "Cinto", "Bolsa"} else "Feminino")
        confidence.setdefault("category", 0.68)
        suggestions.setdefault("condition", "Seminovo")
        confidence.setdefault("condition", 0.55)
    if product_code_has_meaningful_basis(
        title=suggestions.get("title") or title,
        category=suggestions.get("category") or category,
        garment_type=suggestions.get("garment_type") or garment_type,
        color=color,
        brand=brand,
        characteristics=suggestions.get("characteristics") or characteristics,
        style_tags=style_tags,
    ):
        try:
            suggestions["code"] = generate_product_code_preview(
                title=suggestions.get("title") or title,
                category=suggestions.get("category") or category,
                garment_type=suggestions.get("garment_type") or garment_type,
                color=color,
                brand=brand,
                characteristics=suggestions.get("characteristics") or characteristics,
                style_tags=style_tags,
            )
            confidence["code"] = 0.82
        except Exception:
            pass
    reasons = [
        message or "Usei o modo seguro local para continuar o cadastro.",
        "Revise as sugestões antes de salvar.",
    ]
    if not suggestions:
        reasons.append("Digite pelo menos o nome ou o tipo da peça para eu conseguir sugerir com mais segurança.")
    suggestions, confidence = sanitize_ai_product_suggestions(suggestions, confidence)
    return {
        "suggestions": suggestions,
        "confidence": confidence,
        "auto_apply": {k: bool(confidence.get(k, 0) >= 0.76 and k not in {"code", "condition"}) for k in suggestions},
        "reasons": reasons,
        "similar": [],
        "profile": {},
        "fallback": True,
    }


@app.post("/api/product-autofill")
async def api_product_autofill(
    title: str = Form(""),
    category: str = Form(""),
    garment_type: str = Form(""),
    brand: str = Form(""),
    color: str = Form(""),
    characteristics: str = Form(""),
    style_tags: str = Form(""),
    image: UploadFile | None = File(None),
) -> JSONResponse:
    image_bytes: bytes | None = None
    try:
        if image and image.filename:
            image_bytes = await image.read()
            if len(image_bytes) > 7_000_000:
                return JSONResponse({"ok": False, "message": "Foto muito grande. Use uma imagem menor."}, status_code=400)
    except Exception:
        logger.warning("Não foi possível ler a imagem enviada para IA de cadastro.", exc_info=True)
        image_bytes = None

    incoming = sanitize_product_attribute_inputs({
        "title": title,
        "category": category,
        "garment_type": garment_type,
        "brand": brand,
        "color": color,
        "characteristics": characteristics,
        "style_tags": style_tags,
    })
    title = incoming.get("title", title)
    category = incoming.get("category", category)
    garment_type = incoming.get("garment_type", garment_type)
    brand = incoming.get("brand", brand)
    color = incoming.get("color", color)
    characteristics = incoming.get("characteristics", characteristics)
    style_tags = incoming.get("style_tags", style_tags)

    try:
        data = ai_product_autofill_suggestions(
            image_bytes=image_bytes,
            title=title,
            category=category,
            garment_type=garment_type,
            brand=brand,
            color=color,
            characteristics=characteristics,
            style_tags=style_tags,
        )
    except Exception:
        logger.exception("Falha ao chamar IA de cadastro; usando fallback local.")
        data = product_autofill_safe_fallback_payload(
            title=title,
            category=category,
            garment_type=garment_type,
            brand=brand,
            color=color,
            characteristics=characteristics,
            style_tags=style_tags,
            message="A IA completa falhou, então usei a identificação local segura.",
        )

    try:
        with get_db() as con:
            options = get_product_attribute_options(con)
    except Exception:
        logger.warning("Falha ao carregar opções de atributos no autofill.", exc_info=True)
        options = {field: list(DEFAULT_PRODUCT_ATTRIBUTE_OPTIONS.get(field, [])) for field in PRODUCT_OPTION_FIELDS}

    return JSONResponse({"ok": True, "ai": data, "options": options})


@app.get("/api/generate-product-code")
def api_generate_product_code(
    title: str = "",
    category: str = "",
    garment_type: str = "",
    color: str = "",
    brand: str = "",
    characteristics: str = "",
    style_tags: str = "",
) -> JSONResponse:
    cleaned = sanitize_product_attribute_inputs({
        "title": title,
        "category": category,
        "garment_type": garment_type,
        "color": color,
        "brand": brand,
        "characteristics": characteristics,
        "style_tags": style_tags,
    })
    title = cleaned.get("title", title)
    category = cleaned.get("category", category)
    garment_type = cleaned.get("garment_type", garment_type)
    color = cleaned.get("color", color)
    brand = cleaned.get("brand", brand)
    characteristics = cleaned.get("characteristics", characteristics)
    style_tags = cleaned.get("style_tags", style_tags)
    if not product_code_has_meaningful_basis(title, category, garment_type, color, brand, characteristics, style_tags):
        return JSONResponse({
            "ok": False,
            "code": "",
            "message": "Digite o nome ou tipo da peça para gerar um código confiável.",
            "format": "NOME-NNN",
            "example": "VESTIDO-001",
        })
    code = generate_product_code_preview(
        title=title,
        category=category,
        garment_type=garment_type,
        color=color,
        brand=brand,
        characteristics=characteristics,
        style_tags=style_tags,
    )
    return JSONResponse({
        "ok": True,
        "code": code,
        "format": "NOME-NNN",
        "example": "VESTIDO-001",
    })




@app.post("/api/checkout")
async def api_checkout(request: Request) -> JSONResponse:
    data = await request.json()
    codes = [str(c).strip().upper() for c in data.get("codes", []) if str(c).strip()]
    try:
        discount = validate_money_amount(data.get("discount") or 0, "Desconto", minimum=0, allow_zero=True)
        paid = validate_money_amount(data.get("paid") or 0, "Valor pago", minimum=0, allow_zero=True)
    except HTTPException as exc:
        return JSONResponse({"ok": False, "message": exc.detail}, status_code=400)
    customer = str(data.get("customer") or "")[:160]
    payment_method = str(data.get("payment_method") or "Dinheiro")[:80]

    if not codes:
        return JSONResponse({"ok": False, "message": "Carrinho vazio."}, status_code=400)
    if len(codes) != len(set(codes)):
        return JSONResponse({"ok": False, "message": "Há códigos duplicados no carrinho."}, status_code=400)

    placeholders = ",".join("?" for _ in codes)
    with get_db() as con:
        products = con.execute(f"SELECT * FROM products WHERE code IN ({placeholders})", codes).fetchall()
        found_codes = {p["code"] for p in products}
        missing = [code for code in codes if code not in found_codes]
        unavailable = [p["code"] for p in products if p["status"] != "disponivel"]

        if missing:
            return JSONResponse({"ok": False, "message": f"Código não encontrado: {', '.join(missing)}"}, status_code=404)
        if unavailable:
            return JSONResponse({"ok": False, "message": f"Peça indisponível: {', '.join(unavailable)}"}, status_code=400)

        try:
            prices = [validate_money_amount(p["sale_price"], f"Preço da peça {p['code']}", minimum=0, allow_zero=False) for p in products]
        except HTTPException as exc:
            return JSONResponse({"ok": False, "message": exc.detail}, status_code=400)
        subtotal = sum(prices)
        if discount > subtotal:
            return JSONResponse({"ok": False, "message": "Desconto não pode ser maior que o subtotal."}, status_code=400)
        total = round(subtotal - discount, 2)
        change_value = max(0, paid - total)

        sale_id, sale_code = create_sale_record(
            con,
            customer=customer,
            payment_method=payment_method,
            discount=discount,
            total=total,
            paid=paid,
            source="checkout_admin",
            source_ref_id=None,
        )

        for p, price in zip(products, prices):
            con.execute(
                "INSERT INTO sale_items(sale_id, product_id, price) VALUES(?,?,?)",
                (sale_id, p["id"], price),
            )
            sold_time = now_iso()
            con.execute(
                "UPDATE products SET status='vendido', sold_at=?, sync_updated_at=? WHERE id=? AND status='disponivel'",
                (sold_time, sold_time, p["id"]),
            )
            con.execute(
                "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                (p["id"], "venda", f"Vendido na {sale_code}. Peça retirada do estoque disponível.", sold_time),
            )
            enqueue_product_cloud_sync(con, p["id"], reason="sold")
        enqueue_sale_cloud_sync(con, sale_id)

    audit("venda_finalizada", "sales", sale_code, f"Venda com {len(codes)} peça(s), total {total}.")
    try:
        if is_cloud_sync_enabled(request):
            threading.Thread(target=run_auto_cloud_sync, kwargs={"force": True}, daemon=True).start()
    except Exception:
        pass

    return JSONResponse(
        {
            "ok": True,
            "sale_code": sale_code,
            "subtotal": subtotal,
            "discount": discount,
            "total": total,
            "paid": paid,
            "change": change_value,
            "sold_codes": codes,
            "message": "Venda finalizada. Peças retiradas do estoque disponível.",
        }
    )


@app.get("/sales", response_class=HTMLResponse)
def sales_page(request: Request) -> Response:
    with get_db() as con:
        sales = con.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 100").fetchall()
    return templates.TemplateResponse("sales.html", {"request": request, "sales": sales, "active": "sales"})


@app.get("/sales/{sale_id}", response_class=HTMLResponse)
def sale_detail(request: Request, sale_id: int) -> Response:
    with get_db() as con:
        sale = con.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        items = con.execute(
            """
            SELECT si.*, p.code, p.title, p.image_filename, p.garment_type, p.size, p.color
            FROM sale_items si
            JOIN products p ON p.id = si.product_id
            WHERE si.sale_id=?
            """,
            (sale_id,),
        ).fetchall()
        delivery_row = con.execute("SELECT * FROM deliveries WHERE sale_id=? ORDER BY id DESC LIMIT 1", (sale_id,)).fetchone()
        delivery = hydrate_delivery(delivery_row, con) if delivery_row else None
    if not sale:
        raise HTTPException(status_code=404, detail="Venda não encontrada.")
    return templates.TemplateResponse("sale_detail.html", {"request": request, "sale": sale, "items": items, "delivery": delivery, "active": "sales"})



@app.get("/caderno", response_class=HTMLResponse)
def notebook_camera_page(request: Request) -> Response:
    summary = notebook_summary(30)
    return templates.TemplateResponse(
        "notebook_import.html",
        {
            "request": request,
            "active": "caderno",
            "summary": summary,
            "example_text": "Sandra (Nova compra)\nVestido floral 69,90\nCalça jeans nova 79,90\nTotal 149,80\n- 50,00\nNovo total 99,80 10/02/26",
        },
    )


@app.post("/api/caderno/analisar")
def api_notebook_analyze(
    request: Request,
    image: UploadFile | None = File(None),
    text_manual: str = Form(""),
    source: str = Form("camera"),
) -> JSONResponse:
    image_filename = ""
    image_hash = ""
    ocr_text = ""
    ocr_engine = "manual"
    notes: list[str] = []
    if image is not None and image.filename:
        image_filename = save_upload(image, "caderno")
        if image_filename:
            try:
                image_hash, _rgb = image_signature(UPLOAD_DIR / image_filename)
            except Exception:
                image_hash = ""
            ocr_text, ocr_engine, ocr_warning = notebook_try_ocr_image(UPLOAD_DIR / image_filename)
            if ocr_warning:
                notes.append(ocr_warning)

    final_text = notebook_clean_ocr_text(text_manual or ocr_text)
    parsed = notebook_parse_text(final_text)
    if not final_text and image_filename:
        parsed["warnings"].append("Foto salva, mas o OCR não retornou texto. Use o campo de conferência para corrigir antes de aplicar.")

    with get_db() as con:
        batch_id = notebook_persist_import(
            con,
            image_filename=image_filename,
            image_hash=image_hash,
            ocr_engine=ocr_engine,
            ocr_text=ocr_text,
            edited_text=final_text,
            parse_payload=parsed,
            source=source or "camera",
            notes="\n".join(notes),
        )
    return JSONResponse({
        "ok": True,
        "batch_id": batch_id,
        "ocr_engine": ocr_engine,
        "image_filename": image_filename,
        "text": final_text,
        "parsed": parsed,
        "warnings": notes + parsed.get("warnings", []),
        "detail_url": f"/caderno/importacoes/{batch_id}",
        "message": "Caderno analisado. Confira antes de aplicar no sistema.",
    })


@app.get("/api/caderno/importacoes/{batch_id}")
def api_notebook_import_detail(batch_id: int) -> JSONResponse:
    with get_db() as con:
        data = notebook_get_import(con, batch_id)
        batch = row_to_dict(data["batch"])
        lines = [row_to_dict(r) for r in data["lines"]]
    return JSONResponse({"ok": True, "batch": batch, "lines": lines, "payload": data["payload"]})


@app.get("/caderno/importacoes/{batch_id}", response_class=HTMLResponse)
def notebook_import_detail_page(request: Request, batch_id: int) -> Response:
    with get_db() as con:
        data = notebook_get_import(con, batch_id)
    return templates.TemplateResponse(
        "notebook_import_detail.html",
        {
            "request": request,
            "active": "caderno",
            "batch": data["batch"],
            "lines": data["lines"],
            "payload": data["payload"],
        },
    )


@app.post("/caderno/importacoes/{batch_id}/atualizar-texto")
def notebook_update_text(batch_id: int, edited_text: str = Form("")) -> Response:
    parsed = notebook_parse_text(edited_text)
    with get_db() as con:
        notebook_get_import(con, batch_id)
        con.execute(
            "UPDATE notebook_import_batches SET edited_text=?, parse_payload=?, confidence=?, status='rascunho', updated_at=? WHERE id=?",
            (notebook_clean_ocr_text(edited_text), json.dumps(parsed, ensure_ascii=False), float(parsed.get("confidence") or 0), now_iso(), int(batch_id)),
        )
        notebook_replace_import_lines(con, batch_id, parsed)
    return RedirectResponse(url=f"/caderno/importacoes/{batch_id}", status_code=303)


@app.post("/caderno/importacoes/{batch_id}/aplicar")
def notebook_apply_page(batch_id: int, force: int = Form(0)) -> Response:
    with get_db() as con:
        notebook_apply_import(con, batch_id, force=bool(int(force or 0)))
    return RedirectResponse(url=f"/caderno/importacoes/{batch_id}", status_code=303)


@app.post("/api/caderno/importacoes/{batch_id}/aplicar")
def api_notebook_apply(batch_id: int, force: int = Form(0)) -> JSONResponse:
    with get_db() as con:
        result = notebook_apply_import(con, batch_id, force=bool(int(force or 0)))
    return JSONResponse(result)


@app.get("/recognize", response_class=HTMLResponse)
def recognize_form(request: Request, q: str = "") -> Response:
    typed_results = search_products_rows(q=q, status="disponivel", limit=24) if q.strip() else None
    return templates.TemplateResponse(
        "recognize.html",
        {
            "request": request,
            "results": None,
            "text_q": q,
            "text_results": typed_results,
            "active": "recognize",
        },
    )


@app.post("/recognize", response_class=HTMLResponse)
def recognize_image(request: Request, image: UploadFile = File(...)) -> Response:
    filename = save_upload(image, "busca")
    if not filename:
        raise HTTPException(status_code=400, detail="Envie uma imagem.")
    query_hash, query_rgb = image_signature(UPLOAD_DIR / filename)

    matches = recognize_product_matches(query_hash, query_rgb, limit=8, status="disponivel_reservado")
    results = [{"score": item["score"], "product": item} for item in matches]

    return templates.TemplateResponse(
        "recognize.html",
        {
            "request": request,
            "results": results,
            "query_image": filename,
            "text_q": "",
            "text_results": None,
            "active": "recognize",
        },
    )


@app.post("/api/recognize")
def api_recognize(image: UploadFile = File(...)) -> JSONResponse:
    filename = save_upload(image, "busca-api")
    if not filename:
        return JSONResponse({"ok": False, "message": "Envie uma imagem."}, status_code=400)
    query_hash, query_rgb = image_signature(UPLOAD_DIR / filename)

    results = recognize_product_matches(query_hash, query_rgb, limit=5, status="disponivel_reservado")

    return JSONResponse({"ok": True, "query_image": filename, "results": results})


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request) -> Response:
    return templates.TemplateResponse("reports.html", {"request": request, "active": "reports"})


@app.get("/api/reports")
def api_reports(days: int = 30) -> JSONResponse:
    return JSONResponse(report_payload(days))


@app.get("/stock-history", response_class=HTMLResponse)
def stock_history_page(request: Request, status: str = "todos") -> Response:
    payload = report_payload(365)
    rows = payload["stock_history"]
    if status != "todos":
        rows = [row for row in rows if row["status"] == status]
    return templates.TemplateResponse(
        "stock_history.html",
        {"request": request, "rows": rows, "status": status, "active": "stock_history"},
    )


@app.get("/ai", response_class=HTMLResponse)
def ai_page(request: Request) -> Response:
    return templates.TemplateResponse(
        "ai.html",
        {"request": request, "summary": ai_summary(), "active": "ai"},
    )


@app.post("/api/products/{product_id}/ai")
def api_product_ai(product_id: int) -> JSONResponse:
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            return JSONResponse({"ok": False, "message": "Peça não encontrada."}, status_code=404)
        ai = local_fashion_ai(product, con)
        con.execute(
            "UPDATE products SET trend_label=?, last_ai_score=?, last_ai_notes=?, last_ai_at=? WHERE id=?",
            (
                ai["label"],
                ai["score"],
                json.dumps({"reasons": ai["reasons"], "actions": ai["actions"]}, ensure_ascii=False),
                ai["updated_at"],
                product_id,
            ),
        )
    return JSONResponse({"ok": True, "ai": ai})


@app.get("/api/product-advice")
def api_product_advice(
    title: str = "",
    category: str = "",
    garment_type: str = "",
    size: str = "",
    brand: str = "",
    color: str = "",
    condition: str = "",
    characteristics: str = "",
    style_tags: str = "",
    season: str = "",
    target_audience: str = "",
    cost_price: float = 0,
    sale_price: float = 0,
) -> JSONResponse:
    draft = {
        "title": title,
        "category": category,
        "garment_type": garment_type,
        "size": size,
        "brand": brand,
        "color": color,
        "condition": condition,
        "characteristics": characteristics,
        "style_tags": style_tags,
        "season": season,
        "target_audience": target_audience,
        "cost_price": cost_price,
        "sale_price": sale_price,
        "status": "disponivel",
        "created_at": now_iso(),
        "sold_at": None,
    }
    return JSONResponse({"ok": True, "ai": local_fashion_ai(draft)})





@app.get("/marketing", response_class=HTMLResponse)
def marketing_page(request: Request, product_id: int | None = None, q: str = "") -> Response:
    rows = search_products_rows(q=q, status='todos', limit=24 if not q else 60)
    selected_product = None
    selected_media: list[sqlite3.Row] = []
    if product_id:
        selected_product, selected_media = get_product_with_media(product_id)
    drafts = load_marketing_drafts()
    return templates.TemplateResponse(
        "marketing.html",
        {
            "request": request,
            "products": rows,
            "q": q,
            "selected_product": selected_product,
            "selected_media": selected_media,
            "generated": None,
            "drafts": drafts,
            "active": "marketing",
        },
    )


@app.post("/marketing/generate", response_class=HTMLResponse)
def marketing_generate(
    request: Request,
    product_id: int = Form(...),
    content_type: str = Form('post'),
    custom_text: str = Form(''),
    template_style: str = Form('minimalista'),
    seal: str = Form('auto'),
    duration_mode: str = Form('medio'),
    quality_mode: str = Form('alta'),
    audio_mode: str = Form('narracao'),
    music_mode: str = Form('viral'),
    selected_media_ids: list[int] | None = Form(None),
) -> Response:
    product, media = get_product_with_media(product_id)
    if not product:
        raise HTTPException(status_code=404, detail='Peça não encontrada.')

    if selected_media_ids:
        selected_ids = {int(i) for i in selected_media_ids}
        chosen_media = [m for m in media if int(m['id']) in selected_ids]
    else:
        chosen_media = media
    if not chosen_media and media:
        chosen_media = media[:1]

    generated = build_marketing_content(product, chosen_media, custom_text=custom_text, content_type=content_type, template_style=template_style, seal=seal, duration_mode=duration_mode, quality_mode=quality_mode, audio_mode=audio_mode, music_mode=music_mode)
    product_dict = row_to_dict(product)
    media_dicts = [row_to_dict(m) for m in chosen_media]
    generated['rendered_post_url'] = render_post_image(product_dict, media_dicts, generated['caption'], content_type='story' if content_type == 'story' else 'post', template_style=template_style, seal=generated['seal'])
    generated['rendered_reel_url'] = render_reel_video(product_dict, media_dicts, template_style=template_style, seal=generated['seal'], duration_mode=duration_mode, quality_mode=quality_mode) if content_type == 'reel' else None
    generated['carousel_slide_urls'] = render_carousel_slides(product_dict, media_dicts, template_style=template_style, seal=generated['seal']) if content_type == 'carrossel' else []

    with get_db() as con:
        con.execute(
            "INSERT INTO marketing_drafts(product_id, content_type, title, caption, hashtags, media_ids, created_at) VALUES(?,?,?,?,?,?,?)",
            (product_id, content_type, generated['title'], generated['caption'], generated['hashtags'], json.dumps([m['id'] for m in chosen_media]), now_iso()),
        )

    drafts = load_marketing_drafts()
    rows = search_products_rows(q='', status='todos', limit=24)
    return templates.TemplateResponse(
        "marketing.html",
        {
            "request": request,
            "products": rows,
            "q": '',
            "selected_product": product,
            "selected_media": media,
            "generated": generated,
            "drafts": drafts,
            "active": "marketing",
        },
    )




def customer_summary_rows() -> list[dict[str, Any]]:
    with get_db() as con:
        rows = con.execute(
            """
            SELECT COALESCE(NULLIF(s.customer,''), 'Cliente balcão') AS customer,
                   COUNT(*) AS purchases,
                   SUM(s.total) AS total_spent,
                   MAX(s.created_at) AS last_sale
            FROM sales s
            GROUP BY COALESCE(NULLIF(s.customer,''), 'Cliente balcão')
            ORDER BY total_spent DESC
            LIMIT 30
            """
        ).fetchall()
    return [dict(r) for r in rows]


def smart_vitrine_rows(limit: int = 18) -> list[sqlite3.Row]:
    with get_db() as con:
        return con.execute(
            """
            SELECT p.*, 
              CAST(julianday('now') - julianday(p.created_at) AS INTEGER) AS stock_days,
              (p.sale_price - COALESCE(p.cost_price,0)) AS margin_value,
              (SELECT COUNT(*) FROM product_media pm WHERE pm.product_id=p.id) AS media_count
            FROM products p
            WHERE p.status='disponivel'
            ORDER BY
              CASE WHEN p.trend_label LIKE '%tend%' THEN 0 ELSE 1 END,
              margin_value DESC,
              media_count DESC,
              p.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def wishlist_matches(limit: int = 30) -> list[dict[str, Any]]:
    with get_db() as con:
        wishes = con.execute("SELECT * FROM wishlists ORDER BY id DESC LIMIT 80").fetchall()
        matches: list[dict[str, Any]] = []
        for wish in wishes:
            terms = [wish["query"], wish["size"], wish["brand"], wish["color"], wish["style"]]
            q = " ".join(str(t or "") for t in terms).strip()
            if not q:
                continue
            products = search_products_rows(q=q, status="disponivel", limit=3)
            for product in products:
                matches.append({"wish": dict(wish), "product": dict(product)})
                if len(matches) >= limit:
                    return matches
        return matches


def financial_snapshot(days: int = 30) -> dict[str, Any]:
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as con:
        sales = con.execute("SELECT COALESCE(SUM(total),0), COUNT(*) FROM sales WHERE created_at >= ?", (since,)).fetchone()
        expenses = con.execute("SELECT COALESCE(SUM(amount),0), COUNT(*) FROM expenses WHERE created_at >= ?", (since,)).fetchone()
        stock = con.execute("SELECT COALESCE(SUM(sale_price),0), COUNT(*) FROM products WHERE status='disponivel'").fetchone()
    revenue = float(sales[0] or 0)
    expense_total = float(expenses[0] or 0)
    return {
        "days": days,
        "revenue": revenue,
        "sales_count": int(sales[1] or 0),
        "expenses": expense_total,
        "expenses_count": int(expenses[1] or 0),
        "net": revenue - expense_total,
        "stock_value": float(stock[0] or 0),
        "stock_count": int(stock[1] or 0),
    }




def _clean_customer_name(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "Cliente balcão"


def _split_tags(value: Any) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    parts = []
    for piece in raw.replace(";", ",").replace("|", ",").split(","):
        item = piece.strip()
        if item:
            parts.append(item)
    if not parts and raw:
        parts.append(raw)
    return parts


def _top_counter(counter: dict[str, int], limit: int = 5) -> list[dict[str, Any]]:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    return [{"label": label, "count": count} for label, count in items[:limit] if label]


def _add_counter(counter: dict[str, int], value: Any) -> None:
    text = str(value or "").strip()
    if text:
        counter[text] = counter.get(text, 0) + 1


def _safe_pct(value: float, max_value: float) -> int:
    if not max_value:
        return 0
    return max(3, min(100, int((float(value or 0) / max_value) * 100)))


def build_customer_intelligence() -> list[dict[str, Any]]:
    """Cria perfil automático de compra de cada cliente usando vendas + itens vendidos."""
    with get_db() as con:
        rows = con.execute(
            """
            SELECT s.id AS sale_id, s.customer, s.payment_method, s.total, s.created_at AS sale_created_at,
                   p.id AS product_id, p.code, p.title, p.category, p.garment_type, p.size,
                   p.brand, p.color, p.condition, p.characteristics, p.style_tags, p.season,
                   p.target_audience, si.price
            FROM sales s
            LEFT JOIN sale_items si ON si.sale_id = s.id
            LEFT JOIN products p ON p.id = si.product_id
            ORDER BY s.created_at DESC, s.id DESC
            """
        ).fetchall()
        customers_table = con.execute("SELECT * FROM customers ORDER BY name").fetchall()

    customer_lookup: dict[str, dict[str, Any]] = {}
    for c in customers_table:
        name = _clean_customer_name(c["name"])
        customer_lookup[name.casefold()] = dict(c)

    profiles: dict[str, dict[str, Any]] = {}
    sale_seen: dict[str, set[int]] = {}

    for row in rows:
        name = _clean_customer_name(row["customer"])
        key = name.casefold()
        if key not in profiles:
            cdata = customer_lookup.get(key, {})
            profiles[key] = {
                "name": name,
                "customer_data": cdata,
                "phone": cdata.get("phone", ""),
                "instagram": cdata.get("instagram", ""),
                "email": cdata.get("email", ""),
                "measurements": cdata.get("measurements", ""),
                "preferences": cdata.get("preferences", ""),
                "notes": cdata.get("notes", ""),
                "sales_count": 0,
                "pieces_count": 0,
                "total_spent": 0.0,
                "ticket_avg": 0.0,
                "last_sale": row["sale_created_at"],
                "payments": {},
                "categories": {},
                "types": {},
                "sizes": {},
                "colors": {},
                "brands": {},
                "styles": {},
                "seasons": {},
                "audiences": {},
                "products": [],
                "sales_ids": set(),
            }
            sale_seen[key] = set()

        profile = profiles[key]
        sale_id = int(row["sale_id"] or 0)
        if sale_id and sale_id not in sale_seen[key]:
            sale_seen[key].add(sale_id)
            profile["sales_ids"].add(sale_id)
            profile["sales_count"] += 1
            profile["total_spent"] += float(row["total"] or 0)
            _add_counter(profile["payments"], row["payment_method"])

        if row["product_id"]:
            profile["pieces_count"] += 1
            _add_counter(profile["categories"], row["category"])
            _add_counter(profile["types"], row["garment_type"] or row["title"])
            _add_counter(profile["sizes"], row["size"])
            _add_counter(profile["colors"], row["color"])
            _add_counter(profile["brands"], row["brand"])
            _add_counter(profile["seasons"], row["season"])
            _add_counter(profile["audiences"], row["target_audience"])
            for tag in _split_tags(row["style_tags"]):
                _add_counter(profile["styles"], tag)
            for tag in _split_tags(row["characteristics"]):
                _add_counter(profile["styles"], tag)
            profile["products"].append({
                "sale_id": sale_id,
                "date": row["sale_created_at"],
                "code": row["code"],
                "title": row["title"],
                "type": row["garment_type"],
                "size": row["size"],
                "brand": row["brand"],
                "color": row["color"],
                "price": float(row["price"] or 0),
            })

    result: list[dict[str, Any]] = []
    max_spent = max([p["total_spent"] for p in profiles.values()] or [0])
    for profile in profiles.values():
        profile["sales_ids"] = sorted(profile["sales_ids"], reverse=True)
        profile["ticket_avg"] = profile["total_spent"] / profile["sales_count"] if profile["sales_count"] else 0
        profile["top_payments"] = _top_counter(profile["payments"])
        profile["top_categories"] = _top_counter(profile["categories"])
        profile["top_types"] = _top_counter(profile["types"])
        profile["top_sizes"] = _top_counter(profile["sizes"])
        profile["top_colors"] = _top_counter(profile["colors"])
        profile["top_brands"] = _top_counter(profile["brands"])
        profile["top_styles"] = _top_counter(profile["styles"])
        profile["top_seasons"] = _top_counter(profile["seasons"])
        profile["top_audiences"] = _top_counter(profile["audiences"])
        profile["bar_pct"] = _safe_pct(profile["total_spent"], max_spent)
        result.append(profile)

    result.sort(key=lambda p: (p["total_spent"], p["pieces_count"], p["sales_count"]), reverse=True)
    return result


def suggested_products_for_customer(profile: dict[str, Any], limit: int = 12) -> list[sqlite3.Row]:
    """Sugere peças disponíveis com base em tamanho, cor, tipo, marca e estilo que a cliente mais compra."""
    terms: list[str] = []
    for field in ["top_types", "top_sizes", "top_colors", "top_brands", "top_styles", "top_categories"]:
        for item in profile.get(field, [])[:2]:
            label = str(item.get("label") or "").strip()
            if label and label.casefold() not in {t.casefold() for t in terms}:
                terms.append(label)

    if not terms:
        return []

    # Busca combinada primeiro; se vier pouco resultado, busca por termos individuais.
    results: list[sqlite3.Row] = []
    seen_ids: set[int] = set()
    q = " ".join(terms[:4])
    for row in search_products_rows(q=q, status="disponivel", limit=limit):
        if int(row["id"]) not in seen_ids:
            seen_ids.add(int(row["id"]))
            results.append(row)

    for term in terms:
        if len(results) >= limit:
            break
        for row in search_products_rows(q=term, status="disponivel", limit=limit):
            if int(row["id"]) not in seen_ids:
                seen_ids.add(int(row["id"]))
                results.append(row)
                if len(results) >= limit:
                    break
    return results[:limit]


def customer_intelligence_charts(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Dados resumidos para gráficos de clientes."""
    top_spent = profiles[:10]
    payment_counter: dict[str, int] = {}
    style_counter: dict[str, int] = {}
    type_counter: dict[str, int] = {}
    size_counter: dict[str, int] = {}
    color_counter: dict[str, int] = {}
    inactive: list[dict[str, Any]] = []

    for p in profiles:
        for item in p.get("top_payments", [])[:1]:
            payment_counter[item["label"]] = payment_counter.get(item["label"], 0) + 1
        for item in p.get("top_styles", [])[:3]:
            style_counter[item["label"]] = style_counter.get(item["label"], 0) + item["count"]
        for item in p.get("top_types", [])[:3]:
            type_counter[item["label"]] = type_counter.get(item["label"], 0) + item["count"]
        for item in p.get("top_sizes", [])[:2]:
            size_counter[item["label"]] = size_counter.get(item["label"], 0) + item["count"]
        for item in p.get("top_colors", [])[:2]:
            color_counter[item["label"]] = color_counter.get(item["label"], 0) + item["count"]

        last = parse_dt(p.get("last_sale"))
        days = (datetime.now() - last).days if last else 9999
        if days >= 45:
            item = dict(p)
            item["inactive_days"] = days
            inactive.append(item)

    inactive.sort(key=lambda x: x["inactive_days"], reverse=True)
    return {
        "top_spent": top_spent,
        "payments": _top_counter(payment_counter, 8),
        "styles": _top_counter(style_counter, 10),
        "types": _top_counter(type_counter, 10),
        "sizes": _top_counter(size_counter, 10),
        "colors": _top_counter(color_counter, 10),
        "inactive": inactive[:10],
    }


def _write_sqlite_backup(z: zipfile.ZipFile) -> None:
    """Inclui o banco no ZIP usando a API online backup do SQLite.

    Copiar o arquivo .db diretamente enquanto a loja está vendendo pode gerar
    backup inconsistente quando WAL está ativo. Esta rotina cria uma cópia
    transacional segura e só então adiciona ao arquivo final.
    """
    if not DB_PATH.exists():
        return

    tmp_fd, tmp_name = tempfile.mkstemp(prefix="brechorisee-db-", suffix=".db")
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)
    source = None
    target = None
    try:
        source = sqlite3.connect(DB_PATH, timeout=max(1.0, DB_BUSY_TIMEOUT_MS / 1000))
        target = sqlite3.connect(tmp_path)
        source.backup(target)
        target.close()
        source.close()
        z.write(tmp_path, "brechorisee.db")
    finally:
        try:
            if target:
                target.close()
            if source:
                source.close()
        finally:
            tmp_path.unlink(missing_ok=True)


def create_backup_zip() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"backup-brechorisee-{stamp}.zip"
    path = BACKUP_DIR / filename
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        _write_sqlite_backup(z)
        for folder_name in ["uploads", "qrcodes", "generated"]:
            folder = STATIC_DIR / folder_name
            if folder.exists():
                for file in folder.rglob("*"):
                    if file.is_file():
                        z.write(file, f"static/{folder_name}/{file.relative_to(folder)}")
        z.writestr(
            "LEIA.txt",
            "Backup local do BRECHORISEE: banco SQLite consistente, fotos, vídeos, QR Codes e conteúdos gerados.\n"
            "Restaure substituindo o banco e as pastas estáticas correspondentes com o sistema parado.\n",
        )
    return filename




@app.get("/clientes-inteligentes", response_class=HTMLResponse)
def clientes_inteligentes_page(request: Request, cliente: str = "", q: str = "") -> Response:
    profiles = build_customer_intelligence()
    if q.strip():
        query = q.strip().casefold()
        profiles = [
            p for p in profiles
            if query in p["name"].casefold()
            or query in str(p.get("phone") or "").casefold()
            or query in str(p.get("instagram") or "").casefold()
            or any(query in str(item.get("label") or "").casefold() for group in [p.get("top_types", []), p.get("top_styles", []), p.get("top_colors", []), p.get("top_sizes", []), p.get("top_brands", [])] for item in group)
        ]

    selected = None
    if cliente:
        ck = cliente.casefold()
        selected = next((p for p in profiles if p["name"].casefold() == ck), None)
    if selected is None and profiles:
        selected = profiles[0]

    suggestions = suggested_products_for_customer(selected, limit=12) if selected else []
    charts = customer_intelligence_charts(profiles)

    return templates.TemplateResponse(
        "clientes_inteligentes.html",
        {
            "request": request,
            "active": "clientes_inteligentes",
            "profiles": profiles,
            "selected": selected,
            "suggestions": suggestions,
            "charts": charts,
            "q": q,
        },
    )


@app.get("/gestao", response_class=HTMLResponse)
def gestao_page(request: Request) -> Response:
    with get_db() as con:
        customers = con.execute("SELECT * FROM customers ORDER BY id DESC LIMIT 80").fetchall()
        reservations = con.execute(
            """
            SELECT r.*, p.code, p.title, p.image_filename, COALESCE(c.name, r.customer_name) AS customer_display
            FROM reservations r
            JOIN products p ON p.id=r.product_id
            LEFT JOIN customers c ON c.id=r.customer_id
            ORDER BY r.id DESC LIMIT 80
            """
        ).fetchall()
        wishes = con.execute("SELECT w.*, c.name AS customer_display FROM wishlists w LEFT JOIN customers c ON c.id=w.customer_id ORDER BY w.id DESC LIMIT 80").fetchall()
        expenses = con.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 60").fetchall()
        batches = con.execute("SELECT b.*, s.name AS supplier_name FROM product_batches b LEFT JOIN suppliers s ON s.id=b.supplier_id ORDER BY b.id DESC LIMIT 60").fetchall()
        suppliers = con.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
        users = con.execute("SELECT * FROM app_users ORDER BY id DESC LIMIT 30").fetchall()
        campaigns = con.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT 50").fetchall()
        returns = con.execute("SELECT * FROM returns_exchanges ORDER BY id DESC LIMIT 50").fetchall()
        products = con.execute("SELECT * FROM products WHERE status='disponivel' ORDER BY id DESC LIMIT 120").fetchall()
    return templates.TemplateResponse(
        "gestao.html",
        {
            "request": request,
            "active": "gestao",
            "customers": customers,
            "customer_rank": customer_summary_rows(),
            "reservations": reservations,
            "wishes": wishes,
            "wish_matches": wishlist_matches(),
            "expenses": expenses,
            "finance": financial_snapshot(30),
            "batches": batches,
            "suppliers": suppliers,
            "users": users,
            "campaigns": campaigns,
            "returns": returns,
            "products": products,
            "vitrine": smart_vitrine_rows(),
        },
    )


@app.post("/gestao/customers")
def gestao_create_customer(
    name: str = Form(...),
    phone: str = Form(""),
    instagram: str = Form(""),
    email: str = Form(""),
    birthday: str = Form(""),
    measurements: str = Form(""),
    preferences: str = Form(""),
    notes: str = Form(""),
) -> Response:
    with get_db() as con:
        con.execute(
            "INSERT INTO customers(name, phone, instagram, email, birthday, measurements, preferences, notes, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (name, phone, instagram, email, birthday, measurements, preferences, notes, now_iso()),
        )
    return RedirectResponse(url="/gestao#clientes", status_code=303)


@app.post("/gestao/reservations")
def gestao_create_reservation(
    product_id: int = Form(...),
    customer_id: int = Form(0),
    customer_name: str = Form(""),
    expires_at: str = Form(""),
    notes: str = Form(""),
) -> Response:
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Peça não encontrada.")
        con.execute(
            "INSERT INTO reservations(product_id, customer_id, customer_name, expires_at, notes, created_at) VALUES(?,?,?,?,?,?)",
            (product_id, customer_id or None, customer_name, expires_at, notes, now_iso()),
        )
        con.execute("UPDATE products SET status='reservado' WHERE id=? AND status='disponivel'", (product_id,))
        con.execute(
            "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
            (product_id, "reserva", f"Reserva criada até {expires_at or 'sem prazo'}.", now_iso()),
        )
    return RedirectResponse(url="/gestao#reservas", status_code=303)


@app.post("/gestao/reservations/{reservation_id}/close")
def gestao_close_reservation(reservation_id: int, action: str = Form("liberar")) -> Response:
    with get_db() as con:
        row = con.execute("SELECT * FROM reservations WHERE id=?", (reservation_id,)).fetchone()
        if row:
            status = "convertida" if action == "venda" else "cancelada"
            con.execute("UPDATE reservations SET status=? WHERE id=?", (status, reservation_id))
            if action == "liberar":
                con.execute("UPDATE products SET status='disponivel' WHERE id=? AND status='reservado'", (row["product_id"],))
                con.execute(
                    "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                    (row["product_id"], "reserva", "Reserva encerrada. Peça voltou para disponível.", now_iso()),
                )
    return RedirectResponse(url="/gestao#reservas", status_code=303)


@app.post("/gestao/wishlist")
def gestao_create_wishlist(
    customer_id: int = Form(0),
    customer_name: str = Form(""),
    query: str = Form(...),
    size: str = Form(""),
    brand: str = Form(""),
    color: str = Form(""),
    style: str = Form(""),
    notes: str = Form(""),
) -> Response:
    with get_db() as con:
        con.execute(
            "INSERT INTO wishlists(customer_id, customer_name, query, size, brand, color, style, notes, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (customer_id or None, customer_name, query, size, brand, color, style, notes, now_iso()),
        )
    return RedirectResponse(url="/gestao#desejos", status_code=303)


@app.post("/gestao/expenses")
def gestao_create_expense(
    description: str = Form(...),
    category: str = Form(""),
    amount: float = Form(0),
    payment_method: str = Form(""),
) -> Response:
    with get_db() as con:
        con.execute(
            "INSERT INTO expenses(description, category, amount, payment_method, created_at) VALUES(?,?,?,?,?)",
            (description, category, amount, payment_method, now_iso()),
        )
    return RedirectResponse(url="/gestao#financeiro", status_code=303)


@app.post("/gestao/batches")
def gestao_create_batch(
    name: str = Form(...),
    supplier_id: int = Form(0),
    notes: str = Form(""),
) -> Response:
    with get_db() as con:
        con.execute(
            "INSERT INTO product_batches(name, supplier_id, notes, created_at) VALUES(?,?,?,?)",
            (name, supplier_id or None, notes, now_iso()),
        )
    return RedirectResponse(url="/gestao#lotes", status_code=303)


@app.post("/gestao/users")
def gestao_create_user(
    name: str = Form(...),
    role: str = Form("atendente"),
    pin: str = Form(""),
) -> Response:
    with get_db() as con:
        con.execute(
            "INSERT INTO app_users(name, role, pin, created_at) VALUES(?,?,?,?)",
            (name, role, pin, now_iso()),
        )
    return RedirectResponse(url="/gestao#usuarios", status_code=303)


@app.post("/gestao/campaigns")
def gestao_create_campaign(
    name: str = Form(...),
    channel: str = Form("Instagram/WhatsApp"),
    notes: str = Form(""),
) -> Response:
    with get_db() as con:
        con.execute(
            "INSERT INTO campaigns(name, channel, notes, created_at) VALUES(?,?,?,?)",
            (name, channel, notes, now_iso()),
        )
    return RedirectResponse(url="/gestao#campanhas", status_code=303)


@app.post("/gestao/returns")
def gestao_create_return(
    customer_name: str = Form(""),
    sale_id: int = Form(0),
    product_id: int = Form(0),
    reason: str = Form(""),
    action: str = Form("troca"),
) -> Response:
    with get_db() as con:
        con.execute(
            "INSERT INTO returns_exchanges(customer_name, sale_id, product_id, reason, action, created_at) VALUES(?,?,?,?,?,?)",
            (customer_name, sale_id or None, product_id or None, reason, action, now_iso()),
        )
        if product_id and action in {"devolucao", "troca"}:
            con.execute("UPDATE products SET status='disponivel', sold_at=NULL WHERE id=?", (product_id,))
            con.execute(
                "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                (product_id, "troca", f"Registro de {action}: {reason}", now_iso()),
            )
    return RedirectResponse(url="/gestao#trocas", status_code=303)


@app.post("/gestao/backup")
def gestao_backup() -> Response:
    filename = create_backup_zip()
    return RedirectResponse(url=f"/backups/{filename}", status_code=303)


@app.get("/backups/{filename}")
def download_backup(filename: str) -> FileResponse:
    safe = Path(filename).name
    path = BACKUP_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup não encontrado.")
    return FileResponse(str(path), filename=safe, media_type="application/zip")


@app.get("/api/wishlist-matches")
def api_wishlist_matches() -> JSONResponse:
    return JSONResponse({"ok": True, "matches": wishlist_matches()})




def audit(action: str, entity: str = "", entity_id: Any = "", details: str = "", user_name: str = "Sistema") -> None:
    try:
        with get_db() as con:
            con.execute(
                "INSERT INTO audit_logs(user_name, action, entity, entity_id, details, created_at) VALUES(?,?,?,?,?,?)",
                (user_name, action, entity, str(entity_id or ""), details, now_iso()),
            )
    except Exception:
        pass


def get_store_settings() -> dict[str, Any]:
    with get_db() as con:
        row = con.execute("SELECT * FROM store_settings WHERE id=1").fetchone()
    return dict(row) if row else {}


def current_cash_session() -> sqlite3.Row | None:
    with get_db() as con:
        return con.execute("SELECT * FROM cash_sessions WHERE status='aberto' ORDER BY id DESC LIMIT 1").fetchone()


def professional_summary() -> dict[str, Any]:
    with get_db() as con:
        settings = con.execute("SELECT * FROM store_settings WHERE id=1").fetchone()
        open_session = con.execute("SELECT * FROM cash_sessions WHERE status='aberto' ORDER BY id DESC LIMIT 1").fetchone()
        last_backup = None
        backup_files = sorted(BACKUP_DIR.glob("backup-brechorisee-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if backup_files:
            last_backup = {"name": backup_files[0].name, "created_at": datetime.fromtimestamp(backup_files[0].stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")}

        sales_today = con.execute("SELECT COUNT(*) AS qty, COALESCE(SUM(total),0) AS total FROM sales WHERE date(created_at)=date('now','localtime')").fetchone()
        expenses_month = con.execute("SELECT COALESCE(SUM(amount),0) AS total FROM expenses WHERE created_at >= date('now','start of month')").fetchone()
        low_attention = con.execute("SELECT COUNT(*) FROM products WHERE status='disponivel' AND julianday('now') - julianday(created_at) >= 90").fetchone()[0]
        reservations_due = con.execute("SELECT COUNT(*) FROM reservations WHERE status='ativa' AND expires_at IS NOT NULL AND datetime(expires_at) <= datetime('now','+24 hours')").fetchone()[0]
        users = con.execute("SELECT * FROM app_users ORDER BY active DESC, role, name").fetchall()
        audit_rows = con.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 40").fetchall()
        cash_rows = con.execute("SELECT * FROM cash_sessions ORDER BY id DESC LIMIT 20").fetchall()
        movements = con.execute("SELECT * FROM cash_movements ORDER BY id DESC LIMIT 30").fetchall()
        top_exports = [
            {"title": "Estoque CSV", "url": "/export/stock.csv"},
            {"title": "Vendas CSV", "url": "/export/sales.csv"},
            {"title": "Clientes CSV", "url": "/export/customers.csv"},
            {"title": "Fornecedoras CSV", "url": "/export/suppliers.csv"},
            {"title": "Repasses CSV", "url": "/export/settlements.csv"},
            {"title": "Caixa CSV", "url": "/export/cash.csv"},
        ]
    return {
        "settings": dict(settings) if settings else {},
        "open_session": open_session,
        "last_backup": last_backup,
        "sales_today": dict(sales_today),
        "expenses_month": float(expenses_month["total"] or 0),
        "low_attention": low_attention,
        "reservations_due": reservations_due,
        "users": users,
        "audit_rows": audit_rows,
        "cash_rows": cash_rows,
        "movements": movements,
        "exports": top_exports,
        "backup_files": [p.name for p in backup_files[:8]],
    }


def csv_response(filename: str, rows: list[sqlite3.Row], headers: list[str]) -> Response:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row[h] if h in row.keys() else "" for h in headers])
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/profissional", response_class=HTMLResponse)
def professional_page(request: Request) -> Response:
    return templates.TemplateResponse(
        "professional.html",
        {"request": request, "active": "professional", "summary": professional_summary()},
    )


@app.post("/profissional/settings")
def professional_settings(
    store_name: str = Form("BRECHORISEE"),
    whatsapp: str = Form(""),
    instagram: str = Form(""),
    exchange_policy: str = Form(""),
    default_reservation_hours: int = Form(24),
    card_fee_percent: float = Form(0),
    desired_margin_percent: float = Form(50),
) -> Response:
    with get_db() as con:
        con.execute(
            """
            INSERT INTO store_settings(id, store_name, whatsapp, instagram, exchange_policy, default_reservation_hours,
                                       card_fee_percent, desired_margin_percent, created_at, updated_at)
            VALUES(1,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              store_name=excluded.store_name,
              whatsapp=excluded.whatsapp,
              instagram=excluded.instagram,
              exchange_policy=excluded.exchange_policy,
              default_reservation_hours=excluded.default_reservation_hours,
              card_fee_percent=excluded.card_fee_percent,
              desired_margin_percent=excluded.desired_margin_percent,
              updated_at=excluded.updated_at
            """,
            (store_name, whatsapp, instagram, exchange_policy, default_reservation_hours, card_fee_percent, desired_margin_percent, now_iso(), now_iso()),
        )
    audit("configuracao", "store_settings", 1, "Configurações profissionais atualizadas.")
    return RedirectResponse(url="/profissional", status_code=303)


@app.post("/profissional/users")
def professional_user(name: str = Form(...), role: str = Form("atendente"), pin: str = Form("")) -> Response:
    with get_db() as con:
        con.execute(
            "INSERT INTO app_users(name, role, pin, active, created_at) VALUES(?,?,?,?,?)",
            (name, role, pin, 1, now_iso()),
        )
    audit("usuario_criado", "app_users", name, f"Perfil: {role}")
    return RedirectResponse(url="/profissional", status_code=303)


@app.post("/profissional/cash/open")
def professional_cash_open(opened_by: str = Form("Administradora"), opening_amount: float = Form(0), notes: str = Form("")) -> Response:
    with get_db() as con:
        existing = con.execute("SELECT id FROM cash_sessions WHERE status='aberto' ORDER BY id DESC LIMIT 1").fetchone()
        if existing:
            return RedirectResponse(url="/profissional?msg=caixa-ja-aberto", status_code=303)
        cur = con.execute(
            "INSERT INTO cash_sessions(opened_by, opening_amount, status, notes, opened_at) VALUES(?,?,?,?,?)",
            (opened_by, opening_amount, "aberto", notes, now_iso()),
        )
        con.execute(
            "INSERT INTO cash_movements(session_id, movement_type, description, amount, payment_method, created_at) VALUES(?,?,?,?,?,?)",
            (cur.lastrowid, "abertura", "Valor inicial do caixa", opening_amount, "Dinheiro", now_iso()),
        )
    audit("caixa_aberto", "cash_sessions", cur.lastrowid, f"Abertura com {opening_amount}")
    return RedirectResponse(url="/profissional", status_code=303)


@app.post("/profissional/cash/movement")
def professional_cash_movement(movement_type: str = Form("entrada"), description: str = Form(""), amount: float = Form(0), payment_method: str = Form("Dinheiro")) -> Response:
    session = current_cash_session()
    if not session:
        return RedirectResponse(url="/profissional?msg=abra-o-caixa", status_code=303)
    signed_amount = abs(amount) if movement_type == "entrada" else -abs(amount)
    with get_db() as con:
        con.execute(
            "INSERT INTO cash_movements(session_id, movement_type, description, amount, payment_method, created_at) VALUES(?,?,?,?,?,?)",
            (session["id"], movement_type, description, signed_amount, payment_method, now_iso()),
        )
    audit("movimento_caixa", "cash_movements", session["id"], f"{movement_type}: {description} {signed_amount}")
    return RedirectResponse(url="/profissional", status_code=303)


@app.post("/profissional/cash/close")
def professional_cash_close(closing_amount: float = Form(0), notes: str = Form("")) -> Response:
    session = current_cash_session()
    if not session:
        return RedirectResponse(url="/profissional?msg=sem-caixa-aberto", status_code=303)
    with get_db() as con:
        rows = con.execute("SELECT COALESCE(SUM(amount),0) AS total FROM cash_movements WHERE session_id=?", (session["id"],)).fetchone()
        expected = float(rows["total"] or 0)
        con.execute(
            "UPDATE cash_sessions SET closing_amount=?, expected_amount=?, status='fechado', notes=COALESCE(notes,'') || ?, closed_at=? WHERE id=?",
            (closing_amount, expected, f"\nFechamento: {notes}", now_iso(), session["id"]),
        )
    audit("caixa_fechado", "cash_sessions", session["id"], f"Esperado {expected}; real {closing_amount}")
    return RedirectResponse(url="/profissional", status_code=303)


@app.post("/profissional/expense")
def professional_expense(description: str = Form(...), category: str = Form("Geral"), amount: float = Form(...), payment_method: str = Form("Dinheiro")) -> Response:
    with get_db() as con:
        con.execute(
            "INSERT INTO expenses(description, category, amount, payment_method, created_at) VALUES(?,?,?,?,?)",
            (description, category, amount, payment_method, now_iso()),
        )
    audit("despesa", "expenses", description, f"{category}: {amount}")
    return RedirectResponse(url="/profissional", status_code=303)


@app.post("/profissional/maintenance")
def professional_maintenance() -> Response:
    with get_db() as con:
        con.execute("VACUUM")
        con.execute("ANALYZE")
        con.execute(
            "INSERT INTO maintenance_logs(action, result, created_at) VALUES(?,?,?)",
            ("otimizar_banco", "Banco otimizado com VACUUM e ANALYZE.", now_iso()),
        )
    audit("manutencao", "database", "", "Banco otimizado.")
    return RedirectResponse(url="/profissional", status_code=303)


@app.post("/profissional/backup")
def professional_backup() -> Response:
    filename = create_backup_zip()
    audit("backup", "backup", filename, "Backup profissional gerado.")
    return RedirectResponse(url=f"/backups/{filename}", status_code=303)


@app.get("/export/{kind}.csv")
def export_csv(kind: str) -> Response:
    with get_db() as con:
        if kind == "stock":
            headers = ["code", "title", "category", "garment_type", "size", "brand", "color", "status", "cost_price", "sale_price", "created_at", "sold_at"]
            rows = con.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
            return csv_response("brechorisee-estoque.csv", rows, headers)
        if kind == "sales":
            headers = ["sale_code", "customer", "payment_method", "discount", "total", "paid", "change_value", "created_at"]
            rows = con.execute("SELECT * FROM sales ORDER BY id DESC").fetchall()
            return csv_response("brechorisee-vendas.csv", rows, headers)
        if kind == "customers":
            headers = ["name", "phone", "instagram", "email", "birthday", "measurements", "preferences", "notes", "created_at"]
            rows = con.execute("SELECT * FROM customers ORDER BY name").fetchall()
            return csv_response("brechorisee-clientes.csv", rows, headers)
        if kind == "suppliers":
            headers = ["name", "phone", "email", "instagram", "notes", "created_at"]
            rows = con.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
            return csv_response("brechorisee-fornecedoras.csv", rows, headers)
        if kind == "settlements":
            headers = ["supplier_id", "description", "amount", "status", "paid_at", "created_at"]
            rows = con.execute("SELECT * FROM supplier_settlements ORDER BY id DESC").fetchall()
            return csv_response("brechorisee-repasses.csv", rows, headers)
        if kind == "cash":
            headers = ["id", "opened_by", "opening_amount", "closing_amount", "expected_amount", "status", "opened_at", "closed_at", "notes"]
            rows = con.execute("SELECT * FROM cash_sessions ORDER BY id DESC").fetchall()
            return csv_response("brechorisee-caixa.csv", rows, headers)
    raise HTTPException(status_code=404, detail="Exportação não encontrada.")





@app.get("/deliveries", response_class=HTMLResponse)
def deliveries_page(request: Request, status: str = "todos", q: str = "") -> Response:
    where: list[str] = []
    params: list[Any] = []
    if status and status != "todos":
        where.append("d.status = ?")
        params.append(status)
    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(d.customer_name LIKE ? OR d.phone LIKE ? OR d.address LIKE ? OR d.city LIKE ? OR s.sale_code LIKE ?)")
        params.extend([like, like, like, like, like])

    sql = """
        SELECT d.*, s.sale_code, s.total, s.created_at AS sale_created_at
        FROM deliveries d
        JOIN sales s ON s.id = d.sale_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CASE d.status WHEN 'pendente' THEN 0 WHEN 'separado' THEN 1 WHEN 'rota' THEN 2 WHEN 'cliente_ausente' THEN 3 WHEN 'entregue' THEN 4 ELSE 5 END, COALESCE(d.scheduled_at, d.created_at) DESC"

    with get_db() as con:
        delivery_rows = con.execute(sql, params).fetchall()
        deliveries = [hydrate_delivery(row, con) for row in delivery_rows]
        recent_sales = con.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 30").fetchall()

    return templates.TemplateResponse(
        "deliveries.html",
        {
            "request": request,
            "deliveries": deliveries,
            "recent_sales": recent_sales,
            "summary": deliveries_summary_payload(),
            "status": status,
            "q": q,
            "active": "deliveries",
        },
    )


@app.post("/deliveries/create")
def create_delivery(
    sale_id: int = Form(...),
    customer_name: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    scheduled_at: str = Form(""),
    route_notes: str = Form(""),
    delivery_lat: str = Form(""),
    delivery_lng: str = Form(""),
    delivery_maps_url: str = Form(""),
    delivery_eta_minutes: int = Form(35),
) -> Response:
    with get_db() as con:
        sale = con.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if not sale:
            raise HTTPException(status_code=404, detail="Venda não encontrada.")

        existing = con.execute("SELECT id FROM deliveries WHERE sale_id=? ORDER BY id DESC LIMIT 1", (sale_id,)).fetchone()
        if existing:
            delivery_id = existing["id"]
            con.execute(
                """
                UPDATE deliveries
                SET customer_name=?, phone=?, address=?, city=?, scheduled_at=?, route_notes=?,
                    delivery_lat=?, delivery_lng=?, delivery_maps_url=?, delivery_eta_minutes=?, tracking_updated_at=?, updated_at=?
                WHERE id=?
                """,
                (
                    customer_name or sale["customer"],
                    phone,
                    address,
                    city,
                    scheduled_at,
                    route_notes,
                    delivery_lat or None,
                    delivery_lng or None,
                    build_google_maps_url(" ".join([address or "", city or ""]).strip(), delivery_lat, delivery_lng, delivery_maps_url),
                    max(5, min(180, int(delivery_eta_minutes or 35))),
                    now_iso(),
                    now_iso(),
                    delivery_id,
                ),
            )
        else:
            cur = con.execute(
                """
                INSERT INTO deliveries(sale_id, customer_name, phone, address, city, scheduled_at, route_notes,
                    delivery_lat, delivery_lng, delivery_maps_url, delivery_eta_minutes, tracking_updated_at, status, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sale_id,
                    customer_name or sale["customer"],
                    phone,
                    address,
                    city,
                    scheduled_at,
                    route_notes,
                    delivery_lat or None,
                    delivery_lng or None,
                    build_google_maps_url(" ".join([address or "", city or ""]).strip(), delivery_lat, delivery_lng, delivery_maps_url),
                    max(5, min(180, int(delivery_eta_minutes or 35))),
                    now_iso(),
                    "pendente",
                    now_iso(),
                    now_iso(),
                ),
            )
            delivery_id = cur.lastrowid
            items = delivery_items_for_sale(con, sale_id)
            for product in items:
                con.execute(
                    "INSERT INTO delivery_items(delivery_id, product_id, status, created_at) VALUES(?,?,?,?)",
                    (delivery_id, product["id"], "pendente", now_iso()),
                )
        con.execute(
            "INSERT INTO audit_logs(user_name, action, entity, entity_id, details, created_at) VALUES(?,?,?,?,?,?)",
            ("sistema", "entrega_criada", "delivery", str(delivery_id), f"Entrega vinculada à venda {sale['sale_code']}", now_iso()),
        )
    return RedirectResponse(url="/deliveries", status_code=303)


@app.post("/deliveries/{delivery_id}/status")
def update_delivery_status(
    delivery_id: int,
    status: str = Form(...),
    route_notes: str = Form(""),
    delivery_eta_minutes: int = Form(35),
) -> Response:
    allowed = {"pendente", "separado", "rota", "cliente_ausente", "entregue", "cancelada"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Status inválido.")
    delivered_at = now_iso() if status == "entregue" else None
    with get_db() as con:
        delivery = con.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
        if not delivery:
            raise HTTPException(status_code=404, detail="Entrega não encontrada.")
        eta_minutes = max(5, min(180, int(delivery_eta_minutes or delivery["delivery_eta_minutes"] or 35))) if "delivery_eta_minutes" in delivery.keys() else max(5, min(180, int(delivery_eta_minutes or 35)))
        start_at = now_iso() if status == "rota" and not delivery["delivery_started_at"] else delivery["delivery_started_at"] if "delivery_started_at" in delivery.keys() else None
        if status == "entregue":
            con.execute(
                "UPDATE deliveries SET status=?, delivered_at=?, route_notes=COALESCE(NULLIF(?,''), route_notes), delivery_eta_minutes=?, tracking_updated_at=?, updated_at=? WHERE id=?",
                (status, delivered_at, route_notes, eta_minutes, now_iso(), now_iso(), delivery_id),
            )
            con.execute(
                "UPDATE delivery_items SET status='entregue', delivered_at=? WHERE delivery_id=?",
                (delivered_at, delivery_id),
            )
        else:
            con.execute(
                "UPDATE deliveries SET status=?, delivered_at=NULL, route_notes=COALESCE(NULLIF(?,''), route_notes), delivery_eta_minutes=?, delivery_started_at=?, tracking_updated_at=?, updated_at=? WHERE id=?",
                (status, route_notes, eta_minutes, start_at, now_iso(), now_iso(), delivery_id),
            )
            con.execute(
                "UPDATE delivery_items SET status=? WHERE delivery_id=?",
                (status, delivery_id),
            )
        con.execute(
            "INSERT INTO audit_logs(user_name, action, entity, entity_id, details, created_at) VALUES(?,?,?,?,?,?)",
            ("sistema", "entrega_status", "delivery", str(delivery_id), f"Status alterado para {delivery_status_label(status)}", now_iso()),
        )
    return RedirectResponse(url="/deliveries", status_code=303)


@app.post("/deliveries/{delivery_id}/tracking")
def update_delivery_tracking(
    delivery_id: int,
    delivery_eta_minutes: int = Form(35),
    courier_lat: str = Form(""),
    courier_lng: str = Form(""),
    courier_maps_url: str = Form(""),
    route_notes: str = Form(""),
) -> Response:
    """Atualiza a aproximação exibida para a cliente e para o admin."""
    with get_db() as con:
        delivery = con.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
        if not delivery:
            raise HTTPException(status_code=404, detail="Entrega não encontrada.")
        eta_minutes = max(5, min(180, int(delivery_eta_minutes or delivery["delivery_eta_minutes"] or 35)))
        con.execute(
            """
            UPDATE deliveries
            SET status=CASE WHEN status IN ('pendente','separado') THEN 'rota' ELSE status END,
                delivery_started_at=COALESCE(delivery_started_at, ?),
                delivery_eta_minutes=?,
                courier_lat=?,
                courier_lng=?,
                courier_maps_url=?,
                route_notes=COALESCE(NULLIF(?,''), route_notes),
                tracking_updated_at=?,
                updated_at=?
            WHERE id=?
            """,
            (
                now_iso(),
                eta_minutes,
                courier_lat or None,
                courier_lng or None,
                build_google_maps_url("", courier_lat, courier_lng, courier_maps_url),
                route_notes,
                now_iso(),
                now_iso(),
                delivery_id,
            ),
        )
    return RedirectResponse(url="/deliveries?status=rota", status_code=303)


@app.post("/deliveries/{delivery_id}/item/{product_id}/status")
def update_delivery_item_status(delivery_id: int, product_id: int, status: str = Form(...)) -> Response:
    allowed = {"pendente", "separado", "rota", "cliente_ausente", "entregue", "cancelada"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Status inválido.")
    delivered_at = now_iso() if status == "entregue" else None
    with get_db() as con:
        con.execute(
            "UPDATE delivery_items SET status=?, delivered_at=? WHERE delivery_id=? AND product_id=?",
            (status, delivered_at, delivery_id, product_id),
        )
        counts = con.execute(
            "SELECT status, COUNT(*) AS qty FROM delivery_items WHERE delivery_id=? GROUP BY status",
            (delivery_id,),
        ).fetchall()
        count_map = {r["status"]: r["qty"] for r in counts}
        total = sum(count_map.values())
        parent_status = "entregue" if total and count_map.get("entregue", 0) == total else ("cliente_ausente" if count_map.get("cliente_ausente", 0) else ("rota" if count_map.get("rota", 0) else "pendente"))
        con.execute(
            "UPDATE deliveries SET status=?, delivered_at=CASE WHEN ?='entregue' THEN COALESCE(delivered_at, ?) ELSE delivered_at END, updated_at=? WHERE id=?",
            (parent_status, parent_status, now_iso(), now_iso(), delivery_id),
        )
    return RedirectResponse(url="/deliveries", status_code=303)


@app.get("/api/deliveries")
def api_deliveries(status: str = "todos") -> JSONResponse:
    with get_db() as con:
        params: list[Any] = []
        sql = """
            SELECT d.*, s.sale_code, s.total
            FROM deliveries d JOIN sales s ON s.id=d.sale_id
        """
        if status != "todos":
            sql += " WHERE d.status=?"
            params.append(status)
        sql += " ORDER BY d.id DESC LIMIT 100"
        rows = con.execute(sql, params).fetchall()
        payload = []
        for row in rows:
            d = dict(row)
            d.update(delivery_maps_links(d.get("address") or "", d.get("city") or ""))
            if d.get("delivery_maps_url"):
                d["google_maps"] = d.get("delivery_maps_url")
            d["tracking"] = delivery_tracking_payload(d)
            payload.append(d)
    return JSONResponse({"ok": True, "deliveries": payload, "summary": deliveries_summary_payload()})




@app.get("/whatsapp-vendas", response_class=HTMLResponse)
def whatsapp_sales_page(request: Request, q: str = "", status: str = "ativos") -> Response:
    products = search_products_rows(q=q, status="disponivel", limit=40) if q.strip() else search_products_rows(q="", status="disponivel", limit=24)
    with get_db() as con:
        customers = con.execute("SELECT * FROM customers ORDER BY name LIMIT 200").fetchall()
        where = ""
        params: list[Any] = []
        if status and status != "todos":
            if status == "ativos":
                where = "WHERE status NOT IN ('pago','entregue','cancelado')"
            else:
                where = "WHERE status=?"
                params.append(status)
        orders = con.execute(
            f"""
            SELECT wo.*,
                   COUNT(woi.id) AS items_count
            FROM whatsapp_orders wo
            LEFT JOIN whatsapp_order_items woi ON woi.order_id = wo.id
            {where}
            GROUP BY wo.id
            ORDER BY wo.id DESC
            LIMIT 80
            """,
            params,
        ).fetchall()
    return templates.TemplateResponse(
        "whatsapp_sales.html",
        {
            "request": request,
            "products": products,
            "customers": customers,
            "orders": orders,
            "q": q,
            "status": status,
            "active": "whatsapp_sales",
            "statuses": WHATSAPP_ORDER_STATUSES,
        },
    )


@app.post("/whatsapp-vendas/create")
def create_whatsapp_order(
    request: Request,
    customer_name: str = Form(""),
    phone: str = Form(""),
    delivery_type: str = Form("retirada"),
    pickup_location: str = Form(""),
    address: str = Form(""),
    payment_method: str = Form("Pix"),
    payment_link: str = Form(""),
    pix_key: str = Form(""),
    pix_copy_paste: str = Form(""),
    reservation_hours: int = Form(24),
    notes: str = Form(""),
    product_ids: list[int] | None = Form(None),
) -> Response:
    ids = [int(x) for x in (product_ids or [])]
    if not ids:
        raise HTTPException(status_code=400, detail="Selecione pelo menos uma peça.")
    delivery_type = delivery_type if delivery_type in {"retirada", "entrega"} else "retirada"
    reservation_hours = max(1, min(int(reservation_hours or 24), 168))
    expires_at = (datetime.now() + timedelta(hours=reservation_hours)).strftime("%Y-%m-%d %H:%M:%S")

    placeholders = ",".join("?" for _ in ids)
    with get_db() as con:
        products = con.execute(f"SELECT * FROM products WHERE id IN ({placeholders})", ids).fetchall()
        available = [p for p in products if p["status"] == "disponivel"]
        if len(available) != len(ids):
            raise HTTPException(status_code=400, detail="Uma ou mais peças não estão disponíveis.")
        total = sum(float(p["sale_price"] or 0) for p in products)
        cur = con.execute(
            """
            INSERT INTO whatsapp_orders
            (customer_name, phone, delivery_type, pickup_location, address, payment_method, payment_link,
             pix_key, pix_copy_paste, status, reservation_expires_at, notes, total, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                customer_name,
                phone,
                delivery_type,
                pickup_location,
                address,
                payment_method,
                payment_link,
                pix_key,
                pix_copy_paste,
                "aguardando_pagamento",
                expires_at,
                notes,
                total,
                now_iso(),
                now_iso(),
            ),
        )
        order_id = cur.lastrowid
        for p in products:
            con.execute(
                "INSERT INTO whatsapp_order_items(order_id, product_id, price, created_at) VALUES(?,?,?,?)",
                (order_id, p["id"], p["sale_price"], now_iso()),
            )
            con.execute("UPDATE products SET status='reservado' WHERE id=?", (p["id"],))
            ensure_product_reservation_record(
                con,
                int(p["id"]),
                customer_name=customer_name,
                customer_phone=phone,
                notes=f"Reservada para pedido WhatsApp #{order_id}.",
                expires_at=expires_at,
            )
            con.execute(
                "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                (p["id"], "pedido_whatsapp", f"Reservada para pedido WhatsApp #{order_id} / {customer_name or 'cliente'}.", now_iso()),
            )
        if TELEGRAM_NOTIFY_ORDERS:
            try:
                order_row = con.execute("SELECT * FROM whatsapp_orders WHERE id=?", (int(order_id),)).fetchone()
                item_rows = con.execute(
                    """
                    SELECT woi.*, p.code, p.title
                    FROM whatsapp_order_items woi
                    JOIN products p ON p.id=woi.product_id
                    WHERE woi.order_id=?
                    """,
                    (int(order_id),),
                ).fetchall()
                telegram_send_admin_message(con, telegram_order_summary(order_row, item_rows), related_type="whatsapp_order", related_id=int(order_id))
            except Exception as exc:
                logger.warning("Falha ao notificar pedido WhatsApp no Telegram: %s", exc)
    return RedirectResponse(url=f"/whatsapp-vendas/{order_id}", status_code=303)


@app.get("/whatsapp-vendas/{order_id}", response_class=HTMLResponse)
def whatsapp_order_detail(request: Request, order_id: int) -> Response:
    order, items = load_whatsapp_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido WhatsApp não encontrado.")
    message = build_whatsapp_order_message(request, order, items)
    whatsapp_phone = normalize_phone_for_whatsapp(order["phone"] or "")
    whatsapp_url = f"https://wa.me/{whatsapp_phone}?text={quote_plus(message)}" if whatsapp_phone else f"https://wa.me/?text={quote_plus(message)}"
    return templates.TemplateResponse(
        "whatsapp_order_detail.html",
        {
            "request": request,
            "order": order,
            "items": items,
            "message": message,
            "whatsapp_url": whatsapp_url,
            "maps_url": maps_search_url(order["address"] if order["delivery_type"] == "entrega" else order["pickup_location"]),
            "active": "whatsapp_sales",
            "statuses": WHATSAPP_ORDER_STATUSES,
        },
    )


@app.post("/whatsapp-vendas/{order_id}/status")
def update_whatsapp_order_status(order_id: int, status: str = Form(...)) -> Response:
    if status not in WHATSAPP_ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Status inválido.")
    with get_db() as con:
        order = con.execute("SELECT * FROM whatsapp_orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        con.execute("UPDATE whatsapp_orders SET status=?, updated_at=? WHERE id=?", (status, now_iso(), order_id))
    return RedirectResponse(url=f"/whatsapp-vendas/{order_id}", status_code=303)


@app.post("/whatsapp-vendas/{order_id}/confirm-payment")
def confirm_whatsapp_payment(order_id: int) -> Response:
    ok, message, sale_id = whatsapp_order_to_sale(order_id)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return RedirectResponse(url=f"/sales/{sale_id}" if sale_id else f"/whatsapp-vendas/{order_id}", status_code=303)


@app.post("/whatsapp-vendas/{order_id}/cancel")
def cancel_whatsapp_order(order_id: int) -> Response:
    with get_db() as con:
        order = con.execute("SELECT * FROM whatsapp_orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        if order["sale_id"]:
            raise HTTPException(status_code=400, detail="Pedido já virou venda. Use troca/devolução se necessário.")
        items = con.execute("SELECT * FROM whatsapp_order_items WHERE order_id=?", (order_id,)).fetchall()
        for item in items:
            con.execute("UPDATE products SET status='disponivel' WHERE id=? AND status='reservado'", (item["product_id"],))
            con.execute(
                "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                (item["product_id"], "cancelamento_whatsapp", f"Pedido WhatsApp #{order_id} cancelado. Peça voltou ao estoque disponível.", now_iso()),
            )
        con.execute("UPDATE whatsapp_orders SET status='cancelado', updated_at=? WHERE id=?", (now_iso(), order_id))
    return RedirectResponse(url=f"/whatsapp-vendas/{order_id}", status_code=303)






def notification_frequency_hours(frequency: str) -> int:
    frequency = (frequency or "moderado").strip().lower()
    return {
        "imediato": 0,
        "moderado": 12,
        "diario": 24,
        "semanal": 24 * 7,
    }.get(frequency, 12)



def re_split_words(value: str) -> list[str]:
    cleaned = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower()
    for ch in ",.;:/\\|+-_()[]{}":
        cleaned = cleaned.replace(ch, " ")
    return [w.strip() for w in cleaned.split() if w.strip()]


def _split_tags(value: Any) -> list[str]:
    """Normaliza tags de estilo, cores, marcas e características para comparação."""
    raw = str(value or "").replace(";", ",").replace("/", ",").replace("|", ",")
    parts: list[str] = []
    for piece in raw.split(","):
        words = re_split_words(piece)
        if piece.strip() and len(words) > 1:
            parts.append(" ".join(words))
        parts.extend(words)
    # remove palavras muito genéricas
    stop = {"peca", "roupa", "brecho", "moda", "circular", "com", "sem", "para", "tam", "tamanho"}
    seen: set[str] = set()
    result: list[str] = []
    for p in parts:
        if len(p) < 2 or p in stop or p in seen:
            continue
        seen.add(p)
        result.append(p)
    return result


def customer_ai_profile(con: sqlite3.Connection, account: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """Monta perfil da cliente a partir do cadastro, preferências, compras e interesses."""
    a = row_to_dict(account)
    customer_id = a.get("customer_id")
    phone = str(a.get("phone") or "").strip()
    name = str(a.get("name") or "").strip()

    profile: dict[str, Any] = {
        "name": name,
        "phone": phone,
        "tags": set(),
        "types": {},
        "sizes": {},
        "colors": {},
        "brands": {},
        "styles": {},
        "price_values": [],
        "total_spent": 0.0,
        "items_count": 0,
        "last_purchase": None,
        "preferred_payment": "",
        "source_notes": [],
    }

    if customer_id:
        row = con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        if row:
            for field in ("preferences", "measurements", "notes"):
                for tag in _split_tags(row[field]):
                    profile["tags"].add(tag)
            if row["preferences"]:
                profile["source_notes"].append("preferências cadastradas")

    # Histórico de vendas: por customer igual ao nome ou telefone quando existir.
    params: list[Any] = []
    clauses: list[str] = []
    if name:
        clauses.append("LOWER(COALESCE(s.customer,'')) LIKE LOWER(?)")
        params.append(f"%{name}%")
    if phone:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits:
            clauses.append("REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(s.customer,''),' ',''),'-',''),'(',''),')','') LIKE ?")
            params.append(f"%{digits[-8:]}%")
    if clauses:
        rows = con.execute(
            f"""
            SELECT p.*, s.payment_method, s.created_at AS sale_created_at, si.price AS item_price
            FROM sales s
            JOIN sale_items si ON si.sale_id = s.id
            JOIN products p ON p.id = si.product_id
            WHERE {" OR ".join(clauses)}
            ORDER BY s.id DESC
            LIMIT 120
            """,
            params,
        ).fetchall()
    else:
        rows = []

    payment_counts: dict[str, int] = {}
    for p in rows:
        profile["items_count"] += 1
        price = safe_float(p["item_price"] if "item_price" in p.keys() else p["sale_price"])
        profile["price_values"].append(price)
        profile["total_spent"] += price
        profile["last_purchase"] = profile["last_purchase"] or p["sale_created_at"]
        payment = str(p["payment_method"] or "").strip()
        if payment:
            payment_counts[payment] = payment_counts.get(payment, 0) + 1
        buckets = [
            ("types", p["garment_type"] or p["category"] or p["title"]),
            ("sizes", p["size"]),
            ("colors", p["color"]),
            ("brands", p["brand"]),
            ("styles", p["style_tags"] or p["characteristics"] or p["season"]),
        ]
        for key, raw in buckets:
            for tag in _split_tags(raw):
                profile[key][tag] = profile[key].get(tag, 0) + 1
                profile["tags"].add(tag)
    if rows:
        profile["source_notes"].append("histórico de compras")
    if payment_counts:
        profile["preferred_payment"] = max(payment_counts.items(), key=lambda x: x[1])[0]

    # Wishlist pesa bastante.
    wishlist_rows: list[sqlite3.Row] = []
    if customer_id:
        wishlist_rows = con.execute("SELECT * FROM wishlists WHERE customer_id=? ORDER BY id DESC LIMIT 80", (customer_id,)).fetchall()
    elif name:
        wishlist_rows = con.execute("SELECT * FROM wishlists WHERE LOWER(COALESCE(customer_name,'')) LIKE LOWER(?) ORDER BY id DESC LIMIT 80", (f"%{name}%",)).fetchall()
    for w in wishlist_rows:
        for field in ("query", "size", "brand", "color", "style", "notes"):
            for tag in _split_tags(w[field]):
                profile["tags"].add(tag)
                profile["styles"][tag] = profile["styles"].get(tag, 0) + 2
    if wishlist_rows:
        profile["source_notes"].append("lista de desejos")

    # Interesse em links de peças: entra como sinal leve.
    if customer_id or phone or name:
        # Eventos não têm cliente específico em todas as versões, então usamos apenas quando notas contêm telefone/nome.
        terms = [t for t in [phone, name] if t]
        if terms:
            where = " OR ".join("LOWER(COALESCE(pie.notes,'')) LIKE LOWER(?)" for _ in terms)
            irows = con.execute(
                f"""
                SELECT p.*
                FROM product_interest_events pie
                JOIN products p ON p.id = pie.product_id
                WHERE {where}
                ORDER BY pie.id DESC
                LIMIT 60
                """,
                [f"%{t}%" for t in terms],
            ).fetchall()
            for p in irows:
                for raw in (p["garment_type"], p["size"], p["brand"], p["color"], p["style_tags"], p["characteristics"]):
                    for tag in _split_tags(raw):
                        profile["tags"].add(tag)
                        profile["styles"][tag] = profile["styles"].get(tag, 0) + 1
            if irows:
                profile["source_notes"].append("interesses registrados")

    prices = profile["price_values"]
    profile["avg_price"] = round(sum(prices) / len(prices), 2) if prices else None
    profile["max_comfort_price"] = round((profile["avg_price"] or 0) * 1.35, 2) if prices else None
    profile["tags"] = list(profile["tags"])
    return profile


def ai_product_customer_match(
    product: sqlite3.Row | dict[str, Any],
    account: sqlite3.Row | dict[str, Any],
    con: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Calcula compatibilidade peça x cliente. 0-100."""
    close_con = False
    if con is None:
        con = get_db()
        close_con = True
    try:
        p = row_to_dict(product)
        profile = customer_ai_profile(con, account)

        product_tags = set()
        for field in ("title", "category", "garment_type", "size", "brand", "color", "characteristics", "style_tags", "season", "target_audience"):
            product_tags.update(_split_tags(p.get(field)))

        score = 28.0
        reasons: list[str] = []

        def weighted_hits(bucket: str, label: str, weight: float, max_points: float) -> None:
            nonlocal score
            values = profile.get(bucket) or {}
            hits = [tag for tag in product_tags if tag in values]
            if hits:
                pts = min(max_points, sum(values.get(h, 1) for h in hits) * weight)
                score += pts
                reasons.append(f"{label}: {', '.join(hits[:4])}")

        weighted_hits("types", "tipo que costuma comprar", 8, 22)
        weighted_hits("sizes", "tamanho compatível", 10, 18)
        weighted_hits("colors", "cor preferida", 6, 14)
        weighted_hits("brands", "marca de interesse", 6, 12)
        weighted_hits("styles", "estilo/característica parecida", 5, 18)

        # Preferências cadastradas.
        pref_hits = [tag for tag in product_tags if tag in set(profile.get("tags") or [])]
        if pref_hits:
            score += min(16, len(pref_hits) * 3)
            if not any("prefer" in r for r in reasons):
                reasons.append(f"combina com preferências: {', '.join(pref_hits[:5])}")

        avg_price = profile.get("avg_price")
        product_price = safe_float(p.get("sale_price"))
        if avg_price:
            if product_price <= avg_price * 1.35:
                score += 8
                reasons.append("faixa de preço parecida")
            elif product_price > avg_price * 2:
                score -= 15
                reasons.append("preço acima do padrão de compra")
        else:
            score += 4
            reasons.append("cliente nova: teste com curadoria leve")

        # Se não há dados, manda poucas peças com texto menos incisivo.
        if not profile.get("source_notes"):
            score = min(score, 55)
            reasons.append("perfil ainda em aprendizado")

        # Não recomendar peça indisponível.
        if str(p.get("status") or "") != "disponivel":
            score = 0
            reasons.append("peça indisponível")

        score = max(0, min(100, round(score, 1)))
        if score >= 85:
            label = "alta"
        elif score >= 70:
            label = "boa"
        elif score >= 55:
            label = "moderada"
        else:
            label = "baixa"
        return {
            "score": score,
            "label": label,
            "reasons": reasons[:6],
            "profile": profile,
            "product_tags": sorted(product_tags)[:40],
        }
    finally:
        if close_con:
            con.close()


def personalized_customer_message(product: sqlite3.Row | dict[str, Any], account: sqlite3.Row | dict[str, Any], match: dict[str, Any]) -> str:
    p = row_to_dict(product)
    a = row_to_dict(account)
    name = (a.get("name") or "tudo bem").split()[0]
    reasons = match.get("reasons") or []
    reason_text = reasons[0] if reasons else "achei que combina com seu estilo"
    title = p.get("title") or p.get("garment_type") or "uma peça"
    size = p.get("size") or "único"
    brand = p.get("brand") or "sem marca"
    color = p.get("color") or ""
    score = match.get("score") or 0

    opener = "chegou uma novidade que parece muito com você" if score >= 75 else "separei uma novidade que pode combinar com você"
    return (
        f"Oi, {name}! ✨ {opener}: {title}. "
        f"Motivo: {reason_text}. "
        f"Tamanho: {size}. Marca: {brand}. "
        f"{('Cor: ' + color + '. ') if color else ''}"
        f"Valor: {money(p.get('sale_price'))}. "
        f"Quer que eu reserve para você ver?"
    )


def notification_text_matches_customer(product: sqlite3.Row | dict[str, Any], account: sqlite3.Row | dict[str, Any]) -> bool:
    """Compatibilidade mínima usada por versões antigas. Agora usa IA local."""
    with get_db() as con:
        return ai_product_customer_match(product, account, con=con)["score"] >= 55


def ensure_customer_notification_settings(con: sqlite3.Connection, account_id: int) -> sqlite3.Row:
    row = con.execute("SELECT * FROM customer_notification_settings WHERE customer_account_id=?", (account_id,)).fetchone()
    if not row:
        con.execute(
            "INSERT INTO customer_notification_settings(customer_account_id, enabled, channel_app, channel_whatsapp, frequency, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
            (account_id, 1, 1, 0, "moderado", now_iso(), now_iso()),
        )
        row = con.execute("SELECT * FROM customer_notification_settings WHERE customer_account_id=?", (account_id,)).fetchone()
    return row


def queue_new_product_notifications(con: sqlite3.Connection, product_id: int) -> int:
    """Cria avisos de novidade com IA local.

    Em vez de enviar todas as peças para todas as clientes, calcula compatibilidade
    e cria apenas notificações relevantes. A mensagem fica personalizada.
    """
    product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product or product["status"] != "disponivel":
        return 0

    accounts = con.execute("SELECT * FROM customer_accounts WHERE active=1 ORDER BY id DESC LIMIT 800").fetchall()
    created = 0
    for account in accounts:
        settings = ensure_customer_notification_settings(con, int(account["id"]))
        if int(settings["enabled"] or 0) != 1:
            continue

        match = ai_product_customer_match(product, account, con=con)
        # Cliente recebe só se tiver afinidade. Cliente sem histórico entra só em resumo leve.
        minimum_score = 65
        freq = str(settings["frequency"] or "moderado").lower()
        if freq in {"semanal", "diario"}:
            minimum_score = 58
        if match["score"] < minimum_score:
            continue

        last = parse_dt(settings["last_notified_at"])
        hours = notification_frequency_hours(settings["frequency"])
        if last and hours > 0 and datetime.now() - last < timedelta(hours=hours):
            continue

        already = con.execute(
            "SELECT 1 FROM customer_notifications WHERE customer_account_id=? AND product_id=? AND notification_type='nova_peca'",
            (account["id"], product_id),
        ).fetchone()
        if already:
            continue

        title = f"Novidade para você • {int(match['score'])}%"
        message = personalized_customer_message(product, account, match)
        reason = "; ".join(match.get("reasons") or [])
        channel = "app"
        if int(settings["channel_whatsapp"] or 0) == 1 and match["score"] >= 75:
            channel = "app_whatsapp_sugerido"

        con.execute(
            """
            INSERT INTO customer_notifications
            (customer_account_id, product_id, notification_type, title, message, image_filename, action_url, status, scheduled_at, created_at,
             match_score, ai_reason, message_channel, personalized)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                account["id"], product_id, "nova_peca", title, message,
                product["image_filename"], f"/cliente/peca/{product['code']}", "pendente", now_iso(), now_iso(),
                float(match["score"]), reason, channel, 1
            ),
        )
        con.execute(
            "UPDATE customer_notification_settings SET last_notified_at=?, updated_at=? WHERE customer_account_id=?",
            (now_iso(), now_iso(), account["id"]),
        )
        created += 1
    return created


def queue_live_started_notifications(con: sqlite3.Connection, session: sqlite3.Row | dict[str, Any]) -> int:
    """Cria aviso imediato para todas as clientes ativas quando a live começa."""
    s = row_to_dict(session)
    session_id = int(s.get("id") or 0)
    if session_id <= 0:
        return 0

    source_platform = str(s.get("source_platform") or "brechorisee")
    live_url = "/cliente/live-opcoes" if source_platform == "instagram" else "/cliente/live"
    title = "Live BRECHORISEE no Instagram ✨" if source_platform == "instagram" else "BRECHORISEE ao vivo agora ✨"
    message = (
        "A live começou no Instagram. Toque para escolher assistir no Instagram ou acompanhar pelo BRECHORISEE."
        if source_platform == "instagram"
        else "A live começou! Toque para entrar direto na área de live do app cliente."
    )
    image_filename = s.get("snapshot_filename") or None
    created = 0

    accounts = con.execute("SELECT * FROM customer_accounts WHERE active=1 ORDER BY id DESC LIMIT 5000").fetchall()
    for account in accounts:
        settings = ensure_customer_notification_settings(con, int(account["id"]))
        if int(settings["enabled"] or 0) != 1 or int(settings["channel_app"] or 1) != 1:
            continue

        already = con.execute(
            """
            SELECT 1 FROM customer_notifications
            WHERE customer_account_id=? AND notification_type='live_started' AND live_session_id=?
            """,
            (account["id"], session_id),
        ).fetchone()
        if already:
            continue

        name = (account["name"] or "cliente").split()[0]
        con.execute(
            """
            INSERT INTO customer_notifications
            (customer_account_id, product_id, live_session_id, notification_type, title, message,
             image_filename, action_url, status, scheduled_at, created_at, message_channel, personalized)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                account["id"],
                None,
                session_id,
                "live_started",
                title,
                f"Oi, {name}! " + message,
                image_filename,
                live_url,
                "pendente",
                now_iso(),
                now_iso(),
                "app_live",
                1,
            ),
        )
        created += 1

    return created


def customer_unread_notifications_count(account_id: int) -> int:
    with get_db() as con:
        return int(con.execute(
            "SELECT COUNT(*) FROM customer_notifications WHERE customer_account_id=? AND read_at IS NULL AND scheduled_at <= ?",
            (account_id, now_iso()),
        ).fetchone()[0] or 0)


def customer_notifications_rows(account_id: int, limit: int = 60) -> list[sqlite3.Row]:
    with get_db() as con:
        return con.execute(
            """
            SELECT n.*, p.code AS product_code, p.title AS product_title, p.sale_price, p.status AS product_status
            FROM customer_notifications n
            LEFT JOIN products p ON p.id = n.product_id
            WHERE n.customer_account_id=? AND n.scheduled_at <= ?
            ORDER BY n.id DESC
            LIMIT ?
            """,
            (account_id, now_iso(), limit),
        ).fetchall()



@app.get("/cliente", response_class=HTMLResponse)
def customer_portal_entry(request: Request, next: str = CUSTOMER_HOME_PATH) -> Response:
    account = customer_from_request(request)
    safe_next = customer_safe_next_url(next)
    if account:
        return RedirectResponse(url=safe_next, status_code=303)
    return templates.TemplateResponse(
        "customer_login.html",
        {"request": request, "settings": get_store_settings(), "mode": "login", "error": "", "public_mode": True, "next": safe_next},
    )


@app.get("/cliente/cadastrar", response_class=HTMLResponse)
def customer_register_form(request: Request, next: str = CUSTOMER_HOME_PATH) -> Response:
    prefill = {
        "name": request.query_params.get("name", ""),
        "phone": request.query_params.get("phone", ""),
        "email": request.query_params.get("email", ""),
        "instagram": request.query_params.get("instagram", ""),
        "style_preferences": request.query_params.get("style", ""),
        "app": request.query_params.get("app", ""),
    }
    return templates.TemplateResponse(
        "customer_login.html",
        {"request": request, "settings": get_store_settings(), "mode": "register", "error": "", "public_mode": True, "prefill": prefill, "next": customer_safe_next_url(next)},
    )


@app.post("/cliente/cadastrar")
def customer_register(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(""),
    instagram: str = Form(""),
    style_preferences: str = Form(""),
    password: str = Form(...),
    next: str = Form(CUSTOMER_HOME_PATH),
) -> Response:
    if len((password or "").strip()) < 4:
        return templates.TemplateResponse(
            "customer_login.html",
            {"request": request, "settings": get_store_settings(), "mode": "register", "error": "Use uma senha com pelo menos 4 caracteres.", "public_mode": True},
            status_code=400,
        )
    phone_clean = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not phone_clean:
        return templates.TemplateResponse(
            "customer_login.html",
            {"request": request, "settings": get_store_settings(), "mode": "register", "error": "Informe um WhatsApp válido.", "public_mode": True},
            status_code=400,
        )
    with get_db() as con:
        existing = con.execute("SELECT * FROM customer_accounts WHERE phone=?", (phone_clean,)).fetchone()
        if existing:
            return templates.TemplateResponse(
                "customer_login.html",
                {"request": request, "settings": get_store_settings(), "mode": "reset", "error": "Este WhatsApp já tem acesso. Para criar uma nova senha, confirme seu nome/e-mail e defina a senha abaixo.", "public_mode": True, "prefill": {"name": name, "phone": phone_clean, "email": email}, "next": customer_safe_next_url(next)},
                status_code=400,
            )
        customer_id = find_or_create_customer_for_account(con, name, phone_clean, email)
        con.execute(
            "UPDATE customers SET instagram=COALESCE(NULLIF(?,''), instagram), preferences=COALESCE(NULLIF(?,''), preferences) WHERE id=?",
            (instagram, style_preferences, customer_id),
        )
        cur = con.execute(
            "INSERT INTO customer_accounts(customer_id, name, phone, email, instagram, style_preferences, app_origin, password_hash, created_at, last_login_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (customer_id, name, phone_clean, email, instagram, style_preferences, "android" if request.headers.get("user-agent","").lower().find("brechorisee-android") >= 0 else "web", hash_password(password), now_iso(), now_iso()),
        )
        account_id = int(cur.lastrowid)
    auth_log("cliente", account_id, "cadastro_primeiro_acesso", request)
    safe_next = customer_safe_next_url(next)
    resp = RedirectResponse(url=safe_next, status_code=303)
    set_customer_cookie(resp, account_id, request)
    return resp


@app.post("/cliente/login")
def customer_login(request: Request, phone: str = Form(...), password: str = Form(...), next: str = Form(CUSTOMER_HOME_PATH)) -> Response:
    phone_clean = "".join(ch for ch in str(phone or "") if ch.isdigit())
    with get_db() as con:
        account = con.execute("SELECT * FROM customer_accounts WHERE phone=? AND active=1", (phone_clean,)).fetchone()
        if not account or not verify_password(password, account["password_hash"]):
            return templates.TemplateResponse(
                "customer_login.html",
                {"request": request, "settings": get_store_settings(), "mode": "login", "error": "WhatsApp ou senha inválidos.", "public_mode": True},
                status_code=401,
            )
        con.execute("UPDATE customer_accounts SET last_login_at=? WHERE id=?", (now_iso(), account["id"]))
    auth_log("cliente", int(account["id"]), "login", request)
    safe_next = customer_safe_next_url(next)
    resp = RedirectResponse(url=safe_next, status_code=303)
    set_customer_cookie(resp, int(account["id"]), request)
    return resp


@app.get("/cliente/sair")
def customer_logout(request: Request) -> Response:
    resp = RedirectResponse(url="/cliente", status_code=303)
    resp.delete_cookie(CUSTOMER_COOKIE_NAME)
    return resp



@app.get("/cliente/inicio", response_class=HTMLResponse)
@app.get("/cliente/home", response_class=HTMLResponse)
def customer_home_page(request: Request) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url="/cliente?next=/cliente/inicio", status_code=303)
    links = brechorisee_customer_app_links(request)
    with get_db() as con:
        live_info = active_or_last_live_info(request)
        orders = con.execute(
            """
            SELECT * FROM online_orders
            WHERE customer_phone=? OR LOWER(customer_name)=LOWER(?)
            ORDER BY id DESC LIMIT 5
            """,
            (account["phone"], account["name"]),
        ).fetchall()
    return templates.TemplateResponse(
        "customer_home.html",
        {
            "request": request,
            "settings": get_store_settings(),
            "account": account,
            "links": links,
            "live_info": live_info,
            "orders": orders,
            "unread_notifications": customer_unread_notifications_count(int(account["id"])),
            "public_mode": True,
        },
    )


@app.get("/cliente/perfil", response_class=HTMLResponse)
def customer_profile_page(request: Request) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url="/cliente?next=/cliente/perfil", status_code=303)
    return templates.TemplateResponse(
        "customer_profile.html",
        {"request": request, "settings": get_store_settings(), "account": account, "error": "", "success": request.query_params.get("ok", "")},
    )


@app.post("/cliente/perfil")
def customer_profile_save(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(""),
    instagram: str = Form(""),
    style_preferences: str = Form(""),
) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url="/cliente?next=/cliente/perfil", status_code=303)
    phone_clean = normalize_phone(phone)
    if not phone_clean:
        return templates.TemplateResponse(
            "customer_profile.html",
            {"request": request, "settings": get_store_settings(), "account": account, "error": "Informe um WhatsApp válido.", "success": ""},
            status_code=400,
        )
    with get_db() as con:
        duplicate = con.execute("SELECT id FROM customer_accounts WHERE phone=? AND id<>?", (phone_clean, account["id"])).fetchone()
        if duplicate:
            return templates.TemplateResponse(
                "customer_profile.html",
                {"request": request, "settings": get_store_settings(), "account": account, "error": "Este WhatsApp já está em outro acesso.", "success": ""},
                status_code=400,
            )
        con.execute(
            """
            UPDATE customer_accounts
            SET name=?, phone=?, email=?, instagram=?, style_preferences=?
            WHERE id=?
            """,
            (name, phone_clean, email, instagram, style_preferences, account["id"]),
        )
        if account["customer_id"]:
            con.execute(
                "UPDATE customers SET name=?, phone=?, email=?, instagram=?, preferences=? WHERE id=?",
                (name, phone_clean, email, instagram, style_preferences, account["customer_id"]),
            )
    return RedirectResponse(url="/cliente/perfil?ok=Dados atualizados.", status_code=303)


@app.post("/cliente/alterar-senha")
def customer_change_password(
    request: Request,
    current_password: str = Form(""),
    password: str = Form(...),
    password_confirm: str = Form(""),
) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url="/cliente?next=/cliente/perfil", status_code=303)
    if not current_password or not verify_password(current_password, account["password_hash"]):
        auth_log("cliente", int(account["id"]), "alteracao_senha_bloqueada_senha_atual", request)
        return templates.TemplateResponse(
            "customer_profile.html",
            {"request": request, "settings": get_store_settings(), "account": account, "error": "Informe a senha atual correta para alterar a senha.", "success": ""},
            status_code=401,
        )
    if len((password or "").strip()) < 6:
        return templates.TemplateResponse(
            "customer_profile.html",
            {"request": request, "settings": get_store_settings(), "account": account, "error": "Use uma nova senha com pelo menos 6 caracteres.", "success": ""},
            status_code=400,
        )
    if password_confirm and password != password_confirm:
        return templates.TemplateResponse(
            "customer_profile.html",
            {"request": request, "settings": get_store_settings(), "account": account, "error": "A confirmação da senha não confere.", "success": ""},
            status_code=400,
        )
    with get_db() as con:
        con.execute("UPDATE customer_accounts SET password_hash=? WHERE id=?", (hash_password(password), account["id"]))
        log_security_event(con, "customer_password_changed", severity="info", actor_type="cliente", actor_id=account["id"], request=request)
    auth_log("cliente", int(account["id"]), "alterou_senha", request)
    return RedirectResponse(url="/cliente/perfil?ok=Senha alterada com sucesso.", status_code=303)


@app.get("/cliente/redefinir-senha", response_class=HTMLResponse)
def customer_reset_password_page(request: Request, next: str = CUSTOMER_HOME_PATH) -> Response:
    prefill = {"phone": request.query_params.get("phone", ""), "name": request.query_params.get("name", ""), "email": request.query_params.get("email", "")}
    return templates.TemplateResponse(
        "customer_login.html",
        {"request": request, "settings": get_store_settings(), "mode": "reset", "error": "", "public_mode": True, "prefill": prefill, "next": customer_safe_next_url(next)},
    )


@app.post("/cliente/redefinir-senha")
def customer_reset_password(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    password_confirm: str = Form(""),
    next: str = Form(CUSTOMER_HOME_PATH),
) -> Response:
    phone_clean = normalize_phone(phone)
    safe_next = customer_safe_next_url(next)
    weak_public_reset_allowed = os.getenv("BRECHORISEE_ALLOW_PUBLIC_PASSWORD_RESET", "0").strip().lower() in {"1", "true", "sim", "yes", "on"}
    if not phone_clean:
        return templates.TemplateResponse(
            "customer_login.html",
            {"request": request, "settings": get_store_settings(), "mode": "reset", "error": "Informe um WhatsApp válido.", "public_mode": True, "next": safe_next},
            status_code=400,
        )
    if len((password or "").strip()) < 6:
        return templates.TemplateResponse(
            "customer_login.html",
            {"request": request, "settings": get_store_settings(), "mode": "reset", "error": "Use uma senha com pelo menos 6 caracteres.", "public_mode": True, "next": safe_next},
            status_code=400,
        )
    if password_confirm and password != password_confirm:
        return templates.TemplateResponse(
            "customer_login.html",
            {"request": request, "settings": get_store_settings(), "mode": "reset", "error": "A confirmação da senha não confere.", "public_mode": True, "next": safe_next},
            status_code=400,
        )
    with get_db() as con:
        account = con.execute("SELECT * FROM customer_accounts WHERE phone=? LIMIT 1", (phone_clean,)).fetchone()
        if account:
            stored_email = normalize_text_key(account["email"])
            provided_email = normalize_text_key(email)
            stored_name = normalize_text_key(account["name"])
            provided_name = normalize_text_key(name)
            identity_ok = bool(provided_name and stored_name and provided_name == stored_name and stored_email and provided_email and stored_email == provided_email)
            if not weak_public_reset_allowed:
                log_security_event(con, "public_password_reset_blocked", severity="warning", actor_type="cliente", actor_id=account["id"], path="/cliente/redefinir-senha", details="Tentativa pública bloqueada; requer recuperação assistida/admin.", request=request)
                return templates.TemplateResponse(
                    "customer_login.html",
                    {"request": request, "settings": get_store_settings(), "mode": "reset", "error": "Por segurança, a redefinição de senha de uma conta existente deve ser feita pela loja ou por um link/código de recuperação. Fale com a BRECHORISEE pelo WhatsApp.", "public_mode": True, "next": safe_next},
                    status_code=403,
                )
            if not identity_ok:
                log_security_event(con, "public_password_reset_identity_failed", severity="warning", actor_type="cliente", actor_id=account["id"], path="/cliente/redefinir-senha", details="Nome/e-mail não conferem.", request=request)
                return templates.TemplateResponse(
                    "customer_login.html",
                    {"request": request, "settings": get_store_settings(), "mode": "reset", "error": "Para alterar a senha em modo assistido, informe nome e e-mail exatamente como cadastrados.", "public_mode": True, "next": safe_next},
                    status_code=403,
                )
            con.execute(
                "UPDATE customer_accounts SET password_hash=?, name=COALESCE(NULLIF(?,''), name), email=COALESCE(NULLIF(?,''), email), active=1, last_login_at=? WHERE id=?",
                (hash_password(password), name, email, now_iso(), account["id"]),
            )
            account_id = int(account["id"])
            log_security_event(con, "public_password_reset_allowed_by_env", severity="warning", actor_type="cliente", actor_id=account_id, path="/cliente/redefinir-senha", details="Redefinição pública autorizada por BRECHORISEE_ALLOW_PUBLIC_PASSWORD_RESET.", request=request)
        else:
            customer_id = find_or_create_customer_for_account(con, name, phone_clean, email)
            cur = con.execute(
                "INSERT INTO customer_accounts(customer_id, name, phone, email, password_hash, app_origin, created_at, last_login_at) VALUES(?,?,?,?,?,?,?,?)",
                (customer_id, name, phone_clean, email, hash_password(password), "android" if request.headers.get("user-agent","").lower().find("brechorisee-android") >= 0 else "web", now_iso(), now_iso()),
            )
            account_id = int(cur.lastrowid)
            log_security_event(con, "customer_account_created_from_reset_form", severity="info", actor_type="cliente", actor_id=account_id, path="/cliente/redefinir-senha", request=request)
    auth_log("cliente", account_id, "redefiniu_ou_criou_senha", request)
    resp = RedirectResponse(url=safe_next, status_code=303)
    set_customer_cookie(resp, account_id, request)
    return resp



@app.get("/cliente/entregas", response_class=HTMLResponse)
def customer_deliveries_page(request: Request) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url="/cliente?next=/cliente/entregas", status_code=303)
    phone = normalize_phone(account["phone"] if "phone" in account.keys() else "")
    name_key = normalize_text_key(account["name"] if "name" in account.keys() else "")
    rows: list[sqlite3.Row] = []
    with get_db() as con:
        candidates = con.execute(
            """
            SELECT *
            FROM online_orders
            WHERE delivery_method='entrega'
            ORDER BY id DESC
            LIMIT 120
            """
        ).fetchall()
        for row in candidates:
            row_phone = normalize_phone(row["customer_phone"] if "customer_phone" in row.keys() else "")
            row_name = normalize_text_key(row["customer_name"] if "customer_name" in row.keys() else "")
            if (phone and row_phone and phone == row_phone) or (name_key and row_name and name_key == row_name):
                rows.append(row)
        rows = rows[:20]
    deliveries = [{"order": row, "tracking": delivery_tracking_payload(row), "status_label": online_order_status_label(row["status"])} for row in rows]
    return templates.TemplateResponse(
        "customer_deliveries.html",
        {
            "request": request,
            "account": account,
            "deliveries": deliveries,
            "active": "customer_deliveries",
            "public_mode": True,
            "settings": get_store_settings(),
        },
    )


@app.get("/api/cliente/entregas")
def api_customer_deliveries(request: Request) -> JSONResponse:
    account = customer_from_request(request)
    if not account:
        return JSONResponse({"ok": False, "error": "login_required", "deliveries": []}, status_code=401)
    phone = normalize_phone(account["phone"] if "phone" in account.keys() else "")
    account_id = int(account["id"])
    payload: list[dict[str, Any]] = []
    with get_db() as con:
        if "customer_account_id" in table_columns(con, "online_orders"):
            candidates = con.execute(
                """
                SELECT * FROM online_orders
                WHERE delivery_method='entrega' AND customer_account_id=?
                ORDER BY id DESC LIMIT 120
                """,
                (account_id,),
            ).fetchall()
        else:
            candidates = []
        if not candidates and phone:
            candidates = con.execute(
                """
                SELECT * FROM online_orders
                WHERE delivery_method='entrega' AND customer_account_id IS NULL AND customer_phone=?
                ORDER BY id DESC LIMIT 120
                """,
                (phone,),
            ).fetchall()
        for row in candidates:
            d = row_to_dict(row)
            d["tracking"] = delivery_tracking_payload(row)
            d["status_label"] = online_order_status_label(row["status"])
            payload.append(d)
    return JSONResponse({"ok": True, "deliveries": payload[:20]})


@app.get("/cliente/vitrine", response_class=HTMLResponse)
def customer_private_store(request: Request, q: str = "", categoria: str = "") -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url="/cliente", status_code=303)
    products = loja_rows(q=q, category=categoria, limit=120)
    recommendations = customer_recommendations(account, limit=8)
    with get_db() as con:
        categories = con.execute(
            """
            SELECT category AS name, COUNT(*) AS total FROM products
            WHERE status='disponivel' AND COALESCE(category,'') <> ''
            GROUP BY category
            ORDER BY total DESC, category
            LIMIT 20
            """
        ).fetchall()
        orders = con.execute(
            """
            SELECT * FROM online_orders
            WHERE customer_phone=? OR LOWER(customer_name)=LOWER(?)
            ORDER BY id DESC LIMIT 8
            """,
            (account["phone"], account["name"]),
        ).fetchall()
    return templates.TemplateResponse(
        "customer_store.html",
        {
            "request": request,
            "account": account,
            "products": products,
            "recommendations": recommendations,
            "orders": orders,
            "q": q,
            "categoria": categoria,
            "categories": categories,
            "settings": get_store_settings(),
            "unread_notifications": customer_unread_notifications_count(int(account["id"])),
            "public_mode": True,
            "live_info": active_or_last_live_info(request),
        },
    )


@app.get("/cliente/peca/{code}", response_class=HTMLResponse)
def customer_product_page(request: Request, code: str) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url="/cliente", status_code=303)
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE UPPER(code)=UPPER(?) OR CAST(id AS TEXT)=?", (code.strip(), code.strip())).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Peça não encontrada.")
        media = con.execute("SELECT * FROM product_media WHERE product_id=? ORDER BY id DESC", (product["id"],)).fetchall()
        similar = find_similar_products(product, limit=6)
        con.execute(
            "INSERT INTO product_interest_events(product_id, event_type, source, notes, created_at) VALUES(?,?,?,?,?)",
            (product["id"], "cliente_produto_aberto", "area_cliente", f"Cliente: {account['name']} / {account['phone']}", now_iso()),
        )
    return templates.TemplateResponse(
        "customer_product.html",
        {
            "request": request,
            "account": account,
            "product": product,
            "media": media,
            "similar": similar,
            "settings": get_store_settings(),
            "public_mode": True,
        },
    )




@app.get("/cliente/novidades", response_class=HTMLResponse)
def customer_notifications_page(request: Request) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url="/cliente", status_code=303)
    rows = customer_notifications_rows(int(account["id"]))
    with get_db() as con:
        settings = ensure_customer_notification_settings(con, int(account["id"]))
        con.execute(
            "UPDATE customer_notifications SET status='visualizada', read_at=COALESCE(read_at, ?) WHERE customer_account_id=? AND scheduled_at <= ?",
            (now_iso(), account["id"], now_iso()),
        )
    return templates.TemplateResponse(
        "customer_notifications.html",
        {
            "request": request,
            "account": account,
            "notifications": rows,
            "settings": settings,
            "settings_store": get_store_settings(),
            "public_mode": True,
        },
    )


@app.post("/cliente/novidades/configurar")
def customer_notifications_update(
    request: Request,
    enabled: str = Form("0"),
    frequency: str = Form("moderado"),
    channel_whatsapp: str = Form("0"),
) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url="/cliente", status_code=303)
    if frequency not in {"imediato", "moderado", "diario", "semanal"}:
        frequency = "moderado"
    with get_db() as con:
        ensure_customer_notification_settings(con, int(account["id"]))
        con.execute(
            """
            UPDATE customer_notification_settings
            SET enabled=?, channel_app=1, channel_whatsapp=?, frequency=?, updated_at=?
            WHERE customer_account_id=?
            """,
            (1 if enabled == "1" else 0, 1 if channel_whatsapp == "1" else 0, frequency, now_iso(), account["id"]),
        )
    return RedirectResponse(url="/cliente/novidades", status_code=303)


@app.get("/api/cliente/notificacoes")
def api_customer_notifications(request: Request) -> JSONResponse:
    account = customer_from_request(request)
    if not account:
        return JSONResponse({"ok": False, "message": "Cliente não autenticada."}, status_code=401)
    rows = customer_notifications_rows(int(account["id"]), limit=30)
    return JSONResponse({
        "ok": True,
        "unread": customer_unread_notifications_count(int(account["id"])),
        "notifications": [dict(row) for row in rows],
    })


@app.get("/api/cliente/notificacoes/live-alert")
def api_customer_live_alert(request: Request) -> JSONResponse:
    """Aviso de live para app cliente.

    Agora também funciona para cliente ainda não logada: o app recebe um alerta
    público da live ativa e evita repetir usando o id da sessão.
    """
    account = customer_from_request(request)

    def public_live_notification() -> dict[str, Any] | None:
        with get_db() as con:
            live = con.execute(
                """
                SELECT * FROM live_sessions
                WHERE status='ao_vivo'
                ORDER BY COALESCE(started_at, instagram_control_started_at, created_at) DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if not live:
                return None
            started_raw = live["started_at"] if "started_at" in live.keys() and live["started_at"] else (
                live["instagram_control_started_at"] if "instagram_control_started_at" in live.keys() and live["instagram_control_started_at"] else live["created_at"]
            )
            dt = parse_dt(started_raw)
            if dt and (datetime.now() - dt) > timedelta(hours=max(1, LIVE_STARTED_PUBLIC_ALERT_HOURS)):
                return None
            source_platform = str(live["source_platform"] or "brechorisee") if "source_platform" in live.keys() else "brechorisee"
            action_url = "/cliente/live-opcoes" if source_platform == "instagram" else "/cliente/live"
            title = "Live BRECHORISEE no Instagram ✨" if source_platform == "instagram" else "BRECHORISEE ao vivo agora ✨"
            name = ""
            if account:
                try:
                    name = (account["name"] or "").strip().split()[0]
                except Exception:
                    name = ""
            prefix = f"Oi, {name}! " if name else ""
            message = (
                "A live começou. Toque para assistir no Instagram com o card BRECHORISEE de peça atual."
                if source_platform == "instagram"
                else "A live começou. Toque para ver a peça atual, reservar e acompanhar seu carrinho."
            )
            base = get_public_server_url(request).rstrip("/")
            return {
                "id": 1000000 + int(live["id"]),
                "customer_account_id": int(account["id"]) if account else 0,
                "product_id": None,
                "live_session_id": int(live["id"]),
                "notification_type": "live_started_public",
                "title": title,
                "message": prefix + message,
                "image_filename": live["snapshot_filename"] if "snapshot_filename" in live.keys() else None,
                "action_url": action_url,
                "status": "publica",
                "scheduled_at": started_raw,
                "sent_at": None,
                "read_at": None,
                "created_at": started_raw,
                "deep_link": "brechorisee://live?abrir_instagram=1",
                "web_url": base + action_url,
            }

    if account:
        with get_db() as con:
            row = con.execute(
                """
                SELECT * FROM customer_notifications
                WHERE customer_account_id=?
                  AND notification_type='live_started'
                  AND scheduled_at <= ?
                  AND read_at IS NULL
                  AND sent_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (account["id"], now_iso()),
            ).fetchone()
            if row:
                con.execute(
                    "UPDATE customer_notifications SET sent_at=COALESCE(sent_at, ?), status='enviada' WHERE id=?",
                    (now_iso(), row["id"]),
                )
                payload = dict(row)
                payload["action_url"] = payload.get("action_url") or "/cliente/live"
                payload["deep_link"] = "brechorisee://live?abrir_instagram=1"
                payload["web_url"] = get_public_server_url(request).rstrip("/") + payload["action_url"]
                return JSONResponse({"ok": True, "notification": payload, "live": active_or_last_live_info(request)})

    # Não cria aviso só porque existe uma sessão marcada como "ao_vivo".
    # O app cliente só recebe notificação quando uma live foi iniciada de verdade
    # pelos botões /live/start ou /live/instagram/start, que enfileiram
    # customer_notifications com notification_type='live_started'.
    return JSONResponse({"ok": True, "notification": None, "live": active_or_last_live_info(request)})


@app.post("/api/cliente/notificacoes/{notification_id}/lida")
def api_customer_notification_read(request: Request, notification_id: int) -> JSONResponse:
    account = customer_from_request(request)
    if not account:
        return JSONResponse({"ok": False, "message": "Cliente não autenticada."}, status_code=401)
    with get_db() as con:
        con.execute(
            """
            UPDATE customer_notifications
            SET read_at=COALESCE(read_at, ?), status='visualizada'
            WHERE id=? AND customer_account_id=?
            """,
            (now_iso(), notification_id, account["id"]),
        )
    return JSONResponse({"ok": True})


@app.get("/notificacoes", response_class=HTMLResponse)
def notifications_admin_page(request: Request) -> Response:
    with get_db() as con:
        rows = con.execute(
            """
            SELECT n.*, ca.name AS customer_name, ca.phone AS customer_phone, p.code AS product_code, p.title AS product_title
            FROM customer_notifications n
            JOIN customer_accounts ca ON ca.id = n.customer_account_id
            LEFT JOIN products p ON p.id = n.product_id
            ORDER BY n.id DESC
            LIMIT 200
            """
        ).fetchall()
        stats = {
            "total": con.execute("SELECT COUNT(*) FROM customer_notifications").fetchone()[0],
            "pendentes": con.execute("SELECT COUNT(*) FROM customer_notifications WHERE read_at IS NULL").fetchone()[0],
            "clientes_ativos": con.execute("SELECT COUNT(*) FROM customer_accounts WHERE active=1").fetchone()[0],
            "optin": con.execute("SELECT COUNT(*) FROM customer_notification_settings WHERE enabled=1").fetchone()[0],
        }
    return templates.TemplateResponse(
        "notifications_admin.html",
        {"request": request, "notifications": rows, "stats": stats, "active": "notifications"},
    )


@app.post("/notificacoes/gerar-digest")
def notifications_generate_digest() -> Response:
    """Gera avisos para as peças disponíveis mais recentes respeitando periodicidade."""
    created = 0
    with get_db() as con:
        products = con.execute("SELECT id FROM products WHERE status='disponivel' ORDER BY id DESC LIMIT 20").fetchall()
        for product in products:
            created += queue_new_product_notifications(con, int(product["id"]))
    return RedirectResponse(url=f"/notificacoes?geradas={created}", status_code=303)



@app.get("/admin-acesso", response_class=HTMLResponse)
def admin_access_page(request: Request, next: str = "/") -> Response:
    admin = admin_from_request(request)
    if admin:
        return RedirectResponse(url=next or "/", status_code=303)
    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "settings": get_store_settings(), "has_admin": has_admin_account(), "error": "", "next": next or "/"},
    )


@app.get("/admin-primeiro-acesso", response_class=HTMLResponse)
def admin_first_access_alias_page(request: Request, next: str = "/") -> Response:
    """Atalho explícito para não confundir primeiro acesso de cliente com primeiro acesso administrativo."""
    admin = admin_from_request(request)
    if admin:
        return RedirectResponse(url=next or "/", status_code=303)
    return templates.TemplateResponse(
        "admin_login.html",
        {
            "request": request,
            "settings": get_store_settings(),
            "has_admin": has_admin_account(),
            "error": "",
            "next": next or "/",
            "admin_first_access_hint": True,
        },
    )


@app.get("/admin", response_class=HTMLResponse)
def admin_shortcut_page(request: Request) -> Response:
    """Atalho simples para a área administrativa."""
    return RedirectResponse(url="/admin-acesso", status_code=303)



@app.post("/admin-acesso/criar")
def admin_create_first(
    request: Request,
    name: str = Form(...),
    email: str = Form(""),
    instagram: str = Form(""),
    style_preferences: str = Form(""),
    password: str = Form(...),
    next: str = Form("/"),
) -> Response:
    if has_admin_account():
        raise HTTPException(status_code=403, detail="Administrador já configurado.")
    if len((password or "").strip()) < 6:
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "settings": get_store_settings(), "has_admin": False, "error": "Use uma senha de administrador com pelo menos 6 caracteres.", "next": next or "/"},
            status_code=400,
        )
    with get_db() as con:
        cur = con.execute(
            "INSERT INTO admin_accounts(name, email, password_hash, role, created_at, last_login_at) VALUES(?,?,?,?,?,?)",
            (name, email, hash_password(password), "admin", now_iso(), now_iso()),
        )
        admin_id = int(cur.lastrowid)
    auth_log("admin", admin_id, "primeiro_acesso", request)
    safe_next = next if next and next.startswith("/") and not next.startswith("//") else "/"
    resp = RedirectResponse(url=safe_next, status_code=303)
    set_admin_cookie(resp, admin_id, request)
    return resp


@app.post("/admin-acesso/login")
def admin_login(request: Request, email: str = Form(""), password: str = Form(...), next: str = Form("/")) -> Response:
    if not check_login_rate_limit(request):
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "settings": get_store_settings(), "has_admin": has_admin_account(), "error": "Muitas tentativas. Tente novamente em alguns minutos.", "next": next or "/"},
            status_code=429,
        )
    with get_db() as con:
        account = con.execute(
            "SELECT * FROM admin_accounts WHERE (LOWER(email)=LOWER(?) OR LOWER(name)=LOWER(?)) AND active=1 LIMIT 1",
            (email, email),
        ).fetchone()
        if not account or not verify_password(password, account["password_hash"]):
            return templates.TemplateResponse(
                "admin_login.html",
                {"request": request, "settings": get_store_settings(), "has_admin": has_admin_account(), "error": "Acesso administrativo inválido.", "next": next or "/"},
                status_code=401,
            )
        con.execute("UPDATE admin_accounts SET last_login_at=? WHERE id=?", (now_iso(), account["id"]))
    reset_login_rate_limit(request)
    auth_log("admin", int(account["id"]), "login", request)
    safe_next = next if next and next.startswith("/") and not next.startswith("//") else "/"
    resp = RedirectResponse(url=safe_next, status_code=303)
    set_admin_cookie(resp, int(account["id"]), request)
    return resp





@app.get("/admin-recuperar", response_class=HTMLResponse)
def admin_recovery_page(request: Request, next: str = "/") -> Response:
    admin = admin_from_request(request)
    if admin:
        return RedirectResponse(url="/usuarios?ok=Você já está logada. Altere a senha em Usuários.", status_code=303)
    return templates.TemplateResponse(
        "admin_recovery.html",
        {
            "request": request,
            "settings": get_store_settings(),
            "has_admin": has_admin_account(),
            "error": "",
            "next": safe_next_url(next, "/"),
            "token_required": BRECHORISEE_ENV == "production" or bool(BRECHORISEE_ADMIN_RECOVERY_TOKEN),
        },
    )


@app.post("/admin-recuperar/salvar")
def admin_recovery_save(
    request: Request,
    name: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    token: str = Form(""),
    next: str = Form("/"),
) -> Response:
    if len((password or "").strip()) < 6:
        return templates.TemplateResponse(
            "admin_recovery.html",
            {"request": request, "settings": get_store_settings(), "has_admin": has_admin_account(), "error": "Use uma senha de administrador com pelo menos 6 caracteres.", "next": safe_next_url(next, "/"), "token_required": True},
            status_code=400,
        )
    if has_admin_account() and not admin_recovery_allowed(request, token):
        return templates.TemplateResponse(
            "admin_recovery.html",
            {
                "request": request,
                "settings": get_store_settings(),
                "has_admin": True,
                "error": "Para recuperar administrador existente, configure BRECHORISEE_ADMIN_RECOVERY_TOKEN no Render e informe o token aqui.",
                "next": safe_next_url(next, "/"),
                "token_required": True,
            },
            status_code=403,
        )
    with get_db() as con:
        account = con.execute(
            "SELECT * FROM admin_accounts WHERE LOWER(email)=LOWER(?) OR LOWER(name)=LOWER(?) ORDER BY id LIMIT 1",
            (email, name),
        ).fetchone()
        if account:
            admin_id = int(account["id"])
            con.execute(
                "UPDATE admin_accounts SET name=?, email=?, password_hash=?, active=1 WHERE id=?",
                (name, email, hash_password(password), admin_id),
            )
            action = "recuperou_senha_admin"
        else:
            cur = con.execute(
                "INSERT INTO admin_accounts(name, email, password_hash, role, created_at, last_login_at, active) VALUES(?,?,?,?,?,?,1)",
                (name, email, hash_password(password), "admin", now_iso(), now_iso()),
            )
            admin_id = int(cur.lastrowid)
            action = "criou_admin_recuperacao"
    auth_log("admin", admin_id, action, request)
    safe_next = safe_next_url(next, "/")
    resp = RedirectResponse(url=safe_next, status_code=303)
    set_admin_cookie(resp, admin_id, request)
    return resp


def user_accounts_context(request: Request, error: str = "", success: str = "") -> dict[str, Any]:
    current_admin = admin_from_request(request)
    with get_db() as con:
        admins = con.execute("SELECT id, name, email, role, created_at, last_login_at, active FROM admin_accounts ORDER BY active DESC, id ASC").fetchall()
        customers = con.execute(
            """
            SELECT ca.id, ca.name, ca.phone, ca.email, ca.instagram, ca.style_preferences, ca.created_at, ca.last_login_at, ca.active,
                   c.id AS customer_id
            FROM customer_accounts ca
            LEFT JOIN customers c ON c.id = ca.customer_id
            ORDER BY ca.active DESC, ca.id DESC
            LIMIT 300
            """
        ).fetchall()
    return {
        "request": request,
        "settings": get_store_settings(),
        "active": "usuarios",
        "current_admin": current_admin,
        "admins": admins,
        "customers": customers,
        "error": error or request.query_params.get("erro", ""),
        "success": success or request.query_params.get("ok", ""),
    }


@app.get("/usuarios", response_class=HTMLResponse)
def users_admin_page(request: Request) -> Response:
    return templates.TemplateResponse("user_accounts.html", user_accounts_context(request))


@app.post("/usuarios/admin/criar")
def users_admin_create(request: Request, name: str = Form(...), email: str = Form(""), password: str = Form(...), role: str = Form("admin")) -> Response:
    name = (name or "").strip()
    email = (email or "").strip().lower()
    role = role if role in {"admin", "operador", "atendimento"} else "admin"
    if len(name) < 2:
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Informe o nome do administrador."), status_code=400)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or ""):
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Informe um e-mail válido e único para o administrador."), status_code=400)
    if len((password or "").strip()) < 8:
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Use uma senha de administrador com pelo menos 8 caracteres."), status_code=400)
    with get_db() as con:
        duplicate = con.execute("SELECT id FROM admin_accounts WHERE (email IS NOT NULL AND TRIM(email)<>'' AND LOWER(email)=LOWER(?)) OR LOWER(name)=LOWER(?)", (email, name)).fetchone()
        if duplicate:
            return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Já existe administrador com esse e-mail ou nome."), status_code=400)
        cur = con.execute(
            "INSERT INTO admin_accounts(name, email, password_hash, role, created_at, active) VALUES(?,?,?,?,?,1)",
            (name, email, hash_password(password), role or "admin", now_iso()),
        )
        admin_id = int(cur.lastrowid)
        log_security_event(con, "admin_user_created", severity="info", actor_type="admin", actor_id=admin_id, path="/usuarios/admin/criar", request=request)
    auth_log("admin", admin_id, "criou_novo_admin", request)
    return RedirectResponse(url="/usuarios?ok=Administrador criado.", status_code=303)


@app.post("/usuarios/admin/{account_id}/senha")
def users_admin_set_password(request: Request, account_id: int, password: str = Form(...), password_confirm: str = Form("")) -> Response:
    if len((password or "").strip()) < 6:
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Use uma senha de administrador com pelo menos 6 caracteres."), status_code=400)
    if password_confirm and password != password_confirm:
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="A confirmação da senha admin não confere."), status_code=400)
    with get_db() as con:
        if not con.execute("SELECT id FROM admin_accounts WHERE id=?", (account_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Administrador não encontrado.")
        con.execute("UPDATE admin_accounts SET password_hash=?, active=1 WHERE id=?", (hash_password(password), account_id))
    auth_log("admin", account_id, "alterou_senha_admin", request)
    return RedirectResponse(url="/usuarios?ok=Senha do administrador alterada.", status_code=303)


@app.post("/usuarios/admin/{account_id}/status")
def users_admin_status(request: Request, account_id: int, active: int = Form(...)) -> Response:
    current_admin = admin_from_request(request)
    desired = 1 if int(active or 0) else 0
    if current_admin and int(current_admin["id"]) == int(account_id) and desired == 0:
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Você não pode desativar o próprio acesso enquanto está logada."), status_code=400)
    with get_db() as con:
        if desired == 0:
            active_admins = con.execute("SELECT COUNT(*) AS total FROM admin_accounts WHERE active=1").fetchone()["total"]
            if active_admins <= 1:
                return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Não é permitido desativar o último administrador ativo."), status_code=400)
        con.execute("UPDATE admin_accounts SET active=? WHERE id=?", (desired, account_id))
    return RedirectResponse(url="/usuarios?ok=Status do administrador atualizado.", status_code=303)


@app.post("/usuarios/cliente/criar")
def users_customer_create(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(""),
    instagram: str = Form(""),
    style_preferences: str = Form(""),
    password: str = Form(...),
) -> Response:
    name = (name or "").strip()
    phone_clean = normalize_phone(phone)
    email = (email or "").strip().lower()
    if len(name) < 2:
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Informe o nome da cliente."), status_code=400)
    if not phone_clean:
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Informe um WhatsApp válido para a cliente."), status_code=400)
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Informe um e-mail de cliente válido ou deixe vazio."), status_code=400)
    if len((password or "").strip()) < 6:
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Use uma senha de cliente com pelo menos 6 caracteres."), status_code=400)
    with get_db() as con:
        existing = con.execute("SELECT id FROM customer_accounts WHERE phone=?", (phone_clean,)).fetchone()
        if existing:
            return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Já existe cliente com esse WhatsApp. Use Alterar senha."), status_code=400)
        customer_id = find_or_create_customer_for_account(con, name, phone_clean, email)
        if customer_id:
            con.execute("UPDATE customers SET instagram=COALESCE(NULLIF(?,''), instagram), preferences=COALESCE(NULLIF(?,''), preferences) WHERE id=?", (instagram, style_preferences, customer_id))
        cur = con.execute(
            "INSERT INTO customer_accounts(customer_id, name, phone, email, instagram, style_preferences, app_origin, password_hash, created_at, active) VALUES(?,?,?,?,?,?,?,?,?,1)",
            (customer_id, name, phone_clean, email, instagram, style_preferences, "admin", hash_password(password), now_iso()),
        )
        account_id = int(cur.lastrowid)
        log_security_event(con, "customer_user_created_by_admin", severity="info", actor_type="cliente", actor_id=account_id, path="/usuarios/cliente/criar", request=request)
    auth_log("cliente", account_id, "admin_criou_cliente", request)
    return RedirectResponse(url="/usuarios?ok=Cliente criada.", status_code=303)


@app.post("/usuarios/cliente/{account_id}/senha")
def users_customer_set_password(request: Request, account_id: int, password: str = Form(...), password_confirm: str = Form("")) -> Response:
    if len((password or "").strip()) < 4:
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="Use uma senha de cliente com pelo menos 4 caracteres."), status_code=400)
    if password_confirm and password != password_confirm:
        return templates.TemplateResponse("user_accounts.html", user_accounts_context(request, error="A confirmação da senha da cliente não confere."), status_code=400)
    with get_db() as con:
        if not con.execute("SELECT id FROM customer_accounts WHERE id=?", (account_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Cliente não encontrada.")
        con.execute("UPDATE customer_accounts SET password_hash=?, active=1 WHERE id=?", (hash_password(password), account_id))
    auth_log("cliente", account_id, "admin_alterou_senha_cliente", request)
    return RedirectResponse(url="/usuarios?ok=Senha da cliente alterada.", status_code=303)


@app.post("/usuarios/cliente/{account_id}/status")
def users_customer_status(request: Request, account_id: int, active: int = Form(...)) -> Response:
    desired = 1 if int(active or 0) else 0
    with get_db() as con:
        con.execute("UPDATE customer_accounts SET active=? WHERE id=?", (desired, account_id))
    return RedirectResponse(url="/usuarios?ok=Status da cliente atualizado.", status_code=303)


def assistant_token_valid(request: Request, token: str = "") -> bool:
    """Autoriza chamadas do Assistente Instagram Android sem depender de cookie do WebView.

    Produção: configure BRECHORISEE_ASSISTANT_TOKEN ou BRECHORISEE_SYNC_TOKEN no servidor
    e salve o mesmo token no app Admin. Sem token configurado, o modo fica liberado apenas
    para testes locais/simulação.
    """
    expected = ASSISTANT_CONTROL_TOKEN
    provided = (
        token
        or request.headers.get("x-brechorisee-assistant-token")
        or request.headers.get("x-brechorisee-sync-token")
        or request.query_params.get("assistant_token")
        or ""
    ).strip()
    if not expected:
        return True
    return bool(provided) and hmac.compare_digest(provided, expected)


def instagram_assistant_product_payload(con: sqlite3.Connection, product: sqlite3.Row | dict[str, Any], score: float = 0.0, source: str = "instagram") -> dict[str, Any]:
    """Payload único para overlay Instagram, Telegram e app Cliente."""
    if not product:
        return {}
    row = row_to_dict(product)
    status = str(row.get("status") or "")
    base = live_product_payload(product) if hasattr(product, "keys") else live_product_payload(row)  # type: ignore[arg-type]
    if not base:
        image_filename = row.get("image_filename") or ""
        base = {
            "id": int(row.get("id") or 0),
            "code": row.get("code") or "",
            "title": row.get("title") or "Peça",
            "price": safe_float(row.get("sale_price")),
            "price_label": money(row.get("sale_price")),
            "status": status,
            "image_url": f"/static/uploads/{image_filename}" if image_filename else "",
            "public_url": f"/cliente/peca/{row.get('code')}" if status == "disponivel" else "",
            "store_url": f"/loja/produto/{row.get('code')}" if status == "disponivel" else "",
        }
    base["recognition_score"] = round(float(score or 0), 2)
    base["source"] = source
    base["available"] = status == "disponivel"
    if status == "reservado":
        info = product_reservation_info(con, int(base["id"])) or {"reserved_for": "cliente"}
        base.update(info)
        base["status_label"] = f"Reservada para {info.get('reserved_for') or 'cliente'}"
        base["public_url"] = ""
        base["store_url"] = ""
    elif status == "vendido":
        base["status_label"] = "Vendida"
        base["public_url"] = ""
        base["store_url"] = ""
    elif status == "disponivel":
        base["status_label"] = "Disponível"
    else:
        base["status_label"] = status or "Indefinida"
    base["instagram_message"] = instagram_product_message(base)
    return base


def instagram_product_message(product: dict[str, Any]) -> str:
    title = product.get("title") or "Peça BRECHORISEE"
    code = product.get("code") or ""
    price = product.get("price_label") or money(product.get("price"))
    if product.get("status") == "disponivel" and product.get("public_url"):
        return f"{title} 💖\nCód: {code}\n{price}\nComprar/reservar: {product.get('public_url')}"
    if product.get("status") == "reservado":
        return f"{title} já está reservada 💕\nVeja opções parecidas na repescagem."
    if product.get("status") == "vendido":
        return f"{title} já foi vendida 💕\nVeja opções parecidas na vitrine."
    return f"{title} • {code} • {price}"


def queue_instagram_product_to_customers(con: sqlite3.Connection, product: sqlite3.Row | dict[str, Any], message: str = "") -> int:
    """Envia card/link da peça reconhecida para o app Cliente, apenas se estiver disponível."""
    p = row_to_dict(product)
    if not p or str(p.get("status") or "") != "disponivel":
        return 0
    created = 0
    title = f"Peça da live no Instagram: {p.get('title') or 'BRECHORISEE'}"
    body = message.strip() or f"A peça reconhecida na live está disponível. Toque para ver e reservar: {p.get('code')}"
    accounts = con.execute("SELECT * FROM customer_accounts WHERE active=1 ORDER BY id DESC LIMIT 5000").fetchall()
    for account in accounts:
        settings = ensure_customer_notification_settings(con, int(account["id"]))
        if int(settings["enabled"] or 0) != 1 or int(settings["channel_app"] or 1) != 1:
            continue
        con.execute(
            """
            INSERT INTO customer_notifications
            (customer_account_id, product_id, notification_type, title, message, image_filename, action_url, status, scheduled_at, created_at, message_channel, personalized)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                account["id"],
                int(p["id"]),
                "instagram_product",
                title,
                body,
                p.get("image_filename"),
                f"/cliente/peca/{p.get('code')}",
                "pendente",
                now_iso(),
                now_iso(),
                "app_instagram_live",
                1,
            ),
        )
        created += 1
    return created


@app.get("/api/instagram-assistant/status")
def api_instagram_assistant_status(request: Request, assistant_token: str = "") -> JSONResponse:
    if not assistant_token_valid(request, assistant_token):
        return JSONResponse({"ok": False, "message": "Assistente não autorizado."}, status_code=403)
    with get_db() as con:
        live = con.execute("SELECT * FROM live_sessions WHERE status='ao_vivo' ORDER BY id DESC LIMIT 1").fetchone()
        recent = [dict(r) for r in con.execute("SELECT id, direction, text, status, related_type, related_id, created_at FROM telegram_messages ORDER BY id DESC LIMIT 10").fetchall()]
    return JSONResponse({
        "ok": True,
        "assistant_token_configured": bool(ASSISTANT_CONTROL_TOKEN),
        "live": dict(live) if live else None,
        "telegram_configured": telegram_is_configured(),
        "telegram_send_real": TELEGRAM_SEND_REAL,
        "recent_telegram": recent,
        "features": {
            "overlay_android": True,
            "screen_capture_consent": True,
            "manual_confirmation_required": True,
            "auto_instagram_posting": False,
        },
    })



def instagram_assistant_context_guard(frame_path: Path, *, source_text: str = "", live_mode: bool = False) -> dict[str, Any]:
    """Filtro defensivo para evitar reconhecer peças fora do Instagram.

    O app Android tenta validar o pacote em primeiro plano. Este filtro do servidor
    é uma segunda camada: quando a captura claramente é da própria vitrine/admin,
    o reconhecimento não prossegue e a live é limpa.
    """
    source = (source_text or "").strip().lower()
    context = {
        "outside_instagram": False,
        "screen_context": "instagram_indeterminado",
        "context_reason": "",
        "ocr_text": "",
    }

    # Capturas do overlay Android informam a origem. Sem OCR, não bloqueamos; apenas
    # aumentamos a confiança mínima no modo live. Com OCR disponível, bloqueamos
    # textos próprios do sistema BRECHORISEE fora do Instagram.
    try:
        ocr_text, engine, error = notebook_try_ocr_image(frame_path)
        cleaned = " ".join((ocr_text or "").lower().split())
        context["ocr_text"] = cleaned[:500]
        if cleaned:
            own_screen_markers = [
                "vitrine online",
                "área exclusiva da cliente",
                "area exclusiva da cliente",
                "crie seu acesso",
                "sacola",
                "entregas",
                "preenchimento automático",
                "preenchimento automatico",
                "nome da peça",
                "nome da peca",
                "caderno ia",
                "brechorisee vitrine",
            ]
            instagram_markers = [
                "instagram",
                "reels",
                "seguir",
                "traduzir com ia",
                "assistir novamente",
                "ao vivo",
            ]
            own_hits = [m for m in own_screen_markers if m in cleaned]
            ig_hits = [m for m in instagram_markers if m in cleaned]
            if own_hits and not ig_hits:
                context.update({
                    "outside_instagram": True,
                    "screen_context": "fora_instagram",
                    "context_reason": "captura parece ser da vitrine/admin BRECHORISEE, não do Instagram",
                })
                return context
    except Exception:
        # OCR é opcional. O reconhecimento continua, mas com threshold maior no Android live.
        pass

    return context


@app.post("/api/instagram-assistant/recognize-screen")
def api_instagram_assistant_recognize_screen(
    request: Request,
    image: UploadFile = File(...),
    source_text: str = Form(""),
    assistant_token: str = Form(""),
    notify_telegram: int = Form(1),
    send_to_clients: int = Form(0),
    live_mode: int = Form(0),
    auto_clear: int = Form(1),
) -> JSONResponse:
    if not assistant_token_valid(request, assistant_token):
        return JSONResponse({"ok": False, "message": "Assistente não autorizado."}, status_code=403)

    filename = save_upload(image, "instagram_assistant_screen")
    if not filename:
        return JSONResponse({"ok": False, "message": "Imagem não enviada."}, status_code=400)

    is_live_capture = bool(int(live_mode or 0)) or ("live" in (source_text or "").lower())
    frame_path = UPLOAD_DIR / filename
    variants: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    context_guard: dict[str, Any] = {}
    try:
        context_guard = instagram_assistant_context_guard(frame_path, source_text=source_text, live_mode=is_live_capture)
        if context_guard.get("outside_instagram"):
            if is_live_capture and int(auto_clear or 0) == 1:
                with get_db() as con:
                    live = con.execute("SELECT * FROM live_sessions WHERE status='ao_vivo' ORDER BY id DESC LIMIT 1").fetchone()
                    if live:
                        con.execute(
                            "UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='fora_instagram', current_product_event_id=NULL WHERE id=?",
                            (now_iso(), int(live["id"])),
                        )
            return JSONResponse({
                "ok": True,
                "recognition_mode": "instagram_context_guard",
                "live_mode": is_live_capture,
                "outside_instagram": True,
                "screen_context": context_guard.get("screen_context") or "fora_instagram",
                "context_reason": context_guard.get("context_reason") or "captura fora do Instagram",
                "products": [],
                "top_product": None,
                "recognized_count": 0,
                "low_confidence": [],
                "live_updated": False,
                "live_session_id": None,
                "live_references_added": 0,
                "message": "Fora do Instagram. Assistente pausado para não reconhecer tela errada.",
            })
        variants = instagram_screen_signature_variants(frame_path, live_focus=is_live_capture)
        matches = recognize_product_matches_from_variants(
            variants,
            limit=max(5, INSTAGRAM_ASSISTANT_MAX_MATCHES),
            status="todos",
        )
        # Fallback compatível com o reconhecimento antigo. Nunca é usado no modo live,
        # pois a tela inteira gera falso positivo em cenário, texto, logo e vitrine.
        if not matches and not is_live_capture:
            query_hash, query_rgb = image_signature(frame_path)
            matches = recognize_product_matches(query_hash, query_rgb, limit=8, status="todos")
    finally:
        try:
            frame_path.unlink(missing_ok=True)
        except Exception:
            pass

    products: list[dict[str, Any]] = []
    low_confidence: list[dict[str, Any]] = []
    notified_customers = 0
    live_updated = False
    live_session_id = None
    live_references_added = 0
    # Em live no overlay Android, confiança muito mais alta evita que cenário/chão/texto/logo
    # mantenham peça errada na tela. Também exigimos separação do segundo melhor match.
    android_overlay_live = is_live_capture and "android_overlay" in (source_text or "").lower()
    min_score = float((LIVE_RECOGNITION_MIN_SCORE if is_live_capture else INSTAGRAM_ASSISTANT_MIN_SCORE) or 42)
    if android_overlay_live:
        min_score = max(min_score, float(LIVE_RECOGNITION_ANDROID_MIN_SCORE or 78))
    sorted_matches = sorted(matches, key=lambda m: float(m.get("score") or 0), reverse=True)
    top_raw_score = float(sorted_matches[0].get("score") or 0) if sorted_matches else 0.0
    second_raw_score = float(sorted_matches[1].get("score") or 0) if len(sorted_matches) > 1 else 0.0
    ambiguous_top = android_overlay_live and top_raw_score < 85.0 and (top_raw_score - second_raw_score) < float(LIVE_RECOGNITION_ANDROID_GAP_SCORE or 7)

    with get_db() as con:
        for match in sorted_matches:
            score = float(match.get("score") or 0)
            if android_overlay_live and ambiguous_top:
                # Mantém a live limpa: se vários produtos parecem parecidos, é mais seguro
                # não reconhecer nada do que mostrar uma peça antiga/errada.
                low_confidence = []
                break
            row = con.execute("SELECT * FROM products WHERE id=?", (int(match["id"]),)).fetchone()
            if not row:
                continue
            payload = instagram_assistant_product_payload(con, row, score=score, source="instagram_post_reels")
            payload["source_text"] = source_text[:500]
            payload["matched_screen_crop"] = match.get("matched_screen_crop") or ""
            payload["screen_crop_box"] = match.get("screen_crop_box") or []
            payload["screen_crop_size"] = match.get("screen_crop_size") or {}
            payload["screen_type"] = match.get("screen_type") or (variants[0].get("screen_type") if variants else "")
            payload["match_source"] = match.get("match_source") or ""
            if score >= min_score:
                products.append(payload)
            elif not android_overlay_live:
                low_confidence.append(payload)
        top = products[0] if products else None

        if top and int(send_to_clients or 0) == 1 and top.get("status") == "disponivel":
            row = con.execute("SELECT * FROM products WHERE id=?", (int(top["id"]),)).fetchone()
            if row:
                notified_customers = queue_instagram_product_to_customers(con, row, top.get("instagram_message") or "")
        if top and int(notify_telegram or 0) == 1:
            lines = [
                "📲 <b>Assistente Instagram BRECHORISEE</b>",
                "Modo: Post/Reels/Live por captura de tela",
                f"Peça reconhecida: {top.get('code')} — {top.get('title')}",
                f"Status: {top.get('status_label')}",
                f"Score: {top.get('recognition_score')}",
            ]
            if top.get("matched_screen_crop"):
                lines.append(f"Recorte usado: {top.get('matched_screen_crop')}")
            if source_text:
                lines += ["", f"Texto/OCR: {source_text[:700]}"]
            if top.get("public_url"):
                lines += ["", f"Link cliente: {top.get('public_url')}"]
            telegram_send_admin_message(con, "\n".join(lines), related_type="instagram_assistant", related_id=int(top["id"]))

        if is_live_capture:
            live = con.execute(
                "SELECT * FROM live_sessions WHERE status='ao_vivo' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if live:
                live_session_id = int(live["id"])
                if top and top.get("status") == "disponivel":
                    now_value = now_iso()
                    top_product_id = int(top["id"])
                    cur_item_id = _live_insert_item(
                        con,
                        live_session_id,
                        top_product_id,
                        "reconhecida",
                        f"Reconhecimento automático do app Admin na live. Score {top.get('recognition_score')}.",
                        0.0,
                    )
                    live_updated = True
                    # Peças extras vistas no mesmo print entram como referências, sem substituir a peça atual.
                    for extra in products[1:5]:
                        try:
                            if extra.get("status") == "disponivel":
                                _live_insert_item(
                                    con,
                                    live_session_id,
                                    int(extra["id"]),
                                    "referencia",
                                    f"Referência simultânea no print da live. Score {extra.get('recognition_score')}.",
                                    0.0,
                                )
                                live_references_added += 1
                        except Exception:
                            pass
                elif int(auto_clear or 0) == 1:
                    con.execute(
                        "UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='sem_reconhecimento', current_product_event_id=NULL WHERE id=?",
                        (now_iso(), live_session_id),
                    )

    debug_variants = [
        {
            "label": v.get("label"),
            "box": v.get("box"),
            "width": v.get("width"),
            "height": v.get("height"),
            "screen_type": v.get("screen_type"),
        }
        for v in variants[:14]
    ] if INSTAGRAM_ASSISTANT_DEBUG else []

    response_message = "Peça reconhecida no Instagram."
    if not products and android_overlay_live:
        if ambiguous_top:
            response_message = "Nenhuma peça reconhecida com segurança. Resultado antigo limpo; aproxime a peça ou enquadre melhor a live."
        else:
            response_message = "Nenhuma peça reconhecida agora. Resultado antigo limpo para evitar falso positivo."
    elif not products and low_confidence:
        response_message = "Encontrei possíveis peças, mas abaixo da confiança mínima. Toque em reconhecer de novo com a peça maior na tela ou reduza BRECHORISEE_INSTAGRAM_ASSISTANT_MIN_SCORE."
    elif not products:
        response_message = "Nenhuma peça reconhecida. Abra o post/reels com a peça ocupando mais a tela e tente novamente."

    return JSONResponse({
        "ok": True,
        "recognition_mode": "instagram_post_reels_multi_crop",
        "live_mode": is_live_capture,
        "outside_instagram": False,
        "screen_context": (context_guard or {}).get("screen_context") or "instagram_indeterminado",
        "context_reason": (context_guard or {}).get("context_reason") or "",
        "screen_type": variants[0].get("screen_type") if variants else "",
        "min_score": min_score,
        "top_raw_score": top_raw_score,
        "second_raw_score": second_raw_score,
        "ambiguous_top": ambiguous_top,
        "products": products[:5],
        "top_product": products[0] if products else None,
        "recognized_count": len(products[:5]),
        "low_confidence": low_confidence[:3],
        "customers_notified": notified_customers,
        "live_updated": live_updated,
        "live_session_id": live_session_id,
        "live_references_added": live_references_added,
        "crop_variants_tested": len(variants),
        "debug_variants": debug_variants,
        "message": response_message,
    })


@app.post("/api/instagram-assistant/send-product-link")
def api_instagram_assistant_send_product_link(
    request: Request,
    product_id: int = Form(...),
    destination: str = Form("telegram"),
    message: str = Form(""),
    assistant_token: str = Form(""),
) -> JSONResponse:
    if not assistant_token_valid(request, assistant_token):
        return JSONResponse({"ok": False, "message": "Assistente não autorizado."}, status_code=403)

    destination = (destination or "telegram").strip().lower()
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (int(product_id),)).fetchone()
        if not product:
            return JSONResponse({"ok": False, "message": "Peça não encontrada."}, status_code=404)
        payload = instagram_assistant_product_payload(con, product, source="instagram_overlay")
        text = message.strip() or payload.get("instagram_message") or instagram_product_message(payload)
        customers = 0
        telegram_result: dict[str, Any] | None = None
        if destination in {"clientes", "cliente", "app", "ambos", "todos"}:
            customers = queue_instagram_product_to_customers(con, product, text)
        if destination in {"telegram", "ambos", "todos"}:
            telegram_result = telegram_send_admin_message(con, "📣 Link da peça para live/Instagram:\n\n" + text, related_type="instagram_product_link", related_id=int(product_id))
    return JSONResponse({"ok": True, "product": payload, "message_text": text, "customers_notified": customers, "telegram_result": telegram_result})


@app.post("/api/instagram-assistant/register-comment")
def api_instagram_assistant_register_comment(
    request: Request,
    source_user: str = Form("Instagram"),
    message: str = Form(...),
    product_id: int = Form(0),
    assistant_token: str = Form(""),
) -> JSONResponse:
    if not assistant_token_valid(request, assistant_token):
        return JSONResponse({"ok": False, "message": "Assistente não autorizado."}, status_code=403)
    with get_db() as con:
        live = con.execute("SELECT * FROM live_sessions WHERE status='ao_vivo' ORDER BY id DESC LIMIT 1").fetchone()
        live_id = int(live["id"]) if live else None
        if live_id:
            con.execute(
                "INSERT INTO live_comments(live_session_id, author_name, message, source, pinned, created_at) VALUES(?,?,?,?,?,?)",
                (live_id, source_user[:120], message[:1000], "instagram_ocr", 0, now_iso()),
            )
        text = "💬 Comentário detectado no Instagram\n" + f"Cliente: {source_user}\nMensagem: {message}"
        if product_id:
            product = con.execute("SELECT code, title FROM products WHERE id=?", (int(product_id),)).fetchone()
            if product:
                text += f"\nPeça sugerida: {product['code']} — {product['title']}"
        telegram_send_admin_message(con, text, related_type="instagram_comment", related_id=int(product_id) if product_id else None)
    return JSONResponse({"ok": True, "live_session_id": live_id, "message": "Comentário registrado e enviado ao controle."})



@app.get("/admin-sair")
def admin_logout(request: Request) -> Response:
    resp = RedirectResponse(url="/admin-acesso", status_code=303)
    resp.delete_cookie(AUTH_COOKIE_NAME)
    return resp





@app.get("/api/telegram/status")
def api_telegram_status() -> JSONResponse:
    with get_db() as con:
        last = [dict(r) for r in con.execute("SELECT id, direction, chat_id, username, text, command, status, related_type, related_id, error, created_at, sent_at FROM telegram_messages ORDER BY id DESC LIMIT 30").fetchall()]
        proofs = [dict(r) for r in con.execute("SELECT * FROM payment_proofs ORDER BY id DESC LIMIT 20").fetchall()]
        status_text = telegram_status_text(con)
    return JSONResponse({
        "ok": True,
        "configured": telegram_is_configured(),
        "send_real": TELEGRAM_SEND_REAL,
        "bot_token_masked": telegram_mask_token(),
        "admin_chat_id_configured": bool(TELEGRAM_ADMIN_CHAT_ID),
        "allowed_chat_ids_configured": bool(TELEGRAM_ALLOWED_CHAT_IDS),
        "commands_enabled": TELEGRAM_COMMANDS_ENABLED,
        "notify": {
            "orders": TELEGRAM_NOTIFY_ORDERS,
            "live": TELEGRAM_NOTIFY_LIVE,
            "comments": TELEGRAM_NOTIFY_COMMENTS,
            "reservations": TELEGRAM_NOTIFY_RESERVATIONS,
            "waitlist": TELEGRAM_NOTIFY_WAITLIST,
            "payments": TELEGRAM_NOTIFY_PAYMENTS,
        },
        "status_text": status_text,
        "messages": last,
        "payment_proofs": proofs,
    })


@app.get("/telegram", response_class=HTMLResponse)
def telegram_admin_page(request: Request) -> Response:
    with get_db() as con:
        last = con.execute(
            "SELECT id, direction, chat_id, username, text, command, status, related_type, related_id, error, created_at, sent_at FROM telegram_messages ORDER BY id DESC LIMIT 40"
        ).fetchall()
        proofs = con.execute("SELECT * FROM payment_proofs ORDER BY id DESC LIMIT 20").fetchall()
        status_text = telegram_status_text(con)
    return templates.TemplateResponse(
        "telegram_admin.html",
        {
            "request": request,
            "active": "telegram",
            "configured": telegram_is_configured(),
            "send_real": TELEGRAM_SEND_REAL,
            "commands_enabled": TELEGRAM_COMMANDS_ENABLED,
            "bot_token_masked": telegram_mask_token(),
            "admin_chat_id_configured": bool(TELEGRAM_ADMIN_CHAT_ID),
            "allowed_chat_ids_configured": bool(TELEGRAM_ALLOWED_CHAT_IDS),
            "notify_orders": TELEGRAM_NOTIFY_ORDERS,
            "notify_live": TELEGRAM_NOTIFY_LIVE,
            "notify_comments": TELEGRAM_NOTIFY_COMMENTS,
            "notify_reservations": TELEGRAM_NOTIFY_RESERVATIONS,
            "notify_waitlist": TELEGRAM_NOTIFY_WAITLIST,
            "notify_payments": TELEGRAM_NOTIFY_PAYMENTS,
            "status_text": status_text,
            "messages": last,
            "payment_proofs": proofs,
            "public_base_url": get_public_server_url(request),
        },
    )


@app.post("/api/telegram/test")
def api_telegram_test(message: str = Form("Teste BRECHORISEE Telegram")) -> JSONResponse:
    with get_db() as con:
        result = telegram_send_admin_message(con, message or "Teste BRECHORISEE Telegram", related_type="teste")
    return JSONResponse({"ok": bool(result.get("ok")), "result": result})


@app.post("/api/telegram/control")
def api_telegram_control(text: str = Form(...), chat_id: str = Form("admin-local"), username: str = Form("admin")) -> JSONResponse:
    """Simula ou processa um comando vindo do Telegram sem chamar a API externa."""
    answer = telegram_process_text_command(text, chat_id=chat_id, username=username)
    with get_db() as con:
        result = telegram_send_admin_message(con, answer, related_type="telegram_control")
    return JSONResponse({"ok": True, "answer": answer, "telegram_result": result})


@app.post("/api/telegram/webhook")
async def api_telegram_webhook(request: Request) -> JSONResponse:
    """Webhook oficial do Telegram.

    Proteja com TELEGRAM_WEBHOOK_SECRET e chame a URL como:
    /api/telegram/webhook?secret=SEU_SEGREDO
    """
    provided = (request.query_params.get("secret") or request.headers.get("x-telegram-bot-api-secret-token") or "").strip()
    if TELEGRAM_COMMANDS_ENABLED and BRECHORISEE_ENV in {"production", "prod"} and not TELEGRAM_WEBHOOK_SECRET:
        security_event("telegram_webhook_missing_secret_blocked", severity="critical", details="TELEGRAM_WEBHOOK_SECRET ausente em produção.", request=request)
        return JSONResponse({"ok": False, "message": "Webhook Telegram sem segredo configurado em produção."}, status_code=503)
    if TELEGRAM_WEBHOOK_SECRET and not hmac.compare_digest(provided, TELEGRAM_WEBHOOK_SECRET):
        security_event("telegram_webhook_bad_secret", severity="warning", details="Segredo inválido.", request=request)
        return JSONResponse({"ok": False, "message": "Webhook Telegram não autorizado."}, status_code=403)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    message = payload.get("message") or payload.get("edited_message") or {}
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    chat_id = str(chat.get("id") or "")
    username = str(user.get("username") or chat.get("username") or user.get("first_name") or "Telegram")
    text = str(message.get("text") or "").strip()

    if not TELEGRAM_COMMANDS_ENABLED:
        with get_db() as con:
            telegram_record_message(con, "inbound", text or "[telegram desativado]", chat_id=chat_id, username=username, payload=payload, status="bloqueado", error="Comandos Telegram desativados.")
            log_security_event(con, "telegram_commands_disabled", severity="info", actor_type="telegram", actor_id=chat_id, path="/api/telegram/webhook", details=text[:300], request=request)
        return JSONResponse({"ok": False, "message": "Comandos Telegram desativados."}, status_code=403)

    if not telegram_chat_allowed(chat_id):
        with get_db() as con:
            telegram_record_message(con, "inbound", text or "[chat não autorizado]", chat_id=chat_id, username=username, payload=payload, status="bloqueado", error="Chat Telegram não autorizado.")
            log_security_event(con, "telegram_chat_blocked", severity="warning", actor_type="telegram", actor_id=chat_id, path="/api/telegram/webhook", details=f"username={username}", request=request)
        return JSONResponse({"ok": False, "message": "Chat Telegram não autorizado."}, status_code=403)

    # Comprovantes geralmente chegam como foto/documento com legenda.
    if message.get("photo") or message.get("document"):
        answer = telegram_register_payment_proof(payload)
    elif text:
        answer = telegram_process_text_command(text, chat_id=chat_id, username=username)
    else:
        with get_db() as con:
            telegram_record_message(con, "inbound", "[mensagem sem texto]", chat_id=chat_id, username=username, payload=payload, status="recebido")
        answer = "Mensagem recebida."

    with get_db() as con:
        telegram_send_admin_message(con, answer, related_type="telegram_webhook")
    return JSONResponse({"ok": True, "answer": answer})


def customer_checkout_profile(request: Request) -> dict[str, Any]:
    """Dados salvos da cliente para preencher automaticamente o checkout."""
    profile = {
        "customer_name": "",
        "customer_phone": "",
        "customer_instagram": "",
        "delivery_method": "retirada",
        "address": "",
        "payment_method": "pix",
        "pix_text": "",
        "payment_link": "",
        "notes": "",
        "delivery_lat": "",
        "delivery_lng": "",
        "delivery_maps_url": "",
        "logged": False,
    }
    account = customer_from_request(request)
    settings = get_store_settings()
    if settings.get("pix_text"):
        profile["pix_text"] = settings.get("pix_text") or ""
    if not account:
        return profile
    profile["logged"] = True
    keys = set(account.keys()) if hasattr(account, "keys") else set()
    profile["customer_name"] = account["name"] or ""
    profile["customer_phone"] = account["phone"] or ""
    profile["customer_instagram"] = account["instagram"] or ""
    if "default_delivery_method" in keys and account["default_delivery_method"]:
        profile["delivery_method"] = account["default_delivery_method"]
    if "address" in keys and account["address"]:
        profile["address"] = account["address"]
    if "payment_method" in keys and account["payment_method"]:
        profile["payment_method"] = account["payment_method"]
    if "pix_text" in keys and account["pix_text"]:
        profile["pix_text"] = account["pix_text"]
    if "payment_link" in keys and account["payment_link"]:
        profile["payment_link"] = account["payment_link"]
    if "checkout_notes" in keys and account["checkout_notes"]:
        profile["notes"] = account["checkout_notes"]
    if "delivery_lat" in keys and account["delivery_lat"]:
        profile["delivery_lat"] = account["delivery_lat"]
    if "delivery_lng" in keys and account["delivery_lng"]:
        profile["delivery_lng"] = account["delivery_lng"]
    if "delivery_maps_url" in keys and account["delivery_maps_url"]:
        profile["delivery_maps_url"] = account["delivery_maps_url"]

    # Usa o último pedido como fallback, sem apagar dados melhores do cadastro.
    try:
        with get_db() as con:
            last = con.execute(
                """
                SELECT * FROM online_orders
                WHERE customer_phone=? OR LOWER(customer_name)=LOWER(?)
                ORDER BY id DESC LIMIT 1
                """,
                (profile["customer_phone"], profile["customer_name"]),
            ).fetchone()
        if last:
            fallback_map = {
                "customer_instagram": last["customer_instagram"],
                "delivery_method": last["delivery_method"],
                "address": last["address"],
                "payment_method": last["payment_method"],
                "pix_text": last["pix_text"],
                "payment_link": last["payment_link"],
                "notes": last["notes"],
                "delivery_lat": last["delivery_lat"] if "delivery_lat" in set(last.keys()) else "",
                "delivery_lng": last["delivery_lng"] if "delivery_lng" in set(last.keys()) else "",
                "delivery_maps_url": last["delivery_maps_url"] if "delivery_maps_url" in set(last.keys()) else "",
            }
            for key, value in fallback_map.items():
                if not profile.get(key) and value:
                    profile[key] = value
    except Exception:
        pass
    return profile


def save_customer_checkout_profile(
    con: sqlite3.Connection,
    request: Request,
    customer_name: str,
    customer_phone: str,
    customer_instagram: str = "",
    delivery_method: str = "retirada",
    address: str = "",
    payment_method: str = "pix",
    pix_text: str = "",
    payment_link: str = "",
    notes: str = "",
    delivery_lat: str = "",
    delivery_lng: str = "",
    delivery_maps_url: str = "",
) -> None:
    """Atualiza o cadastro da cliente para a próxima compra já vir preenchida."""
    account = customer_from_request(request)
    customer_id = int(account["id"]) if account else None
    if not customer_id and customer_phone:
        row = con.execute("SELECT id FROM customers WHERE phone=? ORDER BY id DESC LIMIT 1", (customer_phone,)).fetchone()
        if row:
            customer_id = int(row["id"])
    if customer_id:
        con.execute(
            """
            UPDATE customers
            SET name=COALESCE(NULLIF(?,''), name),
                phone=COALESCE(NULLIF(?,''), phone),
                instagram=COALESCE(NULLIF(?,''), instagram),
                default_delivery_method=COALESCE(NULLIF(?,''), default_delivery_method),
                address=COALESCE(NULLIF(?,''), address),
                payment_method=COALESCE(NULLIF(?,''), payment_method),
                pix_text=COALESCE(NULLIF(?,''), pix_text),
                payment_link=COALESCE(NULLIF(?,''), payment_link),
                checkout_notes=COALESCE(NULLIF(?,''), checkout_notes),
                delivery_lat=COALESCE(NULLIF(?,''), delivery_lat),
                delivery_lng=COALESCE(NULLIF(?,''), delivery_lng),
                delivery_maps_url=COALESCE(NULLIF(?,''), delivery_maps_url)
            WHERE id=?
            """,
            (customer_name, customer_phone, customer_instagram, delivery_method, address, payment_method, pix_text, payment_link, notes, delivery_lat, delivery_lng, delivery_maps_url, customer_id),
        )
        return
    if customer_phone or customer_name:
        con.execute(
            """
            INSERT INTO customers(name, phone, instagram, default_delivery_method, address, payment_method, pix_text, payment_link, checkout_notes, delivery_lat, delivery_lng, delivery_maps_url, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (customer_name or "Cliente", customer_phone, customer_instagram, delivery_method, address, payment_method, pix_text, payment_link, notes, delivery_lat, delivery_lng, delivery_maps_url, now_iso()),
        )


@app.get("/online")
def online_redirect() -> Response:
    return RedirectResponse(url="/loja", status_code=302)

@app.get("/site")
def site_redirect() -> Response:
    return RedirectResponse(url="/loja", status_code=302)

@app.get("/loja", response_class=HTMLResponse)
def public_storefront(request: Request, q: str = "", categoria: str = "") -> Response:
    auto_sync_if_local_empty("public_storefront")
    settings = get_store_settings()
    products = loja_rows(q=q, category=categoria, limit=120)
    with get_db() as con:
        categories = con.execute(
            """
            SELECT category AS name, COUNT(*) AS total FROM products
            WHERE status='disponivel' AND COALESCE(category,'') <> ''
            GROUP BY category
            ORDER BY total DESC, category
            LIMIT 20
            """
        ).fetchall()
    return templates.TemplateResponse(
        "online_store.html",
        {
            "request": request,
            "products": products,
            "q": q,
            "categoria": categoria,
            "categories": categories,
            "settings": settings,
            "active": "online_store",
            "public_mode": True,
        },
    )


@app.get("/loja/produto/{code}", response_class=HTMLResponse)
def online_product_page(request: Request, code: str, origem: str = "loja") -> Response:
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE UPPER(code)=UPPER(?) OR CAST(id AS TEXT)=?", (code.strip(), code.strip())).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Peça não encontrada.")
        media = con.execute("SELECT * FROM product_media WHERE product_id=? ORDER BY id DESC", (product["id"],)).fetchall()
        similar = find_similar_products(product, limit=6)
        con.execute(
            "INSERT INTO product_interest_events(product_id, event_type, source, notes, created_at) VALUES(?,?,?,?,?)",
            (product["id"], "loja_produto_aberto", origem or "loja", "Produto aberto na loja online self-service.", now_iso()),
        )
    return templates.TemplateResponse(
        "online_product.html",
        {
            "request": request,
            "product": product,
            "media": media,
            "similar": similar,
            "settings": get_store_settings(),
            "active": "online_store",
            "public_mode": True,
        },
    )


@app.get("/loja/carrinho", response_class=HTMLResponse)
def online_cart_page(request: Request) -> Response:
    checkout_profile = customer_checkout_profile(request)
    return templates.TemplateResponse(
        "online_cart.html",
        {
            "request": request,
            "settings": get_store_settings(),
            "checkout_profile": checkout_profile,
            "active": "online_store",
            "public_mode": True,
        },
    )


@app.post("/loja/pedido", response_class=HTMLResponse)
def online_checkout(
    request: Request,
    codes: str = Form(...),
    customer_name: str = Form(...),
    customer_phone: str = Form(""),
    customer_instagram: str = Form(""),
    delivery_method: str = Form("retirada"),
    address: str = Form(""),
    payment_method: str = Form("pix"),
    pix_text: str = Form(""),
    payment_link: str = Form(""),
    notes: str = Form(""),
    delivery_lat: str = Form(""),
    delivery_lng: str = Form(""),
    delivery_maps_url: str = Form(""),
) -> Response:
    customer_name = (customer_name or "").strip()[:160]
    customer_phone = normalize_phone(customer_phone)
    customer_instagram = (customer_instagram or "").strip()[:120]
    delivery_method = delivery_method if delivery_method in {"retirada", "entrega"} else "retirada"
    payment_method = (payment_method or "pix").strip()[:80]
    if len(customer_name) < 2:
        raise HTTPException(status_code=400, detail="Informe o nome da cliente.")
    code_list = []
    seen = set()
    for raw in str(codes or "").replace(";", ",").replace("\n", ",").split(","):
        code = raw.strip().upper()
        if code and code not in seen:
            seen.add(code)
            code_list.append(code)
    if not code_list:
        raise HTTPException(status_code=400, detail="Carrinho vazio.")
    placeholders = ",".join("?" for _ in code_list)
    order_id = None
    order_token = ""
    with get_db() as con:
        products = con.execute(f"SELECT * FROM products WHERE UPPER(code) IN ({placeholders})", code_list).fetchall()
        found = {str(p["code"]).upper(): p for p in products}
        missing = [c for c in code_list if c not in found]
        unavailable = [p["code"] for p in products if p["status"] != "disponivel"]
        if missing:
            raise HTTPException(status_code=400, detail=f"Peça não encontrada: {', '.join(missing)}")
        if unavailable:
            raise HTTPException(status_code=400, detail=f"Peça indisponível: {', '.join(unavailable)}")
        try:
            prices = [validate_money_amount(p["sale_price"], f"Preço da peça {p['code']}", minimum=0, allow_zero=False) for p in products]
        except HTTPException:
            raise

        customer_account_id = find_customer_account_id_for_identity(con, customer_name, customer_phone, "")
        if not customer_account_id:
            account = customer_from_request(request)
            if account:
                customer_account_id = int(account["id"])

        save_customer_checkout_profile(
            con,
            request,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_instagram=customer_instagram,
            delivery_method=delivery_method,
            address=address,
            payment_method=payment_method,
            pix_text=pix_text,
            payment_link=payment_link,
            notes=notes,
            delivery_lat=delivery_lat,
            delivery_lng=delivery_lng,
            delivery_maps_url=build_google_maps_url(address, delivery_lat, delivery_lng, delivery_maps_url),
        )

        subtotal = round(sum(prices), 2)
        total = subtotal
        code = online_order_code()
        order_token = ensure_unique_public_token(con, "online_orders", "public_token", "ord_")
        expires_at = (datetime.now() + timedelta(hours=int(get_store_settings().get("default_reservation_hours") or 24))).strftime("%Y-%m-%d %H:%M:%S")
        cur = con.execute(
            """
            INSERT INTO online_orders(order_code, customer_name, customer_phone, customer_instagram, delivery_method, address, delivery_lat, delivery_lng, delivery_maps_url, payment_method,
              pix_text, payment_link, subtotal, discount, total, status, notes, created_at, expires_at, public_token, customer_account_id, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (code, customer_name, customer_phone, customer_instagram, delivery_method, address, delivery_lat or None, delivery_lng or None, build_google_maps_url(address, delivery_lat, delivery_lng, delivery_maps_url), payment_method,
             pix_text, payment_link, subtotal, 0, total, "aguardando_pagamento", notes, now_iso(), expires_at, order_token, customer_account_id, now_iso()),
        )
        order_id = cur.lastrowid
        for p, price in zip(products, prices):
            con.execute(
                "INSERT INTO online_order_items(order_id, product_id, code, title, price, status, created_at) VALUES(?,?,?,?,?,?,?)",
                (order_id, p["id"], p["code"], p["title"], price, "reservado", now_iso()),
            )
            reserved_ok = reserve_product_for_customer(
                con,
                int(p["id"]),
                customer_name=customer_name,
                customer_phone=customer_phone,
                source="pedido_online",
                notes=f"Reservada pelo pedido online {code} para {customer_name or 'cliente'}. Peça retirada do portfólio público.",
                expires_at=expires_at,
            )
            if not reserved_ok:
                con.execute("UPDATE online_orders SET status='conflito', tracking_updated_at=? WHERE id=?", (now_iso(), order_id))
                raise HTTPException(status_code=409, detail=f"Peça indisponível para reserva: {p['code']}")
        if TELEGRAM_NOTIFY_ORDERS:
            try:
                order_row = con.execute("SELECT * FROM online_orders WHERE id=?", (int(order_id),)).fetchone()
                item_rows = con.execute("SELECT * FROM online_order_items WHERE order_id=?", (int(order_id),)).fetchall()
                telegram_send_admin_message(con, telegram_order_summary(order_row, item_rows), related_type="online_order", related_id=int(order_id))
            except Exception as exc:
                logger.warning("Falha ao notificar pedido online no Telegram: %s", exc)
    return RedirectResponse(url=f"/loja/pedido/{order_token}", status_code=303)


@app.get("/loja/pedido/{order_id}", response_class=HTMLResponse)
def online_order_public_page(request: Request, order_id: str) -> Response:
    order, items = load_online_order_public(order_id, request)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    msg = online_order_message(order, items, request)
    store_phone = str(get_store_settings().get("whatsapp") or "").replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    # O WhatsApp do pedido deve ir para a loja, não para a própria cliente.
    wa_url = f"https://wa.me/55{store_phone}?text=" if store_phone and not store_phone.startswith("55") else f"https://wa.me/{store_phone}?text=" if store_phone else "https://wa.me/?text="
    return templates.TemplateResponse(
        "online_order.html",
        {
            "request": request,
            "order": order,
            "items": items,
            "message": msg,
            "whatsapp_url": wa_url + quote_plus(msg),
            "status_label": online_order_status_label(order["status"]),
            "tracking": delivery_tracking_payload(order),
            "settings": get_store_settings(),
            "active": "online_store",
            "public_mode": True,
        },
    )


@app.get("/loja-admin", response_class=HTMLResponse)
def online_orders_admin(request: Request, status: str = "todos") -> Response:
    where = ""
    params: list[Any] = []
    if status != "todos":
        where = "WHERE status=?"
        params.append(status)
    with get_db() as con:
        orders = con.execute(
            f"""
            SELECT o.*, COUNT(oi.id) AS item_count
            FROM online_orders o
            LEFT JOIN online_order_items oi ON oi.order_id=o.id
            {where}
            GROUP BY o.id
            ORDER BY o.id DESC
            LIMIT 120
            """,
            params,
        ).fetchall()
    return templates.TemplateResponse(
        "online_orders_admin.html",
        {"request": request, "orders": orders, "status": status, "active": "online_store"},
    )


@app.post("/loja-admin/{order_id}/confirmar")
def online_order_confirm_payment(order_id: int) -> Response:
    order, _items = load_online_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    with get_db() as con:
        ok, msg, sale_id = create_sale_for_online_order(con, int(order_id), source_label="venda_online_admin")
        if not ok:
            log_security_event(con, "online_payment_confirmation_failed", severity="warning", actor_type="admin", path=f"/loja-admin/{order_id}/confirmar", details=msg)
            raise HTTPException(status_code=400, detail=msg)
    return RedirectResponse(url=f"/sales/{sale_id}" if sale_id else "/loja-admin?status=todos", status_code=303)


@app.post("/loja-admin/{order_id}/status")
def online_order_update_status(order_id: int, status: str = Form(...)) -> Response:
    allowed = {"aguardando_pagamento", "pago", "separado", "em_entrega", "cliente_ausente", "entregue", "cancelado", "conflito"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Status inválido.")
    if status == "pago":
        with get_db() as con:
            ok, msg, sale_id = create_sale_for_online_order(con, int(order_id), source_label="venda_online_status_pago")
            if not ok:
                log_security_event(con, "online_status_pago_failed", severity="warning", actor_type="admin", path=f"/loja-admin/{order_id}/status", details=msg)
                raise HTTPException(status_code=400, detail=msg)
        return RedirectResponse(url=f"/sales/{sale_id}" if sale_id else "/loja-admin", status_code=303)

    with get_db() as con:
        order = con.execute("SELECT * FROM online_orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        if order["status"] in {"pago", "entregue"} and status in {"aguardando_pagamento", "cancelado", "conflito"}:
            raise HTTPException(status_code=400, detail="Pedido pago/entregue não pode voltar ou ser cancelado por este botão.")
        if status == "em_entrega":
            con.execute(
                "UPDATE online_orders SET status=?, delivery_started_at=COALESCE(delivery_started_at, ?), tracking_updated_at=?, updated_at=? WHERE id=?",
                (status, now_iso(), now_iso(), now_iso(), order_id),
            )
        else:
            con.execute("UPDATE online_orders SET status=?, tracking_updated_at=?, updated_at=? WHERE id=?", (status, now_iso(), now_iso(), order_id))
        if status == "cancelado":
            rows = con.execute("SELECT product_id FROM online_order_items WHERE order_id=?", (order_id,)).fetchall()
            for row in rows:
                con.execute("UPDATE products SET status='disponivel', sync_updated_at=? WHERE id=? AND status='reservado'", (now_iso(), row["product_id"]))
                con.execute("INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)", (row["product_id"], "pedido_online_cancelado", f"Pedido online {order['order_code']} cancelado. Peça voltou para disponível.", now_iso()))
            con.execute("UPDATE online_order_items SET status='cancelado' WHERE order_id=?", (order_id,))
    return RedirectResponse(url="/loja-admin", status_code=303)






@app.get("/ia-clientes", response_class=HTMLResponse)
def ai_customers_page(request: Request, product_id: int | None = None) -> Response:
    with get_db() as con:
        products = con.execute(
            "SELECT * FROM products WHERE status='disponivel' ORDER BY id DESC LIMIT 80"
        ).fetchall()
        accounts = con.execute(
            """
            SELECT ca.*, c.preferences, c.measurements,
                   (SELECT COUNT(*) FROM customer_notifications n WHERE n.customer_account_id=ca.id) AS notifications_count,
                   (SELECT MAX(created_at) FROM customer_notifications n WHERE n.customer_account_id=ca.id) AS last_notification_at
            FROM customer_accounts ca
            LEFT JOIN customers c ON c.id = ca.customer_id
            WHERE ca.active=1
            ORDER BY ca.id DESC
            LIMIT 300
            """
        ).fetchall()
        selected = None
        recommendations: list[dict[str, Any]] = []
        if product_id:
            selected = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            if selected:
                for account in accounts:
                    match = ai_product_customer_match(selected, account, con=con)
                    if match["score"] >= 45:
                        recommendations.append({
                            "account": account,
                            "match": match,
                            "message": personalized_customer_message(selected, account, match),
                        })
                recommendations.sort(key=lambda item: item["match"]["score"], reverse=True)
                recommendations = recommendations[:80]

        # Visão por cliente: melhores peças disponíveis para ela.
        customer_cards: list[dict[str, Any]] = []
        for account in accounts[:80]:
            best: list[dict[str, Any]] = []
            for product in products[:60]:
                match = ai_product_customer_match(product, account, con=con)
                if match["score"] >= 65:
                    best.append({"product": product, "match": match})
            best.sort(key=lambda item: item["match"]["score"], reverse=True)
            profile = customer_ai_profile(con, account)
            customer_cards.append({"account": account, "profile": profile, "best": best[:5]})

    return templates.TemplateResponse(
        "ai_customers.html",
        {
            "request": request,
            "active": "ai_customers",
            "products": products,
            "selected": selected,
            "recommendations": recommendations,
            "customer_cards": customer_cards,
        },
    )


@app.post("/ia-clientes/gerar/{product_id}")
def ai_customers_generate_notifications(product_id: int) -> Response:
    with get_db() as con:
        count = queue_new_product_notifications(con, product_id)
        con.execute(
            "INSERT INTO audit_logs(user_name, action, entity, entity_id, details, created_at) VALUES(?,?,?,?,?,?)",
            ("IA Clientes", "gerar_notificacoes_personalizadas", "product", str(product_id), f"{count} notificação(ões) criada(s).", now_iso()),
        )
    return RedirectResponse(url=f"/ia-clientes?product_id={product_id}", status_code=303)


@app.get("/api/ia-clientes/recomendacoes/{product_id}")
def api_ai_customer_recommendations(product_id: int) -> JSONResponse:
    with get_db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            return JSONResponse({"ok": False, "message": "Peça não encontrada."}, status_code=404)
        accounts = con.execute("SELECT * FROM customer_accounts WHERE active=1 ORDER BY id DESC LIMIT 500").fetchall()
        results = []
        for account in accounts:
            match = ai_product_customer_match(product, account, con=con)
            if match["score"] >= 45:
                results.append({
                    "customer": dict(account),
                    "score": match["score"],
                    "label": match["label"],
                    "reasons": match["reasons"],
                    "message": personalized_customer_message(product, account, match),
                })
        results.sort(key=lambda r: r["score"], reverse=True)
    return JSONResponse({"ok": True, "product": dict(product), "results": results[:100]})



def get_or_create_active_live_session(con: sqlite3.Connection) -> sqlite3.Row:
    row = con.execute("SELECT * FROM live_sessions WHERE status IN ('aberta','ao_vivo') ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        return row
    cur = con.execute(
        "INSERT INTO live_sessions(title, status, notes, created_at) VALUES(?,?,?,?)",
        (f"Live {datetime.now().strftime('%d/%m/%Y %H:%M')}", "aberta", "Sessão criada automaticamente.", now_iso()),
    )
    return con.execute("SELECT * FROM live_sessions WHERE id=?", (cur.lastrowid,)).fetchone()


def live_recap_caption(session: sqlite3.Row, items: list[sqlite3.Row]) -> str:
    lines = [
        f"Repescagem BRECHORISEE ✨",
        "",
        "Peças que apareceram na live e ainda podem estar disponíveis:",
        "",
    ]
    for idx, item in enumerate(items, start=1):
        status = item["status_snapshot"] or ""
        price = money(item["product_price"])
        lines.append(f"{idx}. {item['product_title']} • {item['product_code']} • {price} • {status}")
    lines.extend([
        "",
        "Quer reservar alguma? Chame no direct ou WhatsApp 💌",
        "#brechorisee #modacircular #brechoonline #achadinhos #pecaunica",
    ])
    return "\n".join(lines)


@app.get("/live", response_class=HTMLResponse)
def live_page(request: Request, q: str = "") -> Response:
    with get_db() as con:
        session = get_or_create_active_live_session(con)
        rows = search_products_rows(q=q, status="disponivel", limit=40)
        ignored = con.execute(
            "SELECT product_id FROM live_ignored_products WHERE live_session_id=?",
            (session["id"],),
        ).fetchall()
        ignored_ids = {int(r["product_id"]) for r in ignored}
        products = [p for p in rows if int(p["id"]) not in ignored_ids and p["status"] == "disponivel"]
        items = con.execute(
            """
            SELECT li.*, p.image_filename, p.status AS current_status
            FROM live_session_items li
            LEFT JOIN products p ON p.id = li.product_id
            WHERE li.live_session_id=?
            ORDER BY li.id DESC
            LIMIT 80
            """,
            (session["id"],),
        ).fetchall()
        sessions = con.execute("SELECT * FROM live_sessions ORDER BY id DESC LIMIT 20").fetchall()
    return templates.TemplateResponse(
        "live.html",
        {
            "request": request,
            "active": "live",
            "session": session,
            "products": products,
            "items": items,
            "sessions": sessions,
            "q": q,
        },
    )


@app.post("/live/items")
def live_add_item(product_id: int = Form(...), action: str = Form("fixada"), notes: str = Form("")) -> Response:
    allowed = {"reconhecida", "fixada", "vendida", "ignorada", "repescagem", "cliente_clicou"}
    if action not in allowed:
        action = "reconhecida"
    with get_db() as con:
        session = get_or_create_active_live_session(con)
        _live_insert_item(con, int(session["id"]), product_id, action, notes, 0.0)
        if action == "ignorada":
            con.execute("UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='ignorada', current_product_event_id=NULL WHERE id=? AND current_product_id=?", (now_iso(), session["id"], product_id))
    return RedirectResponse(url="/live", status_code=303)


@app.post("/live/items/{item_id}/sold")
def live_mark_item_sold(request: Request, item_id: int) -> Response:
    with get_db() as con:
        item = con.execute("SELECT * FROM live_session_items WHERE id=?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item da live não encontrado.")
        product = con.execute("SELECT * FROM products WHERE id=?", (item["product_id"],)).fetchone()
        if product and product["status"] != "vendido":
            sold_time = now_iso()
            con.execute("UPDATE products SET status='vendido', sold_at=?, sync_updated_at=? WHERE id=?", (sold_time, sold_time, product["id"]))
            con.execute(
                "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                (product["id"], "live_venda", "Marcada como vendida pela live. Sai da vitrine e do reconhecimento.", sold_time),
            )
            enqueue_product_cloud_sync(con, product["id"], reason="live_vendida")
        con.execute(
            "UPDATE live_session_items SET action='vendida', status_snapshot='vendido', notes=COALESCE(notes,'') || ' • marcada como vendida' WHERE id=?",
            (item_id,),
        )
        con.execute("UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_item', current_product_event_id=NULL WHERE id=? AND current_product_id=?", (now_iso(), item["live_session_id"], item["product_id"]))
    try:
        if is_cloud_sync_enabled(request):
            threading.Thread(target=run_auto_cloud_sync, kwargs={"force": True}, daemon=True).start()
    except Exception:
        pass
    return RedirectResponse(url="/live", status_code=303)


@app.post("/live/items/{item_id}/ignore")
def live_ignore_item(item_id: int) -> Response:
    with get_db() as con:
        item = con.execute("SELECT * FROM live_session_items WHERE id=?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item da live não encontrado.")
        con.execute(
            "INSERT OR IGNORE INTO live_ignored_products(live_session_id, product_id, created_at) VALUES(?,?,?)",
            (item["live_session_id"], item["product_id"], now_iso()),
        )
        con.execute("UPDATE live_session_items SET action='ignorada' WHERE id=?", (item_id,))
        con.execute("UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_item', current_product_event_id=NULL WHERE id=? AND current_product_id=?", (now_iso(), item["live_session_id"], item["product_id"]))
    return RedirectResponse(url="/live", status_code=303)


@app.post("/live/end")
def live_end_session(session_id: int = Form(...)) -> Response:
    with get_db() as con:
        con.execute("UPDATE live_sessions SET status='encerrada', ended_at=? WHERE id=?", (now_iso(), session_id))
    return RedirectResponse(url=f"/live/finalizar/{session_id}", status_code=303)


@app.get("/live/repescagem/{session_id}", response_class=HTMLResponse)
def live_recap_page(request: Request, session_id: int, msg: str = "") -> Response:
    with get_db() as con:
        session = con.execute("SELECT * FROM live_sessions WHERE id=?", (session_id,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Live não encontrada.")
        items = con.execute(
            """
            SELECT li.*, p.image_filename, p.status AS current_status
            FROM live_session_items li
            JOIN products p ON p.id = li.product_id
            WHERE li.live_session_id=?
              AND li.action IN ('reconhecida','fixada','repescagem','cliente_clicou')
              AND p.status='disponivel'
            ORDER BY li.id ASC
            """,
            (session_id,),
        ).fetchall()
        caption = live_recap_caption(session, items)
    return templates.TemplateResponse(
        "live_recap.html",
        {
            "request": request,
            "active": "live",
            "session": session,
            "items": items,
            "caption": caption,
            "instagram_url": "https://www.instagram.com/",
            "msg": msg,
        },
    )


@app.post("/live/repescagem/{session_id}/save")
def live_recap_save(session_id: int, caption: str = Form(""), selected_item_ids: list[int] | None = Form(None)) -> Response:
    with get_db() as con:
        session = con.execute("SELECT * FROM live_sessions WHERE id=?", (session_id,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Live não encontrada.")
        item_ids = selected_item_ids or []
        con.execute(
            "INSERT INTO live_recap_posts(live_session_id, title, caption, item_ids, status, created_at) VALUES(?,?,?,?,?,?)",
            (session_id, f"Repescagem {session['title']}", caption, json.dumps(item_ids), "pronto", now_iso()),
        )
        con.execute("UPDATE live_sessions SET recap_created_at=? WHERE id=?", (now_iso(), session_id))
    return RedirectResponse(url=f"/live/finalizar/{session_id}", status_code=303)


def product_reservation_info(con: sqlite3.Connection, product_id: int) -> dict[str, Any] | None:
    """Retorna para quem a peça está reservada/comprada sem expor em repescagem pública."""
    # 1) Pedido online aguardando pagamento/reserva.
    row = con.execute(
        """
        SELECT o.id AS order_id, o.order_code, o.customer_name, o.customer_phone, o.customer_instagram,
               o.status, o.expires_at, 'pedido_online' AS source
        FROM online_order_items oi
        JOIN online_orders o ON o.id = oi.order_id
        WHERE oi.product_id=?
          AND o.status NOT IN ('cancelado','pago','entregue','conflito')
        ORDER BY o.id DESC
        LIMIT 1
        """,
        (int(product_id),),
    ).fetchone()
    if row:
        return {
            "reserved": True,
            "reserved_for": row["customer_name"] or "Cliente",
            "reserved_phone": row["customer_phone"] or "",
            "reserved_instagram": row["customer_instagram"] or "",
            "reservation_source": "Pedido online",
            "reservation_code": row["order_code"] or f"Pedido #{row['order_id']}",
            "reservation_expires_at": row["expires_at"] or "",
        }

    # 2) Pedido WhatsApp aguardando pagamento.
    row = con.execute(
        """
        SELECT wo.id AS order_id, wo.customer_name, wo.phone, wo.status, wo.reservation_expires_at,
               'pedido_whatsapp' AS source
        FROM whatsapp_order_items woi
        JOIN whatsapp_orders wo ON wo.id = woi.order_id
        WHERE woi.product_id=?
          AND wo.status NOT IN ('cancelado','pago','entregue')
        ORDER BY wo.id DESC
        LIMIT 1
        """,
        (int(product_id),),
    ).fetchone()
    if row:
        return {
            "reserved": True,
            "reserved_for": row["customer_name"] or "Cliente",
            "reserved_phone": row["phone"] or "",
            "reserved_instagram": "",
            "reservation_source": "Pedido WhatsApp",
            "reservation_code": f"WhatsApp #{row['order_id']}",
            "reservation_expires_at": row["reservation_expires_at"] or "",
        }

    # 3) Reserva manual.
    row = con.execute(
        """
        SELECT r.*, c.phone AS customer_phone, c.instagram AS customer_instagram
        FROM reservations r
        LEFT JOIN customers c ON c.id = r.customer_id
        WHERE r.product_id=? AND r.status='ativa'
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (int(product_id),),
    ).fetchone()
    if row:
        return {
            "reserved": True,
            "reserved_for": row["customer_name"] or "Cliente",
            "reserved_phone": row["customer_phone"] or "",
            "reserved_instagram": row["customer_instagram"] or "",
            "reservation_source": "Reserva",
            "reservation_code": f"Reserva #{row['id']}",
            "reservation_expires_at": row["expires_at"] or "",
        }
    return None


def live_product_payload_with_reservation(con: sqlite3.Connection, product: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    payload = live_product_payload(product) if product else None
    if not payload:
        return None
    if payload.get("status") == "reservado":
        info = product_reservation_info(con, int(payload["id"])) or {"reserved": True, "reserved_for": "Cliente"}
        payload.update(info)
        payload["reserved_label"] = f"Reservada para {info.get('reserved_for') or 'cliente'}"
        payload["public_url"] = ""
        payload["store_url"] = ""
        payload["source_label"] = payload["reserved_label"]
    return payload


def ensure_product_reservation_record(
    con: sqlite3.Connection,
    product_id: int,
    customer_name: str = "",
    customer_phone: str = "",
    notes: str = "",
    expires_at: str = "",
) -> None:
    """Cria registro de reserva para ficar claro no reconhecimento: reservada para Nome."""
    existing = con.execute(
        "SELECT id FROM reservations WHERE product_id=? AND status='ativa' ORDER BY id DESC LIMIT 1",
        (int(product_id),),
    ).fetchone()
    if existing:
        return
    customer_id = None
    clean_phone = "".join(ch for ch in str(customer_phone or "") if ch.isdigit())
    if customer_name or clean_phone:
        try:
            customer_id = find_or_create_customer_for_account(con, customer_name or "Cliente", clean_phone, "")
        except Exception:
            customer_id = None
    con.execute(
        "INSERT INTO reservations(product_id, customer_id, customer_name, expires_at, status, notes, created_at) VALUES(?,?,?,?,?,?,?)",
        (int(product_id), customer_id, customer_name or "Cliente", expires_at, "ativa", notes, now_iso()),
    )



def reserve_product_for_customer(
    con: sqlite3.Connection,
    product_id: int,
    customer_name: str,
    customer_phone: str = "",
    source: str = "reserva",
    notes: str = "",
    expires_at: str = "",
) -> bool:
    """Reserva uma peça e retira automaticamente do portfólio/vitrine/repescagem pública.

    Retorna True quando a peça saiu de 'disponivel' para 'reservado'.
    Peças já reservadas/vendidas ficam bloqueadas para outras clientes.
    """
    product = con.execute("SELECT * FROM products WHERE id=?", (int(product_id),)).fetchone()
    if not product or product["status"] != "disponivel":
        return False

    con.execute("UPDATE products SET status='reservado' WHERE id=? AND status='disponivel'", (int(product_id),))
    ensure_product_reservation_record(
        con,
        int(product_id),
        customer_name=customer_name or "Cliente",
        customer_phone=customer_phone or "",
        notes=notes or f"Reservada por {source}.",
        expires_at=expires_at or "",
    )
    con.execute(
        "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
        (
            int(product_id),
            source,
            notes or f"Peça reservada para {customer_name or 'cliente'}. Retirada do portfólio público automaticamente.",
            now_iso(),
        ),
    )
    try:
        enqueue_product_cloud_sync(con, int(product_id), reason="reserved")
    except Exception:
        pass
    return True



def live_product_payload(product: sqlite3.Row | None) -> dict[str, Any] | None:
    if not product:
        return None
    image_filename = product['image_filename'] if 'image_filename' in product.keys() else ''
    image_url = f"/static/uploads/{image_filename}" if image_filename else ""
    payload = {
        "id": int(product["id"]),
        "code": product["code"],
        "title": product["title"],
        "price": float(product["sale_price"] or 0),
        "price_label": money(product["sale_price"] or 0),
        "size": product["size"] or "",
        "brand": product["brand"] or "",
        "color": product["color"] or "",
        "status": product["status"] or "",
        "image_url": image_url,
        "public_url": f"/cliente/peca/{product['code']}" if (product["status"] or "") == "disponivel" else "",
        "store_url": f"/loja/produto/{product['code']}" if (product["status"] or "") == "disponivel" else "",
        "characteristics": product["characteristics"] or "",
        "measurements": product["measurements"] or "",
    }
    keys = set(product.keys()) if hasattr(product, "keys") else set()
    clip_filename = product["clip_filename"] if "clip_filename" in keys else ""
    if clip_filename:
        payload["clip_url"] = f"/static/live/clips/{clip_filename}"
        payload["clip_filename"] = clip_filename
        payload["clip_start_seconds"] = product["clip_start_seconds"] if "clip_start_seconds" in keys else None
        payload["clip_end_seconds"] = product["clip_end_seconds"] if "clip_end_seconds" in keys else None
    return payload


def live_reference_products(con: sqlite3.Connection, session_id: int, current_product_id: int | None = None, limit: int = 4) -> list[sqlite3.Row]:
    """Peças/referências visíveis agora na live.

    Profissional:
    - referência automática expira em poucos segundos quando não aparece mais;
    - peça fixada/manual continua até o admin trocar;
    - vendidas/removidas/ignoradas deixam de aparecer.
    """
    params: list[Any] = [session_id, f"-{max(3, int(LIVE_REFERENCE_STALE_SECONDS))} seconds"]
    order_current = ""
    if current_product_id:
        order_current = "CASE WHEN p.id=? THEN 0 ELSE 1 END,"
        order_param = int(current_product_id)
    else:
        order_param = None
    if order_param is not None:
        params.append(order_param)
    params.append(int(limit))
    return con.execute(
        f"""
        SELECT
          p.*,
          MAX(li.id) AS last_live_item_id,
          (
            SELECT l2.clip_filename
            FROM live_session_items l2
            WHERE l2.live_session_id=li.live_session_id
              AND l2.product_id=p.id
              AND COALESCE(l2.clip_filename,'') <> ''
            ORDER BY l2.id DESC
            LIMIT 1
          ) AS clip_filename,
          (
            SELECT l2.clip_start_seconds
            FROM live_session_items l2
            WHERE l2.live_session_id=li.live_session_id
              AND l2.product_id=p.id
              AND COALESCE(l2.clip_filename,'') <> ''
            ORDER BY l2.id DESC
            LIMIT 1
          ) AS clip_start_seconds,
          (
            SELECT l2.clip_end_seconds
            FROM live_session_items l2
            WHERE l2.live_session_id=li.live_session_id
              AND l2.product_id=p.id
              AND COALESCE(l2.clip_filename,'') <> ''
            ORDER BY l2.id DESC
            LIMIT 1
          ) AS clip_end_seconds
        FROM live_session_items li
        JOIN products p ON p.id = li.product_id
        WHERE li.live_session_id=?
          AND li.action IN ('reconhecida','fixada','cliente_clicou','repescagem','referencia')
          AND (
                li.action IN ('fixada','cliente_clicou','repescagem')
                OR datetime(li.created_at) >= datetime('now', ?)
              )
          AND p.status='disponivel'
          AND NOT EXISTS (
            SELECT 1 FROM live_session_items rx
            WHERE rx.live_session_id=li.live_session_id
              AND rx.product_id=p.id
              AND rx.action='removida'
          )
          AND NOT EXISTS (
            SELECT 1 FROM live_ignored_products ig
            WHERE ig.live_session_id=li.live_session_id
              AND ig.product_id=p.id
          )
        GROUP BY p.id
        ORDER BY {order_current} last_live_item_id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()



def live_viewer_count(con: sqlite3.Connection, session_id: int, active_seconds: int = 45) -> int:
    """Conta clientes realmente ativos na tela da live, sem número fake."""
    cutoff = (datetime.now() - timedelta(seconds=max(10, int(active_seconds)))).strftime("%Y-%m-%d %H:%M:%S")
    try:
        con.execute("DELETE FROM live_viewers WHERE last_seen_at < ?", (cutoff,))
        row = con.execute(
            "SELECT COUNT(*) FROM live_viewers WHERE live_session_id=? AND last_seen_at >= ?",
            (int(session_id), cutoff),
        ).fetchone()
        return int(row[0] or 0)
    except Exception:
        return 0


def record_live_viewer(con: sqlite3.Connection, session_id: int, request: Request | None = None) -> int:
    """Registra presença apenas quando a cliente abre a live no app/portal cliente."""
    account_id = None
    viewer_key = ""
    if request is not None:
        try:
            account = customer_from_request(request)
            if account:
                account_id = int(account["id"])
                viewer_key = f"cliente:{account_id}"
        except Exception:
            account_id = None
        if not viewer_key:
            raw = request.cookies.get(CUSTOMER_COOKIE_NAME) or ""
            viewer_key = "anon:" + hashlib.sha256((raw or (request.client.host if request.client else "anon")).encode("utf-8")).hexdigest()[:24]
    if not viewer_key:
        viewer_key = f"anon:{secrets.token_hex(8)}"
    now = now_iso()
    try:
        con.execute(
            """
            INSERT INTO live_viewers(live_session_id, viewer_key, customer_account_id, last_seen_at, created_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(live_session_id, viewer_key)
            DO UPDATE SET last_seen_at=excluded.last_seen_at, customer_account_id=excluded.customer_account_id
            """,
            (int(session_id), viewer_key, account_id, now, now),
        )
    except Exception:
        pass
    return live_viewer_count(con, int(session_id))


def active_or_last_live_info(request: Request | None = None) -> dict[str, Any] | None:
    with get_db() as con:
        session = con.execute(
            "SELECT * FROM live_sessions WHERE status IN ('ao_vivo','aberta','encerrada','arquivada','otimizada') ORDER BY CASE WHEN status='ao_vivo' THEN 0 WHEN status='aberta' THEN 1 ELSE 2 END, id DESC LIMIT 1"
        ).fetchone()
        if not session:
            return None
        current_product = None
        current_product_id = int(session['current_product_id']) if session['current_product_id'] else None
        current_source = session["current_product_source"] if "current_product_source" in session.keys() else ""
        current_set_at = session["current_product_set_at"] if "current_product_set_at" in session.keys() else ""
        if current_product_id and (session["status"] or "") == "ao_vivo" and current_source in {"reconhecida", "sem_reconhecimento", "android_overlay_live"}:
            try:
                if current_set_at:
                    parsed_set_at = datetime.strptime(str(current_set_at)[:19], "%Y-%m-%d %H:%M:%S")
                    if (datetime.now() - parsed_set_at).total_seconds() > max(3, int(LIVE_CURRENT_STALE_SECONDS)):
                        con.execute(
                            "UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_stale_live', current_product_event_id=NULL WHERE id=?",
                            (now_iso(), session["id"]),
                        )
                        current_product_id = None
            except Exception:
                pass
        if current_product_id:
            current_product = con.execute("SELECT * FROM products WHERE id=? AND status='disponivel'", (current_product_id,)).fetchone()
            if not current_product:
                con.execute("UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_unavailable', current_product_event_id=NULL WHERE id=?", (now_iso(), session['id']))
                current_product_id = None
        # Em live ao vivo, não ressuscita peça antiga pelo histórico. Se saiu da tela, fica sem peça.
        # Para lives encerradas/arquivadas, ainda é útil mostrar a última peça como histórico.
        if not current_product and (session["status"] or "") not in {"ao_vivo", "aberta"}:
            current_product = con.execute(
                """
                SELECT p.* FROM live_session_items li
                JOIN products p ON p.id = li.product_id
                WHERE li.live_session_id=? AND li.action IN ('reconhecida','fixada','cliente_clicou') AND p.status='disponivel'
                ORDER BY li.id DESC LIMIT 1
                """,
                (session['id'],),
            ).fetchone()
            current_product_id = int(current_product['id']) if current_product else None
        reference_products = [live_product_payload(p) for p in live_reference_products(con, int(session['id']), current_product_id=current_product_id, limit=4)]
        comments = [dict(r) for r in con.execute("SELECT * FROM live_comments WHERE live_session_id=? ORDER BY id DESC LIMIT 20", (session['id'],)).fetchall()]
        reactions = [dict(r) for r in con.execute("SELECT * FROM live_reactions WHERE live_session_id=? ORDER BY id DESC LIMIT 25", (session['id'],)).fetchall()]
        if request is not None:
            viewer_count = record_live_viewer(con, int(session['id']), request)
        else:
            viewer_count = live_viewer_count(con, int(session['id']))
        return {
            "id": int(session['id']),
            "title": session['title'],
            "status": session['status'],
            "viewer_count": viewer_count,
            "started_at": session['started_at'] or session['created_at'],
            "recording_url": f"/static/live/{session['recording_filename']}" if session['recording_filename'] else "",
            "optimized_url": f"/static/live/{session['optimized_filename']}" if session['optimized_filename'] else "",
            "snapshot_url": f"/static/live/{session['snapshot_filename']}" if session['snapshot_filename'] else "",
            "source_platform": session["source_platform"] if "source_platform" in session.keys() and session["source_platform"] else "brechorisee",
            "instagram_live_url": session["instagram_live_url"] if "instagram_live_url" in session.keys() else "",
            "brechorisee_watch_enabled": bool(session["brechorisee_watch_enabled"]) if "brechorisee_watch_enabled" in session.keys() else True,
            "current_product": live_product_payload(current_product),
            "reference_products": reference_products,
            "comments": comments[::-1],
            "reactions": reactions[::-1],
        }

def _live_insert_item(con: sqlite3.Connection, session_id: int, product_id: int, action: str = 'reconhecida', notes: str = '', second_offset: float = 0.0) -> int:
    product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        raise HTTPException(status_code=404, detail='Peça não encontrada.')
    cur = con.execute(
        """
        INSERT INTO live_session_items
        (live_session_id, product_id, action, status_snapshot, product_code, product_title, product_price, notes, second_offset, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (session_id, product_id, action, product['status'], product['code'], product['title'], product['sale_price'], notes, float(second_offset or 0), now_iso()),
    )
    if action in {'reconhecida', 'fixada', 'cliente_clicou', 'repescagem'} and product['status'] == 'disponivel':
        con.execute(
            "UPDATE live_sessions SET current_product_id=?, current_product_set_at=?, current_product_source=?, current_product_event_id=? WHERE id=?",
            (product_id, now_iso(), action, int(cur.lastrowid), session_id),
        )
    if action in {'reconhecida', 'fixada', 'cliente_clicou'}:
        con.execute(
            "INSERT INTO live_markers(live_session_id, product_id, marker_type, label, second_offset, created_at) VALUES(?,?,?,?,?,?)",
            (session_id, product_id, action, product['title'], float(second_offset or 0), now_iso()),
        )
    if action == 'ignorada':
        con.execute("INSERT OR IGNORE INTO live_ignored_products(live_session_id, product_id, created_at) VALUES(?,?,?)", (session_id, product_id, now_iso()))
    return int(cur.lastrowid)


def _live_merge_ranges(seconds: list[float], before: float = 2.5, after: float = 18.0) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for sec in sorted(float(s) for s in seconds if s is not None):
        start = max(0.0, sec - before)
        end = sec + after
        if not ranges or start > ranges[-1][1] + 1.5:
            ranges.append((start, end))
        else:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
    return ranges


def _live_reference_clip_range(con: sqlite3.Connection, session_id: int, product_id: int, item_id: int | None = None) -> tuple[float, float]:
    """Calcula o trecho da gravação relacionado a uma referência da live."""
    center: float | None = None
    if item_id:
        item = con.execute("SELECT second_offset FROM live_session_items WHERE id=?", (int(item_id),)).fetchone()
        if item and item["second_offset"] is not None:
            center = float(item["second_offset"] or 0)

    if center is None:
        marker = con.execute(
            """
            SELECT second_offset FROM live_markers
            WHERE live_session_id=? AND product_id=?
            ORDER BY id DESC LIMIT 1
            """,
            (session_id, product_id),
        ).fetchone()
        if marker and marker["second_offset"] is not None:
            center = float(marker["second_offset"] or 0)

    if center is None:
        row = con.execute(
            """
            SELECT COUNT(*) AS pos FROM live_session_items
            WHERE live_session_id=? AND id <= COALESCE(?, id)
            """,
            (session_id, item_id),
        ).fetchone()
        center = float(max(0, int(row["pos"] or 1) - 1) * 18)

    next_marker = con.execute(
        """
        SELECT second_offset FROM live_markers
        WHERE live_session_id=? AND second_offset > ?
          AND COALESCE(product_id,0) <> ?
        ORDER BY second_offset ASC LIMIT 1
        """,
        (session_id, center + 3, product_id),
    ).fetchone()

    start = max(0.0, center - 4.0)
    end = center + 26.0
    if next_marker and next_marker["second_offset"] is not None:
        end = min(end, max(center + 8.0, float(next_marker["second_offset"]) - 1.0))
    return start, max(start + 4.0, end)


def create_live_reference_clip(session_id: int, product_id: int, item_id: int | None = None) -> tuple[bool, str, str | None]:
    """Corta um vídeo curto da live e liga o arquivo à referência/peça."""
    with get_db() as con:
        session = con.execute("SELECT * FROM live_sessions WHERE id=?", (session_id,)).fetchone()
        if not session or not session["recording_filename"]:
            return False, "A live ainda não tem gravação salva para cortar.", None

        source = LIVE_DIR / session["recording_filename"]
        if not source.exists():
            return False, "Arquivo original da live não encontrado.", None

        if item_id is None:
            item = con.execute(
                """
                SELECT * FROM live_session_items
                WHERE live_session_id=? AND product_id=?
                  AND action IN ('reconhecida','fixada','cliente_clicou','repescagem')
                ORDER BY id DESC LIMIT 1
                """,
                (session_id, product_id),
            ).fetchone()
        else:
            item = con.execute("SELECT * FROM live_session_items WHERE id=? AND live_session_id=?", (item_id, session_id)).fetchone()

        if not item:
            return False, "Referência da live não encontrada.", None

        product_id = int(item["product_id"])
        start, end = _live_reference_clip_range(con, session_id, product_id, int(item["id"]))
        duration = max(4.0, end - start)

        clips_dir = LIVE_DIR / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"live_{session_id}_peca_{product_id}_item_{int(item['id'])}_{int(time.time())}.mp4"
        out_path = clips_dir / out_name
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [
            ffmpeg_bin, "-y",
            "-ss", f"{start:.2f}",
            "-i", str(source),
            "-t", f"{duration:.2f}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception as e:
            if out_path.exists():
                out_path.unlink(missing_ok=True)
            return False, f"Falha ao cortar vídeo da referência: {e}", None

        con.execute(
            """
            UPDATE live_session_items
            SET clip_filename=?, clip_start_seconds=?, clip_end_seconds=?, clip_created_at=?, clip_notes=?
            WHERE id=?
            """,
            (out_name, start, end, now_iso(), "Clipe curto gerado automaticamente para a referência da live.", int(item["id"])),
        )
        return True, "Clipe curto ligado à referência.", out_name


def generate_live_reference_clips(session_id: int, limit: int = 80) -> tuple[int, list[str]]:
    """Gera clipes curtos para todas as referências disponíveis que ainda não têm vídeo curto."""
    generated = 0
    messages: list[str] = []
    with get_db() as con:
        rows = con.execute(
            """
            SELECT li.id, li.product_id
            FROM live_session_items li
            JOIN products p ON p.id=li.product_id
            WHERE li.live_session_id=?
              AND li.action IN ('reconhecida','fixada','cliente_clicou','repescagem','referencia')
              AND p.status='disponivel'
              AND COALESCE(li.clip_filename,'')=''
            GROUP BY li.product_id
            ORDER BY li.id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    for row in rows:
        ok, msg, _filename = create_live_reference_clip(session_id, int(row["product_id"]), int(row["id"]))
        messages.append(msg)
        if ok:
            generated += 1
    return generated, messages



def optimize_live_recording(session_id: int) -> tuple[bool, str]:
    with get_db() as con:
        session = con.execute("SELECT * FROM live_sessions WHERE id=?", (session_id,)).fetchone()
        if not session or not session['recording_filename']:
            return False, 'Nenhum vídeo gravado foi enviado para esta live.'
        input_path = LIVE_DIR / session['recording_filename']
        if not input_path.exists():
            return False, 'Arquivo original da live não encontrado.'
        markers = con.execute(
            "SELECT second_offset FROM live_markers WHERE live_session_id=? AND marker_type IN ('reconhecida','fixada','highlight','descricao','medidas','valor','como_usar') ORDER BY second_offset ASC",
            (session_id,),
        ).fetchall()
        seconds = [float(r['second_offset'] or 0) for r in markers if r['second_offset'] is not None]
        if not seconds:
            items = con.execute("SELECT id FROM live_session_items WHERE live_session_id=? ORDER BY id ASC", (session_id,)).fetchall()
            seconds = [float(idx * 12) for idx, _ in enumerate(items)]
        if not seconds:
            seconds = [0.0]
        ranges = _live_merge_ranges(seconds)
        tmp_dir = LIVE_DIR / f"tmp_live_{session_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        segments = []
        ffmpeg_bin = shutil.which('ffmpeg') or 'ffmpeg'
        try:
            for idx, (start, end) in enumerate(ranges, start=1):
                seg_path = tmp_dir / f"segment_{idx:03d}.mp4"
                duration = max(3.0, end - start)
                cmd = [ffmpeg_bin, '-y', '-ss', f'{start:.2f}', '-i', str(input_path), '-t', f'{duration:.2f}', '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'aac', str(seg_path)]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                segments.append(seg_path)
            if not segments:
                return False, 'Não foi possível gerar trechos otimizados.'
            list_file = tmp_dir / 'segments.txt'
            list_file.write_text(''.join(f"file '{p.as_posix()}'\n" for p in segments), encoding='utf-8')
            out_name = f"live_otimizada_{session_id}_{int(time.time())}.mp4"
            out_path = LIVE_DIR / out_name
            subprocess.run([ffmpeg_bin, '-y', '-f', 'concat', '-safe', '0', '-i', str(list_file), '-c', 'copy', str(out_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            con.execute("UPDATE live_sessions SET optimized_filename=?, optimized_at=?, ended_action='otimizar', status='otimizada' WHERE id=?", (out_name, now_iso(), session_id))
            con.commit()
            try:
                clip_count, _clip_messages = generate_live_reference_clips(session_id)
            except Exception:
                clip_count = 0
            if clip_count:
                return True, f'Vídeo otimizado e {clip_count} clipe(s) curto(s) ligado(s) às referências.'
            return True, 'Vídeo otimizado com foco nas peças e descrições principais.'
        except Exception as e:
            return False, f'Falha ao otimizar: {e}'
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)



def normalize_instagram_live_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return "https://www.instagram.com/"
    if url.startswith("@"):
        return "https://www.instagram.com/" + url[1:].strip("/") + "/"
    if url.startswith("instagram.com/"):
        return "https://" + url
    if not (url.startswith("https://") or url.startswith("http://")):
        return "https://www.instagram.com/" + url.strip("/") + "/"
    return url


def live_session_public_mode(session: sqlite3.Row) -> dict[str, Any]:
    source = session["source_platform"] if "source_platform" in session.keys() and session["source_platform"] else "brechorisee"
    instagram_url = session["instagram_live_url"] if "instagram_live_url" in session.keys() else ""
    return {
        "source_platform": source,
        "instagram_live_url": instagram_url,
        "brechorisee_watch_enabled": bool(session["brechorisee_watch_enabled"]) if "brechorisee_watch_enabled" in session.keys() else True,
    }


@app.get('/live/instagram', response_class=HTMLResponse)
def live_instagram_control_page(request: Request) -> Response:
    with get_db() as con:
        session = get_or_create_active_live_session(con)
        current_product = con.execute("SELECT * FROM products WHERE id=? AND status='disponivel'", (session["current_product_id"],)).fetchone() if session["current_product_id"] else None
        references = [live_product_payload(p) for p in live_reference_products(con, int(session["id"]), current_product_id=int(session["current_product_id"] or 0), limit=6)]
    return templates.TemplateResponse(
        'live_instagram_control.html',
        {
            'request': request,
            'active': 'live',
            'session': session,
            'current_product': current_product,
            'references': references,
            'public_mode': False,
        },
    )


@app.post('/live/instagram/start')
def live_instagram_start(
    session_id: int = Form(...),
    instagram_live_url: str = Form(""),
    brechorisee_watch_enabled: str = Form("1"),
) -> Response:
    instagram_url = normalize_instagram_live_url(instagram_live_url)
    notified = 0
    with get_db() as con:
        session = con.execute("SELECT * FROM live_sessions WHERE id=?", (session_id,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Live não encontrada.")
        was_live = str(session["status"] or "") == "ao_vivo"
        con.execute(
            """
            UPDATE live_sessions
            SET status='ao_vivo',
                source_platform='instagram',
                instagram_live_url=?,
                brechorisee_watch_enabled=?,
                instagram_control_started_at=COALESCE(instagram_control_started_at, ?),
                started_at=COALESCE(started_at, ?),
                ended_at=NULL
            WHERE id=?
            """,
            (instagram_url, 1 if brechorisee_watch_enabled == "1" else 0, now_iso(), now_iso(), session_id),
        )
        session = con.execute("SELECT * FROM live_sessions WHERE id=?", (session_id,)).fetchone()
        if not was_live:
            notified = queue_live_started_notifications(con, session)
        con.execute(
            "INSERT INTO live_comments(live_session_id, author_name, message, source, created_at) VALUES(?,?,?,?,?)",
            (session_id, "BRECHORISEE", f"Controle da live no Instagram iniciado. {notified} cliente(s) avisada(s).", "sistema", now_iso()),
        )
    return RedirectResponse(url=f"/live/instagram?started=1", status_code=303)


@app.post('/live/instagram/update')
def live_instagram_update(
    session_id: int = Form(...),
    instagram_live_url: str = Form(""),
    brechorisee_watch_enabled: str = Form("1"),
) -> Response:
    with get_db() as con:
        session = con.execute("SELECT * FROM live_sessions WHERE id=?", (session_id,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Live não encontrada.")
        con.execute(
            "UPDATE live_sessions SET source_platform='instagram', instagram_live_url=?, brechorisee_watch_enabled=? WHERE id=?",
            (normalize_instagram_live_url(instagram_live_url), 1 if brechorisee_watch_enabled == "1" else 0, session_id),
        )
    return RedirectResponse(url="/live/instagram?updated=1", status_code=303)


@app.get('/cliente/live-opcoes', response_class=HTMLResponse)
def customer_live_options_page(request: Request) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url='/cliente?next=/cliente/inicio', status_code=303)
    return templates.TemplateResponse(
        'customer_live_options.html',
        {
            'request': request,
            'account': account,
            'settings': get_store_settings(),
            'public_mode': True,
            'live_info': active_or_last_live_info(request),
            'app_links': brechorisee_customer_app_links(request),
        },
    )


@app.post('/live/start')
def live_start_session(session_id: int = Form(...)) -> Response:
    notified = 0
    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail='Live não encontrada.')
        was_live = str(session["status"] or "") == "ao_vivo"
        con.execute("UPDATE live_sessions SET status='ao_vivo', source_platform='brechorisee', brechorisee_watch_enabled=1, started_at=COALESCE(started_at, ?), ended_at=NULL WHERE id=?", (now_iso(), session_id))
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not was_live:
            notified = queue_live_started_notifications(con, session)
            con.execute(
                "INSERT INTO live_comments(live_session_id, author_name, message, source, created_at) VALUES(?,?,?,?,?)",
                (session_id, "BRECHORISEE", f"Live iniciada. {notified} cliente(s) avisada(s).", "sistema", now_iso()),
            )
    return RedirectResponse(url=f'/live/studio/{session_id}', status_code=303)


@app.get('/live/studio/{session_id}', response_class=HTMLResponse)
def live_studio_page(request: Request, session_id: int) -> Response:
    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail='Live não encontrada.')
        items = con.execute(
            """
            SELECT li.*, p.image_filename, p.status AS current_status
            FROM live_session_items li
            LEFT JOIN products p ON p.id = li.product_id
            WHERE li.live_session_id=?
            ORDER BY li.id DESC
            LIMIT 20
            """,
            (session_id,),
        ).fetchall()
        current_product = con.execute("SELECT * FROM products WHERE id=? AND status='disponivel'", (session['current_product_id'],)).fetchone() if session['current_product_id'] else None
        current_product_id = int(current_product['id']) if current_product else None
        reference_products = [live_product_payload(p) for p in live_reference_products(con, int(session_id), current_product_id=current_product_id, limit=LIVE_RECOGNITION_MAX_PRODUCTS)]
    return templates.TemplateResponse('live_studio.html', {'request': request, 'session': session, 'items': items, 'current_product': current_product, 'reference_products': reference_products, 'active': 'live'})


@app.get('/cliente/live', response_class=HTMLResponse)
def customer_live_page(request: Request) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url='/cliente?next=/cliente/inicio', status_code=303)
    with get_db() as con:
        con.execute(
            """
            UPDATE customer_notifications
            SET read_at=COALESCE(read_at, ?), status='visualizada'
            WHERE customer_account_id=? AND notification_type='live_started' AND read_at IS NULL
            """,
            (now_iso(), account["id"]),
        )
    return templates.TemplateResponse('customer_live.html', {'request': request, 'account': account, 'settings': get_store_settings(), 'public_mode': True, 'live_info': active_or_last_live_info(request)})


@app.post('/api/live/remove-reference/{session_id}')
def api_live_remove_reference(
    session_id: int,
    product_id: int = Form(...),
    reason: str = Form("referencia_incorreta"),
) -> JSONResponse:
    """Remove uma referência reconhecida incorretamente sem alterar o estoque da peça.

    Uso no Studio/Admin: quando o reconhecimento sugerir uma peça errada, a administradora
    pode removê-la da prateleira lateral da live. A peça continua com seu status original
    no estoque, mas deixa de aparecer como referência desta sessão.
    """
    reason = (reason or "referencia_incorreta").strip()[:120]
    with get_db() as con:
        session = con.execute("SELECT * FROM live_sessions WHERE id=?", (int(session_id),)).fetchone()
        product = con.execute("SELECT * FROM products WHERE id=?", (int(product_id),)).fetchone()
        if not session or not product:
            return JSONResponse({"ok": False, "message": "Live ou peça não encontrada."}, status_code=404)
        updated = con.execute(
            """
            UPDATE live_session_items
            SET action='removida',
                notes=TRIM(COALESCE(notes,'') || ' • removida do studio: ' || ?)
            WHERE live_session_id=?
              AND product_id=?
              AND action IN ('reconhecida','fixada','cliente_clicou','repescagem')
            """,
            (reason, int(session_id), int(product_id)),
        ).rowcount
        con.execute(
            "UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='removida', current_product_event_id=NULL WHERE id=? AND current_product_id=?",
            (now_iso(), int(session_id), int(product_id)),
        )
        con.execute(
            "INSERT OR IGNORE INTO live_ignored_products(live_session_id, product_id, created_at) VALUES(?,?,?)",
            (int(session_id), int(product_id), now_iso()),
        )
        con.execute(
            "INSERT INTO product_interest_events(product_id, event_type, source, notes, created_at) VALUES(?,?,?,?,?)",
            (int(product_id), "referencia_removida_live", "admin_live", f"Live {session_id}: {reason}", now_iso()),
        )
        current_product_id = None
        refs = [live_product_payload(p) for p in live_reference_products(con, int(session_id), current_product_id=current_product_id, limit=LIVE_RECOGNITION_MAX_PRODUCTS)]
    return JSONResponse({
        "ok": True,
        "removed": int(updated or 0),
        "product_id": int(product_id),
        "message": "Referência removida da live. O estoque da peça não foi alterado.",
        "reference_products": refs,
    })


@app.get('/api/live/dashboard/{session_id}')
def api_live_dashboard(session_id: int) -> JSONResponse:
    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not session:
            return JSONResponse({'ok': False, 'message': 'Live não encontrada.'}, status_code=404)
        current_product_id = int(session['current_product_id']) if session['current_product_id'] else None
        current_product = con.execute("SELECT * FROM products WHERE id=? AND status='disponivel'", (current_product_id,)).fetchone() if current_product_id else None
        if current_product_id and not current_product:
            con.execute("UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_unavailable', current_product_event_id=NULL WHERE id=?", (now_iso(), session_id))
            current_product_id = None
        references = [live_product_payload(p) for p in live_reference_products(con, session_id, current_product_id=current_product_id, limit=4)]
        reserved_rows = con.execute(
            """
            SELECT p.*
            FROM live_session_items li
            JOIN products p ON p.id=li.product_id
            WHERE li.live_session_id=?
              AND li.action IN ('reservada','reconhecida','fixada','cliente_clicou','repescagem')
              AND p.status='reservado'
            GROUP BY p.id
            ORDER BY MAX(li.id) DESC
            LIMIT 6
            """,
            (int(session_id),),
        ).fetchall()
        reserved_products = [live_product_payload_with_reservation(con, p) for p in reserved_rows]
        reserved_products = [p for p in reserved_products if p]
        comments = [dict(r) for r in con.execute("SELECT * FROM live_comments WHERE live_session_id=? ORDER BY id DESC LIMIT 30", (session_id,)).fetchall()]
        reactions = [dict(r) for r in con.execute("SELECT * FROM live_reactions WHERE live_session_id=? ORDER BY id DESC LIMIT 40", (session_id,)).fetchall()]
        viewer_count = live_viewer_count(con, int(session_id))
    return JSONResponse({
        'ok': True,
        'session': {
            'id': session_id,
            'status': session['status'],
            'title': session['title'],
            'viewer_count': viewer_count,
            'source_platform': session['source_platform'] if 'source_platform' in session.keys() and session['source_platform'] else 'brechorisee',
            'instagram_live_url': session['instagram_live_url'] if 'instagram_live_url' in session.keys() else '',
            'brechorisee_watch_enabled': bool(session['brechorisee_watch_enabled']) if 'brechorisee_watch_enabled' in session.keys() else True,
        },
        'current_product': live_product_payload(current_product),
        'reference_products': references,
        'reserved_products': reserved_products,
        'admin_reference_products': references + reserved_products,
        'comments': comments[::-1],
        'reactions': reactions[::-1],
    })



def _live_recognition_regions(width: int, height: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Regiões rápidas e seguras para reconhecer peças na live.

    Importante:
    - Não usa mais o frame inteiro como principal, porque cenário, chão e cards antigos
      geravam falso positivo e deixavam a peça presa na tela.
    - Evita a lateral direita extrema e o rodapé, onde ficam botões/cards da interface.
    - Divide a área útil em pedaços para reconhecer conjunto/duas referências quando
      aparecem ao mesmo tempo.
    """
    w = max(1, int(width))
    h = max(1, int(height))
    raw_regions = [
        ("principal_sem_ui", (int(w * 0.04), int(h * 0.05), int(w * 0.76), int(h * 0.82))),
        ("centro_peca", (int(w * 0.12), int(h * 0.08), int(w * 0.72), int(h * 0.76))),
        ("zoom_centro", (int(w * 0.20), int(h * 0.12), int(w * 0.68), int(h * 0.70))),
        ("dupla_esquerda", (int(w * 0.00), int(h * 0.08), int(w * 0.52), int(h * 0.82))),
        ("dupla_direita_segura", (int(w * 0.38), int(h * 0.08), int(w * 0.76), int(h * 0.82))),
        ("superior_peca", (int(w * 0.08), int(h * 0.00), int(w * 0.76), int(h * 0.55))),
        ("inferior_peca", (int(w * 0.08), int(h * 0.34), int(w * 0.76), int(h * 0.82))),
        ("meio_esquerda", (int(w * 0.00), int(h * 0.22), int(w * 0.55), int(h * 0.76))),
        ("meio_direita_segura", (int(w * 0.36), int(h * 0.22), int(w * 0.76), int(h * 0.76))),
    ]
    regions: list[tuple[str, tuple[int, int, int, int]]] = []
    seen: set[tuple[int, int, int, int]] = set()
    min_area = max(1, int(w * h * 0.08))
    for name, box in raw_regions:
        x1, y1, x2, y2 = box
        x1 = max(0, min(w - 1, x1))
        y1 = max(0, min(h - 1, y1))
        x2 = max(x1 + 1, min(w, x2))
        y2 = max(y1 + 1, min(h, y2))
        safe_box = (x1, y1, x2, y2)
        if safe_box in seen:
            continue
        if (x2 - x1) * (y2 - y1) < min_area:
            continue
        seen.add(safe_box)
        regions.append((name, safe_box))
    return regions


def live_recognize_multiple_products_from_frame(image_path: Path, limit: int = LIVE_RECOGNITION_MAX_PRODUCTS, min_score: float = LIVE_RECOGNITION_MIN_SCORE) -> list[dict[str, Any]]:
    """Analisa o frame inteiro e cortes da imagem para reconhecer várias peças ao mesmo tempo.

    O reconhecimento antigo olhava apenas o frame inteiro. Em uma live, isso falha quando
    há uma peça na mão, outra no cabide e outra sobre uma mesa. Aqui o frame é dividido
    em regiões úteis e as melhores referências são agrupadas por produto.
    """
    best_by_product: dict[int, dict[str, Any]] = {}
    temp_paths: list[Path] = []
    try:
        original = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
        width, height = original.size

        # Reduz falso positivo em chão/parede/cenário sem peça.
        try:
            from PIL import ImageStat
            stat_img = original.copy()
            stat_img.thumbnail((160, 160))
            stddev = sum(ImageStat.Stat(stat_img).stddev) / 3.0
            if stddev < 8.0:
                return []
        except Exception:
            pass

        regions = _live_recognition_regions(width, height)

        for region_name, box in regions:
            crop_path = image_path
            if region_name != "frame_inteiro":
                crop = original.crop(box)
                # Padroniza tamanho para reduzir ruído e custo do hash.
                crop.thumbnail((900, 900))
                crop_path = UPLOAD_DIR / f"live_crop_{secrets.token_hex(8)}.jpg"
                crop.save(crop_path, "JPEG", quality=82, optimize=True)
                temp_paths.append(crop_path)

            try:
                query_hash, query_rgb = image_signature(crop_path)
                matches = recognize_product_matches(query_hash, query_rgb, limit=max(6, int(limit) * 2), status="disponivel_reservado")
            except Exception:
                continue

            for product in matches:
                score = float(product.get("score") or 0)
                # Regiões muito amplas e laterais exigem mais confiança para não manter peça falsa na tela.
                region_threshold = float(min_score)
                if region_name in {"principal_sem_ui", "superior_peca", "inferior_peca"}:
                    region_threshold += 2.0
                if "direita" in region_name:
                    region_threshold += 3.0
                if score < region_threshold:
                    continue
                product_id = int(product["id"])
                candidate = dict(product)
                candidate["recognition_region"] = region_name
                candidate["recognition_score"] = score
                current = best_by_product.get(product_id)
                if current is None or score > float(current.get("recognition_score") or current.get("score") or 0):
                    best_by_product[product_id] = candidate

        results = list(best_by_product.values())
        results.sort(key=lambda p: float(p.get("recognition_score") or p.get("score") or 0), reverse=True)
        return results[: max(1, int(limit))]
    finally:
        for path in temp_paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass




@app.post('/api/live/recognize-frame/{session_id}')
def api_live_recognize_frame(session_id: int, image: UploadFile = File(...), elapsed_seconds: float = Form(0.0)) -> JSONResponse:
    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not session:
            return JSONResponse({'ok': False, 'message': 'Live não encontrada.'}, status_code=404)

    filename = save_upload(image, 'live_frame_recognition')
    frame_path = UPLOAD_DIR / filename
    try:
        matches = live_recognize_multiple_products_from_frame(
            frame_path,
            limit=LIVE_RECOGNITION_MAX_PRODUCTS,
            min_score=LIVE_RECOGNITION_MIN_SCORE,
        )
    finally:
        try:
            frame_path.unlink(missing_ok=True)
        except Exception:
            pass

    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not session:
            return JSONResponse({'ok': False, 'message': 'Live não encontrada.'}, status_code=404)
        was_live = str(session["status"] or "") == "ao_vivo"

        existing_ids = {
            int(r['id'])
            for r in live_reference_products(con, int(session_id), current_product_id=session['current_product_id'], limit=20)
        }
        existing_reserved_ids = {
            int(r["product_id"])
            for r in con.execute(
                "SELECT DISTINCT product_id FROM live_session_items WHERE live_session_id=? AND action='reservada'",
                (int(session_id),),
            ).fetchall()
        }
        ignored_ids = {
            int(r["product_id"])
            for r in con.execute(
                "SELECT DISTINCT product_id FROM live_ignored_products WHERE live_session_id=?",
                (int(session_id),),
            ).fetchall()
        }
        inserted_ids: list[int] = []
        payload_products: list[dict[str, Any]] = []
        reserved_products: list[dict[str, Any]] = []

        for match in matches:
            product_id = int(match['id'])
            if product_id in ignored_ids:
                continue
            product_status = str(match.get("status") or "")
            score_label = f"{float(match.get('recognition_score') or match.get('score') or 0):.1f}"
            if product_status == "reservado":
                row = con.execute('SELECT * FROM products WHERE id=? AND status="reservado"', (product_id,)).fetchone()
                payload = live_product_payload_with_reservation(con, row)
                if payload:
                    payload['recognition_region'] = match.get('recognition_region', '')
                    payload['recognition_score'] = float(match.get('recognition_score') or match.get('score') or 0)
                    reserved_products.append(payload)
                    if product_id not in existing_reserved_ids:
                        owner = payload.get("reserved_for") or "cliente"
                        _live_insert_item(
                            con,
                            int(session_id),
                            product_id,
                            'reservada',
                            f"Reconhecida na live, mas já está reservada para {owner} • região {match.get('recognition_region','frame')} • score {score_label}",
                            elapsed_seconds,
                        )
                        existing_reserved_ids.add(product_id)
                continue

            if product_id not in existing_ids:
                _live_insert_item(
                    con,
                    int(session_id),
                    product_id,
                    'reconhecida',
                    f"Reconhecimento automático • região {match.get('recognition_region','frame')} • score {score_label}",
                    elapsed_seconds,
                )
                existing_ids.add(product_id)
                inserted_ids.append(product_id)
            row = con.execute('SELECT * FROM products WHERE id=? AND status="disponivel"', (product_id,)).fetchone()
            payload = live_product_payload(row)
            if payload:
                payload['recognition_region'] = match.get('recognition_region', '')
                payload['recognition_score'] = float(match.get('recognition_score') or match.get('score') or 0)
                payload_products.append(payload)

        if payload_products:
            top_id = int(payload_products[0]['id'])
            top_event = con.execute(
                """
                SELECT id, created_at, action FROM live_session_items
                WHERE live_session_id=? AND product_id=? AND action IN ('reconhecida','fixada','cliente_clicou','repescagem')
                ORDER BY id DESC LIMIT 1
                """,
                (int(session_id), top_id),
            ).fetchone()
            event_at = top_event["created_at"] if top_event else now_iso()
            event_id = int(top_event["id"]) if top_event else None
            event_source = top_event["action"] if top_event else "reconhecida"
            con.execute(
                "UPDATE live_sessions SET current_product_id=?, current_product_set_at=?, current_product_source=?, current_product_event_id=?, status=CASE WHEN status='aberta' THEN 'ao_vivo' ELSE status END, started_at=COALESCE(started_at, ?) WHERE id=?",
                (top_id, event_at, event_source, event_id, now_iso(), int(session_id)),
            )
            session_after = con.execute("SELECT * FROM live_sessions WHERE id=?", (int(session_id),)).fetchone()
            if not was_live and session_after and str(session_after["status"] or "") == "ao_vivo":
                queue_live_started_notifications(con, session_after)
        elif reserved_products and session['current_product_id'] and int(session['current_product_id']) in {int(p['id']) for p in reserved_products}:
            con.execute("UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_reserved', current_product_event_id=NULL WHERE id=?", (now_iso(), int(session_id)))
        elif not payload_products:
            # Quando a câmera não reconhece nenhuma peça com confiança, remove a peça
            # automática da tela. Isso evita card antigo preso quando a apresentadora
            # vira a câmera para o chão, parede ou troca de produto.
            source = str(session["current_product_source"] or "") if "current_product_source" in session.keys() else ""
            if source in {"reconhecida", "sem_reconhecimento", "clear_auto", ""}:
                con.execute(
                    "UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_auto', current_product_event_id=NULL WHERE id=?",
                    (now_iso(), int(session_id)),
                )

        current_product_id = int(payload_products[0]['id']) if payload_products else None
        current_product = con.execute("SELECT * FROM products WHERE id=? AND status='disponivel'", (current_product_id,)).fetchone() if current_product_id else None
        # A resposta do reconhecimento deve trazer apenas as peças visíveis agora.
        # O histórico continua salvo no banco, mas não fica preso na tela do Studio/Admin.
        references = payload_products + reserved_products

    return JSONResponse({
        'ok': True,
        'product': live_product_payload(current_product),
        'products': payload_products,
        'reserved_products': reserved_products,
        'reference_products': references,
        'admin_reference_products': payload_products + reserved_products,
        'recognized_count': len(payload_products),
        'reserved_count': len(reserved_products),
        'inserted_ids': inserted_ids,
        'recognition_clear': not bool(payload_products or reserved_products),
        'message': 'Peças visíveis atualizadas.' if (payload_products or reserved_products) else 'Nenhuma peça visível com confiança; tela limpa.',
        'min_score': LIVE_RECOGNITION_MIN_SCORE,
    })

@app.post('/api/live/current-product/{session_id}')
def api_live_set_current_product(session_id: int, product_id: int = Form(...), action: str = Form('fixada'), notes: str = Form(''), elapsed_seconds: float = Form(0.0)) -> JSONResponse:
    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not session:
            return JSONResponse({'ok': False, 'message': 'Live não encontrada.'}, status_code=404)
        was_live = str(session["status"] or "") == "ao_vivo"
        item_id = _live_insert_item(con, session_id, product_id, action, notes, elapsed_seconds)
        con.execute(
            "UPDATE live_sessions SET status=CASE WHEN status='aberta' THEN 'ao_vivo' ELSE status END, started_at=COALESCE(started_at, ?) WHERE id=?",
            (now_iso(), int(session_id)),
        )
        session_after = con.execute("SELECT * FROM live_sessions WHERE id=?", (int(session_id),)).fetchone()
        if not was_live and session_after and str(session_after["status"] or "") == "ao_vivo":
            queue_live_started_notifications(con, session_after)
        product = con.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
    return JSONResponse({'ok': True, 'item_id': item_id, 'product': live_product_payload(product)})


@app.post('/api/live/mark-sold/{session_id}')
def api_live_mark_current_sold(session_id: int, product_id: int = Form(...), elapsed_seconds: float = Form(0.0)) -> JSONResponse:
    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        product = con.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        if not session or not product:
            return JSONResponse({'ok': False, 'message': 'Live ou peça não encontrada.'}, status_code=404)
        sold_time = now_iso()
        con.execute("UPDATE products SET status='vendido', sold_at=?, sync_updated_at=? WHERE id=?", (sold_time, sold_time, product_id))
        con.execute("INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)", (product_id, 'live_venda', 'Marcada como vendida na transmissão ao vivo.', sold_time))
        _live_insert_item(con, session_id, product_id, 'vendida', 'Vendida durante a live.', elapsed_seconds)
        con.execute("UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_sold', current_product_event_id=NULL WHERE id=? AND current_product_id=?", (now_iso(), session_id, product_id))
        con.execute("INSERT INTO live_markers(live_session_id, product_id, marker_type, label, second_offset, created_at) VALUES(?,?,?,?,?,?)", (session_id, product_id, 'valor', product['title'], float(elapsed_seconds or 0), now_iso()))
        references = [live_product_payload(p) for p in live_reference_products(con, session_id, current_product_id=None, limit=4)]
        if TELEGRAM_NOTIFY_LIVE:
            telegram_send_admin_message(
                con,
                f"✅ <b>Vendida na live #{session_id}</b>\n{product['code']} — {product['title']} — {money(product['sale_price'])}",
                related_type="live_sale",
                related_id=int(product_id),
            )
    return JSONResponse({'ok': True, 'reference_products': references})


@app.post('/api/live/skip-current/{session_id}')
def api_live_skip_current(session_id: int, product_id: int = Form(...), elapsed_seconds: float = Form(0.0)) -> JSONResponse:
    with get_db() as con:
        _live_insert_item(con, session_id, product_id, 'ignorada', 'Trocar para próxima peça.', elapsed_seconds)
        con.execute("UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='trocar_peca', current_product_event_id=NULL WHERE id=?", (now_iso(), session_id))
    return JSONResponse({'ok': True})


@app.post('/api/live/marker/{session_id}')
def api_live_marker(session_id: int, marker_type: str = Form(...), label: str = Form(''), product_id: int = Form(0), elapsed_seconds: float = Form(0.0)) -> JSONResponse:
    allowed = {'highlight', 'descricao', 'medidas', 'valor', 'como_usar'}
    if marker_type not in allowed:
        marker_type = 'highlight'
    with get_db() as con:
        con.execute("INSERT INTO live_markers(live_session_id, product_id, marker_type, label, second_offset, created_at) VALUES(?,?,?,?,?,?)", (session_id, product_id or None, marker_type, label, float(elapsed_seconds or 0), now_iso()))
    return JSONResponse({'ok': True})


@app.post('/api/live/upload-recording/{session_id}')
def api_live_upload_recording(session_id: int, recording: UploadFile = File(...)) -> JSONResponse:
    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not session:
            return JSONResponse({'ok': False, 'message': 'Live não encontrada.'}, status_code=404)
    saved = save_media_upload(recording, f'live_recording_{session_id}')
    if not saved:
        return JSONResponse({'ok': False, 'message': 'Gravação não enviada.'}, status_code=400)
    filename, media_type = saved
    if media_type != 'video':
        (UPLOAD_DIR / filename).unlink(missing_ok=True)
        return JSONResponse({'ok': False, 'message': 'Envie um arquivo de vídeo.'}, status_code=400)
    src = UPLOAD_DIR / filename
    dest = LIVE_DIR / filename
    shutil.move(str(src), str(dest))
    with get_db() as con:
        con.execute('UPDATE live_sessions SET recording_filename=? WHERE id=?', (filename, session_id))
    return JSONResponse({'ok': True, 'url': f'/static/live/{filename}'})


@app.post('/api/live/frame/{session_id}')
def api_live_upload_frame(session_id: int, image: UploadFile = File(...)) -> JSONResponse:
    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not session:
            return JSONResponse({'ok': False, 'message': 'Live não encontrada.'}, status_code=404)
    filename = save_upload(image, f'live_snapshot_{session_id}')
    src = UPLOAD_DIR / filename
    dest = LIVE_DIR / filename
    shutil.move(str(src), str(dest))
    old = session['snapshot_filename']
    if old and old != filename:
        try:
            (LIVE_DIR / old).unlink(missing_ok=True)
        except Exception:
            pass
    with get_db() as con:
        con.execute('UPDATE live_sessions SET snapshot_filename=? WHERE id=?', (filename, session_id))
    return JSONResponse({'ok': True, 'url': f'/static/live/{filename}'})


@app.get('/api/public-live/current')
def api_public_live_current(request: Request) -> JSONResponse:
    info = active_or_last_live_info(request)
    return JSONResponse({'ok': True, 'live': info})


@app.post('/api/public-live/comment')
def api_public_live_comment(request: Request, session_id: int = Form(...), message: str = Form(...)) -> JSONResponse:
    account = customer_from_request(request)
    if not account:
        return JSONResponse({'ok': False, 'message': 'Cliente não autenticada.'}, status_code=401)
    message = (message or '').strip()
    if not message:
        return JSONResponse({'ok': False, 'message': 'Mensagem vazia.'}, status_code=400)
    with get_db() as con:
        con.execute("INSERT INTO live_comments(live_session_id, author_name, message, source, created_at) VALUES(?,?,?,?,?)", (session_id, account['name'], message[:220], 'cliente', now_iso()))
        if TELEGRAM_NOTIFY_COMMENTS:
            telegram_send_admin_message(
                con,
                f"💬 <b>Comentário na live #{session_id}</b>\n{account['name']}: {message[:220]}",
                related_type="live_comment",
                related_id=int(session_id),
                disable_notification=True,
            )
    return JSONResponse({'ok': True})


@app.post('/api/public-live/reaction')
def api_public_live_reaction(request: Request, session_id: int = Form(...), emoji: str = Form('❤️')) -> JSONResponse:
    account = customer_from_request(request)
    if not account:
        return JSONResponse({'ok': False, 'message': 'Cliente não autenticada.'}, status_code=401)
    emoji = (emoji or '❤️')[:4]
    with get_db() as con:
        con.execute("INSERT INTO live_reactions(live_session_id, emoji, author_name, created_at) VALUES(?,?,?,?)", (session_id, emoji, account['name'], now_iso()))
    return JSONResponse({'ok': True})



def _latest_live_session_for_customer_search(con: sqlite3.Connection, session_id: int | None = None) -> sqlite3.Row | None:
    if session_id:
        return con.execute("SELECT * FROM live_sessions WHERE id=?", (int(session_id),)).fetchone()
    return con.execute(
        "SELECT * FROM live_sessions WHERE status IN ('ao_vivo','aberta','encerrada','arquivada','otimizada') "
        "ORDER BY CASE WHEN status='ao_vivo' THEN 0 WHEN status='aberta' THEN 1 ELSE 2 END, id DESC LIMIT 1"
    ).fetchone()


def _live_reference_id_set(con: sqlite3.Connection, session_id: int) -> set[int]:
    rows = con.execute(
        """
        SELECT DISTINCT p.id
        FROM live_session_items li
        JOIN products p ON p.id=li.product_id
        WHERE li.live_session_id=?
          AND li.action IN ('reconhecida','fixada','cliente_clicou','repescagem','referencia')
          AND p.status='disponivel'
        """,
        (session_id,),
    ).fetchall()
    return {int(r["id"]) for r in rows}


def _public_live_search_payload(product: Any, reference_ids: set[int], score: float | None = None) -> dict[str, Any]:
    payload = live_product_payload(product)
    if not payload:
        return {}
    payload["in_live_reference"] = int(payload["id"]) in reference_ids
    if score is not None:
        payload["score"] = round(float(score), 3)
    payload["source_label"] = "Referência da live" if payload["in_live_reference"] else "Peça disponível"
    return payload


@app.post('/api/public-live/search-reference')
def api_public_live_search_reference(
    request: Request,
    session_id: int = Form(0),
    q: str = Form(""),
    image: UploadFile | None = File(None),
) -> JSONResponse:
    """Busca peça por código/texto ou print da live. Cliente pode selecionar ou descartar o resultado."""
    account = customer_from_request(request)
    if not account:
        return JSONResponse({'ok': False, 'message': 'Cliente não autenticada.'}, status_code=401)

    q = (q or "").strip()
    candidates: list[tuple[Any, float | None]] = []
    unavailable_match: dict[str, Any] | None = None
    with get_db() as con:
        session = _latest_live_session_for_customer_search(con, session_id or None)
        if not session:
            return JSONResponse({'ok': False, 'message': 'Nenhuma live encontrada.'}, status_code=404)
        reference_ids = _live_reference_id_set(con, int(session["id"]))

        if image is not None and image.filename:
            filename = save_upload(image, "print-live-cliente")
            try:
                query_hash, query_rgb = image_signature(UPLOAD_DIR / filename)
                recognized_all = recognize_product_matches(query_hash, query_rgb, limit=8, status="todos")
                for result in recognized_all:
                    product = result.get("product") or result
                    try:
                        product_status = product["status"]
                    except Exception:
                        product_status = ""
                    if product_status != "disponivel" and unavailable_match is None:
                        unavailable_match = {
                            "id": int(product["id"]),
                            "code": product["code"],
                            "title": product["title"],
                            "status": product_status,
                            "score": round(float(result.get("score") or 0), 3),
                        }
                    if product_status == "disponivel":
                        candidates.append((result, float(result.get("score") or 0)))
                # Fallback: se nada disponível foi encontrado no reconhecimento geral, busca similares disponíveis.
                if not candidates:
                    recognized = recognize_product_matches(query_hash, query_rgb, limit=12, status="disponivel")
                    for result in recognized:
                        candidates.append((result, float(result.get("score") or 0)))
            finally:
                try:
                    (UPLOAD_DIR / filename).unlink(missing_ok=True)
                except Exception:
                    pass

        if q:
            # Código exato primeiro. Se o código existir mas estiver reservado/vendido, avisa sem liberar compra.
            exact_any = con.execute(
                "SELECT * FROM products WHERE UPPER(code)=UPPER(?) OR CAST(id AS TEXT)=? LIMIT 1",
                (q, q),
            ).fetchone()
            if exact_any and exact_any["status"] != "disponivel":
                unavailable_match = {
                    "id": int(exact_any["id"]),
                    "code": exact_any["code"],
                    "title": exact_any["title"],
                    "status": exact_any["status"],
                    "score": 100.0,
                }
            elif exact_any:
                candidates.append((exact_any, 100.0))
            for row in search_products_rows(q=q, status="disponivel", limit=20):
                candidates.append((row, None))

        if not q and not (image is not None and image.filename):
            for row in live_reference_products(con, int(session["id"]), current_product_id=None, limit=8):
                candidates.append((row, None))

        seen: set[int] = set()
        payloads: list[dict[str, Any]] = []
        for product, score in candidates:
            try:
                pid = int(product["id"])
            except Exception:
                continue
            if pid in seen:
                continue
            seen.add(pid)
            payload = _public_live_search_payload(product, reference_ids, score)
            if payload:
                payloads.append(payload)

        payloads.sort(key=lambda p: (0 if p.get("in_live_reference") else 1, -(p.get("score") or 0), p.get("title") or ""))

    if unavailable_match:
        if payloads:
            message = (
                f"A peça {unavailable_match.get('code') or ''} parece estar {unavailable_match.get('status')}. "
                "Ela não pode ser reservada agora. Mostramos apenas opções disponíveis parecidas."
            )
        else:
            message = (
                f"A peça {unavailable_match.get('code') or ''} está {unavailable_match.get('status')} "
                "e não aparece mais para compra ou repescagem."
            )
    else:
        message = '' if payloads else 'Nenhuma referência disponível encontrada para este código/print.'

    return JSONResponse({
        'ok': True,
        'session_id': int(session["id"]),
        'q': q,
        'results': payloads[:12],
        'message': message,
        'unavailable_match': unavailable_match,
    })


@app.post('/api/public-live/reference-decision')
def api_public_live_reference_decision(
    request: Request,
    session_id: int = Form(...),
    product_id: int = Form(...),
    decision: str = Form("selecionada"),
) -> JSONResponse:
    """Cliente seleciona ou descarta uma referência encontrada por código/print."""
    account = customer_from_request(request)
    if not account:
        return JSONResponse({'ok': False, 'message': 'Cliente não autenticada.'}, status_code=401)
    decision = "descartada" if decision == "descartada" else "selecionada"
    with get_db() as con:
        session = con.execute("SELECT * FROM live_sessions WHERE id=?", (session_id,)).fetchone()
        product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not session or not product:
            return JSONResponse({'ok': False, 'message': 'Live ou peça não encontrada.'}, status_code=404)
        if product["status"] != "disponivel":
            return JSONResponse({'ok': False, 'message': 'Esta peça não está mais disponível.'}, status_code=409)

        event_type = "cliente_selecionou_referencia_live" if decision == "selecionada" else "cliente_descartou_referencia_live"
        notes = f"Cliente: {account['name']} / {account['phone']} • live {session_id}"
        con.execute(
            "INSERT INTO product_interest_events(product_id, event_type, source, notes, created_at) VALUES(?,?,?,?,?)",
            (product_id, event_type, "live_cliente", notes, now_iso()),
        )
        reserved = False
        if decision == "selecionada":
            reservation_hours = int(get_store_settings().get("default_reservation_hours") or 24)
            expires_at = (datetime.now() + timedelta(hours=reservation_hours)).strftime("%Y-%m-%d %H:%M:%S")
            reserved = reserve_product_for_customer(
                con,
                int(product_id),
                customer_name=account["name"],
                customer_phone=account["phone"] or "",
                source="reserva_repescagem",
                notes=f"Reservada pela repescagem/busca por print da live {session_id} para {account['name']} / {account['phone']}. Peça retirada do portfólio público.",
                expires_at=expires_at,
            )
            if not reserved:
                return JSONResponse({'ok': False, 'message': 'Esta peça não está mais disponível para reserva.'}, status_code=409)
            _live_insert_item(
                con,
                int(session_id),
                int(product_id),
                "cliente_clicou",
                f"Cliente reservou referência por busca/print: {account['name']} / {account['phone']}",
                0.0,
            )
            product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            if TELEGRAM_NOTIFY_LIVE:
                telegram_send_admin_message(
                    con,
                    telegram_live_reservation_summary(account["name"], account["phone"] or "", product, int(session_id), source="repescagem/print/live"),
                    related_type="reservation",
                    related_id=int(product_id),
                )
        payload = live_product_payload(product)

    return JSONResponse({
        'ok': True,
        'decision': decision,
        'reserved': reserved,
        'product': payload,
        'open_url': payload["public_url"] if payload and payload.get("public_url") else "/cliente/vitrine",
        'message': 'Peça reservada para você e retirada da vitrine/repescagem.' if reserved else "Referência descartada.",
    })


@app.get('/live/finalizar/{session_id}', response_class=HTMLResponse)
def live_finalize_page(request: Request, session_id: int, msg: str = '') -> Response:
    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail='Live não encontrada.')
        recap_count = con.execute("SELECT COUNT(*) FROM live_session_items WHERE live_session_id=?", (session_id,)).fetchone()[0]
        clip_items = con.execute(
            """
            SELECT li.*, p.image_filename, p.status AS current_status
            FROM live_session_items li
            JOIN products p ON p.id=li.product_id
            WHERE li.live_session_id=?
              AND li.action IN ('reconhecida','fixada','cliente_clicou','repescagem','referencia')
            ORDER BY li.id ASC
            LIMIT 80
            """,
            (session_id,),
        ).fetchall()
    return templates.TemplateResponse('live_finalize.html', {'request': request, 'session': session, 'recap_count': recap_count, 'clip_items': clip_items, 'msg': msg, 'active': 'live'})


@app.post('/live/finalizar/{session_id}')
def live_finalize_action(session_id: int, action: str = Form(...)) -> Response:
    safe_msg = 'Ação concluída.'
    with get_db() as con:
        session = con.execute('SELECT * FROM live_sessions WHERE id=?', (session_id,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail='Live não encontrada.')
        if action == 'arquivar':
            con.execute("UPDATE live_sessions SET status='arquivada', ended_action='arquivar' WHERE id=?", (session_id,))
            safe_msg = 'Live arquivada com sucesso.'
        elif action == 'excluir':
            for key in ('recording_filename', 'optimized_filename', 'snapshot_filename'):
                filename = session[key]
                if filename:
                    try:
                        (LIVE_DIR / filename).unlink(missing_ok=True)
                    except Exception:
                        pass
            clip_rows = con.execute("SELECT clip_filename FROM live_session_items WHERE live_session_id=? AND COALESCE(clip_filename,'')<>''", (session_id,)).fetchall()
            for clip in clip_rows:
                try:
                    (LIVE_DIR / "clips" / clip["clip_filename"]).unlink(missing_ok=True)
                except Exception:
                    pass
            con.execute("UPDATE live_session_items SET clip_filename=NULL, clip_start_seconds=NULL, clip_end_seconds=NULL, clip_created_at=NULL WHERE live_session_id=?", (session_id,))
            con.execute("UPDATE live_sessions SET status='excluida', ended_action='excluir', recording_filename=NULL, optimized_filename=NULL, snapshot_filename=NULL, current_product_id=NULL WHERE id=?", (session_id,))
            safe_msg = 'Arquivos da live excluídos.'
        elif action == 'otimizar':
            ok, safe_msg = optimize_live_recording(session_id)
            if not ok:
                return RedirectResponse(url=f"/live/finalizar/{session_id}?msg={quote_plus(safe_msg)}", status_code=303)
        else:
            safe_msg = 'Ação não reconhecida.'
    return RedirectResponse(url=f"/live/finalizar/{session_id}?msg={quote_plus(safe_msg)}", status_code=303)



@app.post("/live/repescagem/{session_id}/clips")
def live_generate_recap_clips(session_id: int) -> Response:
    generated, messages = generate_live_reference_clips(session_id)
    message = f"{generated} clipe(s) curto(s) gerado(s) e ligado(s) às referências."
    if generated == 0 and messages:
        message = messages[-1]
    return RedirectResponse(url=f"/live/repescagem/{session_id}?msg={quote_plus(message)}", status_code=303)


@app.post("/live/items/{item_id}/clip")
def live_generate_item_clip(item_id: int) -> Response:
    with get_db() as con:
        item = con.execute("SELECT * FROM live_session_items WHERE id=?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Referência da live não encontrada.")
        session_id = int(item["live_session_id"])
        product_id = int(item["product_id"])
    ok, msg, _filename = create_live_reference_clip(session_id, product_id, item_id)
    return RedirectResponse(url=f"/live/repescagem/{session_id}?msg={quote_plus(msg)}", status_code=303)


@app.post("/api/live/reference-clip/{item_id}")
def api_live_reference_clip(item_id: int) -> JSONResponse:
    with get_db() as con:
        item = con.execute("SELECT * FROM live_session_items WHERE id=?", (item_id,)).fetchone()
        if not item:
            return JSONResponse({"ok": False, "message": "Referência da live não encontrada."}, status_code=404)
        session_id = int(item["live_session_id"])
        product_id = int(item["product_id"])
    ok, msg, filename = create_live_reference_clip(session_id, product_id, item_id)
    return JSONResponse({
        "ok": ok,
        "message": msg,
        "clip_url": f"/static/live/clips/{filename}" if filename else "",
    }, status_code=200 if ok else 400)





@app.get("/labels", response_class=HTMLResponse)
def labels_page(request: Request) -> Response:
    with get_db() as con:
        products = con.execute("SELECT * FROM products WHERE status='disponivel' ORDER BY id DESC").fetchall()
    return templates.TemplateResponse("labels.html", {"request": request, "products": products, "active": "labels"})



# ---------------------------------------------------------------------------
# Central da Live: fila inteligente, intenção de comentários, reservas por ordem
# de chegada, carrinho por cliente, página pública da peça atual e modo apresentadora.
# Este bloco é aditivo: não altera os fluxos antigos de live/reconhecimento.
# ---------------------------------------------------------------------------

LIVE_RESERVATION_TIMEOUT_MINUTES = int(os.getenv("BRECHORISEE_LIVE_RESERVATION_TIMEOUT_MINUTES", "30"))
LIVE_COMPANION_POLL_MS = int(os.getenv("BRECHORISEE_LIVE_COMPANION_POLL_MS", "1000"))
LIVE_COMPANION_FULL_CARD_SECONDS = int(os.getenv("BRECHORISEE_LIVE_COMPANION_FULL_CARD_SECONDS", "9"))
LIVE_COMPANION_STALE_SECONDS = int(os.getenv("BRECHORISEE_LIVE_COMPANION_STALE_SECONDS", "8"))
LIVE_STARTED_PUBLIC_ALERT_HOURS = int(os.getenv("BRECHORISEE_LIVE_STARTED_PUBLIC_ALERT_HOURS", "1"))


def init_live_central_schema() -> None:
    with get_db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS live_queue_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_session_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pendente',
                shown_at TEXT,
                hidden_at TEXT,
                seconds_on_screen REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                UNIQUE(live_session_id, product_id),
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS live_reservation_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_session_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                customer_handle TEXT,
                customer_phone TEXT,
                source TEXT DEFAULT 'central_live',
                source_comment_id INTEGER,
                queue_position INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'aguardando_pagamento',
                reserved_at TEXT NOT NULL,
                expires_at TEXT,
                paid_at TEXT,
                cancelled_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                customer_account_id INTEGER,
                sale_id INTEGER,
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (source_comment_id) REFERENCES live_comments(id)
            );

            CREATE TABLE IF NOT EXISTS live_customer_carts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_session_id INTEGER NOT NULL,
                customer_key TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT,
                customer_instagram TEXT,
                status TEXT NOT NULL DEFAULT 'aberto',
                subtotal REAL NOT NULL DEFAULT 0,
                discount REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                delivery_method TEXT DEFAULT 'retirada',
                pix_key TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                expires_at TEXT,
                public_token TEXT,
                customer_account_id INTEGER,
                UNIQUE(live_session_id, customer_key),
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id)
            );

            CREATE TABLE IF NOT EXISTS live_customer_cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cart_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                reservation_id INTEGER,
                price REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'reservado',
                created_at TEXT NOT NULL,
                updated_at TEXT,
                UNIQUE(cart_id, product_id),
                FOREIGN KEY (cart_id) REFERENCES live_customer_carts(id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (reservation_id) REFERENCES live_reservation_queue(id)
            );

            CREATE TABLE IF NOT EXISTS live_comment_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                live_comment_id INTEGER,
                live_session_id INTEGER NOT NULL,
                product_id INTEGER,
                customer_name TEXT,
                message TEXT NOT NULL,
                intent TEXT NOT NULL,
                suggested_action TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'sugerida',
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                FOREIGN KEY (live_comment_id) REFERENCES live_comments(id),
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_live_queue_session_order ON live_queue_items(live_session_id, status, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_live_reservation_product_status ON live_reservation_queue(live_session_id, product_id, status, queue_position);
            CREATE INDEX IF NOT EXISTS idx_live_reservation_customer_status ON live_reservation_queue(live_session_id, customer_name, status);
            CREATE INDEX IF NOT EXISTS idx_live_carts_session_customer ON live_customer_carts(live_session_id, customer_key);
            CREATE INDEX IF NOT EXISTS idx_live_cart_items_cart ON live_customer_cart_items(cart_id);
            CREATE INDEX IF NOT EXISTS idx_live_comment_intents_session ON live_comment_intents(live_session_id, status, created_at);
            """
        )
        ensure_column(con, "live_reservation_queue", "customer_account_id", "INTEGER")
        ensure_column(con, "live_reservation_queue", "sale_id", "INTEGER")
        ensure_column(con, "live_customer_carts", "public_token", "TEXT")
        ensure_column(con, "live_customer_carts", "customer_account_id", "INTEGER")
        con.executescript(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_live_carts_public_token ON live_customer_carts(public_token) WHERE public_token IS NOT NULL AND TRIM(public_token)<>'';
            CREATE INDEX IF NOT EXISTS idx_live_reservation_customer_account ON live_reservation_queue(customer_account_id, created_at);
            """
        )
        try:
            for row in con.execute("SELECT id FROM live_customer_carts WHERE public_token IS NULL OR TRIM(public_token)=''").fetchall():
                ensure_live_cart_token(con, int(row["id"]))
        except Exception:
            logger.debug("Tokens públicos de carrinho da live serão criados sob demanda.", exc_info=True)
        con.commit()


def _live_text_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9@._\-\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _live_customer_key(name: Any, handle: Any = "") -> str:
    base = _live_text_key(handle or name)
    return base or "cliente"


def live_detect_comment_intent(message: Any) -> dict[str, str]:
    raw = str(message or "").strip()
    text = _live_text_key(raw)

    rules: list[tuple[str, str, str, str]] = [
        ("reserva", r"\b(eu quero|quero essa|quero|reserva|reservar|fica pra mim|pego essa|sou eu|quero tambem|quero também)\b", "Reservar peça atual", "reservar"),
        ("fila_espera", r"\b(se .*desistir|segunda da fila|fila|lista de espera|quero se sobrar)\b", "Colocar na fila de espera", "reservar"),
        ("preco", r"\b(qual (o )?valor|valor\?|preco|preço|quanto|qto|quanto custa)\b", "Responder preço", "responder_preco"),
        ("medidas", r"\b(medida|medidas|comprimento|busto|cintura|quadril|ombro|veste)\b", "Enviar medidas", "enviar_medidas"),
        ("tamanho", r"\b(tamanho|tam\b|tem no|serve p|serve m|serve g|e p|e m|e g|é p|é m|é g)\b", "Responder tamanho disponível", "responder_tamanho"),
        ("link", r"\b(manda link|manda o link|me envia|envia link|link|checkout|carrinho)\b", "Copiar/enviar link da peça", "enviar_link"),
        ("pagamento", r"\b(pix|paguei|pagamento|chave|comprovante|finalizar)\b", "Conferir pagamento/carrinho", "conferir_pagamento"),
    ]

    for intent, pattern, label, action in rules:
        if re.search(pattern, text):
            return {"intent": intent, "label": label, "suggested_action": action, "raw": raw}
    return {"intent": "comentario", "label": "Acompanhar comentário", "suggested_action": "acompanhar", "raw": raw}


def _live_product_payload_for_central(product: sqlite3.Row | None, request: Request | None = None) -> dict[str, Any] | None:
    payload = live_product_payload(product)
    if not payload:
        return None
    payload["condition"] = product["condition"] if "condition" in product.keys() else ""
    payload["category"] = product["category"] if "category" in product.keys() else ""
    payload["garment_type"] = product["garment_type"] if "garment_type" in product.keys() else ""
    if request:
        base = str(request.base_url).rstrip("/")
        payload["public_current_url"] = f"{base}/live/peca-atual"
        payload["public_product_url"] = f"{base}/loja/produto/{product['code']}"
        payload["short_url"] = f"{base}/p/{product['code']}"
    else:
        payload["public_current_url"] = "/live/peca-atual"
        payload["public_product_url"] = f"/loja/produto/{product['code']}"
        payload["short_url"] = f"/p/{product['code']}"
    return payload


def _live_session_or_404(con: sqlite3.Connection, session_id: int) -> sqlite3.Row:
    session = con.execute("SELECT * FROM live_sessions WHERE id=?", (int(session_id),)).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Live não encontrada.")
    return session


def _live_active_session(con: sqlite3.Connection) -> sqlite3.Row:
    return get_or_create_active_live_session(con)


def _live_get_product(con: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM products WHERE id=?", (int(product_id),)).fetchone()


def _live_current_queue_item(con: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    return con.execute(
        """
        SELECT lq.*, p.code, p.title, p.sale_price, p.size, p.measurements, p.condition, p.status AS product_status,
               p.image_filename, p.characteristics, p.brand, p.color, p.category, p.garment_type
        FROM live_queue_items lq
        JOIN products p ON p.id = lq.product_id
        WHERE lq.live_session_id=? AND lq.status='atual'
        ORDER BY lq.shown_at DESC, lq.id DESC
        LIMIT 1
        """,
        (int(session_id),),
    ).fetchone()


def _live_queue_product_payload(row: sqlite3.Row | None, request: Request | None = None) -> dict[str, Any] | None:
    if not row:
        return None
    product_like = {
        "id": row["product_id"] if "product_id" in row.keys() else row["id"],
        "code": row["code"],
        "title": row["title"],
        "sale_price": row["sale_price"],
        "size": row["size"] if "size" in row.keys() else "",
        "brand": row["brand"] if "brand" in row.keys() else "",
        "color": row["color"] if "color" in row.keys() else "",
        "status": row["product_status"] if "product_status" in row.keys() else row["status"],
        "image_filename": row["image_filename"] if "image_filename" in row.keys() else "",
        "characteristics": row["characteristics"] if "characteristics" in row.keys() else "",
        "measurements": row["measurements"] if "measurements" in row.keys() else "",
        "condition": row["condition"] if "condition" in row.keys() else "",
        "category": row["category"] if "category" in row.keys() else "",
        "garment_type": row["garment_type"] if "garment_type" in row.keys() else "",
    }

    class _RowProxy(dict):
        def keys(self):
            return super().keys()

    payload = _RowProxy(product_like)
    product_payload = {
        "id": int(product_like["id"]),
        "code": product_like["code"],
        "title": product_like["title"],
        "price": float(product_like["sale_price"] or 0),
        "price_label": money(product_like["sale_price"] or 0),
        "size": product_like["size"] or "",
        "brand": product_like["brand"] or "",
        "color": product_like["color"] or "",
        "status": product_like["status"] or "",
        "image_url": f"/static/uploads/{product_like['image_filename']}" if product_like["image_filename"] else "",
        "public_url": f"/cliente/peca/{product_like['code']}",
        "store_url": f"/loja/produto/{product_like['code']}",
        "characteristics": product_like["characteristics"] or "",
        "measurements": product_like["measurements"] or "",
        "condition": product_like["condition"] or "",
        "category": product_like["category"] or "",
        "garment_type": product_like["garment_type"] or "",
    }
    if request:
        base = str(request.base_url).rstrip("/")
        product_payload["public_current_url"] = f"{base}/live/peca-atual"
        product_payload["public_product_url"] = f"{base}/loja/produto/{product_like['code']}"
        product_payload["short_url"] = f"{base}/p/{product_like['code']}"
    product_payload["queue_item_id"] = int(row["id"]) if "id" in row.keys() else None
    product_payload["queue_status"] = row["status"] if "status" in row.keys() else ""
    product_payload["shown_at"] = row["shown_at"] if "shown_at" in row.keys() else ""
    product_payload["seconds_on_screen"] = float(row["seconds_on_screen"] or 0) if "seconds_on_screen" in row.keys() else 0
    return product_payload


def _live_expire_overdue_reservations(con: sqlite3.Connection, session_id: int) -> None:
    now = datetime.now()
    overdue = con.execute(
        """
        SELECT * FROM live_reservation_queue
        WHERE live_session_id=? AND status='aguardando_pagamento' AND expires_at IS NOT NULL AND expires_at < ?
        ORDER BY id
        """,
        (int(session_id), now_iso()),
    ).fetchall()
    for row in overdue:
        con.execute(
            "UPDATE live_reservation_queue SET status='desistiu', cancelled_at=?, updated_at=?, notes=COALESCE(notes,'') || ? WHERE id=?",
            (now_iso(), now_iso(), "\nReserva vencida automaticamente.", int(row["id"])),
        )
        product_id = int(row["product_id"])
        promoted = _live_promote_next_waiting(con, int(session_id), product_id)
        if not promoted:
            product = con.execute("SELECT status FROM products WHERE id=?", (product_id,)).fetchone()
            if product and product["status"] == "reservado":
                con.execute("UPDATE products SET status='disponivel', sync_updated_at=? WHERE id=?", (now_iso(), product_id))


def _live_get_or_create_cart(
    con: sqlite3.Connection,
    session_id: int,
    customer_name: str,
    customer_handle: str = "",
    customer_phone: str = "",
    expires_at: str | None = None,
    customer_account_id: int | None = None,
) -> sqlite3.Row:
    key = _live_customer_key(customer_name, customer_handle or customer_phone)
    existing = con.execute(
        "SELECT * FROM live_customer_carts WHERE live_session_id=? AND customer_key=?",
        (int(session_id), key),
    ).fetchone()
    if existing:
        token = row_get(existing, "public_token", "") or ensure_live_cart_token(con, int(existing["id"]))
        con.execute(
            """
            UPDATE live_customer_carts
            SET customer_name=?, customer_phone=COALESCE(NULLIF(?,''), customer_phone),
                customer_instagram=COALESCE(NULLIF(?,''), customer_instagram),
                expires_at=COALESCE(?, expires_at), customer_account_id=COALESCE(customer_account_id, ?),
                public_token=COALESCE(NULLIF(public_token,''), ?), updated_at=?
            WHERE id=?
            """,
            (customer_name, normalize_phone(customer_phone), customer_handle, expires_at, customer_account_id, token, now_iso(), int(existing["id"])),
        )
        return con.execute("SELECT * FROM live_customer_carts WHERE id=?", (int(existing["id"]),)).fetchone()
    public_token = ensure_unique_public_token(con, "live_customer_carts", "public_token", "cart_")
    cur = con.execute(
        """
        INSERT INTO live_customer_carts(live_session_id, customer_key, customer_name, customer_phone, customer_instagram, status, created_at, updated_at, expires_at, public_token, customer_account_id)
        VALUES(?,?,?,?,?,'aberto',?,?,?,?,?)
        """,
        (int(session_id), key, customer_name, normalize_phone(customer_phone), customer_handle, now_iso(), now_iso(), expires_at, public_token, customer_account_id),
    )
    return con.execute("SELECT * FROM live_customer_carts WHERE id=?", (cur.lastrowid,)).fetchone()


def _live_recalculate_cart(con: sqlite3.Connection, cart_id: int) -> None:
    total = con.execute(
        """
        SELECT COALESCE(SUM(price),0) AS total
        FROM live_customer_cart_items
        WHERE cart_id=? AND status NOT IN ('cancelado','desistiu','fila_espera')
        """,
        (int(cart_id),),
    ).fetchone()["total"]
    con.execute(
        "UPDATE live_customer_carts SET subtotal=?, total=? - discount, updated_at=? WHERE id=?",
        (float(total or 0), float(total or 0), now_iso(), int(cart_id)),
    )


def _live_add_cart_item_for_reservation(con: sqlite3.Connection, reservation: sqlite3.Row) -> None:
    product = _live_get_product(con, int(reservation["product_id"]))
    if not product:
        return
    customer_account_id = row_get(reservation, "customer_account_id") or find_customer_account_id_for_identity(con, reservation["customer_name"], reservation["customer_phone"], "")
    cart = _live_get_or_create_cart(
        con,
        int(reservation["live_session_id"]),
        reservation["customer_name"],
        reservation["customer_handle"] or "",
        reservation["customer_phone"] or "",
        reservation["expires_at"],
        int(customer_account_id) if customer_account_id else None,
    )
    price = validate_money_amount(product["sale_price"], f"Preço da peça {product['code']}", minimum=0, allow_zero=False)
    con.execute(
        """
        INSERT OR IGNORE INTO live_customer_cart_items(cart_id, product_id, reservation_id, price, status, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?)
        """,
        (int(cart["id"]), int(product["id"]), int(reservation["id"]), price, "reservado", now_iso(), now_iso()),
    )
    con.execute(
        "UPDATE live_customer_cart_items SET reservation_id=?, price=?, status=CASE WHEN status='fila_espera' THEN 'reservado' ELSE status END, updated_at=? WHERE cart_id=? AND product_id=?",
        (int(reservation["id"]), price, now_iso(), int(cart["id"]), int(product["id"])),
    )
    _live_recalculate_cart(con, int(cart["id"]))


def _live_promote_next_waiting(con: sqlite3.Connection, session_id: int, product_id: int) -> sqlite3.Row | None:
    next_wait = con.execute(
        """
        SELECT * FROM live_reservation_queue
        WHERE live_session_id=? AND product_id=? AND status='fila_espera'
        ORDER BY queue_position ASC, id ASC
        LIMIT 1
        """,
        (int(session_id), int(product_id)),
    ).fetchone()
    if not next_wait:
        return None
    expires_at = (datetime.now() + timedelta(minutes=LIVE_RESERVATION_TIMEOUT_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    con.execute(
        "UPDATE live_reservation_queue SET status='aguardando_pagamento', reserved_at=?, expires_at=?, updated_at=?, notes=COALESCE(notes,'') || ? WHERE id=?",
        (now_iso(), expires_at, now_iso(), "\nPromovida automaticamente da fila de espera.", int(next_wait["id"])),
    )
    con.execute("UPDATE products SET status='reservado', sync_updated_at=? WHERE id=?", (now_iso(), int(product_id)))
    promoted = con.execute("SELECT * FROM live_reservation_queue WHERE id=?", (int(next_wait["id"]),)).fetchone()
    _live_add_cart_item_for_reservation(con, promoted)
    return promoted


def _live_reservation_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "live_session_id": int(row["live_session_id"]),
        "product_id": int(row["product_id"]),
        "customer_name": row["customer_name"],
        "customer_handle": row["customer_handle"] or "",
        "customer_phone": row["customer_phone"] or "",
        "queue_position": int(row["queue_position"] or 1),
        "status": row["status"],
        "reserved_at": row["reserved_at"],
        "expires_at": row["expires_at"] or "",
        "paid_at": row["paid_at"] or "",
        "notes": row["notes"] or "",
    }


def _live_generate_current_qr(con: sqlite3.Connection, request: Request, session_id: int) -> str:
    try:
        url = str(request.base_url).rstrip("/") + "/live/peca-atual"
        filename = f"live_atual_{int(session_id)}.png"
        path = QR_DIR / filename
        if not path.exists() or (time.time() - path.stat().st_mtime) > 300:
            img = qrcode.make(url)
            img.save(path)
        return f"/static/qrcodes/{filename}"
    except Exception:
        logger.debug("Não foi possível gerar QR da live.", exc_info=True)
        return ""


def _live_build_cart_summary(con: sqlite3.Connection, cart_id: int | str, request: Request | None = None) -> dict[str, Any] | None:
    token_or_id = str(cart_id or "").strip()
    if token_or_id.isdigit():
        cart = con.execute("SELECT * FROM live_customer_carts WHERE id=?", (int(token_or_id),)).fetchone()
    else:
        cart = con.execute("SELECT * FROM live_customer_carts WHERE public_token=?", (token_or_id,)).fetchone()
    if not cart:
        return None
    token = row_get(cart, "public_token", "") or ensure_live_cart_token(con, int(cart["id"]))
    if not row_get(cart, "public_token", ""):
        cart = con.execute("SELECT * FROM live_customer_carts WHERE id=?", (int(cart["id"]),)).fetchone()
    items = con.execute(
        """
        SELECT lci.*, p.code, p.title, p.sale_price
        FROM live_customer_cart_items lci
        JOIN products p ON p.id=lci.product_id
        WHERE lci.cart_id=? AND lci.status NOT IN ('cancelado','desistiu','fila_espera')
        ORDER BY lci.id
        """,
        (int(cart["id"]),),
    ).fetchall()
    lines = []
    for idx, item in enumerate(items, 1):
        lines.append(f"{idx}. {item['title']} - {money(item['price'])}")
    base = str(request.base_url).rstrip("/") if request else ""
    cart_link = f"{base}/live/carrinho/{token}" if base else f"/live/carrinho/{token}"
    cta = brechorisee_customer_app_cta(request, compact=False) if request else brechorisee_customer_app_cta(None, compact=False)
    msg = (
        f"Oi, {cart['customer_name']}! Separei suas peças da live 💖\n\n"
        + ("\n".join(lines) if lines else "Seu carrinho da live ainda está vazio.")
        + f"\n\nTotal: {money(cart['total'] or 0)}\n\nPara finalizar, acesse:\n{cart_link}\n\n{cta}"
    )
    return {
        "id": int(cart["id"]),
        "public_token": token,
        "customer_account_id": row_get(cart, "customer_account_id", None),
        "customer_name": cart["customer_name"],
        "customer_phone": cart["customer_phone"] or "",
        "customer_instagram": cart["customer_instagram"] or "",
        "status": cart["status"],
        "subtotal": float(cart["subtotal"] or 0),
        "total": float(cart["total"] or 0),
        "total_label": money(cart["total"] or 0),
        "expires_at": cart["expires_at"] or "",
        "link": cart_link,
        "message": msg,
        "items": [
            {
                "id": int(item["id"]),
                "product_id": int(item["product_id"]),
                "code": item["code"],
                "title": item["title"],
                "price": float(item["price"] or 0),
                "price_label": money(item["price"] or 0),
                "status": item["status"],
            }
            for item in items
        ],
    }



def _telegram_live_session_for_commands(con: sqlite3.Connection, create_if_missing: bool = True) -> sqlite3.Row | None:
    init_live_central_schema()
    live = con.execute(
        """
        SELECT * FROM live_sessions
        WHERE status IN ('ao_vivo','aberta')
        ORDER BY CASE status WHEN 'ao_vivo' THEN 0 WHEN 'aberta' THEN 1 ELSE 2 END, id DESC
        LIMIT 1
        """
    ).fetchone()
    if live:
        return live
    if create_if_missing:
        return _live_active_session(con)
    return con.execute("SELECT * FROM live_sessions ORDER BY id DESC LIMIT 1").fetchone()


def _telegram_live_current_product(con: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    current = _live_current_queue_item(con, int(session_id))
    if current:
        return current
    live = con.execute("SELECT * FROM live_sessions WHERE id=?", (int(session_id),)).fetchone()
    product_id = int(live["current_product_id"] or 0) if live and "current_product_id" in live.keys() else 0
    if not product_id:
        return None
    product = con.execute(
        """
        SELECT p.id AS product_id, p.code, p.title, p.sale_price, p.size, p.measurements, p.condition,
               p.status AS product_status, p.image_filename, p.characteristics, p.brand, p.color,
               p.category, p.garment_type, 'atual' AS status, NULL AS shown_at, 0 AS seconds_on_screen
        FROM products p
        WHERE p.id=?
        """,
        (product_id,),
    ).fetchone()
    return product


def _telegram_live_product_line(row: sqlite3.Row | dict[str, Any] | None) -> str:
    if not row:
        return "sem peça"
    data = row_to_dict(row)
    code = telegram_html(data.get("code") or "")
    title = telegram_html(data.get("title") or "Peça")
    return f"{code} — {title} — {money(data.get('sale_price') or data.get('price') or 0)}"


def _telegram_live_current_text(con: sqlite3.Connection, session_id: int | None = None) -> str:
    live = _telegram_live_session_for_commands(con)
    if not live:
        return "Nenhuma live cadastrada."
    session_id = int(session_id or live["id"])
    current = _telegram_live_current_product(con, session_id)
    next_row = con.execute(
        """
        SELECT lq.*, p.code, p.title, p.sale_price, p.size, p.measurements, p.condition, p.status AS product_status
        FROM live_queue_items lq
        JOIN products p ON p.id=lq.product_id
        WHERE lq.live_session_id=? AND lq.status='pendente'
        ORDER BY lq.sort_order ASC, lq.id ASC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    if not current:
        return "\n".join([
            f"🎥 Live #{session_id} — {telegram_html(live['title'])}",
            "Peça atual: nenhuma peça na tela.",
            f"Próxima: {_telegram_live_product_line(next_row) if next_row else 'sem próxima peça'}",
            "",
            "Use /proxima para puxar a próxima peça da fila ou /addfila CODIGO para adicionar.",
        ])
    status = current["product_status"] if "product_status" in current.keys() else current["status"]
    elapsed = ""
    if "shown_at" in current.keys() and current["shown_at"]:
        dt = parse_dt(current["shown_at"])
        if dt:
            seconds = max(0, int((datetime.now() - dt).total_seconds()))
            elapsed = f"\nTempo na tela: {seconds // 60:02d}:{seconds % 60:02d}"
    link = telegram_public_url("/live/peca-atual")
    lines = [
        f"🎥 <b>Peça atual da live #{session_id}</b>",
        f"Código: {telegram_html(current['code'])}",
        f"Nome: {telegram_html(current['title'])}",
        f"Valor: {money(current['sale_price'] or 0)}",
        f"Tamanho: {telegram_html(current['size'] if 'size' in current.keys() else '') or '-'}",
        f"Medidas: {telegram_html(current['measurements'] if 'measurements' in current.keys() else '') or '-'}",
        f"Estado: {telegram_html(current['condition'] if 'condition' in current.keys() else '') or '-'}",
        f"Status: {telegram_html(status or '')}",
        f"Link/QR: {link}",
    ]
    if elapsed:
        lines.append(elapsed.strip())
    lines += [
        "",
        f"Próxima: {_telegram_live_product_line(next_row) if next_row else 'sem próxima peça'}",
        "",
        "Comandos: /reservar NOME | TELEFONE · /espera NOME · /vendida · /proxima",
    ]
    return "\n".join(lines)


def _telegram_live_panel_text(con: sqlite3.Connection) -> str:
    live = _telegram_live_session_for_commands(con)
    if not live:
        return "Nenhuma live cadastrada."
    session_id = int(live["id"])
    _live_expire_overdue_reservations(con, session_id)
    current = _telegram_live_current_product(con, session_id)
    pending_count = con.execute("SELECT COUNT(*) AS total FROM live_queue_items WHERE live_session_id=? AND status='pendente'", (session_id,)).fetchone()["total"]
    shown_count = con.execute(
        "SELECT COUNT(*) AS total FROM live_queue_items WHERE live_session_id=? AND status IN ('atual','mostrada','reservada','vendida','pulada')",
        (session_id,),
    ).fetchone()["total"]
    pending_res = con.execute(
        """
        SELECT COALESCE(SUM(p.sale_price),0) AS total, COUNT(*) AS qty
        FROM live_reservation_queue r
        JOIN products p ON p.id=r.product_id
        WHERE r.live_session_id=? AND r.status='aguardando_pagamento'
        """,
        (session_id,),
    ).fetchone()
    paid = con.execute(
        """
        SELECT COALESCE(SUM(p.sale_price),0) AS total, COUNT(*) AS qty
        FROM live_reservation_queue r
        JOIN products p ON p.id=r.product_id
        WHERE r.live_session_id=? AND r.status IN ('pago','vendido')
        """,
        (session_id,),
    ).fetchone()
    waiting = con.execute("SELECT COUNT(*) AS total FROM live_reservation_queue WHERE live_session_id=? AND status='fila_espera'", (session_id,)).fetchone()["total"]
    comments_waiting = con.execute("SELECT COUNT(*) AS total FROM live_comment_intents WHERE live_session_id=? AND status='sugerida'", (session_id,)).fetchone()["total"]
    return "\n".join([
        f"🎛️ <b>Central da Live #{session_id}</b>",
        f"Título: {telegram_html(live['title'])}",
        f"Status: {telegram_html(live['status'])}",
        f"Peça atual: {_telegram_live_product_line(current)}",
        f"Peças mostradas: {int(shown_count or 0)}",
        f"Próximas na fila: {int(pending_count or 0)}",
        f"Reservado pendente: {money(pending_res['total'] or 0)} ({int(pending_res['qty'] or 0)})",
        f"Pago/vendido: {money(paid['total'] or 0)} ({int(paid['qty'] or 0)})",
        f"Fila de espera: {int(waiting or 0)}",
        f"Comentários para revisar: {int(comments_waiting or 0)}",
        "",
        f"Painel: {telegram_public_url(f'/live/central/{session_id}')}",
        f"Página pública: {telegram_public_url('/live/peca-atual')}",
        "",
        "Comandos úteis: /atual · /fila · /proxima · /reservar Maria | telefone · /pago Maria · /resumo_live",
    ])


def _telegram_live_queue_text(con: sqlite3.Connection) -> str:
    live = _telegram_live_session_for_commands(con)
    if not live:
        return "Nenhuma live cadastrada."
    session_id = int(live["id"])
    rows = con.execute(
        """
        SELECT lq.*, p.code, p.title, p.sale_price
        FROM live_queue_items lq
        JOIN products p ON p.id=lq.product_id
        WHERE lq.live_session_id=?
        ORDER BY CASE lq.status WHEN 'atual' THEN 0 WHEN 'pendente' THEN 1 WHEN 'reservada' THEN 2 WHEN 'vendida' THEN 3 ELSE 4 END,
                 lq.sort_order ASC, lq.id ASC
        LIMIT 20
        """,
        (session_id,),
    ).fetchall()
    if not rows:
        return f"Fila da live #{session_id} vazia. Use /addfila CODIGO."
    lines = [f"📋 <b>Fila da live #{session_id}</b>"]
    for idx, row in enumerate(rows, 1):
        prefix = "▶️" if row["status"] == "atual" else f"{idx}."
        lines.append(f"{prefix} {telegram_html(row['code'])} — {telegram_html(row['title'])} — {money(row['sale_price'] or 0)} — {telegram_html(row['status'])}")
    return "\n".join(lines)


def _telegram_find_product_for_live(con: sqlite3.Connection, term: str) -> sqlite3.Row | None:
    term = (term or "").strip()
    if not term:
        return None
    product = con.execute("SELECT * FROM products WHERE lower(code)=lower(?) AND deleted_at IS NULL LIMIT 1", (term,)).fetchone()
    if product:
        return product
    like = "%" + term.replace("%", "") + "%"
    return con.execute(
        """
        SELECT * FROM products
        WHERE deleted_at IS NULL AND (code LIKE ? OR title LIKE ? OR brand LIKE ?)
        ORDER BY CASE status WHEN 'disponivel' THEN 0 WHEN 'reservado' THEN 1 ELSE 2 END, id DESC
        LIMIT 1
        """,
        (like, like, like),
    ).fetchone()


def _telegram_live_add_queue(con: sqlite3.Connection, session_id: int, term: str) -> str:
    product = _telegram_find_product_for_live(con, term)
    if not product:
        return "Peça não encontrada. Use /addfila CODIGO ou parte do nome."
    max_order = con.execute("SELECT COALESCE(MAX(sort_order),0) AS max_order FROM live_queue_items WHERE live_session_id=?", (session_id,)).fetchone()["max_order"]
    try:
        con.execute(
            "INSERT INTO live_queue_items(live_session_id, product_id, sort_order, status, notes, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
            (session_id, int(product["id"]), int(max_order or 0) + 10, "pendente", "Adicionada pelo Telegram.", now_iso(), now_iso()),
        )
    except sqlite3.IntegrityError:
        con.execute(
            "UPDATE live_queue_items SET status=CASE WHEN status IN ('vendida','reservada') THEN status ELSE 'pendente' END, notes=?, updated_at=? WHERE live_session_id=? AND product_id=?",
            ("Reativada/adicionada pelo Telegram.", now_iso(), session_id, int(product["id"])),
        )
    return f"✅ {telegram_html(product['code'])} — {telegram_html(product['title'])} adicionada à fila da live."


def _telegram_live_advance_next(con: sqlite3.Connection, session_id: int) -> str:
    _live_session_or_404(con, session_id)
    now = now_iso()
    current = con.execute("SELECT * FROM live_queue_items WHERE live_session_id=? AND status='atual' ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
    if current:
        seconds = 0
        if current["shown_at"]:
            dt = parse_dt(current["shown_at"])
            if dt:
                seconds = max(0, int((datetime.now() - dt).total_seconds()))
        con.execute(
            "UPDATE live_queue_items SET status='mostrada', hidden_at=?, seconds_on_screen=?, updated_at=? WHERE id=?",
            (now, float(seconds), now, int(current["id"])),
        )
    next_item = con.execute(
        "SELECT * FROM live_queue_items WHERE live_session_id=? AND status='pendente' ORDER BY sort_order ASC, id ASC LIMIT 1",
        (session_id,),
    ).fetchone()
    if not next_item:
        return "Não há próxima peça na fila. Use /addfila CODIGO."
    product = _live_get_product(con, int(next_item["product_id"]))
    if not product:
        return "A próxima peça não foi encontrada no estoque."
    con.execute("UPDATE live_queue_items SET status='atual', shown_at=?, updated_at=? WHERE id=?", (now, now, int(next_item["id"])))
    con.execute(
        "UPDATE live_sessions SET current_product_id=?, status=CASE WHEN status='aberta' THEN 'ao_vivo' ELSE status END, started_at=COALESCE(started_at, ?) WHERE id=?",
        (int(product["id"]), now, session_id),
    )
    _live_insert_item(con, session_id, int(product["id"]), "mostrada", "Peça mostrada por comando do Telegram.", 0)
    return "▶️ Próxima peça na tela:\n" + _telegram_live_current_text(con, session_id)


def _telegram_parse_customer_spec(spec: str) -> tuple[str, str, str]:
    spec = (spec or "").strip()
    parts = [p.strip() for p in re.split(r"\s*\|\s*", spec, maxsplit=2) if p.strip()]
    name = parts[0] if parts else ""
    phone = parts[1] if len(parts) >= 2 else ""
    handle = ""
    m = re.search(r"@\w[\w._]*", name)
    if m:
        handle = m.group(0)
        name = name.replace(handle, "").strip() or handle
    return name[:120], handle[:120], phone[:40]


def _telegram_live_reserve_current(con: sqlite3.Connection, session_id: int, spec: str, force_waitlist: bool = False) -> str:
    customer_name, customer_handle, customer_phone = _telegram_parse_customer_spec(spec)
    if not customer_name:
        return "Informe a cliente. Exemplo: /reservar Maria | 11999999999"
    _live_expire_overdue_reservations(con, session_id)
    current = _telegram_live_current_product(con, session_id)
    product_id = int(current["product_id"]) if current and "product_id" in current.keys() else 0
    if not product_id and current and "id" in current.keys():
        product_id = int(current["id"])
    product = _live_get_product(con, product_id) if product_id else None
    if not product:
        return "Não há peça atual para reservar. Use /proxima primeiro."
    if product["status"] == "vendido":
        return f"⚠️ {telegram_html(product['code'])} já está vendida."

    dup = con.execute(
        """
        SELECT * FROM live_reservation_queue
        WHERE live_session_id=? AND product_id=? AND lower(customer_name)=lower(?) AND status IN ('aguardando_pagamento','fila_espera','pago','vendido')
        LIMIT 1
        """,
        (session_id, int(product_id), customer_name),
    ).fetchone()
    if dup:
        return f"Cliente já está nesta peça como {telegram_html(dup['status'])}. Posição {int(dup['queue_position'] or 1)}."

    principal = con.execute(
        """
        SELECT * FROM live_reservation_queue
        WHERE live_session_id=? AND product_id=? AND status IN ('aguardando_pagamento','pago','vendido')
        ORDER BY queue_position ASC LIMIT 1
        """,
        (session_id, int(product_id)),
    ).fetchone()
    max_pos = con.execute(
        "SELECT COALESCE(MAX(queue_position),0) AS max_pos FROM live_reservation_queue WHERE live_session_id=? AND product_id=?",
        (session_id, int(product_id)),
    ).fetchone()["max_pos"]
    status = "fila_espera" if principal or force_waitlist else "aguardando_pagamento"
    expires_at = (datetime.now() + timedelta(minutes=LIVE_RESERVATION_TIMEOUT_MINUTES)).strftime("%Y-%m-%d %H:%M:%S") if status == "aguardando_pagamento" else None
    cur = con.execute(
        """
        INSERT INTO live_reservation_queue(
            live_session_id, product_id, customer_name, customer_handle, customer_phone, source,
            queue_position, status, reserved_at, expires_at, notes, created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id, int(product_id), customer_name, customer_handle, customer_phone, "telegram",
            int(max_pos or 0) + 1, status, now_iso(), expires_at, "Criada pelo Telegram.", now_iso(), now_iso(),
        ),
    )
    reservation = con.execute("SELECT * FROM live_reservation_queue WHERE id=?", (int(cur.lastrowid),)).fetchone()
    if status == "aguardando_pagamento":
        con.execute("UPDATE products SET status='reservado', sync_updated_at=? WHERE id=?", (now_iso(), int(product_id)))
        _live_add_cart_item_for_reservation(con, reservation)
        con.execute(
            "UPDATE live_queue_items SET status=CASE WHEN status='atual' THEN 'atual' ELSE 'reservada' END, updated_at=? WHERE live_session_id=? AND product_id=?",
            (now_iso(), session_id, int(product_id)),
        )
    _live_insert_item(con, session_id, int(product_id), "reservada", f"Reserva pelo Telegram: {customer_name} ({status}).", 0)
    cart_line = ""
    if status == "aguardando_pagamento":
        cart = con.execute(
            "SELECT * FROM live_customer_carts WHERE live_session_id=? AND customer_key=?",
            (session_id, _live_customer_key(customer_name, customer_handle)),
        ).fetchone()
        if cart:
            cart_url = telegram_public_url("/live/carrinho/{}".format(int(cart["id"])))
            cart_line = f"\nCarrinho: {cart_url}"
    status_label = "ficou com a reserva principal" if status == "aguardando_pagamento" else "entrou na fila de espera"
    return "\n".join([
        f"🔒 {telegram_html(customer_name)} {status_label}.",
        f"Peça: {telegram_html(product['code'])} — {telegram_html(product['title'])}",
        f"Valor: {money(product['sale_price'] or 0)}",
        f"Prazo: {LIVE_RESERVATION_TIMEOUT_MINUTES} min" if status == "aguardando_pagamento" else f"Posição na fila: {int(reservation['queue_position'] or 1)}",
        cart_line.strip(),
    ]).strip()


def _telegram_live_mark_current_sold(con: sqlite3.Connection, session_id: int) -> str:
    current = _telegram_live_current_product(con, session_id)
    product_id = int(current["product_id"]) if current and "product_id" in current.keys() else 0
    if not product_id and current and "id" in current.keys():
        product_id = int(current["id"])
    product = _live_get_product(con, product_id) if product_id else None
    if not product:
        return "Não há peça atual para marcar como vendida."
    sold_time = now_iso()
    con.execute("UPDATE products SET status='vendido', sold_at=?, sync_updated_at=? WHERE id=?", (sold_time, sold_time, int(product_id)))
    con.execute(
        "UPDATE live_queue_items SET status='vendida', hidden_at=COALESCE(hidden_at, ?), updated_at=? WHERE live_session_id=? AND product_id=?",
        (sold_time, sold_time, session_id, int(product_id)),
    )
    con.execute("UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_sold', current_product_event_id=NULL WHERE id=? AND current_product_id=?", (now_iso(), session_id, int(product_id)))
    con.execute("INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)", (int(product_id), "live_venda_telegram", "Marcada como vendida pelo Telegram.", sold_time))
    _live_insert_item(con, session_id, int(product_id), "vendida", "Vendida pelo Telegram.", 0)
    reservation = con.execute(
        """
        SELECT * FROM live_reservation_queue
        WHERE live_session_id=? AND product_id=? AND status='aguardando_pagamento'
        ORDER BY queue_position ASC LIMIT 1
        """,
        (session_id, int(product_id)),
    ).fetchone()
    buyer = ""
    if reservation:
        con.execute("UPDATE live_reservation_queue SET status='vendido', paid_at=COALESCE(paid_at, ?), updated_at=? WHERE id=?", (sold_time, sold_time, int(reservation["id"])))
        con.execute("UPDATE live_customer_cart_items SET status='vendido', updated_at=? WHERE reservation_id=?", (sold_time, int(reservation["id"])))
        buyer = f"\nCliente: {telegram_html(reservation['customer_name'])}"
    return f"✅ {telegram_html(product['code'])} — {telegram_html(product['title'])} marcada como vendida.{buyer}"


def _telegram_live_confirm_payment(con: sqlite3.Connection, session_id: int, term: str) -> str:
    term = (term or "").strip()
    if not term:
        return "Informe a cliente ou ID da reserva. Exemplo: /pago Maria"
    rows: list[sqlite3.Row]
    m_id = re.search(r"#?(\d+)$", term)
    if m_id and term.startswith("#"):
        rows = con.execute(
            """
            SELECT r.*, p.code, p.title, p.sale_price
            FROM live_reservation_queue r
            JOIN products p ON p.id=r.product_id
            WHERE r.live_session_id=? AND r.id=? AND r.status='aguardando_pagamento'
            """,
            (session_id, int(m_id.group(1))),
        ).fetchall()
    else:
        like = "%" + term.replace("%", "") + "%"
        rows = con.execute(
            """
            SELECT r.*, p.code, p.title, p.sale_price
            FROM live_reservation_queue r
            JOIN products p ON p.id=r.product_id
            WHERE r.live_session_id=?
              AND r.status='aguardando_pagamento'
              AND (r.customer_name LIKE ? OR r.customer_handle LIKE ? OR r.customer_phone LIKE ?)
            ORDER BY r.id
            """,
            (session_id, like, like, like),
        ).fetchall()
    if not rows:
        return "Nenhuma reserva aguardando pagamento encontrada para essa cliente."
    total = 0.0
    names = set()
    pieces = []
    sale_ids = []
    for row in rows:
        ok, msg, sale_id = create_sale_for_live_reservation(con, int(row["id"]), source_label="live_payment_telegram")
        if not ok:
            return "⚠️ " + msg
        total += float(row["sale_price"] or 0)
        names.add(row["customer_name"])
        pieces.append(f"{row['code']} — {row['title']}")
        if sale_id:
            sale_ids.append(str(sale_id))
        con.execute("UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_paid', current_product_event_id=NULL WHERE id=? AND current_product_id=?", (now_iso(), session_id, int(row["product_id"])))
    return "\n".join([
        f"✅ Pagamento confirmado para {telegram_html(', '.join(sorted(names)))}.",
        f"Itens: {len(rows)}",
        f"Total: {money(total)}",
        f"Vendas: {', '.join(sale_ids) if sale_ids else '-'}",
        "Peças:",
        *[f"• {telegram_html(piece)}" for piece in pieces[:12]],
    ])


def _telegram_live_cart_text(con: sqlite3.Connection, session_id: int, term: str = "") -> str:
    term = (term or "").strip()
    if term:
        like = "%" + term.replace("%", "") + "%"
        rows = con.execute(
            """
            SELECT * FROM live_customer_carts
            WHERE live_session_id=? AND (customer_name LIKE ? OR customer_instagram LIKE ? OR customer_phone LIKE ?)
            ORDER BY updated_at DESC
            LIMIT 5
            """,
            (session_id, like, like, like),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM live_customer_carts WHERE live_session_id=? ORDER BY total DESC, updated_at DESC LIMIT 8",
            (session_id,),
        ).fetchall()
    if not rows:
        return "Nenhum carrinho encontrado na live."
    if not term and len(rows) > 1:
        lines = [f"🛒 Carrinhos da live #{session_id}:"]
        for cart in rows:
            lines.append(f"#{cart['id']} — {telegram_html(cart['customer_name'])} — {money(cart['total'] or 0)} — /carrinho {telegram_html(cart['customer_name'])}")
        return "\n".join(lines)
    cart = _live_build_cart_summary(con, int(rows[0]["id"]), None)
    if not cart:
        return "Carrinho encontrado, mas não foi possível montar o resumo."
    link = telegram_public_url(cart["link"])
    lines = [
        f"🛒 <b>Carrinho da live</b>",
        f"Cliente: {telegram_html(cart['customer_name'])}",
        f"Total: {cart['total_label']}",
        f"Link: {link}",
        "",
        "Mensagem pronta:",
        telegram_html(cart["message"].replace(cart["link"], link)),
    ]
    return "\n".join(lines)


def _telegram_live_report_text(con: sqlite3.Connection, session_id: int | None = None) -> str:
    live = _telegram_live_session_for_commands(con, create_if_missing=False)
    if not live:
        return "Nenhuma live encontrada."
    session_id = int(session_id or live["id"])
    _live_expire_overdue_reservations(con, session_id)
    shown = con.execute("SELECT COUNT(*) AS total FROM live_queue_items WHERE live_session_id=? AND status IN ('atual','mostrada','reservada','vendida','pulada')", (session_id,)).fetchone()["total"]
    sold = con.execute(
        """
        SELECT COALESCE(SUM(p.sale_price),0) AS total, COUNT(DISTINCT r.product_id) AS qty
        FROM live_reservation_queue r
        JOIN products p ON p.id=r.product_id
        WHERE r.live_session_id=? AND r.status IN ('pago','vendido')
        """,
        (session_id,),
    ).fetchone()
    pending = con.execute(
        """
        SELECT COALESCE(SUM(p.sale_price),0) AS total, COUNT(*) AS qty
        FROM live_reservation_queue r
        JOIN products p ON p.id=r.product_id
        WHERE r.live_session_id=? AND r.status='aguardando_pagamento'
        """,
        (session_id,),
    ).fetchone()
    waitlist = con.execute("SELECT COUNT(*) AS total FROM live_reservation_queue WHERE live_session_id=? AND status='fila_espera'", (session_id,)).fetchone()["total"]
    unsold = con.execute(
        """
        SELECT COUNT(*) AS total
        FROM live_queue_items lq
        JOIN products p ON p.id=lq.product_id
        WHERE lq.live_session_id=? AND lq.status IN ('mostrada','pendente','atual') AND p.status='disponivel'
        """,
        (session_id,),
    ).fetchone()["total"]
    buyers = con.execute(
        """
        SELECT customer_name, SUM(p.sale_price) AS total, COUNT(*) AS qty
        FROM live_reservation_queue r
        JOIN products p ON p.id=r.product_id
        WHERE r.live_session_id=? AND r.status IN ('pago','vendido','aguardando_pagamento')
        GROUP BY customer_name
        ORDER BY total DESC
        LIMIT 5
        """,
        (session_id,),
    ).fetchall()
    lines = [
        f"📊 <b>Resumo da live #{session_id}</b>",
        f"Peças mostradas: {int(shown or 0)}",
        f"Vendido/pago: {money(sold['total'] or 0)} ({int(sold['qty'] or 0)})",
        f"Reservado pendente: {money(pending['total'] or 0)} ({int(pending['qty'] or 0)})",
        f"Fila de espera: {int(waitlist or 0)}",
        f"Disponíveis para repescagem: {int(unsold or 0)}",
        f"Repescagem: {telegram_public_url(f'/live/repescagem/{session_id}')}",
    ]
    if buyers:
        lines += ["", "Top clientes:"]
        for idx, row in enumerate(buyers, 1):
            lines.append(f"{idx}. {telegram_html(row['customer_name'])} — {money(row['total'] or 0)} — {int(row['qty'] or 0)} peça(s)")
    return "\n".join(lines)


def telegram_try_live_central_command(
    con: sqlite3.Connection,
    raw: str,
    low: str,
    chat_id: str = "",
    username: str = "",
) -> str | None:
    if not TELEGRAM_COMMANDS_ENABLED:
        return None
    normalized = _live_text_key(raw)
    parts = raw.strip().split(maxsplit=1)
    cmd = (parts[0].lower() if parts else "").strip()
    arg = parts[1].strip() if len(parts) > 1 else ""
    live = _telegram_live_session_for_commands(con)
    session_id = int(live["id"]) if live else 0

    if cmd in {"/painel", "/central", "/livecentral", "/central_live"} or normalized in {"painel", "central", "livecentral", "central live"}:
        return _telegram_live_panel_text(con)

    if cmd in {"/atual", "/peca", "/peça"} or normalized in {"atual", "peca atual", "peça atual"}:
        return _telegram_live_current_text(con, session_id)

    if cmd in {"/fila", "/filalive", "/fila_live"} or normalized in {"fila", "fila live", "fila da live"}:
        return _telegram_live_queue_text(con)

    if cmd in {"/proxima", "/próxima", "/next"} or normalized in {"proxima", "próxima", "proxima peca", "próxima peça", "mostrar proxima", "mostrar próxima"}:
        return _telegram_live_advance_next(con, session_id)

    if cmd in {"/addfila", "/add", "/filaadd", "/adicionar"}:
        if not arg:
            return "Informe o código/nome. Exemplo: /addfila BLUSA-023"
        return _telegram_live_add_queue(con, session_id, arg)

    if cmd in {"/reservar", "/reserva"} or normalized.startswith("reservar "):
        spec = arg or raw.split(" ", 1)[1].strip() if " " in raw else ""
        return _telegram_live_reserve_current(con, session_id, spec, force_waitlist=False)

    if cmd in {"/espera", "/filaespera", "/waitlist"} or normalized.startswith("espera "):
        spec = arg or raw.split(" ", 1)[1].strip() if " " in raw else ""
        return _telegram_live_reserve_current(con, session_id, spec, force_waitlist=True)

    if cmd in {"/vendida", "/vender", "/sold"} or normalized in {"vendida", "marcar vendida", "marcar como vendida"}:
        return _telegram_live_mark_current_sold(con, session_id)

    if cmd in {"/pago", "/pix", "/pagou", "/confirmar"} or normalized.startswith("pago "):
        spec = arg or raw.split(" ", 1)[1].strip() if " " in raw else ""
        return _telegram_live_confirm_payment(con, session_id, spec)

    if cmd in {"/carrinho", "/cart"} or normalized.startswith("carrinho"):
        return _telegram_live_cart_text(con, session_id, arg)

    if cmd in {"/resumo_live", "/resumolive", "/poslive", "/pós-live", "/relatorio_live", "/relatório_live"} or normalized in {"resumo live", "relatorio live", "relatório live", "pos live", "pós live"}:
        return _telegram_live_report_text(con, session_id)

    return None


def _live_recent_comments_with_intent(con: sqlite3.Connection, session_id: int, current_product_id: int | None) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT * FROM live_comments WHERE live_session_id=? ORDER BY id DESC LIMIT 80",
        (int(session_id),),
    ).fetchall()
    result = []
    for row in rows[::-1]:
        intent = live_detect_comment_intent(row["message"])
        result.append(
            {
                "id": int(row["id"]),
                "author_name": row["author_name"] or "Cliente",
                "message": row["message"],
                "source": row["source"],
                "created_at": row["created_at"],
                "intent": intent["intent"],
                "intent_label": intent["label"],
                "suggested_action": intent["suggested_action"],
                "product_id": current_product_id,
                "needs_answer": intent["suggested_action"] not in {"acompanhar"},
            }
        )
    return result


def _live_dashboard_payload(con: sqlite3.Connection, request: Request, session_id: int) -> dict[str, Any]:
    init_live_central_schema()
    session = _live_session_or_404(con, int(session_id))
    _live_expire_overdue_reservations(con, int(session_id))
    session = con.execute("SELECT * FROM live_sessions WHERE id=?", (int(session_id),)).fetchone()

    current_row = _live_current_queue_item(con, int(session_id))
    current_product = _live_queue_product_payload(current_row, request)
    current_product_id = int(current_product["id"]) if current_product else (int(session["current_product_id"]) if session["current_product_id"] else None)
    if not current_product and current_product_id:
        product = _live_get_product(con, current_product_id)
        current_product = _live_product_payload_for_central(product, request)

    current_product_set_at = ""
    current_product_source = ""
    current_product_event_id = None
    if current_row and current_row["shown_at"]:
        current_product_set_at = current_row["shown_at"]
        current_product_source = "central"
        current_product_event_id = int(current_row["id"])
    else:
        if "current_product_set_at" in session.keys() and session["current_product_set_at"]:
            current_product_set_at = session["current_product_set_at"]
        if "current_product_source" in session.keys() and session["current_product_source"]:
            current_product_source = session["current_product_source"]
        if "current_product_event_id" in session.keys() and session["current_product_event_id"]:
            current_product_event_id = int(session["current_product_event_id"])
        if current_product and not current_product_set_at:
            latest_item = con.execute(
                """
                SELECT id, action, created_at FROM live_session_items
                WHERE live_session_id=? AND product_id=? AND action IN ('reconhecida','fixada','cliente_clicou','repescagem','mostrada')
                ORDER BY id DESC LIMIT 1
                """,
                (int(session_id), int(current_product["id"])),
            ).fetchone()
            if latest_item:
                current_product_set_at = latest_item["created_at"]
                current_product_source = latest_item["action"] or current_product_source
                current_product_event_id = int(latest_item["id"])
    if current_product:
        current_product["shown_at"] = current_product.get("shown_at") or current_product_set_at
        current_product["source"] = current_product_source or current_product.get("source") or ""
        current_product["event_id"] = current_product_event_id
        current_product["event_key_seed"] = f"{int(session_id)}:{current_product.get('id')}:{current_product_event_id or ''}:{current_product_set_at}"

    next_row = con.execute(
        """
        SELECT lq.*, p.code, p.title, p.sale_price, p.size, p.measurements, p.condition, p.status AS product_status,
               p.image_filename, p.characteristics, p.brand, p.color, p.category, p.garment_type
        FROM live_queue_items lq
        JOIN products p ON p.id = lq.product_id
        WHERE lq.live_session_id=? AND lq.status='pendente'
        ORDER BY lq.sort_order ASC, lq.id ASC
        LIMIT 1
        """,
        (int(session_id),),
    ).fetchone()
    next_product = _live_queue_product_payload(next_row, request)

    queue_rows = con.execute(
        """
        SELECT lq.*, p.code, p.title, p.sale_price, p.size, p.status AS product_status, p.image_filename
        FROM live_queue_items lq
        JOIN products p ON p.id=lq.product_id
        WHERE lq.live_session_id=?
        ORDER BY
          CASE lq.status WHEN 'atual' THEN 0 WHEN 'pendente' THEN 1 WHEN 'reservada' THEN 2 WHEN 'vendida' THEN 3 ELSE 4 END,
          lq.sort_order ASC,
          lq.id ASC
        LIMIT 100
        """,
        (int(session_id),),
    ).fetchall()
    queue = []
    for row in queue_rows:
        queue.append(
            {
                "id": int(row["id"]),
                "product_id": int(row["product_id"]),
                "code": row["code"],
                "title": row["title"],
                "price_label": money(row["sale_price"] or 0),
                "status": row["status"],
                "product_status": row["product_status"],
                "sort_order": int(row["sort_order"] or 0),
                "shown_at": row["shown_at"] or "",
                "image_url": f"/static/uploads/{row['image_filename']}" if row["image_filename"] else "",
            }
        )

    reservation_rows = con.execute(
        """
        SELECT lrq.*, p.code, p.title, p.sale_price, p.image_filename
        FROM live_reservation_queue lrq
        JOIN products p ON p.id=lrq.product_id
        WHERE lrq.live_session_id=? AND lrq.status IN ('aguardando_pagamento','fila_espera','pago','vendido')
        ORDER BY
          CASE lrq.status WHEN 'aguardando_pagamento' THEN 0 WHEN 'fila_espera' THEN 1 WHEN 'pago' THEN 2 ELSE 3 END,
          lrq.product_id, lrq.queue_position, lrq.id
        LIMIT 120
        """,
        (int(session_id),),
    ).fetchall()
    reservations = []
    for row in reservation_rows:
        reservations.append(
            {
                **_live_reservation_payload(row),
                "code": row["code"],
                "title": row["title"],
                "price_label": money(row["sale_price"] or 0),
                "image_url": f"/static/uploads/{row['image_filename']}" if row["image_filename"] else "",
            }
        )

    carts_raw = con.execute(
        """
        SELECT * FROM live_customer_carts
        WHERE live_session_id=? AND status IN ('aberto','aguardando_pagamento','pendente')
        ORDER BY total DESC, updated_at DESC
        LIMIT 50
        """,
        (int(session_id),),
    ).fetchall()
    carts = [_live_build_cart_summary(con, int(row["id"]), request) for row in carts_raw]
    carts = [c for c in carts if c]

    comments = _live_recent_comments_with_intent(con, int(session_id), current_product_id)
    waiting_answers = [c for c in comments if c["needs_answer"]][-30:]

    sold_total = con.execute(
        """
        SELECT COALESCE(SUM(p.sale_price),0) AS total, COUNT(DISTINCT p.id) AS qty
        FROM products p
        JOIN live_session_items li ON li.product_id=p.id
        WHERE li.live_session_id=? AND (li.action='vendida' OR p.status='vendido')
        """,
        (int(session_id),),
    ).fetchone()
    paid_res = con.execute(
        """
        SELECT COALESCE(SUM(p.sale_price),0) AS total, COUNT(DISTINCT lrq.product_id) AS qty
        FROM live_reservation_queue lrq
        JOIN products p ON p.id=lrq.product_id
        WHERE lrq.live_session_id=? AND lrq.status IN ('pago','vendido')
        """,
        (int(session_id),),
    ).fetchone()
    pending_res = con.execute(
        """
        SELECT COALESCE(SUM(p.sale_price),0) AS total, COUNT(DISTINCT lrq.product_id) AS qty
        FROM live_reservation_queue lrq
        JOIN products p ON p.id=lrq.product_id
        WHERE lrq.live_session_id=? AND lrq.status='aguardando_pagamento'
        """,
        (int(session_id),),
    ).fetchone()
    shown_count = con.execute(
        "SELECT COUNT(*) AS qty FROM live_queue_items WHERE live_session_id=? AND status IN ('atual','mostrada','reservada','vendida','pulada')",
        (int(session_id),),
    ).fetchone()["qty"]

    # Evita somar duas vezes quando a venda também virou reserva paga.
    total_sold_value = max(float(sold_total["total"] or 0), float(paid_res["total"] or 0))
    total_sold_qty = max(int(sold_total["qty"] or 0), int(paid_res["qty"] or 0))

    qr_url = _live_generate_current_qr(con, request, int(session_id))
    elapsed = 0
    if current_product and current_product.get("shown_at"):
        dt = parse_dt(current_product.get("shown_at"))
        if dt:
            elapsed = max(0, int((datetime.now() - dt).total_seconds()))
    if current_product and elapsed >= LIVE_COMPANION_STALE_SECONDS:
        # Segurança: se o app Admin parou de reconhecer ou a peça saiu da tela,
        # o card do cliente some em vez de ficar preso em uma peça antiga.
        current_product = None
        current_product_id = None

    app_cta_compact = brechorisee_customer_app_cta(request, compact=True)
    quick_replies = [
        f"Essa peça ainda está disponível 💖\n{app_cta_compact}",
        f"Essa peça já foi reservada, mas posso colocar você na fila de espera.\n{app_cta_compact}",
        f"Vou colocar você na fila de espera.\n{app_cta_compact}",
        f"Segue o link da peça: {{link}}\n{app_cta_compact}",
        f"Segue seu carrinho da live: {{cart_link}}\n{app_cta_compact}",
        f"Pode retirar na loja. Te passo o endereço certinho no fechamento.\n{app_cta_compact}",
        f"O pagamento é via Pix. Assim que confirmar, separo sua peça.\n{app_cta_compact}",
        f"Me confirma seu nome e telefone, por favor?\n{app_cta_compact}",
    ]

    current_message = ""
    if current_product:
        link = current_product.get("public_product_url") or current_product.get("short_url") or ""
        current_message = (
            f"{current_product['title']} 💖\n"
            f"Código: {current_product['code']}\n"
            f"Valor: {current_product['price_label']}\n"
            f"Tamanho: {current_product.get('size') or 'não informado'}\n"
            f"Medidas: {current_product.get('measurements') or 'me chama que confirmo'}\n"
            f"Link: {link}\n\n"
            f"{brechorisee_customer_app_cta(request)}"
        )

    return {
        "ok": True,
        "session": {
            "id": int(session["id"]),
            "title": session["title"],
            "status": session["status"],
            "started_at": session["started_at"] if "started_at" in session.keys() else "",
            "viewer_count": live_viewer_count(con, int(session_id)),
            "source_platform": session["source_platform"] if "source_platform" in session.keys() and session["source_platform"] else "brechorisee",
            "instagram_live_url": session["instagram_live_url"] if "instagram_live_url" in session.keys() and session["instagram_live_url"] else "",
            "brechorisee_watch_enabled": bool(session["brechorisee_watch_enabled"]) if "brechorisee_watch_enabled" in session.keys() else True,
        },
        "current_product": current_product,
        "next_product": next_product,
        "current_elapsed_seconds": elapsed,
        "queue": queue,
        "comments": comments,
        "waiting_answers": waiting_answers,
        "reservations": reservations,
        "carts": carts,
        "quick_replies": quick_replies,
        "current_product_message": current_message,
        "qr_url": qr_url,
        "stats": {
            "sold_total": total_sold_value,
            "sold_total_label": money(total_sold_value),
            "sold_count": total_sold_qty,
            "pending_reserved_total": float(pending_res["total"] or 0),
            "pending_reserved_total_label": money(pending_res["total"] or 0),
            "pending_reserved_count": int(pending_res["qty"] or 0),
            "shown_count": int(shown_count or 0),
            "queue_pending_count": len([q for q in queue if q["status"] == "pendente"]),
            "waiting_answer_count": len(waiting_answers),
        },
    }


@app.get("/live/central", response_class=HTMLResponse)
def live_central_page(request: Request) -> Response:
    init_live_central_schema()
    with get_db() as con:
        session = _live_active_session(con)
    return RedirectResponse(url=f"/live/central/{int(session['id'])}", status_code=303)


@app.get("/live/central/{session_id}", response_class=HTMLResponse)
def live_central_session_page(request: Request, session_id: int) -> Response:
    init_live_central_schema()
    with get_db() as con:
        session = _live_session_or_404(con, int(session_id))
    return templates.TemplateResponse(
        "live_central.html",
        {"request": request, "active": "live", "session": session, "reservation_timeout": LIVE_RESERVATION_TIMEOUT_MINUTES},
    )


@app.get("/api/live/central/{session_id}")
def api_live_central_dashboard(request: Request, session_id: int) -> JSONResponse:
    with get_db() as con:
        data = _live_dashboard_payload(con, request, int(session_id))
    return JSONResponse(data)


@app.post("/api/live/central/{session_id}/queue-add")
def api_live_central_queue_add(
    session_id: int,
    product_id: int = Form(0),
    product_code: str = Form(""),
    notes: str = Form(""),
) -> JSONResponse:
    init_live_central_schema()
    with get_db() as con:
        _live_session_or_404(con, int(session_id))
        product = None
        if product_id:
            product = con.execute("SELECT * FROM products WHERE id=?", (int(product_id),)).fetchone()
        code = (product_code or "").strip()
        if not product and code:
            product = con.execute("SELECT * FROM products WHERE lower(code)=lower(?)", (code,)).fetchone()
        if not product and code:
            like = f"%{code}%"
            product = con.execute(
                "SELECT * FROM products WHERE (title LIKE ? OR code LIKE ?) AND deleted_at IS NULL ORDER BY CASE status WHEN 'disponivel' THEN 0 WHEN 'reservado' THEN 1 ELSE 2 END, id DESC LIMIT 1",
                (like, like),
            ).fetchone()
        if not product:
            return JSONResponse({"ok": False, "message": "Peça não encontrada pelo código/nome informado."}, status_code=404)
        max_order = con.execute("SELECT COALESCE(MAX(sort_order),0) AS max_order FROM live_queue_items WHERE live_session_id=?", (int(session_id),)).fetchone()["max_order"]
        try:
            con.execute(
                """
                INSERT INTO live_queue_items(live_session_id, product_id, sort_order, status, notes, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (int(session_id), int(product["id"]), int(max_order or 0) + 10, "pendente", notes[:500], now_iso(), now_iso()),
            )
        except sqlite3.IntegrityError:
            con.execute(
                "UPDATE live_queue_items SET status=CASE WHEN status IN ('vendida','reservada') THEN status ELSE 'pendente' END, notes=?, updated_at=? WHERE live_session_id=? AND product_id=?",
                (notes[:500], now_iso(), int(session_id), int(product["id"])),
            )
        if TELEGRAM_NOTIFY_LIVE:
            telegram_send_admin_message(
                con,
                f"📋 Peça adicionada à fila da live #{int(session_id)}:\n{telegram_html(product['code'])} — {telegram_html(product['title'])} — {money(product['sale_price'] or 0)}",
                related_type="live_queue",
                related_id=int(product["id"]),
            )
    return JSONResponse({"ok": True, "message": f"{product['code']} adicionada à fila da live."})


@app.post("/api/live/central/{session_id}/next")
def api_live_central_next(session_id: int) -> JSONResponse:
    init_live_central_schema()
    with get_db() as con:
        session_before = _live_session_or_404(con, int(session_id))
        was_live = str(session_before["status"] or "") == "ao_vivo"
        now = now_iso()
        current = con.execute("SELECT * FROM live_queue_items WHERE live_session_id=? AND status='atual' ORDER BY id DESC LIMIT 1", (int(session_id),)).fetchone()
        if current:
            seconds = 0
            if current["shown_at"]:
                dt = parse_dt(current["shown_at"])
                if dt:
                    seconds = max(0, int((datetime.now() - dt).total_seconds()))
            con.execute(
                "UPDATE live_queue_items SET status='mostrada', hidden_at=?, seconds_on_screen=?, updated_at=? WHERE id=?",
                (now, float(seconds), now, int(current["id"])),
            )
        next_item = con.execute(
            """
            SELECT * FROM live_queue_items
            WHERE live_session_id=? AND status='pendente'
            ORDER BY sort_order ASC, id ASC
            LIMIT 1
            """,
            (int(session_id),),
        ).fetchone()
        if not next_item:
            return JSONResponse({"ok": False, "message": "Não há próxima peça na fila. Adicione peças primeiro."}, status_code=404)
        product = _live_get_product(con, int(next_item["product_id"]))
        con.execute(
            "UPDATE live_queue_items SET status='atual', shown_at=?, updated_at=? WHERE id=?",
            (now, now, int(next_item["id"])),
        )
        con.execute(
            "UPDATE live_sessions SET current_product_id=?, current_product_set_at=?, current_product_source='central', current_product_event_id=?, status=CASE WHEN status='aberta' THEN 'ao_vivo' ELSE status END, started_at=COALESCE(started_at, ?) WHERE id=?",
            (int(product["id"]), now, int(next_item["id"]), now, int(session_id)),
        )
        _live_insert_item(con, int(session_id), int(product["id"]), "mostrada", "Peça mostrada pela Central da Live.", 0)
        session_after = con.execute("SELECT * FROM live_sessions WHERE id=?", (int(session_id),)).fetchone()
        notified_clients = 0
        if not was_live and session_after and str(session_after["status"] or "") == "ao_vivo":
            notified_clients = queue_live_started_notifications(con, session_after)
            con.execute(
                "INSERT INTO live_comments(live_session_id, author_name, message, source, created_at) VALUES(?,?,?,?,?)",
                (int(session_id), "BRECHORISEE", f"Live iniciada pela Central. {notified_clients} cliente(s) avisada(s).", "sistema", now_iso()),
            )
        if TELEGRAM_NOTIFY_LIVE:
            telegram_send_admin_message(
                con,
                f"▶️ Peça atual na live #{int(session_id)}:\n{telegram_html(product['code'])} — {telegram_html(product['title'])} — {money(product['sale_price'] or 0)}\n{telegram_public_url('/live/peca-atual')}",
                related_type="live_current_product",
                related_id=int(product["id"]),
            )
    return JSONResponse({"ok": True, "message": f"Peça atual: {product['code']} — {product['title']}"})


@app.post("/api/live/central/{session_id}/reserve")
def api_live_central_reserve(
    session_id: int,
    product_id: int = Form(0),
    customer_name: str = Form(...),
    customer_handle: str = Form(""),
    customer_phone: str = Form(""),
    source_comment_id: int = Form(0),
    force_waitlist: int = Form(0),
) -> JSONResponse:
    init_live_central_schema()
    customer_name = (customer_name or "").strip()[:120]
    customer_handle = (customer_handle or "").strip()[:120]
    customer_phone = normalize_phone(customer_phone)[:40]
    if not customer_name:
        return JSONResponse({"ok": False, "message": "Informe o nome da cliente."}, status_code=400)

    with get_db() as con:
        _live_session_or_404(con, int(session_id))
        _live_expire_overdue_reservations(con, int(session_id))
        if not product_id:
            current = _live_current_queue_item(con, int(session_id))
            product_id = int(current["product_id"]) if current else 0
        product = _live_get_product(con, int(product_id))
        if not product:
            return JSONResponse({"ok": False, "message": "Peça não encontrada."}, status_code=404)
        if product["status"] == "vendido":
            return JSONResponse({"ok": False, "message": "Essa peça já está vendida."}, status_code=409)
        try:
            validate_money_amount(product["sale_price"], f"Preço da peça {product['code']}", minimum=0, allow_zero=False)
        except HTTPException as exc:
            return JSONResponse({"ok": False, "message": exc.detail}, status_code=400)

        customer_account_id = find_customer_account_id_for_identity(con, customer_name, customer_phone, "")
        dup = None
        if customer_account_id:
            dup = con.execute(
                """
                SELECT * FROM live_reservation_queue
                WHERE live_session_id=? AND product_id=? AND customer_account_id=? AND status IN ('aguardando_pagamento','fila_espera','pago','vendido')
                LIMIT 1
                """,
                (int(session_id), int(product_id), int(customer_account_id)),
            ).fetchone()
        if not dup:
            dup = con.execute(
                """
                SELECT * FROM live_reservation_queue
                WHERE live_session_id=? AND product_id=?
                  AND ((?<>'' AND customer_phone=?) OR lower(customer_name)=lower(?))
                  AND status IN ('aguardando_pagamento','fila_espera','pago','vendido')
                LIMIT 1
                """,
                (int(session_id), int(product_id), customer_phone, customer_phone, customer_name),
            ).fetchone()
        if dup:
            return JSONResponse({"ok": True, "message": "Cliente já está nessa reserva/fila.", "reservation": _live_reservation_payload(dup), "duplicate": True})

        principal = con.execute(
            """
            SELECT * FROM live_reservation_queue
            WHERE live_session_id=? AND product_id=? AND status IN ('aguardando_pagamento','pago','vendido')
            ORDER BY queue_position ASC LIMIT 1
            """,
            (int(session_id), int(product_id)),
        ).fetchone()
        max_pos = con.execute(
            "SELECT COALESCE(MAX(queue_position),0) AS max_pos FROM live_reservation_queue WHERE live_session_id=? AND product_id=?",
            (int(session_id), int(product_id)),
        ).fetchone()["max_pos"]
        status = "fila_espera" if principal or force_waitlist else "aguardando_pagamento"
        expires_at = (datetime.now() + timedelta(minutes=LIVE_RESERVATION_TIMEOUT_MINUTES)).strftime("%Y-%m-%d %H:%M:%S") if status == "aguardando_pagamento" else None
        cur = con.execute(
            """
            INSERT INTO live_reservation_queue(
                live_session_id, product_id, customer_name, customer_handle, customer_phone, source, source_comment_id,
                queue_position, status, reserved_at, expires_at, notes, created_at, updated_at, customer_account_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                int(session_id), int(product_id), customer_name, customer_handle, customer_phone, "central_live",
                int(source_comment_id) if source_comment_id else None, int(max_pos or 0) + 1, status, now_iso(),
                expires_at, "", now_iso(), now_iso(), int(customer_account_id) if customer_account_id else None,
            ),
        )
        reservation = con.execute("SELECT * FROM live_reservation_queue WHERE id=?", (cur.lastrowid,)).fetchone()
        if status == "aguardando_pagamento":
            con.execute("UPDATE products SET status='reservado', sync_updated_at=? WHERE id=?", (now_iso(), int(product_id)))
            _live_add_cart_item_for_reservation(con, reservation)
            con.execute(
                "UPDATE live_queue_items SET status=CASE WHEN status='atual' THEN 'atual' ELSE 'reservada' END, updated_at=? WHERE live_session_id=? AND product_id=?",
                (now_iso(), int(session_id), int(product_id)),
            )
        _live_insert_item(con, int(session_id), int(product_id), "reservada", f"Reserva: {customer_name} ({status}).", 0)
        active_count = con.execute(
            "SELECT COUNT(*) AS qty FROM live_reservation_queue WHERE live_session_id=? AND ((customer_account_id IS NOT NULL AND customer_account_id=?) OR lower(customer_name)=lower(?)) AND status='aguardando_pagamento'",
            (int(session_id), int(customer_account_id) if customer_account_id else -1, customer_name),
        ).fetchone()["qty"]
        msg = f"{customer_name} ficou com a reserva principal por {LIVE_RESERVATION_TIMEOUT_MINUTES} min." if status == "aguardando_pagamento" else f"{customer_name} entrou na fila de espera."
        should_notify = (status == "aguardando_pagamento" and TELEGRAM_NOTIFY_RESERVATIONS) or (status == "fila_espera" and TELEGRAM_NOTIFY_WAITLIST)
        if should_notify:
            emoji = "🔒" if status == "aguardando_pagamento" else "⏳"
            telegram_send_admin_message(
                con,
                f"{emoji} {telegram_html(customer_name)} — {telegram_html(status)}\nPeça: {telegram_html(product['code'])} — {telegram_html(product['title'])}\nValor: {money(product['sale_price'] or 0)}\nLive #{int(session_id)}",
                related_type="live_reservation",
                related_id=int(reservation["id"]),
            )
    return JSONResponse({"ok": True, "message": msg, "reservation": _live_reservation_payload(reservation), "customer_active_reservations": int(active_count or 0)})


@app.post("/api/live/central/{session_id}/mark-sold")
def api_live_central_mark_sold(session_id: int, product_id: int = Form(0)) -> JSONResponse:
    init_live_central_schema()
    with get_db() as con:
        _live_session_or_404(con, int(session_id))
        if not product_id:
            current = _live_current_queue_item(con, int(session_id))
            product_id = int(current["product_id"]) if current else 0
        product = _live_get_product(con, int(product_id))
        if not product:
            return JSONResponse({"ok": False, "message": "Peça não encontrada."}, status_code=404)
        reservation = con.execute(
            """
            SELECT * FROM live_reservation_queue
            WHERE live_session_id=? AND product_id=? AND status='aguardando_pagamento'
            ORDER BY queue_position ASC LIMIT 1
            """,
            (int(session_id), int(product_id)),
        ).fetchone()
        sale_id = None
        if reservation:
            ok, msg, sale_id = create_sale_for_live_reservation(con, int(reservation["id"]), source_label="live_sale_central")
            if not ok:
                return JSONResponse({"ok": False, "message": msg}, status_code=400)
            sold_time = now_iso()
        else:
            validate_money_amount(product["sale_price"], f"Preço da peça {product['code']}", minimum=0, allow_zero=False)
            sold_time = now_iso()
            sale_id, sale_code = create_sale_record(
                con,
                customer="Cliente live",
                payment_method="Live/manual",
                total=float(product["sale_price"] or 0),
                paid=float(product["sale_price"] or 0),
                source="live_manual_sold",
                source_ref_id=int(product_id),
            )
            con.execute("INSERT INTO sale_items(sale_id, product_id, price) VALUES(?,?,?)", (sale_id, int(product_id), float(product["sale_price"] or 0)))
            con.execute("UPDATE products SET status='vendido', sold_at=?, sync_updated_at=? WHERE id=?", (sold_time, sold_time, int(product_id)))
            con.execute("INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)", (int(product_id), "live_venda", f"Marcada como vendida pela Central da Live. Venda {sale_code}.", sold_time))
            enqueue_sale_cloud_sync(con, int(sale_id))
        con.execute(
            "UPDATE live_queue_items SET status='vendida', hidden_at=COALESCE(hidden_at, ?), updated_at=? WHERE live_session_id=? AND product_id=?",
            (sold_time, sold_time, int(session_id), int(product_id)),
        )
        con.execute(
            "UPDATE live_sessions SET current_product_id=NULL, current_product_set_at=?, current_product_source='clear_sold', current_product_event_id=NULL WHERE id=? AND current_product_id=?",
            (sold_time, int(session_id), int(product_id)),
        )
        _live_insert_item(con, int(session_id), int(product_id), "vendida", "Vendida pela Central da Live.", 0)
        enqueue_product_cloud_sync(con, int(product_id), reason="live_vendida")
        if TELEGRAM_NOTIFY_PAYMENTS or TELEGRAM_NOTIFY_LIVE:
            buyer = f"\nCliente: {telegram_html(reservation['customer_name'])}" if reservation else ""
            telegram_send_admin_message(
                con,
                f"✅ Vendida na live #{int(session_id)}:\n{telegram_html(product['code'])} — {telegram_html(product['title'])} — {money(product['sale_price'] or 0)}{buyer}\nVenda: #{sale_id}",
                related_type="live_sale",
                related_id=int(product["id"]),
            )
    return JSONResponse({"ok": True, "message": f"{product['code']} marcada como vendida.", "sale_id": sale_id})


@app.post("/api/live/central/reservation/{reservation_id}/paid")
def api_live_central_reservation_paid(reservation_id: int) -> JSONResponse:
    init_live_central_schema()
    with get_db() as con:
        reservation = con.execute("SELECT * FROM live_reservation_queue WHERE id=?", (int(reservation_id),)).fetchone()
        if not reservation:
            return JSONResponse({"ok": False, "message": "Reserva não encontrada."}, status_code=404)
        product = _live_get_product(con, int(reservation["product_id"]))
        ok, msg, sale_id = create_sale_for_live_reservation(con, int(reservation_id), source_label="live_payment_admin")
        if not ok:
            log_security_event(con, "live_payment_confirmation_failed", severity="warning", actor_type="admin", path=f"/api/live/central/reservation/{reservation_id}/paid", details=msg)
            return JSONResponse({"ok": False, "message": msg}, status_code=400)
        if TELEGRAM_NOTIFY_PAYMENTS:
            telegram_send_admin_message(
                con,
                f"💸 Pix/pagamento confirmado:\nCliente: {telegram_html(reservation['customer_name'])}\nPeça: {telegram_html(product['code'] if product else 'peça')} — {telegram_html(product['title'] if product else '')}\nValor: {money(product['sale_price'] if product else 0)}\nVenda: #{sale_id}",
                related_type="live_payment",
                related_id=int(reservation_id),
            )
    return JSONResponse({"ok": True, "message": msg, "sale_id": sale_id})


@app.post("/api/live/central/reservation/{reservation_id}/cancel")
def api_live_central_reservation_cancel(reservation_id: int) -> JSONResponse:
    init_live_central_schema()
    with get_db() as con:
        reservation = con.execute("SELECT * FROM live_reservation_queue WHERE id=?", (int(reservation_id),)).fetchone()
        if not reservation:
            return JSONResponse({"ok": False, "message": "Reserva não encontrada."}, status_code=404)
        con.execute("UPDATE live_reservation_queue SET status='desistiu', cancelled_at=?, updated_at=? WHERE id=?", (now_iso(), now_iso(), int(reservation_id)))
        con.execute("UPDATE live_customer_cart_items SET status='desistiu', updated_at=? WHERE reservation_id=?", (now_iso(), int(reservation_id)))
        promoted = _live_promote_next_waiting(con, int(reservation["live_session_id"]), int(reservation["product_id"]))
        if not promoted:
            product = _live_get_product(con, int(reservation["product_id"]))
            if product and product["status"] == "reservado":
                con.execute("UPDATE products SET status='disponivel', sync_updated_at=? WHERE id=?", (now_iso(), int(reservation["product_id"])))
            msg = "Reserva cancelada. Não havia fila de espera."
        else:
            msg = f"Reserva cancelada. {promoted['customer_name']} foi promovida para reserva principal."
        if TELEGRAM_NOTIFY_RESERVATIONS or TELEGRAM_NOTIFY_WAITLIST:
            extra = f"\nPromovida: {telegram_html(promoted['customer_name'])}" if promoted else ""
            telegram_send_admin_message(
                con,
                f"↩️ Reserva cancelada na live #{int(reservation['live_session_id'])}: {telegram_html(reservation['customer_name'])}{extra}",
                related_type="live_reservation_cancel",
                related_id=int(reservation_id),
            )
    return JSONResponse({"ok": True, "message": msg, "promoted": _live_reservation_payload(promoted) if promoted else None})


@app.get("/api/live/central/cart/{cart_id}")
def api_live_central_cart(request: Request, cart_id: str) -> JSONResponse:
    init_live_central_schema()
    with get_db() as con:
        cart = _live_build_cart_summary(con, cart_id, request)
    if not cart:
        return JSONResponse({"ok": False, "message": "Carrinho não encontrado."}, status_code=404)
    # Para links legados por ID, exige admin ou a própria cliente quando o ID numérico foi usado.
    if str(cart_id).isdigit() and not admin_from_request(request):
        account = customer_from_request(request)
        if not account or (cart.get("customer_account_id") and int(cart.get("customer_account_id")) != int(account["id"])):
            return JSONResponse({"ok": False, "message": "Use o link seguro do carrinho."}, status_code=403)
    return JSONResponse({"ok": True, "cart": cart})


@app.get("/live/carrinho/{cart_id}", response_class=HTMLResponse)
def live_cart_public_page(request: Request, cart_id: str) -> Response:
    init_live_central_schema()
    with get_db() as con:
        cart = _live_build_cart_summary(con, cart_id, request)
        if cart and str(cart_id).isdigit() and not admin_from_request(request):
            account = customer_from_request(request)
            same_account = account and cart.get("customer_account_id") and int(cart.get("customer_account_id")) == int(account["id"])
            if not same_account:
                log_security_event(con, "legacy_live_cart_id_public_blocked", severity="warning", path="/live/carrinho", details=f"cart_id={cart_id}", request=request)
                cart = None
    if not cart:
        raise HTTPException(status_code=404, detail="Carrinho não encontrado.")
    page_html = """
    <!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Carrinho da live</title><style>body{font-family:system-ui;background:#fff8f4;color:#3a2420;margin:0;padding:20px}.card{max-width:720px;margin:auto;background:white;border-radius:28px;padding:22px;box-shadow:0 20px 70px #0001}.item{display:flex;justify-content:space-between;border-bottom:1px solid #eee;padding:12px 0}.total{font-size:1.35rem;font-weight:800}.btn{display:block;text-align:center;margin-top:16px;border-radius:18px;padding:14px 18px;background:#a84d3a;color:white;text-decoration:none;font-weight:800}</style></head><body>
    <main class="card"><h1>Carrinho da live 💖</h1><p>Cliente: <strong>{{ customer }}</strong></p>{{ items }}<p class="total">Total: {{ total }}</p><p>Pagamento via Pix ou retirada/entrega combinada com a loja.</p><a class="btn" href="/app/cliente">Baixar/abrir app BRECHORISEE</a><a class="btn" href="/live/peca-atual" style="background:#f4ebe6;color:#704033">Voltar para peça atual</a><a class="btn" href="/loja">Ver loja</a></main></body></html>
    """
    items_html = "".join(f"<div class='item'><span>{html.escape(i['title'])}</span><strong>{i['price_label']}</strong></div>" for i in cart["items"]) or "<p>Carrinho vazio.</p>"
    return HTMLResponse(page_html.replace("{{ customer }}", html.escape(cart["customer_name"])).replace("{{ items }}", items_html).replace("{{ total }}", cart["total_label"]))


@app.get("/live/peca-atual", response_class=HTMLResponse)
def live_public_current_page(request: Request) -> Response:
    init_live_central_schema()
    with get_db() as con:
        live = con.execute("SELECT * FROM live_sessions WHERE status IN ('ao_vivo','aberta') ORDER BY id DESC LIMIT 1").fetchone()
        session_id = int(live["id"]) if live else int(_live_active_session(con)["id"])
    return templates.TemplateResponse("live_public_current.html", {"request": request, "session_id": session_id})


@app.get("/api/live/peca-atual")
def api_live_public_current_piece(request: Request) -> JSONResponse:
    init_live_central_schema()
    with get_db() as con:
        live = con.execute("SELECT * FROM live_sessions WHERE status IN ('ao_vivo','aberta') ORDER BY id DESC LIMIT 1").fetchone()
        if not live:
            return JSONResponse({"ok": False, "message": "Nenhuma live ativa."}, status_code=404)
        data = _live_dashboard_payload(con, request, int(live["id"]))
        public = {
            "ok": True,
            "session": data["session"],
            "current_product": data["current_product"],
            "next_product": data["next_product"],
            "stats": {"shown_count": data["stats"]["shown_count"]},
        }
    return JSONResponse(public)


@app.post("/api/live/peca-atual/reservar")
def api_live_public_reserve_current(
    customer_name: str = Form(...),
    customer_phone: str = Form(""),
    customer_instagram: str = Form(""),
    force_waitlist: int = Form(0),
) -> JSONResponse:
    init_live_central_schema()
    with get_db() as con:
        live = con.execute("SELECT * FROM live_sessions WHERE status IN ('ao_vivo','aberta') ORDER BY id DESC LIMIT 1").fetchone()
        if not live:
            return JSONResponse({"ok": False, "message": "Nenhuma live ativa."}, status_code=404)
        current = _live_current_queue_item(con, int(live["id"]))
        product_id = int(current["product_id"]) if current else int(live["current_product_id"] or 0)
    # Reusa a mesma regra da central para preservar fila por ordem.
    return api_live_central_reserve(
        int(live["id"]),
        product_id=product_id,
        customer_name=customer_name,
        customer_handle=customer_instagram,
        customer_phone=customer_phone,
        source_comment_id=0,
        force_waitlist=int(force_waitlist or 0),
    )


def _abs_url_for_client(request: Request, path_or_url: Any = "") -> str:
    value = str(path_or_url or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://") or value.startswith("brechorisee://"):
        return value
    base = get_public_server_url(request).rstrip("/")
    return base + "/" + value.lstrip("/")


def _live_companion_payload(request: Request, account: sqlite3.Row | dict[str, Any] | None = None) -> dict[str, Any]:
    """Estado público da live para app cliente, site, QR Code e card flutuante.

    O app cliente não lê a tela da cliente. Ele apenas consulta este endpoint e exibe
    a peça que a Central da Live/app admin colocou no servidor.
    """
    init_live_central_schema()
    with get_db() as con:
        live = con.execute(
            """
            SELECT * FROM live_sessions
            WHERE status='ao_vivo'
            ORDER BY COALESCE(started_at, instagram_control_started_at, created_at) DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        if not live:
            last = con.execute("SELECT * FROM live_sessions ORDER BY id DESC LIMIT 1").fetchone()
            links = brechorisee_customer_app_links(request)
            return {
                "ok": False,
                "message": "Nenhuma live ativa no momento.",
                "live": dict(last) if last else None,
                "session": dict(last) if last else None,
                "current_product": None,
                "next_product": None,
                "links": links,
                "app": {
                    "download_url": links["download"],
                    "android_url": links["android"],
                    "ios_url": links["ios"],
                    "deep_live": links["deep_live"],
                },
                "display": {
                    "poll_ms": LIVE_COMPANION_POLL_MS,
                    "full_card_seconds": LIVE_COMPANION_FULL_CARD_SECONDS,
                    "stale_seconds": LIVE_COMPANION_STALE_SECONDS,
                    "auto_hide_when_no_product": True,
                },
                "cta_text": brechorisee_customer_app_cta(request),
                "server_time": now_iso(),
            }

        data = _live_dashboard_payload(con, request, int(live["id"]))
        current = data.get("current_product") or None
        next_product = data.get("next_product") or None
        links = brechorisee_customer_app_links(request)
        base = links["base"]
        settings = get_store_settings()
        phone = str(settings.get("whatsapp") or "").replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

        def enrich_product(p: dict[str, Any] | None) -> dict[str, Any] | None:
            if not p:
                return None
            p = dict(p)
            if p.get("image_url"):
                p["image_url"] = _abs_url_for_client(request, p["image_url"])
            code = p.get("code") or p.get("id") or ""
            p["public_url"] = f"{base}/vitrine/peca/{code}?origem=live"
            p["customer_url"] = f"{base}/cliente/peca/{code}"
            p["live_current_url"] = f"{base}/live/peca-atual"
            p["deep_link"] = f"brechorisee://peca?id={p.get('id') or ''}"
            whatsapp_text = (
                f"Oi! Estou na live da BRECHORISEE e quero essa peça 💖\n\n"
                f"{p.get('title') or 'Peça'}\n"
                f"Código: {p.get('code') or '-'}\n"
                f"Valor: {p.get('price_label') or money(p.get('price') or 0)}\n\n"
                f"Link: {p['live_current_url']}\n\n"
                f"{brechorisee_customer_app_cta(request, compact=True)}"
            )
            if phone:
                wa_phone = phone if phone.startswith("55") else "55" + phone
                p["whatsapp_url"] = f"https://wa.me/{wa_phone}?text={quote_plus(whatsapp_text)}"
            else:
                p["whatsapp_url"] = "https://wa.me/?text=" + quote_plus(whatsapp_text)
            return p

        current = enrich_product(current)
        next_product = enrich_product(next_product)
        recent_products = []
        try:
            current_id = int(current.get("id")) if current else None
            for row in live_reference_products(con, int(live["id"]), current_product_id=current_id, limit=8):
                enriched = enrich_product(live_product_payload(row))
                if enriched:
                    recent_products.append(enriched)
        except Exception:
            recent_products = []
        instagram_url = data["session"].get("instagram_live_url") or str(settings.get("instagram") or "")
        if instagram_url and not instagram_url.startswith("http"):
            instagram_url = instagram_profile_url({"instagram": instagram_url})

        event_key = "sem-peca"
        if current:
            event_key = str(current.get("event_key_seed") or "")
            if not event_key:
                event_key = f"{int(data['session']['id'])}:{current.get('id')}:{current.get('queue_item_id') or current.get('event_id') or ''}:{current.get('shown_at') or ''}:{current.get('status') or ''}"

        customer = None
        if account:
            acc = row_to_dict(account)
            customer = {
                "id": int(acc.get("id") or 0),
                "name": acc.get("name") or "",
                "phone": acc.get("phone") or "",
                "instagram": acc.get("instagram") or "",
            }

        return {
            "ok": True,
            "message": "Live ativa.",
            "session": data["session"],
            "live": data["session"],
            "current_product": current,
            "next_product": next_product,
            "recent_products": recent_products,
            "stats": data.get("stats") or {},
            "current_elapsed_seconds": data.get("current_elapsed_seconds") or 0,
            "event_key": event_key,
            "links": {
                **links,
                "instagram_live": instagram_url,
                "current_product": current.get("public_url") if current else links["live_current"],
                "reserve": f"{base}/live/peca-atual",
                "cart": f"{base}/loja/carrinho",
                "whatsapp": f"https://wa.me/{phone if phone.startswith('55') else '55' + phone}" if phone else "https://wa.me/",
            },
            "app": {
                "download_url": links["download"],
                "android_url": links["android"],
                "ios_url": links["ios"],
                "deep_live": links["deep_live"],
                "deep_current": current.get("deep_link") if current else "brechorisee://live",
                "overlay_available": True,
                "overlay_explanation": "O app mostra a peça atual por cima do Instagram usando dados da Central da Live, sem ler a tela da cliente.",
            },
            "display": {
                "poll_ms": LIVE_COMPANION_POLL_MS,
                "full_card_seconds": LIVE_COMPANION_FULL_CARD_SECONDS,
                "stale_seconds": LIVE_COMPANION_STALE_SECONDS,
                "auto_hide_when_no_product": True,
                "event_key": event_key,
                "current_elapsed_seconds": data.get("current_elapsed_seconds") or 0,
            },
            "customer": customer,
            "cta_text": brechorisee_customer_app_cta(request),
            "server_time": now_iso(),
        }


@app.get("/api/live/companion")
def api_live_companion(request: Request) -> JSONResponse:
    account = customer_from_request(request)
    return JSONResponse(_live_companion_payload(request, account))


@app.post("/api/live/companion/reservar")
def api_live_companion_reserve(
    request: Request,
    customer_name: str = Form(""),
    customer_phone: str = Form(""),
    customer_instagram: str = Form(""),
    force_waitlist: int = Form(0),
) -> JSONResponse:
    account = customer_from_request(request)
    if account:
        customer_name = customer_name or account["name"]
        customer_phone = customer_phone or account["phone"]
        customer_instagram = customer_instagram or account["instagram"]
    if not (customer_name or "").strip():
        return JSONResponse({"ok": False, "message": "Informe seu nome para reservar."}, status_code=400)

    response = api_live_public_reserve_current(
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_instagram=customer_instagram,
        force_waitlist=int(force_waitlist or 0),
    )
    try:
        payload = json.loads(response.body.decode("utf-8"))
        payload["cta_text"] = brechorisee_customer_app_cta(request)
        payload["app_links"] = brechorisee_customer_app_links(request)
        return JSONResponse(payload, status_code=response.status_code)
    except Exception:
        return response


@app.get("/live/companion", response_class=HTMLResponse)
def live_companion_public_page(request: Request) -> Response:
    return templates.TemplateResponse(
        "live_companion.html",
        {"request": request, "account": None, "settings": get_store_settings(), "public_mode": True},
    )


@app.get("/cliente/live-companion", response_class=HTMLResponse)
def customer_live_companion_page(request: Request) -> Response:
    account = customer_from_request(request)
    if not account:
        return RedirectResponse(url="/cliente?next=/cliente/inicio", status_code=303)
    return templates.TemplateResponse(
        "live_companion.html",
        {"request": request, "account": account, "settings": get_store_settings(), "public_mode": True},
    )



@app.get("/api/cliente/tutorial")
def api_customer_tutorial(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "tutorial": brechorisee_customer_tutorial_payload(request)})


@app.get("/cliente/tutorial", response_class=HTMLResponse)
def customer_tutorial_page(request: Request) -> Response:
    account = customer_from_request(request)
    return templates.TemplateResponse(
        "customer_tutorial.html",
        {
            "request": request,
            "account": account,
            "settings": get_store_settings(),
            "tutorial": brechorisee_customer_tutorial_payload(request),
            "app_links": brechorisee_customer_app_links(request),
            "public_mode": True,
        },
    )


@app.get("/app/tutorial", response_class=HTMLResponse)
def customer_app_tutorial_alias(request: Request) -> Response:
    return RedirectResponse(url="/cliente/tutorial", status_code=303)


@app.get("/tutorial-cliente", response_class=HTMLResponse)
def customer_tutorial_short_alias(request: Request) -> Response:
    return RedirectResponse(url="/cliente/tutorial", status_code=303)



@app.get("/api/app/cliente/download-status")
def api_customer_app_download_status(request: Request) -> JSONResponse:
    """Status público do APK para a página de instalação."""
    return JSONResponse({"ok": True, "apk": brechorisee_customer_apk_info(request), "links": brechorisee_customer_app_links(request)})


@app.get("/download/app-cliente.apk")
def download_customer_android_apk(request: Request) -> Response:
    """Download público do APK cliente pelo site BRECHORISEE."""
    info = brechorisee_customer_apk_info(request)
    path = brechorisee_customer_apk_path()
    if not info["available"]:
        html_page = f"""
        <!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
        <title>APK BRECHORISEE indisponível</title>
        <style>body{{font-family:system-ui;margin:0;background:#fff8f4;color:#33201b}}.wrap{{max-width:720px;margin:auto;padding:24px}}.card{{background:#fff;border:1px solid #eadfd8;border-radius:24px;padding:22px;box-shadow:0 18px 50px #0001}}.btn{{display:inline-block;background:#a84d3a;color:white;text-decoration:none;border-radius:16px;padding:13px 18px;font-weight:900}}</style>
        </head><body><main class='wrap'><section class='card'>
        <h1>APK cliente indisponível</h1>
        <p>O arquivo do app cliente não foi publicado ou está inválido/corrompido.</p>
        <p>Motivo: <b>{html.escape(str(info.get("validation_message") or "não informado"))}</b></p>
        <p>Rode <b>SISTEMA_BRECHORISEE.cmd</b> no Windows, copie o conteúdo de <b>PACOTE_CELULAR_SERVIDOR</b> para Downloads do celular servidor e execute <b>bash SISTEMA_BRECHORISEE_CELULAR.sh</b>.</p>
        <a class='btn' href='/app/cliente'>Voltar para instalar o app</a>
        </section></main></body></html>
        """
        return HTMLResponse(html_page, status_code=404)
    headers = {
        "Content-Disposition": 'attachment; filename="BRECHORISEE_CLIENTE.apk"',
        "Cache-Control": "public, max-age=300",
    }
    return FileResponse(
        str(path),
        media_type="application/vnd.android.package-archive",
        filename="BRECHORISEE_CLIENTE.apk",
        headers=headers,
    )


@app.get("/baixar-app")
def baixar_app_cliente_redirect() -> Response:
    return RedirectResponse(url="/app/cliente", status_code=303)


@app.get("/apk")
def baixar_apk_cliente_redirect() -> Response:
    return RedirectResponse(url="/download/app-cliente.apk", status_code=303)


@app.get("/app-cliente.apk")
def baixar_apk_cliente_alias() -> Response:
    return RedirectResponse(url="/download/app-cliente.apk", status_code=303)




@app.get("/api/app/admin/download-status")
def api_admin_app_download_status(request: Request) -> JSONResponse:
    """Status do APK Admin publicado no servidor."""
    return JSONResponse({"ok": True, "apk": brechorisee_admin_apk_info(request)})


@app.get("/download/app-admin.apk")
def download_admin_android_apk(request: Request) -> Response:
    """Download do APK Admin para uso interno da equipe BRECHORISEE."""
    info = brechorisee_admin_apk_info(request)
    path = brechorisee_admin_apk_path()
    if not info["available"]:
        html_page = f"""
        <!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
        <title>APK Admin indisponível</title>
        <style>body{{font-family:system-ui;margin:0;background:#fff8f4;color:#33201b}}.wrap{{max-width:720px;margin:auto;padding:24px}}.card{{background:#fff;border:1px solid #eadfd8;border-radius:24px;padding:22px;box-shadow:0 18px 50px #0001}}.btn{{display:inline-block;background:#a84d3a;color:white;text-decoration:none;border-radius:16px;padding:13px 18px;font-weight:900}}</style>
        </head><body><main class='wrap'><section class='card'>
        <h1>APK Admin indisponível</h1>
        <p>O arquivo do app Admin não foi publicado ou está inválido/corrompido.</p>
        <p>Motivo: <b>{html.escape(str(info.get("validation_message") or "não informado"))}</b></p>
        <p>Rode <b>SISTEMA_BRECHORISEE.cmd</b> no Windows, copie o conteúdo de <b>PACOTE_CELULAR_SERVIDOR</b> para Downloads do celular servidor e execute <b>bash SISTEMA_BRECHORISEE_CELULAR.sh</b>.</p>
        <a class='btn' href='/admin'>Abrir Admin pelo navegador</a>
        </section></main></body></html>
        """
        return HTMLResponse(html_page, status_code=404)
    headers = {
        "Content-Disposition": 'attachment; filename="BRECHORISEE_ADMIN.apk"',
        "Cache-Control": "public, max-age=300",
    }
    return FileResponse(
        str(path),
        media_type="application/vnd.android.package-archive",
        filename="BRECHORISEE_ADMIN.apk",
        headers=headers,
    )


@app.get("/apk-admin")
def baixar_apk_admin_redirect() -> Response:
    return RedirectResponse(url="/download/app-admin.apk", status_code=303)


@app.get("/admin.apk")
def baixar_apk_admin_alias() -> Response:
    return RedirectResponse(url="/download/app-admin.apk", status_code=303)


@app.get("/app/cliente", response_class=HTMLResponse)
def customer_app_download_page(request: Request) -> Response:
    links = brechorisee_customer_app_links(request)
    apk = brechorisee_customer_apk_info(request)
    apk_status = "Disponível" if apk["available"] else "Ainda não publicado"
    apk_size = f"{apk['size_mb']} MB" if apk["available"] else "—"
    apk_updated = apk["updated_at"] or "—"
    google_play = links.get("google_play") or ""
    apk_button = (
        f"<a class='btn' href='{html.escape(links['apk'])}'>⬇️ Baixar APK Android pelo site</a>"
        if apk["available"]
        else (
            "<div class='mini' style='text-align:left;background:#fff3ed'>"
            "<b>APK não instalado:</b><br>"
            f"{html.escape(str(apk.get('validation_message') or 'APK ainda não publicado.'))}<br>"
            "Você pode continuar usando pelo navegador. O APK antigo foi bloqueado; compile e publique um APK novo v4.8.9 assinado antes de liberar instalação."
            "</div>"
        )
    )
    html_page = f"""
    <!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>Baixar app BRECHORISEE</title>
    <style>
    body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:linear-gradient(135deg,#fff8f4,#f4e1d7);color:#34221e}}
    .wrap{{max-width:880px;margin:auto;padding:22px}}
    .card{{background:#fff;border-radius:30px;padding:24px;box-shadow:0 24px 80px #0001;border:1px solid #eadfd8;margin:16px 0}}
    .hero{{text-align:center}}
    .badge{{display:inline-flex;gap:8px;align-items:center;background:#f6ebe6;border-radius:999px;padding:8px 12px;color:#704033;font-weight:800}}
    .btn{{display:block;text-align:center;border-radius:18px;padding:15px;margin:12px 0;background:#a84d3a;color:#fff;text-decoration:none;font-weight:900}}
    .btn.secondary{{background:#704033}}
    .ghost{{background:#f4ebe6;color:#704033}}
    .hint{{color:#6f5c55;line-height:1.5}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}}
    .mini{{background:#fff8f4;border:1px solid #eadfd8;border-radius:20px;padding:14px}}
    code{{background:#fff3ed;border-radius:10px;padding:2px 6px}}
    </style></head>
    <body><main class='wrap'>
    <section class='card hero'>
      <div class='badge'>💖 App BRECHORISEE Cliente</div>
      <h1>Baixe o app para reservar mais rápido na live</h1>
      <p class='hint'>No app, a cliente recebe a peça atual em tempo real, reserva com um toque, entra na fila, acompanha sacola/carrinho e recebe avisos da loja.</p>
      {apk_button}
      {f"<a class='btn secondary' href='{html.escape(google_play)}'>▶️ Abrir na Google Play</a>" if google_play else ""}
      <a class='btn ghost' href='{html.escape(links.get("customer_home") or links["download"])}'>Continuar sem app pelo navegador</a>
      <a class='btn ghost' href='{html.escape(links["tutorial"])}'>Ver animação: como usar app e site</a>
    </section>

    <section class='card'>
      <h2>Status do APK</h2>
      <div class='grid'>
        <div class='mini'><b>Status</b><br>{html.escape(apk_status)}</div>
        <div class='mini'><b>Arquivo</b><br>{html.escape(str(apk["filename"]))}</div>
        <div class='mini'><b>Tamanho</b><br>{html.escape(apk_size)}</div>
        <div class='mini'><b>Atualizado</b><br>{html.escape(apk_updated)}</div>
        <div class='mini'><b>Validação</b><br>{html.escape(str(apk.get("validation_message") or "—"))}</div>
      </div>
      <p class='hint'>Link direto para enviar às clientes:</p>
      <p><code>{html.escape(str(apk["url"]))}</code></p>
    </section>

    <section class='card'>
      <h2>Como instalar pelo APK</h2>
      <p class='hint'>1. Toque em <b>Baixar APK Android pelo site</b>.<br>
      2. Quando o Android pedir, permita instalar apps desta fonte.<br>
      3. Abra o BRECHORISEE, permita notificações e acompanhe a live.<br>
      4. Quem não quiser instalar agora pode continuar pelo navegador.</p>
      <a class='btn ghost' href='{html.escape(links.get("customer_home") or links["download"])}'>Abrir área da cliente sem instalar</a>
    </section>

    <section class='card'>
      <h2>Links úteis</h2>
      <a class='btn ghost' href='{html.escape(links.get("customer_home") or links["download"])}'>Área da cliente</a>
      <a class='btn ghost' href='{html.escape(links["live_current"])}'>Peça atual da live</a>
      <a class='btn ghost' href='{html.escape(links["tutorial"])}'>Tutorial animado</a>
    </section>
    </main></body></html>
    """
    return HTMLResponse(html_page)


@app.get("/live/apresentadora/{session_id}", response_class=HTMLResponse)
def live_presenter_mode_page(request: Request, session_id: int) -> Response:
    init_live_central_schema()
    with get_db() as con:
        _live_session_or_404(con, int(session_id))
    return templates.TemplateResponse("live_presenter.html", {"request": request, "session_id": int(session_id), "active": "live"})


@app.post("/api/live/central/{session_id}/comment-intent")
def api_live_comment_intent(session_id: int, message: str = Form(...), customer_name: str = Form("Cliente")) -> JSONResponse:
    intent = live_detect_comment_intent(message)
    with get_db() as con:
        _live_session_or_404(con, int(session_id))
        current = _live_current_queue_item(con, int(session_id))
        product_id = int(current["product_id"]) if current else None
        cur = con.execute(
            """
            INSERT INTO live_comment_intents(live_session_id, product_id, customer_name, message, intent, suggested_action, created_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (int(session_id), product_id, customer_name[:120], message[:1000], intent["intent"], intent["suggested_action"], now_iso()),
        )
        if TELEGRAM_NOTIFY_COMMENTS and intent["suggested_action"] != "acompanhar":
            telegram_send_admin_message(
                con,
                f"💬 Comentário com intenção na live #{int(session_id)}:\n{telegram_html(customer_name)}: {telegram_html(message)}\nSugestão: {telegram_html(intent['label'])}",
                related_type="live_comment_intent",
                related_id=int(cur.lastrowid),
            )
    return JSONResponse({"ok": True, "id": cur.lastrowid, "intent": intent})


@app.post("/api/live/central/{session_id}/register-comment")
def api_live_central_register_comment(session_id: int, customer_name: str = Form("Cliente"), message: str = Form(...), source: str = Form("manual")) -> JSONResponse:
    init_live_central_schema()
    intent = live_detect_comment_intent(message)
    with get_db() as con:
        _live_session_or_404(con, int(session_id))
        cur = con.execute(
            "INSERT INTO live_comments(live_session_id, author_name, message, source, pinned, created_at) VALUES(?,?,?,?,?,?)",
            (int(session_id), customer_name[:120], message[:1000], source[:60], 0, now_iso()),
        )
        current = _live_current_queue_item(con, int(session_id))
        product_id = int(current["product_id"]) if current else None
        intent_cur = con.execute(
            "INSERT INTO live_comment_intents(live_comment_id, live_session_id, product_id, customer_name, message, intent, suggested_action, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (int(cur.lastrowid), int(session_id), product_id, customer_name[:120], message[:1000], intent["intent"], intent["suggested_action"], now_iso()),
        )
        if TELEGRAM_NOTIFY_COMMENTS and intent["suggested_action"] != "acompanhar":
            telegram_send_admin_message(
                con,
                f"💬 Comentário para revisar na live #{int(session_id)}:\n{telegram_html(customer_name)}: {telegram_html(message)}\nSugestão: {telegram_html(intent['label'])}",
                related_type="live_comment",
                related_id=int(intent_cur.lastrowid),
            )
    return JSONResponse({"ok": True, "comment_id": cur.lastrowid, "intent": intent})



# ---------------------------------------------------------------------------
# Google Play / área pública obrigatória do app cliente
# ---------------------------------------------------------------------------

def _legal_support_email() -> str:
    return os.getenv("BRECHORISEE_SUPPORT_EMAIL", "suporte@brechorisee.com.br").strip() or "suporte@brechorisee.com.br"


def _legal_store_name() -> str:
    return os.getenv("BRECHORISEE_STORE_LEGAL_NAME", "BRECHORISEE").strip() or "BRECHORISEE"


def _legal_html_page(title: str, body: str) -> HTMLResponse:
    app_version = html.escape(APP_VERSION)
    support_email = html.escape(_legal_support_email())
    brand = html.escape(_legal_store_name())
    page = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · {brand}</title>
<style>
:root{{color-scheme:light;--bg:#fff8f4;--card:#fff;--ink:#34231f;--muted:#735e57;--brand:#a84d3a;--soft:#f3e3db}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Arial,Helvetica,sans-serif;background:linear-gradient(160deg,#fff8f4,#f8ece5);color:var(--ink)}}
.wrap{{max-width:920px;margin:0 auto;padding:24px}}.card{{background:var(--card);border:1px solid #ead8cf;border-radius:28px;padding:26px;box-shadow:0 20px 60px #00000012}}
h1{{margin:0 0 10px;font-size:30px}}h2{{margin-top:28px;color:#6d3125}}p,li{{line-height:1.58;color:var(--muted);font-size:16px}}a{{color:var(--brand);font-weight:800}}.badge{{display:inline-block;background:var(--soft);border-radius:999px;padding:8px 12px;color:#70382d;font-weight:800}}
.footer{{margin-top:28px;padding-top:18px;border-top:1px solid #efddd5;color:#836d65;font-size:14px}}.btn{{display:inline-block;background:var(--brand);color:#fff;text-decoration:none;border-radius:15px;padding:12px 16px;margin:8px 8px 0 0}}
</style>
</head>
<body><main class="wrap"><section class="card">
<span class="badge">BRECHORISEE Cliente · versão {app_version}</span>
{body}
<div class="footer">
<p>Suporte: <a href="mailto:{support_email}">{support_email}</a></p>
<p><a class="btn" href="{html.escape(get_public_server_url())}/cliente">Abrir área da cliente</a>
<a class="btn" href="{html.escape(get_public_server_url())}/cliente/tutorial">Como usar o app</a></p>
</div>
</section></main></body></html>"""
    return HTMLResponse(page)


@app.get("/privacidade", response_class=HTMLResponse)
@app.get("/politica-privacidade", response_class=HTMLResponse)
@app.get("/privacy", response_class=HTMLResponse)
def customer_privacy_policy() -> HTMLResponse:
    brand = html.escape(_legal_store_name())
    support = html.escape(_legal_support_email())
    body = f"""
<h1>Política de Privacidade</h1>
<p>Esta política explica como o {brand} trata informações no app cliente, no site, na vitrine online, nas reservas da live, no carrinho e no atendimento.</p>

<h2>Dados que podem ser informados pela cliente</h2>
<ul>
<li>Nome, telefone e dados de contato para reserva, carrinho, entrega, retirada e suporte.</li>
<li>Endereço de entrega ou preferência de retirada, quando a cliente escolhe finalizar uma compra.</li>
<li>Itens reservados, fila de espera, carrinho, pedidos, comprovantes e histórico de atendimento.</li>
<li>Mensagens enviadas voluntariamente pelo site, WhatsApp, Telegram ou canais de atendimento da loja.</li>
</ul>

<h2>Dados técnicos do app</h2>
<ul>
<li>O app usa internet para abrir o site BRECHORISEE e sincronizar peça atual da live, carrinho e notificações.</li>
<li>O app pode pedir notificação para avisar quando uma live começar, quando a peça atual mudar ou quando houver atualização do pedido.</li>
<li>O app pode pedir câmera/arquivos apenas para funções escolhidas pela cliente, como enviar comprovante, imagem ou acessar páginas que tenham upload.</li>
<li>O app pode pedir permissão de sobreposição no Android para mostrar o card da peça atual enquanto a cliente assiste à live no Instagram.</li>
</ul>

<h2>O que o app não faz</h2>
<ul>
<li>Não coleta senha do Instagram.</li>
<li>Não lê mensagens privadas do Instagram, WhatsApp ou Telegram.</li>
<li>Não captura a tela da cliente.</li>
<li>Não vende dados pessoais para anunciantes.</li>
<li>Não usa a camada flutuante para controlar outros aplicativos.</li>
</ul>

<h2>Uso das informações</h2>
<p>Os dados são usados para reservar peças, organizar fila de espera, montar carrinho, confirmar pagamento, combinar entrega ou retirada, enviar notificações úteis e melhorar o atendimento da loja.</p>

<h2>Compartilhamento</h2>
<p>Os dados podem ser usados por serviços necessários para funcionamento do atendimento, hospedagem, mensagens, pagamento, entrega e suporte. O {brand} não vende dados pessoais.</p>

<h2>Exclusão e suporte</h2>
<p>A cliente pode pedir correção ou exclusão de dados pelo e-mail <a href="mailto:{support}">{support}</a> ou pela página <a href="/excluir-dados">/excluir-dados</a>.</p>

<h2>Atualizações</h2>
<p>Esta política pode ser atualizada para acompanhar novas versões do app, site e operações da loja. A versão exibida nesta página acompanha a versão do sistema publicada.</p>
"""
    return _legal_html_page("Política de Privacidade", body)


@app.get("/termos", response_class=HTMLResponse)
@app.get("/termos-de-uso", response_class=HTMLResponse)
def customer_terms_of_use() -> HTMLResponse:
    brand = html.escape(_legal_store_name())
    body = f"""
<h1>Termos de Uso</h1>
<p>Ao usar o app e o site {brand}, a cliente concorda com estes termos de uso para navegação, reservas, carrinho, live, vitrine e atendimento.</p>

<h2>Reservas e fila de espera</h2>
<p>A reserva de uma peça pode ter prazo de pagamento. Se o prazo vencer, o sistema pode liberar a peça para a próxima cliente da fila de espera.</p>

<h2>Preço, disponibilidade e estado das peças</h2>
<p>As peças podem ser únicas. A disponibilidade exibida no app/site depende da sincronização da live e da confirmação da loja. Medidas, estado da peça e fotos devem ser conferidos antes da finalização.</p>

<h2>Pagamento, retirada e entrega</h2>
<p>As formas de pagamento, retirada e entrega são informadas pela loja durante o fechamento do carrinho. O pedido é considerado finalizado após confirmação da loja.</p>

<h2>Uso da camada flutuante</h2>
<p>No Android, a cliente pode ativar uma camada flutuante para ver a peça atual enquanto assiste à live no Instagram. Essa camada não lê a tela, não grava o Instagram e não controla outro aplicativo.</p>

<h2>Uso correto</h2>
<p>A cliente deve fornecer dados corretos para contato, entrega e pagamento. O uso indevido do app, tentativas de burlar filas ou reservas falsas podem levar ao cancelamento da reserva.</p>
"""
    return _legal_html_page("Termos de Uso", body)


@app.get("/excluir-dados", response_class=HTMLResponse)
@app.get("/solicitar-exclusao-de-dados", response_class=HTMLResponse)
def customer_delete_data_page() -> HTMLResponse:
    support = html.escape(_legal_support_email())
    body = f"""
<h1>Solicitar exclusão de dados</h1>
<p>A cliente pode solicitar exclusão, correção ou consulta dos dados mantidos pelo BRECHORISEE.</p>

<h2>Como solicitar</h2>
<p>Envie um e-mail para <a href="mailto:{support}?subject=Solicitação%20de%20exclusão%20de%20dados%20BRECHORISEE">{support}</a> com:</p>
<ul>
<li>Nome usado nas compras ou reservas;</li>
<li>Telefone/WhatsApp cadastrado;</li>
<li>Pedido, carrinho ou live relacionada, se houver;</li>
<li>O que deseja excluir ou corrigir.</li>
</ul>

<h2>Observação</h2>
<p>Alguns dados podem precisar ser mantidos pelo período necessário para obrigações fiscais, prevenção de fraude, comprovação de compra, entrega, garantia ou defesa de direitos.</p>
"""
    return _legal_html_page("Excluir dados", body)


@app.get("/suporte", response_class=HTMLResponse)
@app.get("/contato", response_class=HTMLResponse)
def customer_support_page() -> HTMLResponse:
    support = html.escape(_legal_support_email())
    base = html.escape(get_public_server_url())
    body = f"""
<h1>Suporte BRECHORISEE</h1>
<p>Precisa de ajuda com app, site, live, reserva, carrinho, Pix, retirada ou entrega?</p>
<p>Fale com a equipe pelo e-mail <a href="mailto:{support}">{support}</a>.</p>
<p>Links úteis:</p>
<ul>
<li><a href="{base}/cliente/tutorial">Como usar o app e o site</a></li>
<li><a href="{base}/cliente">Área da cliente</a></li>
<li><a href="{base}/live/peca-atual">Peça atual da live</a></li>
<li><a href="{base}/privacidade">Política de privacidade</a></li>
<li><a href="{base}/termos">Termos de uso</a></li>
</ul>
"""
    return _legal_html_page("Suporte", body)


@app.get("/.well-known/assetlinks.json")
def android_assetlinks() -> JSONResponse:
    """Digital Asset Links para links verificados do Android.

    Depois de gerar a chave/AAB, coloque no Render:
    BRECHORISEE_ANDROID_SHA256_FINGERPRINTS=AA:BB:CC...[,OUTRA_DIGITAL]
    """
    package_name = os.getenv("BRECHORISEE_ANDROID_PACKAGE_NAME", "com.brechorisee.cliente").strip() or "com.brechorisee.cliente"
    raw_fingerprints = os.getenv("BRECHORISEE_ANDROID_SHA256_FINGERPRINTS", "").strip()
    fingerprints = [fp.strip() for fp in raw_fingerprints.replace(";", ",").split(",") if fp.strip()]
    payload = []
    if fingerprints:
        payload.append({
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": package_name,
                "sha256_cert_fingerprints": fingerprints,
            },
        })
    return JSONResponse(payload, headers={"Cache-Control": "public, max-age=300"})


# Inicializa também quando executado por servidores que não disparam startup durante testes.
init_db()
init_live_central_schema()
register_schema_version()



@app.get("/sistema/status")
def sistema_status() -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "app": "BRECHORISEE",
        "version": APP_VERSION,
        "env": BRECHORISEE_ENV,
        "db_path": str(DB_PATH),
        "persistent_dir": str(PERSISTENT_DIR),
        "uploads": str(UPLOAD_DIR),
        "render": bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID")),
        "time": datetime.now().isoformat(timespec="seconds"),
    })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)


# ---------------------------------------------------------------------------
# Instagram Live Overlay Pro 4.2
# Integra Instagram como palco e BRECHORISEE como camada de compra:
# - /instagram público para link da bio
# - /instagram-studio admin para posts/stories/reels e live automática
# - endpoints públicos de overlay para app cliente com miniatura da peça atual
# ---------------------------------------------------------------------------

@app.get("/instagram", response_class=HTMLResponse)
def instagram_public_live_hub(request: Request) -> Response:
    """Página pública para link da bio: live no Instagram + reserva no BRECHORISEE."""
    payload = _live_companion_payload(request, customer_from_request(request))
    return templates.TemplateResponse(
        "instagram_live_hub.html",
        {
            "request": request,
            "payload": payload,
            "settings": get_store_settings(),
            "app_links": brechorisee_customer_app_links(request),
            "cta_text": brechorisee_customer_app_cta(request),
        },
    )


@app.get("/api/instagram/live-overlay")
def api_instagram_live_overlay(request: Request) -> JSONResponse:
    """Alias público para o app cliente/overlay consumir a peça atual da live."""
    payload = _live_companion_payload(request, customer_from_request(request))
    payload["overlay_mode"] = {
        "name": "instagram_live_overlay_pro",
        "show_thumbnail": True,
        "compact_default": True,
        "tap_to_expand": True,
        "open_instagram_native": True,
        "reserve_inside_brechorisee": True,
    }
    return JSONResponse(payload)


@app.get("/api/instagram/live-card")
def api_instagram_live_card(request: Request) -> JSONResponse:
    """Payload compacto para miniatura flutuante: imagem, preço, tamanho, status e ação."""
    payload = _live_companion_payload(request, customer_from_request(request))
    product = payload.get("current_product") or {}
    card = {
        "ok": bool(payload.get("ok") and product),
        "live": payload.get("session") or {},
        "product": product,
        "image_url": product.get("image_url") if product else "",
        "title": product.get("title") if product else "",
        "price_label": product.get("price_label") if product else "",
        "size": product.get("size") if product else "",
        "status": product.get("status") if product else "",
        "reserve_url": (payload.get("links") or {}).get("current_product") or "/live/peca-atual",
        "instagram_live_url": (payload.get("links") or {}).get("instagram_live") or "",
        "poll_ms": (payload.get("display") or {}).get("poll_ms", LIVE_COMPANION_POLL_MS),
        "server_time": now_iso(),
    }
    return JSONResponse(card)


def _instagram_studio_live_session_dict(con: sqlite3.Connection, request: Request) -> dict[str, Any] | None:
    init_live_central_schema()
    live = con.execute(
        "SELECT * FROM live_sessions WHERE status IN ('ao_vivo','aberta') ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not live:
        return None
    try:
        data = _live_dashboard_payload(con, request, int(live["id"]))
        return data.get("session") or dict(live)
    except Exception:
        return dict(live)


def _instagram_studio_generated_for_product(
    request: Request,
    product_id: int,
    content_type: str = "story",
    custom_text: str = "",
    template_style: str = "live",
) -> dict[str, Any]:
    product, media = get_product_with_media(int(product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Peça não encontrada.")
    generated = build_marketing_content(
        product,
        media,
        custom_text=custom_text,
        content_type=content_type,
        template_style=template_style,
        seal="auto",
        duration_mode="curto" if content_type in {"story", "reel"} else "medio",
        quality_mode="alta",
        audio_mode="narracao",
        music_mode="viral",
    )
    media_dicts = [row_to_dict(m) for m in media]
    product_dict = row_to_dict(product)
    rendered_type = "story" if content_type == "story" else "post"
    try:
        generated["rendered_url"] = render_post_image(
            product_dict,
            media_dicts,
            generated.get("full_caption") or generated.get("caption") or "",
            content_type=rendered_type,
            template_style=template_style,
            seal=generated.get("seal") or "BRECHORISEE",
        )
    except Exception:
        generated["rendered_url"] = ""
    generated["product"] = product_dict
    generated["media"] = media_dicts
    generated["share_url"] = _abs_url_for_client(request, f"/vitrine/peca/{product_dict.get('code') or product_dict.get('id')}?origem=instagram")
    generated["live_url"] = _abs_url_for_client(request, "/instagram")
    return generated


@app.get("/instagram-studio", response_class=HTMLResponse)
def instagram_studio_page(
    request: Request,
    product_id: int | None = None,
    q: str = "",
    msg: str = "",
) -> Response:
    rows = search_products_rows(q=q, status="todos", limit=36 if not q else 80)
    selected_product = None
    selected_media: list[sqlite3.Row] = []
    if product_id:
        selected_product, selected_media = get_product_with_media(int(product_id))
    with get_db() as con:
        live_session = _instagram_studio_live_session_dict(con, request)
        recent_items = con.execute(
            """
            SELECT li.*, p.id AS product_id, p.code, p.title, p.sale_price, p.size, p.status, p.image_filename
            FROM live_session_items li
            JOIN products p ON p.id=li.product_id
            ORDER BY li.id DESC
            LIMIT 18
            """
        ).fetchall()
    return templates.TemplateResponse(
        "instagram_studio.html",
        {
            "request": request,
            "products": rows,
            "selected_product": selected_product,
            "selected_media": selected_media,
            "q": q,
            "generated": None,
            "generated_collection": [],
            "live_session": live_session,
            "recent_items": recent_items,
            "msg": msg,
            "active": "instagram-studio",
            "app_links": brechorisee_customer_app_links(request),
        },
    )


@app.post("/instagram-studio/gerar", response_class=HTMLResponse)
def instagram_studio_generate(
    request: Request,
    product_id: int = Form(...),
    content_type: str = Form("story"),
    custom_text: str = Form(""),
    template_style: str = Form("live"),
    q: str = Form(""),
) -> Response:
    generated = _instagram_studio_generated_for_product(
        request,
        int(product_id),
        content_type=content_type,
        custom_text=custom_text,
        template_style=template_style,
    )
    products = search_products_rows(q=q, status="todos", limit=36 if not q else 80)
    selected_product, selected_media = get_product_with_media(int(product_id))
    with get_db() as con:
        live_session = _instagram_studio_live_session_dict(con, request)
        recent_items = con.execute(
            """
            SELECT li.*, p.id AS product_id, p.code, p.title, p.sale_price, p.size, p.status, p.image_filename
            FROM live_session_items li
            JOIN products p ON p.id=li.product_id
            ORDER BY li.id DESC
            LIMIT 18
            """
        ).fetchall()
    return templates.TemplateResponse(
        "instagram_studio.html",
        {
            "request": request,
            "products": products,
            "selected_product": selected_product,
            "selected_media": selected_media,
            "q": q,
            "generated": generated,
            "generated_collection": [],
            "live_session": live_session,
            "recent_items": recent_items,
            "msg": "Conteúdo gerado para Instagram.",
            "active": "instagram-studio",
            "app_links": brechorisee_customer_app_links(request),
        },
    )


@app.post("/instagram-studio/live-automatica/iniciar")
def instagram_studio_start_automatic_live(
    request: Request,
    title: str = Form(""),
    instagram_live_url: str = Form(""),
) -> Response:
    """Inicia live sem escolher peças antes; o app admin reconhece automaticamente durante a live."""
    init_live_central_schema()
    title = (title or "").strip() or f"Live Instagram {datetime.now().strftime('%d/%m %H:%M')}"
    instagram_live_url = (instagram_live_url or "").strip()
    with get_db() as con:
        session = get_or_create_active_live_session(con)
        cols = table_columns(con, "live_sessions")
        sets = ["title=?", "status=?"]
        values: list[Any] = [title, "ao_vivo"]
        if "started_at" in cols:
            sets.append("started_at=COALESCE(started_at, ?)")
            values.append(now_iso())
        if "source_platform" in cols:
            sets.append("source_platform=?")
            values.append("instagram")
        if "instagram_live_url" in cols and instagram_live_url:
            sets.append("instagram_live_url=?")
            values.append(instagram_live_url)
        if "brechorisee_watch_enabled" in cols:
            sets.append("brechorisee_watch_enabled=?")
            values.append(1)
        if "notes" in cols:
            sets.append("notes=?")
            values.append("Live Automática Inteligente: sem lista prévia; reconhecimento automático pelo app Admin.")
        values.append(int(session["id"]))
        con.execute(f"UPDATE live_sessions SET {', '.join(sets)} WHERE id=?", values)
    return RedirectResponse(url="/instagram-studio?msg=Live%20autom%C3%A1tica%20iniciada", status_code=303)


@app.post("/instagram-studio/repescagem", response_class=HTMLResponse)
def instagram_studio_generate_recap_pack(
    request: Request,
    session_id: int = Form(0),
    content_type: str = Form("story"),
) -> Response:
    """Gera pacote de stories/posts das peças mostradas e ainda disponíveis."""
    init_live_central_schema()
    generated_collection: list[dict[str, Any]] = []
    with get_db() as con:
        if not session_id:
            live = con.execute("SELECT * FROM live_sessions ORDER BY id DESC LIMIT 1").fetchone()
            session_id = int(live["id"]) if live else 0
        rows = con.execute(
            """
            SELECT DISTINCT p.id, p.code, p.title, p.sale_price, p.status, MAX(li.id) AS last_item_id
            FROM live_session_items li
            JOIN products p ON p.id=li.product_id
            WHERE li.live_session_id=? AND p.status='disponivel'
            GROUP BY p.id
            ORDER BY last_item_id DESC
            LIMIT 12
            """,
            (int(session_id or 0),),
        ).fetchall()
    for row in rows:
        try:
            generated_collection.append(
                _instagram_studio_generated_for_product(
                    request,
                    int(row["id"]),
                    content_type=content_type,
                    custom_text="Sobrou da live e ainda está disponível. Reserve pelo link da bio ou pelo app BRECHORISEE.",
                    template_style="repescagem",
                )
            )
        except Exception:
            pass

    products = search_products_rows(q="", status="todos", limit=36)
    with get_db() as con:
        live_session = _instagram_studio_live_session_dict(con, request)
        recent_items = con.execute(
            """
            SELECT li.*, p.id AS product_id, p.code, p.title, p.sale_price, p.size, p.status, p.image_filename
            FROM live_session_items li
            JOIN products p ON p.id=li.product_id
            ORDER BY li.id DESC
            LIMIT 18
            """
        ).fetchall()
    return templates.TemplateResponse(
        "instagram_studio.html",
        {
            "request": request,
            "products": products,
            "selected_product": None,
            "selected_media": [],
            "q": "",
            "generated": None,
            "generated_collection": generated_collection,
            "live_session": live_session,
            "recent_items": recent_items,
            "msg": f"{len(generated_collection)} arte(s) de repescagem gerada(s).",
            "active": "instagram-studio",
            "app_links": brechorisee_customer_app_links(request),
        },
    )



# ============================================================
# CHAT RISEE - Bate-papo interno estilo WhatsApp
# Integra cliente, admin, live, pedidos, peças, overlay e Telegram.
# ============================================================

# Ajuste dinâmico dos grupos de rotas para o middleware existente.
try:
    ADMIN_ROUTE_PREFIXES = tuple(dict.fromkeys(list(ADMIN_ROUTE_PREFIXES) + ["/atendimento", "/api/chat/admin"]))
except Exception:
    pass
try:
    PUBLIC_ROUTE_PREFIXES = tuple(dict.fromkeys(list(PUBLIC_ROUTE_PREFIXES) + [
        "/cliente/chat", "/api/chat/cliente", "/api/chat/public"
    ]))
except Exception:
    pass


def init_chat_schema() -> None:
    """Cria/atualiza as tabelas do Chat BRECHORISEE sem depender de migração externa."""
    with get_db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_account_id INTEGER,
                customer_id INTEGER,
                product_id INTEGER,
                order_id INTEGER,
                live_session_id INTEGER,
                title TEXT NOT NULL,
                origin TEXT NOT NULL DEFAULT 'geral',
                status TEXT NOT NULL DEFAULT 'aberto',
                priority TEXT NOT NULL DEFAULT 'normal',
                last_message_at TEXT,
                unread_admin INTEGER NOT NULL DEFAULT 0,
                unread_customer INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id),
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (order_id) REFERENCES online_orders(id),
                FOREIGN KEY (live_session_id) REFERENCES live_sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_chat_threads_customer_account ON chat_threads(customer_account_id);
            CREATE INDEX IF NOT EXISTS idx_chat_threads_product ON chat_threads(product_id);
            CREATE INDEX IF NOT EXISTS idx_chat_threads_order ON chat_threads(order_id);
            CREATE INDEX IF NOT EXISTS idx_chat_threads_status ON chat_threads(status, last_message_at DESC);
            CREATE INDEX IF NOT EXISTS idx_chat_threads_live ON chat_threads(live_session_id);

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                sender_type TEXT NOT NULL,
                sender_id INTEGER,
                sender_name TEXT,
                message_type TEXT NOT NULL DEFAULT 'text',
                body TEXT,
                attachment_filename TEXT,
                attachment_url TEXT,
                metadata_json TEXT,
                read_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES chat_threads(id)
            );

            CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id, id);
            CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at);

            CREATE TABLE IF NOT EXISTS chat_quick_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                body TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'geral',
                active INTEGER NOT NULL DEFAULT 1,
                usage_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chat_quick_replies_active ON chat_quick_replies(active, category, usage_count DESC);
            """
        )
        chat_columns = {row["name"] for row in con.execute("PRAGMA table_info(chat_threads)").fetchall()}
        chat_alters = {
            "bot_mode": "bot_mode TEXT NOT NULL DEFAULT 'auto'",
            "bot_paused": "bot_paused INTEGER NOT NULL DEFAULT 0",
            "bot_paused_reason": "bot_paused_reason TEXT NOT NULL DEFAULT ''",
            "assigned_admin_id": "assigned_admin_id INTEGER",
            "assigned_admin_name": "assigned_admin_name TEXT NOT NULL DEFAULT ''",
            "human_takeover_at": "human_takeover_at TEXT",
            "bot_resumed_at": "bot_resumed_at TEXT",
        }
        for col_name, ddl in chat_alters.items():
            if col_name not in chat_columns:
                con.execute(f"ALTER TABLE chat_threads ADD COLUMN {ddl}")
        con.execute("CREATE INDEX IF NOT EXISTS idx_chat_threads_bot_mode ON chat_threads(bot_mode, bot_paused)")
        defaults = [
            ("Boas-vindas", "Oi! Tudo bem? Sou do BRECHORISEE. Como posso te ajudar?", "geral"),
            ("Disponibilidade", "Essa peça ainda está disponível no momento. Posso reservar para você?", "peca"),
            ("Reservada", "Prontinho, deixei sua peça reservada. A reserva fica segura enquanto combinamos o pagamento.", "pedido"),
            ("Pix", "Pode enviar o comprovante por aqui. Assim que confirmar, atualizo seu pedido.", "pagamento"),
            ("Entrega", "Me envie seu endereço completo ou escolha retirada. Já te confirmo a melhor forma de entrega.", "entrega"),
            ("Live", "Essa é a peça que está passando agora na live. Quer que eu reserve para você?", "live"),
        ]
        for label, body, category in defaults:
            exists = con.execute(
                "SELECT 1 FROM chat_quick_replies WHERE label=? AND body=? LIMIT 1",
                (label, body),
            ).fetchone()
            if not exists:
                con.execute(
                    "INSERT INTO chat_quick_replies(label, body, category, active, usage_count, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                    (label, body, category, 1, 0, now_iso(), now_iso()),
                )


@app.on_event("startup")
def startup_chat_risee() -> None:
    init_chat_schema()


def chat_clean_text(value: Any, limit: int = 2500) -> str:
    text_value = str(value or "").replace("\x00", "").strip()
    return text_value[:limit]


def chat_sender_name(sender_type: str, account: sqlite3.Row | dict[str, Any] | None = None) -> str:
    if sender_type == "admin":
        if account:
            return str(row_get(account, "name", "") or "Atendimento BRECHORISEE")
        return "Atendimento BRECHORISEE"
    if account:
        return str(row_get(account, "name", "") or "Cliente")
    return "Cliente"


def chat_attachment_dir() -> Path:
    path = BASE_DIR / "static" / "uploads" / "chat"
    path.mkdir(parents=True, exist_ok=True)
    return path


def chat_public_attachment_url(filename: str | None) -> str:
    if not filename:
        return ""
    return f"/static/uploads/chat/{filename}"


async def save_chat_attachment(file: UploadFile | None) -> tuple[str, str, str]:
    """Salva uma imagem/anexo simples do chat. Retorna (filename, url, message_type)."""
    if not file or not file.filename:
        return "", "", "text"
    original = Path(str(file.filename)).name
    suffix = Path(original).suffix.lower()
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".txt"}
    if suffix not in allowed:
        suffix = ".bin"
    raw = await file.read()
    max_bytes = 8 * 1024 * 1024
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(6)}{suffix}"
    target = chat_attachment_dir() / filename
    target.write_bytes(raw)
    message_type = "image" if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else "file"
    return filename, chat_public_attachment_url(filename), message_type


def chat_product_image_url(product: sqlite3.Row | dict[str, Any] | None) -> str:
    if not product:
        return ""
    filename = row_get(product, "image_filename", "") or ""
    if not filename:
        return ""
    return f"/static/uploads/{filename}"


def chat_format_thread_row(row: sqlite3.Row | dict[str, Any], product: sqlite3.Row | dict[str, Any] | None = None, order: sqlite3.Row | dict[str, Any] | None = None, customer: sqlite3.Row | dict[str, Any] | None = None) -> dict[str, Any]:
    data = row_to_dict(row)
    data["product"] = row_to_dict(product) if product else None
    if data["product"]:
        data["product"]["image_url"] = chat_product_image_url(product)
        data["product"]["price_label"] = money(row_get(product, "sale_price", 0))
    data["order"] = row_to_dict(order) if order else None
    data["customer"] = row_to_dict(customer) if customer else None
    data["unread_admin"] = int(data.get("unread_admin") or 0)
    data["unread_customer"] = int(data.get("unread_customer") or 0)
    return data


def chat_get_context_rows(con: sqlite3.Connection, thread: sqlite3.Row | dict[str, Any]) -> tuple[sqlite3.Row | None, sqlite3.Row | None, sqlite3.Row | None]:
    product = None
    order = None
    customer = None
    product_id = int(row_get(thread, "product_id", 0) or 0)
    order_id = int(row_get(thread, "order_id", 0) or 0)
    customer_account_id = int(row_get(thread, "customer_account_id", 0) or 0)
    if product_id:
        product = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if order_id:
        order = con.execute("SELECT * FROM online_orders WHERE id=?", (order_id,)).fetchone()
    if customer_account_id:
        customer = con.execute("SELECT * FROM customer_accounts WHERE id=?", (customer_account_id,)).fetchone()
    return product, order, customer


def chat_find_product(con: sqlite3.Connection, product_id: int | None = None, produto: str = "", code: str = "") -> sqlite3.Row | None:
    if product_id:
        row = con.execute("SELECT * FROM products WHERE id=?", (int(product_id),)).fetchone()
        if row:
            return row
    code_value = (produto or code or "").strip()
    if code_value:
        return con.execute("SELECT * FROM products WHERE code=? COLLATE NOCASE", (code_value,)).fetchone()
    return None


def chat_active_live_session_id(con: sqlite3.Connection) -> int | None:
    row = con.execute("SELECT id FROM live_sessions WHERE status IN ('ao_vivo','aberta') ORDER BY id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def chat_thread_title(product: sqlite3.Row | None = None, order: sqlite3.Row | None = None, origin: str = "geral") -> str:
    if order:
        return f"Pedido {order['order_code'] or ('#' + str(order['id']))}"
    if product:
        return f"{product['code']} — {product['title']}"
    if origin == "live":
        return "Dúvida da live"
    return "Atendimento BRECHORISEE"


def chat_get_or_create_thread(
    con: sqlite3.Connection,
    account: sqlite3.Row | dict[str, Any],
    product_id: int | None = None,
    order_id: int | None = None,
    live_session_id: int | None = None,
    origin: str = "geral",
) -> sqlite3.Row:
    init_chat_schema()
    account_id = int(row_get(account, "id", 0))
    customer_id = int(row_get(account, "customer_id", 0) or 0) or None
    product = con.execute("SELECT * FROM products WHERE id=?", (int(product_id),)).fetchone() if product_id else None
    order = con.execute("SELECT * FROM online_orders WHERE id=?", (int(order_id),)).fetchone() if order_id else None

    query = "SELECT * FROM chat_threads WHERE customer_account_id=? AND status<>'arquivado'"
    params: list[Any] = [account_id]
    if order_id:
        query += " AND order_id=?"
        params.append(int(order_id))
    elif product_id:
        query += " AND product_id=? AND origin=?"
        params.extend([int(product_id), origin or "geral"])
    elif live_session_id:
        query += " AND live_session_id=? AND origin='live'"
        params.append(int(live_session_id))
    else:
        query += " AND product_id IS NULL AND order_id IS NULL AND origin=?"
        params.append(origin or "geral")
    query += " ORDER BY id DESC LIMIT 1"
    existing = con.execute(query, tuple(params)).fetchone()
    if existing:
        return existing

    title = chat_thread_title(product=product, order=order, origin=origin)
    now = now_iso()
    cur = con.execute(
        """
        INSERT INTO chat_threads(customer_account_id, customer_id, product_id, order_id, live_session_id, title, origin, status, priority, last_message_at, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (account_id, customer_id, int(product_id) if product_id else None, int(order_id) if order_id else None, int(live_session_id) if live_session_id else None, title, origin or "geral", "aberto", "normal", now, now, now),
    )
    return con.execute("SELECT * FROM chat_threads WHERE id=?", (int(cur.lastrowid),)).fetchone()


def chat_add_system_context_message(con: sqlite3.Connection, thread: sqlite3.Row, product: sqlite3.Row | None = None, order: sqlite3.Row | None = None, origin: str = "") -> None:
    """Adiciona uma mensagem automática de contexto quando a conversa nasce."""
    exists = con.execute(
        "SELECT 1 FROM chat_messages WHERE thread_id=? AND sender_type='system' LIMIT 1",
        (thread["id"],),
    ).fetchone()
    if exists:
        return
    lines: list[str] = []
    if product:
        lines.append(f"Peça vinculada: {product['code']} — {product['title']} • {money(product['sale_price'])}")
    if order:
        lines.append(f"Pedido vinculado: {order['order_code']} • {money(order['total'])} • {order['status']}")
    if origin == "live":
        lines.append("Origem: cliente veio da live/overlay do Instagram.")
    body = "\n".join(lines).strip()
    if body:
        con.execute(
            "INSERT INTO chat_messages(thread_id, sender_type, sender_name, message_type, body, metadata_json, read_at, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (thread["id"], "system", "Sistema", "context", body, json.dumps({"origin": origin}, ensure_ascii=False), now_iso(), now_iso()),
        )


def chat_insert_message(
    con: sqlite3.Connection,
    thread_id: int,
    sender_type: str,
    sender_id: int | None,
    sender_name: str,
    body: str = "",
    message_type: str = "text",
    attachment_filename: str = "",
    attachment_url: str = "",
    metadata: dict[str, Any] | None = None,
) -> sqlite3.Row:
    init_chat_schema()
    body = chat_clean_text(body, 2500)
    now = now_iso()
    cur = con.execute(
        """
        INSERT INTO chat_messages(thread_id, sender_type, sender_id, sender_name, message_type, body, attachment_filename, attachment_url, metadata_json, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            int(thread_id),
            sender_type,
            int(sender_id) if sender_id else None,
            sender_name,
            message_type or "text",
            body,
            attachment_filename or "",
            attachment_url or "",
            json.dumps(metadata or {}, ensure_ascii=False),
            now,
        ),
    )
    unread_admin = 1 if sender_type == "cliente" else 0
    unread_customer = 1 if sender_type == "admin" else 0
    con.execute(
        """
        UPDATE chat_threads
        SET last_message_at=?, updated_at=?, unread_admin=unread_admin+?, unread_customer=unread_customer+?
        WHERE id=?
        """,
        (now, now, unread_admin, unread_customer, int(thread_id)),
    )
    return con.execute("SELECT * FROM chat_messages WHERE id=?", (int(cur.lastrowid),)).fetchone()


def chat_thread_for_customer(con: sqlite3.Connection, thread_id: int, account_id: int) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM chat_threads WHERE id=? AND customer_account_id=?",
        (int(thread_id), int(account_id)),
    ).fetchone()


def chat_mark_read(con: sqlite3.Connection, thread_id: int, reader: str) -> None:
    now = now_iso()
    if reader == "admin":
        con.execute("UPDATE chat_messages SET read_at=COALESCE(read_at, ?) WHERE thread_id=? AND sender_type='cliente'", (now, int(thread_id)))
        con.execute("UPDATE chat_threads SET unread_admin=0, updated_at=? WHERE id=?", (now, int(thread_id)))
    elif reader == "cliente":
        con.execute("UPDATE chat_messages SET read_at=COALESCE(read_at, ?) WHERE thread_id=? AND sender_type='admin'", (now, int(thread_id)))
        con.execute("UPDATE chat_threads SET unread_customer=0, updated_at=? WHERE id=?", (now, int(thread_id)))


def chat_messages_payload(con: sqlite3.Connection, thread_id: int, after_id: int = 0) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT * FROM chat_messages
        WHERE thread_id=? AND id>?
        ORDER BY id ASC
        LIMIT 200
        """,
        (int(thread_id), int(after_id or 0)),
    ).fetchall()
    payload = []
    for row in rows:
        item = row_to_dict(row)
        item["attachment_url"] = item.get("attachment_url") or chat_public_attachment_url(item.get("attachment_filename"))
        try:
            item["metadata"] = json.loads(item.get("metadata_json") or "{}")
        except Exception:
            item["metadata"] = {}
        payload.append(item)
    return payload


def chat_notify_admin_new_message(thread: sqlite3.Row | dict[str, Any], message: sqlite3.Row | dict[str, Any], customer: sqlite3.Row | dict[str, Any] | None = None, product: sqlite3.Row | dict[str, Any] | None = None) -> None:
    """Alerta opcional no Telegram quando cliente manda mensagem."""
    body = str(row_get(message, "body", "") or "")
    if not body and row_get(message, "attachment_url", ""):
        body = "Enviou um anexo/comprovante."
    customer_name = row_get(customer, "name", "") or f"Cliente #{row_get(thread, 'customer_account_id', '-')}"
    lines = [
        "💬 <b>Nova mensagem no Chat BRECHORISEE</b>",
        f"Cliente: {telegram_html(customer_name)}",
        f"Conversa: #{row_get(thread, 'id', '')} — {telegram_html(row_get(thread, 'title', ''))}",
    ]
    if product:
        lines.append(f"Peça: {telegram_html(row_get(product, 'code', ''))} — {telegram_html(row_get(product, 'title', ''))}")
    lines += ["", telegram_html(body[:700])]
    thread_id_value = int(row_get(thread, "id", 0) or 0)
    lines += [
        "",
        f"Responder pelo Telegram: /responder {thread_id_value} sua mensagem",
        f"Atalho: /r {thread_id_value} sua mensagem",
        f"Painel: {telegram_public_url('/atendimento/' + str(thread_id_value))}",
    ]
    telegram_notify_admin("\n".join(lines), related_type="chat_thread", related_id=thread_id_value)



def telegram_chat_last_threads(con: sqlite3.Connection, limit: int = 8) -> str:
    """Lista conversas recentes para responder pelo Telegram."""
    init_chat_schema()
    rows = con.execute(
        """
        SELECT t.id, t.title, t.status, t.unread_admin, t.last_message_at,
               ca.name AS customer_name, ca.phone AS customer_phone,
               (
                   SELECT body FROM chat_messages m
                   WHERE m.thread_id=t.id
                   ORDER BY m.id DESC
                   LIMIT 1
               ) AS last_body
        FROM chat_threads t
        LEFT JOIN customer_accounts ca ON ca.id=t.customer_account_id
        ORDER BY COALESCE(t.last_message_at, t.created_at) DESC, t.id DESC
        LIMIT ?
        """,
        (int(limit or 8),),
    ).fetchall()
    if not rows:
        return "Nenhuma conversa encontrada no Chat BRECHORISEE."
    lines = ["💬 <b>Últimas conversas do Chat BRECHORISEE</b>", ""]
    for row in rows:
        name = row["customer_name"] or f"Cliente #{row['id']}"
        unread = int(row["unread_admin"] or 0)
        last = (row["last_body"] or "").replace("\n", " ")[:90]
        badge = f" • {unread} nova(s)" if unread else ""
        lines.append(f"#{row['id']} — {telegram_html(name)} — {telegram_html(row['status'])}{badge}")
        if last:
            lines.append(f"   {telegram_html(last)}")
        lines.append(f"   Responder: /responder {row['id']} sua mensagem")
    return "\n".join(lines).strip()


def telegram_reply_to_chat_thread(
    con: sqlite3.Connection,
    thread_id: int,
    reply_text: str,
    chat_id: str = "",
    username: str = "",
) -> str:
    """Grava uma resposta da atendente do Telegram dentro do chat da cliente."""
    init_chat_schema()
    message_text = chat_clean_text(reply_text, 2500)
    if not message_text:
        return "Mensagem vazia. Use: /responder ID mensagem"
    thread = con.execute("SELECT * FROM chat_threads WHERE id=?", (int(thread_id),)).fetchone()
    if not thread:
        return f"Conversa #{int(thread_id)} não encontrada."
    admin_name = "Atendimento BRECHORISEE"
    if username:
        admin_name = f"Atendimento BRECHORISEE via Telegram"
    if not chat_thread_bot_is_paused(thread):
        chat_set_bot_mode(con, int(thread_id), "humano", admin=None, reason="Resposta enviada pelo Telegram.", insert_notice=False)
        thread = con.execute("SELECT * FROM chat_threads WHERE id=?", (int(thread_id),)).fetchone()
    message = chat_insert_message(
        con,
        int(thread_id),
        "admin",
        None,
        admin_name,
        body=message_text,
        message_type="text",
        metadata={
            "source": "telegram",
            "telegram_chat_id": str(chat_id or ""),
            "telegram_username": str(username or ""),
        },
    )
    con.execute(
        "UPDATE chat_threads SET status='aberto', updated_at=? WHERE id=?",
        (now_iso(), int(thread_id)),
    )
    customer = con.execute(
        """
        SELECT ca.name, ca.phone
        FROM chat_threads t
        LEFT JOIN customer_accounts ca ON ca.id=t.customer_account_id
        WHERE t.id=?
        """,
        (int(thread_id),),
    ).fetchone()
    customer_name = (customer["name"] if customer else "") or f"Cliente #{int(thread_id)}"
    return "\n".join([
        f"✅ Resposta enviada para {telegram_html(customer_name)} no Chat BRECHORISEE.",
        f"Conversa: #{int(thread_id)}",
        f"Mensagem: {telegram_html(message_text[:700])}",
        f"Painel: {telegram_public_url('/atendimento/' + str(int(thread_id)))}",
    ])


def telegram_try_chat_command(con: sqlite3.Connection, raw: str, low: str, chat_id: str = "", username: str = "") -> str | None:
    """Comandos do Telegram para conversar com cliente pelo Chat BRECHORISEE."""
    clean = (raw or "").strip()
    if not clean:
        return None
    if low in {"/chats", "chats", "/conversas", "conversas", "/chat", "chat"}:
        return telegram_chat_last_threads(con)

    match = re.match(r"^/?(?:responder|resposta|reply|r)\s+#?(\d+)\s+([\s\S]+)$", clean, flags=re.IGNORECASE)
    if match:
        return telegram_reply_to_chat_thread(
            con,
            int(match.group(1)),
            match.group(2).strip(),
            chat_id=chat_id,
            username=username,
        )

    if re.match(r"^/?(?:responder|resposta|reply|r)(?:\s+.*)?$", clean, flags=re.IGNORECASE):
        return "Use assim: /responder ID mensagem\nExemplo: /responder 12 Oi Amanda, vou verificar essa blusa para você."

    return None


def chat_thread_bot_is_paused(thread: sqlite3.Row | dict[str, Any] | None) -> bool:
    if not thread:
        return False
    if str(row_get(thread, "bot_mode", "auto") or "auto").lower() in {"humano", "manual", "pausado"}:
        return True
    try:
        return int(row_get(thread, "bot_paused", 0) or 0) == 1
    except Exception:
        return False


def chat_set_bot_mode(
    con: sqlite3.Connection,
    thread_id: int,
    mode: str,
    admin: sqlite3.Row | dict[str, Any] | None = None,
    reason: str = "",
    insert_notice: bool = True,
) -> sqlite3.Row | None:
    """Pausa ou devolve uma conversa para o Bot BRECHORISEE sem perder histórico."""
    init_chat_schema()
    clean_mode = bot_risee_normalize(mode).replace(" ", "_")
    now = now_iso()
    admin_id = int(row_get(admin, "id", 0) or 0) if admin else None
    admin_name = chat_sender_name("admin", admin)
    if clean_mode in {"humano", "manual", "pausar", "pausado", "assumir"}:
        con.execute(
            """
            UPDATE chat_threads
            SET bot_mode='humano', bot_paused=1, bot_paused_reason=?, assigned_admin_id=?,
                assigned_admin_name=?, human_takeover_at=COALESCE(human_takeover_at, ?), updated_at=?
            WHERE id=?
            """,
            (chat_clean_text(reason or "Atendimento humano assumiu a conversa.", 300), admin_id, admin_name, now, now, int(thread_id)),
        )
        if insert_notice:
            chat_insert_message(con, int(thread_id), "system", None, "Sistema", body="Atendimento humano assumiu esta conversa. Bot BRECHORISEE pausado aqui.", message_type="system", metadata={"feature": "bot_handoff", "mode": "humano"})
    elif clean_mode in {"auto", "automatico", "automático", "bot", "continuar", "devolver", "devolver_bot"}:
        con.execute(
            """
            UPDATE chat_threads
            SET bot_mode='auto', bot_paused=0, bot_paused_reason='', bot_resumed_at=?, updated_at=?
            WHERE id=?
            """,
            (now, now, int(thread_id)),
        )
        if insert_notice:
            chat_insert_message(con, int(thread_id), "system", None, "Sistema", body="Bot BRECHORISEE voltou a acompanhar esta conversa. A atendente pode assumir novamente quando quiser.", message_type="system", metadata={"feature": "bot_handoff", "mode": "auto"})
    else:
        return None
    return con.execute("SELECT * FROM chat_threads WHERE id=?", (int(thread_id),)).fetchone()


@app.get("/cliente/chat", response_class=HTMLResponse)
def customer_chat_page(
    request: Request,
    thread_id: int | None = None,
    produto: str = "",
    product_id: int | None = None,
    order_id: int | None = None,
    origem: str = "geral",
    live: int = 0,
) -> Response:
    init_chat_schema()
    account = customer_from_request(request)
    if not account:
        next_url = str(request.url.path)
        if request.url.query:
            next_url += "?" + str(request.url.query)
        return RedirectResponse(url=f"/cliente?next={quote_plus(next_url)}", status_code=303)

    selected_thread = None
    with get_db() as con:
        product = chat_find_product(con, product_id=product_id, produto=produto)
        live_session_id = chat_active_live_session_id(con) if live or origem == "live" else None
        if product or order_id or live_session_id:
            selected_thread = chat_get_or_create_thread(
                con,
                account,
                product_id=int(product["id"]) if product else None,
                order_id=int(order_id) if order_id else None,
                live_session_id=live_session_id,
                origin="live" if (live or origem == "live") else (origem or "geral"),
            )
            order = con.execute("SELECT * FROM online_orders WHERE id=?", (int(order_id),)).fetchone() if order_id else None
            chat_add_system_context_message(con, selected_thread, product=product, order=order, origin="live" if (live or origem == "live") else origem)
        elif thread_id:
            selected_thread = chat_thread_for_customer(con, int(thread_id), int(account["id"]))

        threads = con.execute(
            """
            SELECT t.*, p.code, p.title AS product_title, p.sale_price, p.size, p.image_filename,
                   o.order_code, o.status AS order_status, o.total AS order_total
            FROM chat_threads t
            LEFT JOIN products p ON p.id=t.product_id
            LEFT JOIN online_orders o ON o.id=t.order_id
            WHERE t.customer_account_id=? AND t.status<>'arquivado'
            ORDER BY COALESCE(t.last_message_at, t.created_at) DESC, t.id DESC
            LIMIT 60
            """,
            (account["id"],),
        ).fetchall()
        if not selected_thread and threads:
            selected_thread = con.execute("SELECT * FROM chat_threads WHERE id=?", (int(threads[0]["id"]),)).fetchone()
        if selected_thread:
            chat_mark_read(con, int(selected_thread["id"]), "cliente")
            selected_product, selected_order, _ = chat_get_context_rows(con, selected_thread)
            messages = chat_messages_payload(con, int(selected_thread["id"]))
        else:
            selected_product, selected_order, messages = None, None, []

    return templates.TemplateResponse(
        "customer_chat.html",
        {
            "request": request,
            "settings": get_store_settings(),
            "account": account,
            "threads": threads,
            "selected_thread": selected_thread,
            "selected_product": selected_product,
            "selected_order": selected_order,
            "messages": messages,
            "public_mode": True,
        },
    )


@app.get("/cliente/chat/{thread_id}", response_class=HTMLResponse)
def customer_chat_thread_page(request: Request, thread_id: int) -> Response:
    return customer_chat_page(request, thread_id=int(thread_id))


@app.get("/api/chat/cliente/threads")
def api_customer_chat_threads(request: Request) -> JSONResponse:
    init_chat_schema()
    account = customer_from_request(request)
    if not account:
        return JSONResponse({"ok": False, "message": "Login da cliente obrigatório."}, status_code=401)
    with get_db() as con:
        rows = con.execute(
            """
            SELECT t.*, p.code, p.title AS product_title, p.sale_price, p.size, p.image_filename,
                   o.order_code, o.status AS order_status, o.total AS order_total
            FROM chat_threads t
            LEFT JOIN products p ON p.id=t.product_id
            LEFT JOIN online_orders o ON o.id=t.order_id
            WHERE t.customer_account_id=? AND t.status<>'arquivado'
            ORDER BY COALESCE(t.last_message_at, t.created_at) DESC, t.id DESC
            LIMIT 80
            """,
            (account["id"],),
        ).fetchall()
    return JSONResponse({"ok": True, "threads": [row_to_dict(r) for r in rows]})


@app.get("/api/chat/cliente/{thread_id}/messages")
def api_customer_chat_messages(request: Request, thread_id: int, after_id: int = 0) -> JSONResponse:
    init_chat_schema()
    account = customer_from_request(request)
    if not account:
        return JSONResponse({"ok": False, "message": "Login da cliente obrigatório."}, status_code=401)
    with get_db() as con:
        thread = chat_thread_for_customer(con, int(thread_id), int(account["id"]))
        if not thread:
            return JSONResponse({"ok": False, "message": "Conversa não encontrada."}, status_code=404)
        chat_mark_read(con, int(thread_id), "cliente")
        product, order, customer = chat_get_context_rows(con, thread)
        return JSONResponse({
            "ok": True,
            "thread": chat_format_thread_row(thread, product=product, order=order, customer=customer),
            "messages": chat_messages_payload(con, int(thread_id), after_id=after_id),
        })


@app.post("/api/chat/cliente/{thread_id}/messages")
async def api_customer_chat_send(
    request: Request,
    thread_id: int,
    body: str = Form(""),
    attachment: UploadFile | None = File(None),
) -> JSONResponse:
    init_chat_schema()
    account = customer_from_request(request)
    if not account:
        return JSONResponse({"ok": False, "message": "Login da cliente obrigatório."}, status_code=401)
    attachment_filename, attachment_url, attachment_type = await save_chat_attachment(attachment)
    body = chat_clean_text(body, 2500)
    if not body and not attachment_url:
        return JSONResponse({"ok": False, "message": "Mensagem vazia."}, status_code=400)
    with get_db() as con:
        thread = chat_thread_for_customer(con, int(thread_id), int(account["id"]))
        if not thread:
            return JSONResponse({"ok": False, "message": "Conversa não encontrada."}, status_code=404)
        message = chat_insert_message(
            con,
            int(thread_id),
            "cliente",
            int(account["id"]),
            chat_sender_name("cliente", account),
            body=body,
            message_type=attachment_type if attachment_url else "text",
            attachment_filename=attachment_filename,
            attachment_url=attachment_url,
            metadata={"user_agent": request.headers.get("user-agent", "")[:180]},
        )
        product, order, customer = chat_get_context_rows(con, thread)
        payload = row_to_dict(message)
        payload["attachment_url"] = payload.get("attachment_url") or chat_public_attachment_url(payload.get("attachment_filename"))
        bot_reply = bot_risee_maybe_reply(con, thread, body, account=account, product=product, order=order, attachment_present=bool(attachment_url))
        notify_thread = row_to_dict(thread)
        notify_message = dict(payload)
        notify_customer = row_to_dict(customer) if customer else row_to_dict(account)
        notify_product = row_to_dict(product) if product else None
    chat_notify_admin_new_message(notify_thread, notify_message, customer=notify_customer, product=notify_product)
    return JSONResponse({"ok": True, "message": payload, "bot_reply": bot_reply})


@app.post("/api/chat/cliente/start")
def api_customer_chat_start(
    request: Request,
    product_id: int = Form(0),
    produto: str = Form(""),
    order_id: int = Form(0),
    origin: str = Form("geral"),
    message: str = Form(""),
) -> JSONResponse:
    init_chat_schema()
    account = customer_from_request(request)
    if not account:
        return JSONResponse({"ok": False, "message": "Login da cliente obrigatório."}, status_code=401)
    with get_db() as con:
        product = chat_find_product(con, product_id=int(product_id or 0) or None, produto=produto)
        order = con.execute("SELECT * FROM online_orders WHERE id=?", (int(order_id),)).fetchone() if order_id else None
        live_session_id = chat_active_live_session_id(con) if origin == "live" else None
        thread = chat_get_or_create_thread(
            con,
            account,
            product_id=int(product["id"]) if product else None,
            order_id=int(order_id) if order_id else None,
            live_session_id=live_session_id,
            origin=origin or "geral",
        )
        chat_add_system_context_message(con, thread, product=product, order=order, origin=origin)
        notify_thread = row_to_dict(thread)
        notify_message = None
        notify_product = row_to_dict(product) if product else None
        notify_customer = row_to_dict(account)
        if message.strip():
            msg = chat_insert_message(con, int(thread["id"]), "cliente", int(account["id"]), chat_sender_name("cliente", account), body=message, metadata={"origin": origin})
            bot_risee_maybe_reply(con, thread, message, account=account, product=product, order=order)
            notify_message = row_to_dict(msg)
    if notify_message:
        chat_notify_admin_new_message(notify_thread, notify_message, customer=notify_customer, product=notify_product)
    return JSONResponse({"ok": True, "thread_id": int(thread["id"]), "url": f"/cliente/chat/{int(thread['id'])}"})


@app.get("/atendimento", response_class=HTMLResponse)
def admin_chat_page(request: Request, status: str = "aberto", q: str = "", thread_id: int | None = None) -> Response:
    init_chat_schema()
    with get_db() as con:
        params: list[Any] = []
        where = "1=1"
        if status and status != "todos":
            where += " AND t.status=?"
            params.append(status)
        if q.strip():
            like = f"%{q.strip()}%"
            where += " AND (t.title LIKE ? OR ca.name LIKE ? OR ca.phone LIKE ? OR p.code LIKE ? OR p.title LIKE ? OR o.order_code LIKE ?)"
            params.extend([like, like, like, like, like, like])
        threads = con.execute(
            f"""
            SELECT t.*, ca.name AS customer_name, ca.phone AS customer_phone, ca.instagram AS customer_instagram,
                   p.code, p.title AS product_title, p.sale_price, p.size, p.image_filename,
                   o.order_code, o.status AS order_status, o.total AS order_total
            FROM chat_threads t
            LEFT JOIN customer_accounts ca ON ca.id=t.customer_account_id
            LEFT JOIN products p ON p.id=t.product_id
            LEFT JOIN online_orders o ON o.id=t.order_id
            WHERE {where}
            ORDER BY t.unread_admin DESC, COALESCE(t.last_message_at, t.created_at) DESC, t.id DESC
            LIMIT 120
            """,
            tuple(params),
        ).fetchall()
        selected_thread = None
        if thread_id:
            selected_thread = con.execute("SELECT * FROM chat_threads WHERE id=?", (int(thread_id),)).fetchone()
        elif threads:
            selected_thread = con.execute("SELECT * FROM chat_threads WHERE id=?", (int(threads[0]["id"]),)).fetchone()
        if selected_thread:
            chat_mark_read(con, int(selected_thread["id"]), "admin")
            selected_product, selected_order, selected_customer = chat_get_context_rows(con, selected_thread)
            messages = chat_messages_payload(con, int(selected_thread["id"]))
        else:
            selected_product, selected_order, selected_customer, messages = None, None, None, []
        quick_replies = con.execute("SELECT * FROM chat_quick_replies WHERE active=1 ORDER BY category, usage_count DESC, id LIMIT 60").fetchall()
    return templates.TemplateResponse(
        "admin_chat.html",
        {
            "request": request,
            "active": "atendimento",
            "threads": threads,
            "selected_thread": selected_thread,
            "selected_product": selected_product,
            "selected_order": selected_order,
            "selected_customer": selected_customer,
            "messages": messages,
            "quick_replies": quick_replies,
            "status": status,
            "q": q,
        },
    )


@app.get("/atendimento/{thread_id}", response_class=HTMLResponse)
def admin_chat_thread_page(request: Request, thread_id: int) -> Response:
    return admin_chat_page(request, thread_id=int(thread_id))


@app.get("/api/chat/admin/threads")
def api_admin_chat_threads(request: Request, status: str = "aberto", q: str = "") -> JSONResponse:
    init_chat_schema()
    with get_db() as con:
        params: list[Any] = []
        where = "1=1"
        if status and status != "todos":
            where += " AND t.status=?"
            params.append(status)
        if q.strip():
            like = f"%{q.strip()}%"
            where += " AND (t.title LIKE ? OR ca.name LIKE ? OR ca.phone LIKE ? OR p.code LIKE ? OR p.title LIKE ? OR o.order_code LIKE ?)"
            params.extend([like, like, like, like, like, like])
        rows = con.execute(
            f"""
            SELECT t.*, ca.name AS customer_name, ca.phone AS customer_phone, ca.instagram AS customer_instagram,
                   p.code, p.title AS product_title, p.sale_price, p.size, p.image_filename,
                   o.order_code, o.status AS order_status, o.total AS order_total
            FROM chat_threads t
            LEFT JOIN customer_accounts ca ON ca.id=t.customer_account_id
            LEFT JOIN products p ON p.id=t.product_id
            LEFT JOIN online_orders o ON o.id=t.order_id
            WHERE {where}
            ORDER BY t.unread_admin DESC, COALESCE(t.last_message_at, t.created_at) DESC, t.id DESC
            LIMIT 120
            """,
            tuple(params),
        ).fetchall()
    return JSONResponse({"ok": True, "threads": [row_to_dict(r) for r in rows]})


@app.get("/api/chat/admin/{thread_id}/messages")
def api_admin_chat_messages(request: Request, thread_id: int, after_id: int = 0) -> JSONResponse:
    init_chat_schema()
    with get_db() as con:
        thread = con.execute("SELECT * FROM chat_threads WHERE id=?", (int(thread_id),)).fetchone()
        if not thread:
            return JSONResponse({"ok": False, "message": "Conversa não encontrada."}, status_code=404)
        chat_mark_read(con, int(thread_id), "admin")
        product, order, customer = chat_get_context_rows(con, thread)
        return JSONResponse({
            "ok": True,
            "thread": chat_format_thread_row(thread, product=product, order=order, customer=customer),
            "messages": chat_messages_payload(con, int(thread_id), after_id=after_id),
        })


@app.post("/api/chat/admin/{thread_id}/messages")
async def api_admin_chat_send(
    request: Request,
    thread_id: int,
    body: str = Form(""),
    quick_reply_id: int = Form(0),
    attachment: UploadFile | None = File(None),
) -> JSONResponse:
    init_chat_schema()
    admin = admin_from_request(request)
    sender_name = chat_sender_name("admin", admin)
    attachment_filename, attachment_url, attachment_type = await save_chat_attachment(attachment)
    body = chat_clean_text(body, 2500)
    with get_db() as con:
        if quick_reply_id and not body:
            reply = con.execute("SELECT * FROM chat_quick_replies WHERE id=? AND active=1", (int(quick_reply_id),)).fetchone()
            if reply:
                body = reply["body"]
                con.execute("UPDATE chat_quick_replies SET usage_count=usage_count+1, updated_at=? WHERE id=?", (now_iso(), int(quick_reply_id)))
        if not body and not attachment_url:
            return JSONResponse({"ok": False, "message": "Mensagem vazia."}, status_code=400)
        thread = con.execute("SELECT * FROM chat_threads WHERE id=?", (int(thread_id),)).fetchone()
        if not thread:
            return JSONResponse({"ok": False, "message": "Conversa não encontrada."}, status_code=404)
        # Quando uma atendente responde, o bot pausa nesta conversa para não disputar atendimento.
        if not chat_thread_bot_is_paused(thread):
            chat_set_bot_mode(con, int(thread_id), "humano", admin=admin, reason="Admin entrou no atendimento.", insert_notice=False)
            thread = con.execute("SELECT * FROM chat_threads WHERE id=?", (int(thread_id),)).fetchone()
        message = chat_insert_message(
            con,
            int(thread_id),
            "admin",
            int(admin["id"]) if admin else None,
            sender_name,
            body=body,
            message_type=attachment_type if attachment_url else "text",
            attachment_filename=attachment_filename,
            attachment_url=attachment_url,
            metadata={"user_agent": request.headers.get("user-agent", "")[:180]},
        )
        payload = row_to_dict(message)
        payload["attachment_url"] = payload.get("attachment_url") or chat_public_attachment_url(payload.get("attachment_filename"))
    return JSONResponse({"ok": True, "message": payload})


@app.post("/api/chat/admin/{thread_id}/status")
def api_admin_chat_status(request: Request, thread_id: int, status: str = Form("aberto")) -> JSONResponse:
    init_chat_schema()
    status_clean = (status or "aberto").strip().lower()
    if status_clean not in {"aberto", "pendente", "resolvido", "arquivado"}:
        return JSONResponse({"ok": False, "message": "Status inválido."}, status_code=400)
    with get_db() as con:
        con.execute("UPDATE chat_threads SET status=?, updated_at=? WHERE id=?", (status_clean, now_iso(), int(thread_id)))
    return JSONResponse({"ok": True, "status": status_clean})


@app.post("/api/chat/admin/{thread_id}/bot-mode")
def api_admin_chat_bot_mode(request: Request, thread_id: int, mode: str = Form("auto"), reason: str = Form("")) -> JSONResponse:
    init_chat_schema()
    admin = admin_from_request(request)
    with get_db() as con:
        thread = con.execute("SELECT * FROM chat_threads WHERE id=?", (int(thread_id),)).fetchone()
        if not thread:
            return JSONResponse({"ok": False, "message": "Conversa não encontrada."}, status_code=404)
        updated = chat_set_bot_mode(con, int(thread_id), mode, admin=admin, reason=reason, insert_notice=True)
        if not updated:
            return JSONResponse({"ok": False, "message": "Modo inválido. Use 'humano' ou 'auto'."}, status_code=400)
        product, order, customer = chat_get_context_rows(con, updated)
        payload = chat_format_thread_row(updated, product=product, order=order, customer=customer)
    return JSONResponse({"ok": True, "thread": payload, "bot_mode": payload.get("bot_mode"), "bot_paused": payload.get("bot_paused")})


@app.post("/api/chat/admin/{thread_id}/assumir")
def api_admin_chat_assumir(request: Request, thread_id: int) -> JSONResponse:
    return api_admin_chat_bot_mode(request, thread_id, mode="humano", reason="Atendente assumiu manualmente.")


@app.post("/api/chat/admin/{thread_id}/devolver-bot")
def api_admin_chat_devolver_bot(request: Request, thread_id: int) -> JSONResponse:
    return api_admin_chat_bot_mode(request, thread_id, mode="auto", reason="Atendimento devolvido ao Bot BRECHORISEE.")


@app.get("/api/chat/admin/quick-replies")
def api_admin_chat_quick_replies(request: Request) -> JSONResponse:
    init_chat_schema()
    with get_db() as con:
        rows = con.execute("SELECT * FROM chat_quick_replies WHERE active=1 ORDER BY category, usage_count DESC, id").fetchall()
    return JSONResponse({"ok": True, "quick_replies": [row_to_dict(r) for r in rows]})




@app.get("/api/painel-notificacoes")
def api_painel_notificacoes_491(request: Request) -> JSONResponse:
    """Resumo leve para bolinhas/contadores no topo do Cliente e Admin.

    Retorna sempre OK, mesmo se alguma tabela ainda não existir, para não quebrar tela.
    """
    payload: dict[str, Any] = {
        "ok": True,
        "messages": 0,
        "chat": 0,
        "live": 0,
        "pieces_new": 0,
        "reservas": 0,
        "admin_chat": 0,
        "admin_pending": 0,
    }
    account = customer_from_request(request)
    admin = admin_from_request(request)
    cutoff = (datetime.now() - timedelta(hours=48)).isoformat(timespec="seconds")
    with get_db() as con:
        try:
            live_count = con.execute("SELECT COUNT(*) FROM live_sessions WHERE status='ao_vivo'").fetchone()[0]
            payload["live"] = int(live_count or 0)
        except Exception:
            payload["live"] = 0
        try:
            # Usa created_at quando existir; se a coluna/status for diferente, falha de forma segura.
            pieces_count = con.execute(
                "SELECT COUNT(*) FROM products WHERE COALESCE(created_at,'')>=? AND COALESCE(status,'disponivel') NOT IN ('vendido','excluido')",
                (cutoff,),
            ).fetchone()[0]
            payload["pieces_new"] = int(pieces_count or 0)
        except Exception:
            payload["pieces_new"] = 0
        if account:
            try:
                payload["messages"] = int(customer_unread_notifications_count(int(account["id"])) or 0)
            except Exception:
                payload["messages"] = 0
            try:
                chat_count = con.execute(
                    "SELECT COALESCE(SUM(unread_customer),0) FROM chat_threads WHERE customer_account_id=? AND status<>'arquivado'",
                    (int(account["id"]),),
                ).fetchone()[0]
                payload["chat"] = int(chat_count or 0)
            except Exception:
                payload["chat"] = 0
        if admin:
            try:
                admin_chat = con.execute(
                    "SELECT COALESCE(SUM(unread_admin),0) FROM chat_threads WHERE status<>'arquivado'"
                ).fetchone()[0]
                payload["admin_chat"] = int(admin_chat or 0)
            except Exception:
                payload["admin_chat"] = 0
            try:
                pending = con.execute(
                    "SELECT COUNT(*) FROM chat_threads WHERE status IN ('aberto','pendente')"
                ).fetchone()[0]
                payload["admin_pending"] = int(pending or 0)
            except Exception:
                payload["admin_pending"] = 0
            try:
                reservas = con.execute(
                    "SELECT COUNT(*) FROM reservations WHERE COALESCE(status,'') IN ('pendente','reservado','aguardando')"
                ).fetchone()[0]
                payload["reservas"] = int(reservas or 0)
            except Exception:
                payload["reservas"] = 0
    payload["total"] = int(payload.get("messages", 0)) + int(payload.get("chat", 0)) + int(payload.get("live", 0)) + int(payload.get("pieces_new", 0))
    payload["admin_total"] = int(payload.get("admin_chat", 0)) + int(payload.get("admin_pending", 0)) + int(payload.get("reservas", 0))
    return JSONResponse(payload)


# =============================================================================
# BOT RISEE - ATENDIMENTO AUTOMATICO COM MAIS DE 50 PERGUNTAS E RESPOSTAS
# =============================================================================

BOT_RISEE_FAQS: list[tuple[str, str, str, str, str]] = [('live_001', 'live', 'Qual peça está aparecendo agora?', 'A peça atual da live é {product_title}. Código: {product_code}. Tamanho: {product_size}. Valor: {product_price}.', 'peca atual agora live mostrando qual codigo'), ('live_002', 'live', 'Quanto custa a peça da live?', 'A peça atual está por {product_price}. Se quiser, posso te orientar para reservar agora.', 'preco custa valor quanto live atual'), ('live_003', 'live', 'Qual é o tamanho da peça da live?', 'A peça atual é tamanho {product_size}. Também posso te informar medidas se estiverem cadastradas.', 'tamanho tam numero medidas veste live'), ('live_004', 'live', 'A peça da live está disponível?', 'Status da peça atual: {product_status}. Se aparecer disponível, você pode reservar pelo botão da live.', 'disponivel ainda tem vendeu reservado status live'), ('live_005', 'live', 'Como reservar a peça que está na live?', 'Toque em Reservar no overlay/app. A reserva fica registrada no BRECHORISEE e o atendimento acompanha por aqui.', 'reservar reserva quero pegar live como faço'), ('live_006', 'live', 'Entrei na fila, o que acontece?', 'A fila guarda sua posição. Se a reserva principal não for confirmada, a próxima pessoa é chamada automaticamente.', 'fila espera posicao proxima reserva'), ('live_007', 'live', 'Perdi a peça que passou, consigo ver depois?', 'Sim. Depois da live, as peças mostradas ficam na repescagem quando ainda estão disponíveis.', 'perdi passou repescagem ver depois sobrou'), ('live_008', 'live', 'A peça voltou na live?', 'Quando uma peça reaparece, o sistema atualiza a peça atual e mantém o histórico da live.', 'voltou reapresentou apareceu novamente live'), ('live_009', 'live', 'Posso comprar mais de uma peça da live?', 'Sim. Você pode reservar mais de uma peça e combinar tudo no mesmo atendimento/pedido quando possível.', 'comprar varias peças mais de uma juntar pedido'), ('live_010', 'live', 'A miniatura do overlay é a peça certa?', 'A miniatura mostra a peça reconhecida pelo sistema. Confira foto, preço e tamanho antes de reservar.', 'miniatura overlay foto certa peca reconhecida'), ('reserva_001', 'reserva', 'Quero reservar essa peça.', 'Perfeito! Para garantir, toque em Reservar. A reserva só fica segura quando aparece confirmada no sistema.', 'quero reservar fica pra mim separa guarda'), ('reserva_002', 'reserva', 'Por quanto tempo a reserva fica válida?', 'A reserva fica válida pelo prazo definido pela loja. Se precisar de mais tempo, chamo a atendente para confirmar.', 'tempo reserva prazo segura quantos minutos'), ('reserva_003', 'reserva', 'Minha reserva está confirmada?', 'Vou verificar pelo seu atendimento/pedido. Se estiver confirmada, ela aparece com status reservado ou aguardando pagamento.', 'minha reserva confirmada status'), ('reserva_004', 'reserva', 'Posso cancelar uma reserva?', 'Pode sim. Me avise aqui no chat para liberarmos a peça para outra cliente.', 'cancelar reserva desistir liberar'), ('reserva_005', 'reserva', 'Posso trocar a peça reservada?', 'Você pode pedir troca antes da confirmação final. Vou chamar a atendente se precisar ajustar sua reserva.', 'trocar peça reservada mudar outra'), ('reserva_006', 'reserva', 'A peça já foi vendida?', 'Status atual: {product_status}. Se estiver vendida, posso te ajudar a procurar uma parecida.', 'vendida vendeu acabou indisponivel'), ('reserva_007', 'reserva', 'Estou na fila de espera?', 'Se você entrou depois da primeira reserva, o sistema registra sua posição na fila da peça.', 'fila espera estou posicao'), ('reserva_008', 'reserva', 'Como sei que fui a primeira?', 'A reserva principal aparece primeiro no sistema. Quando confirmada, você recebe o status no app/chat.', 'primeira primeiro lugar fila reserva'), ('pagamento_001', 'pagamento', 'Aceita Pix?', 'Sim, aceitamos Pix. Após reservar, envie o comprovante por aqui para conferência.', 'pix aceita pagamento'), ('pagamento_002', 'pagamento', 'Qual é a chave Pix?', 'A chave Pix é enviada no atendimento/pedido pela loja. Vou chamar a atendente se ela ainda não apareceu para você.', 'chave pix qual enviar'), ('pagamento_003', 'pagamento', 'Enviei o comprovante.', 'Recebi sua mensagem. Se o comprovante estiver anexado, a equipe confere e confirma seu pedido.', 'comprovante enviei mandei pagamento'), ('pagamento_004', 'pagamento', 'Posso pagar na retirada?', 'Isso depende da regra da loja para a peça/pedido. Vou chamar a atendente para confirmar essa opção.', 'pagar retirada pagamento retirar'), ('pagamento_005', 'pagamento', 'Aceita cartão?', 'A loja pode informar as opções disponíveis no atendimento. Vou chamar a atendente se precisar combinar cartão.', 'cartao credito debito aceita'), ('pagamento_006', 'pagamento', 'Meu pagamento foi aprovado?', 'Vou verificar o status do pedido. Quando aprovado, o pedido muda para confirmado/separado.', 'pagamento aprovado confirmou status'), ('pagamento_007', 'pagamento', 'Posso dividir o pagamento?', 'Para parcelamento ou divisão, a atendente precisa confirmar as condições da loja.', 'dividir parcelar pagamento'), ('pagamento_008', 'pagamento', 'Tenho desconto pagando no Pix?', 'Promoções e descontos dependem da campanha da loja. Posso chamar a atendente para avaliar.', 'desconto pix promoção valor menor'), ('entrega_001', 'entrega', 'Faz entrega?', 'Sim, a loja pode combinar entrega conforme região. Envie seu endereço completo para cálculo/combinação.', 'entrega entregar delivery'), ('entrega_002', 'entrega', 'Qual valor da entrega?', 'O valor depende do endereço e da forma de envio. Envie seu CEP/endereço para a equipe calcular.', 'valor entrega taxa frete cep'), ('entrega_003', 'entrega', 'Posso retirar no local?', 'Pode combinar retirada com a loja. A atendente confirma endereço, dia e horário disponíveis.', 'retirar retirada local buscar'), ('entrega_004', 'entrega', 'Qual o prazo de entrega?', 'O prazo depende da região e da forma de envio. A equipe confirma depois do endereço/pagamento.', 'prazo entrega quando chega'), ('entrega_005', 'entrega', 'Vocês enviam pelo correio?', 'A loja pode informar se o envio pelos Correios/transportadora está disponível para sua região.', 'correio sedex pac transportadora envio'), ('entrega_006', 'entrega', 'Como mando meu endereço?', 'Pode enviar aqui no chat: nome, rua, número, bairro, cidade, CEP e ponto de referência.', 'endereco mandar enviar dados'), ('entrega_007', 'entrega', 'Posso mudar o endereço?', 'Pode solicitar aqui. Se o pedido ainda não saiu, a equipe atualiza o endereço.', 'mudar endereco trocar endereço'), ('entrega_008', 'entrega', 'Meu pedido saiu para entrega?', 'Vou verificar o status do pedido. Quando sair, o status aparece como em entrega/enviado.', 'saiu entrega enviado rastreio'), ('produto_001', 'produto', 'Tem mais fotos dessa peça?', 'Se houver fotos extras, a atendente pode enviar por aqui. Também posso chamar alguém para te ajudar.', 'mais fotos foto detalhe'), ('produto_002', 'produto', 'Quais são as medidas?', 'Medidas cadastradas: {product_measurements}. Se não estiverem cadastradas, posso pedir para a equipe medir.', 'medidas busto cintura comprimento largura'), ('produto_003', 'produto', 'Qual o estado da peça?', 'Estado cadastrado: {product_condition}. Se precisar, a atendente pode enviar detalhes extras.', 'estado condição conservada defeito'), ('produto_004', 'produto', 'A peça tem defeito?', 'Se houver observação cadastrada, ela aparece na descrição. Posso chamar a atendente para confirmar detalhes.', 'defeito mancha avaria rasgo bolinha'), ('produto_005', 'produto', 'Qual a cor real?', 'Cor cadastrada: {product_color}. A cor pode variar pela luz da live/foto, então confira pela miniatura e pergunte se tiver dúvida.', 'cor real qual tom'), ('produto_006', 'produto', 'Qual a marca?', 'Marca cadastrada: {product_brand}. Se não houver marca informada, a peça pode estar sem etiqueta.', 'marca etiqueta fabricante'), ('produto_007', 'produto', 'Essa peça veste qual numeração?', 'Tamanho cadastrado: {product_size}. Para melhor segurança, confira também as medidas.', 'veste numeração manequim tamanho'), ('produto_008', 'produto', 'Tem peça parecida?', 'Posso chamar a atendente para indicar peças parecidas no catálogo ou na repescagem da live.', 'parecida semelhante outra igual'), ('produto_009', 'produto', 'Essa peça combina com o quê?', 'Posso sugerir combinações com peças neutras ou chamar a atendente para montar um look para você.', 'combina look usar com que'), ('produto_010', 'produto', 'A peça é nova ou usada?', 'Condição cadastrada: {product_condition}. Como brechó, cada peça é única e revisada antes da venda.', 'nova usada brecho condição'), ('pedido_001', 'pedido', 'Qual o status do meu pedido?', 'Status do pedido: {order_status}. Se precisar, a equipe detalha a próxima etapa.', 'status pedido meu pedido'), ('pedido_002', 'pedido', 'Meu pedido foi separado?', 'Quando o pedido é confirmado, a equipe separa a peça e atualiza o status no sistema.', 'separado separar pedido'), ('pedido_003', 'pedido', 'Posso juntar pedidos?', 'Pode ser possível juntar pedidos antes do envio/retirada. Vou chamar a atendente para confirmar.', 'juntar pedidos combinar frete'), ('pedido_004', 'pedido', 'Quero adicionar outra peça ao pedido.', 'Pode sim, se ainda estiver disponível. Envie o código ou toque na peça para adicionarmos ao atendimento.', 'adicionar peça incluir pedido'), ('pedido_005', 'pedido', 'Como vejo minhas compras?', 'No app/site cliente você pode acessar seu perfil e acompanhar pedidos/reservas vinculados à sua conta.', 'minhas compras historico pedidos'), ('pedido_006', 'pedido', 'Recebi pedido errado.', 'Sinto muito por isso. Vou encaminhar para atendimento humano resolver com prioridade.', 'pedido errado recebi troca problema'), ('pedido_007', 'pedido', 'Quero nota ou comprovante da compra.', 'A equipe pode enviar o comprovante/registro do pedido pelo atendimento.', 'nota comprovante compra recibo'), ('atendimento_001', 'atendimento', 'Quero falar com uma atendente.', 'Claro, vou chamar uma atendente para continuar seu atendimento aqui no chat. 😊', 'atendente humano pessoa falar loja'), ('atendimento_002', 'atendimento', 'Qual o horário de atendimento?', 'O horário pode variar conforme a loja/live. Se mandar sua dúvida aqui, a equipe responde assim que possível.', 'horario atendimento funciona aberto'), ('atendimento_003', 'atendimento', 'Onde fica a loja?', 'A atendente pode confirmar endereço/ponto de retirada atualizado pelo chat.', 'onde fica loja endereço'), ('atendimento_004', 'atendimento', 'Como funciona o BRECHORISEE?', 'Você acompanha as peças pelo app/site, reserva durante a live e combina pagamento/entrega pelo atendimento.', 'como funciona brecho risee sistema'), ('atendimento_005', 'atendimento', 'Vocês respondem pelo WhatsApp?', 'O atendimento principal fica salvo aqui no Chat BRECHORISEE, mas a loja pode orientar outros canais quando necessário.', 'whatsapp zap direct instagram contato'), ('atendimento_006', 'atendimento', 'Não consigo reservar.', 'Vou chamar a atendente para verificar sua conta, a peça e o status da reserva.', 'nao consigo reservar erro problema'), ('troca_001', 'troca', 'Tem troca?', 'Regras de troca dependem da política da loja e do estado da peça. Vou chamar a atendente para confirmar.', 'troca trocar devolução'), ('troca_002', 'troca', 'Posso devolver?', 'A devolução segue a política da loja. A equipe avalia o caso pelo atendimento.', 'devolver devolução arrependi'), ('troca_003', 'troca', 'A peça não serviu.', 'Me avise o número do pedido e a equipe orienta as opções conforme a política da loja.', 'nao serviu apertada grande pequena'), ('posvenda_001', 'posvenda', 'Como avalio minha compra?', 'Depois do atendimento, você pode enviar sua avaliação aqui ou pelo canal indicado pela loja.', 'avaliar avaliação gostei feedback'), ('posvenda_002', 'posvenda', 'Quero receber aviso da próxima live.', 'Você pode acompanhar pelo app/site e ativar notificações quando disponíveis.', 'proxima live aviso notificação'), ('posvenda_003', 'posvenda', 'Quero ver promoções.', 'Acesse a vitrine/repescagem pelo app ou peça para a atendente te mostrar as promoções ativas.', 'promoção promocoes desconto liquidação'), ('fallback_001', 'geral', 'Não entendi a pergunta.', 'Posso te ajudar com reserva, preço, tamanho, pagamento, entrega, pedido ou peça da live. Se preferir, chamo uma atendente.', 'ajuda duvida')]


def bot_risee_normalize(value: Any) -> str:
    text_value = str(value or "").lower().strip()
    text_value = unicodedata.normalize("NFKD", text_value)
    text_value = "".join(ch for ch in text_value if not unicodedata.combining(ch))
    text_value = re.sub(r"[^a-z0-9\s]", " ", text_value)
    return re.sub(r"\s+", " ", text_value).strip()


def bot_risee_tokens(value: Any) -> set[str]:
    stop = {
        "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
        "e", "ou", "em", "no", "na", "nos", "nas", "para", "pra", "por", "com", "sem",
        "que", "qual", "quais", "como", "me", "te", "se", "eu", "voce", "voces", "essa",
        "esse", "isso", "esta", "está", "minha", "meu", "tem", "ta", "tá"
    }
    return {tok for tok in bot_risee_normalize(value).split() if len(tok) >= 3 and tok not in stop}


def bot_risee_price(value: Any) -> str:
    try:
        return brl(float(value or 0))
    except Exception:
        try:
            return f"R$ {float(value or 0):.2f}".replace(".", ",")
        except Exception:
            return "valor sob consulta"


def bot_risee_format_answer(answer: str, product: sqlite3.Row | dict[str, Any] | None = None, order: sqlite3.Row | dict[str, Any] | None = None, customer: sqlite3.Row | dict[str, Any] | None = None) -> str:
    placeholders = {
        "product_title": row_get(product, "title", "a peça da live"),
        "product_code": row_get(product, "code", "sem código"),
        "product_size": row_get(product, "size", "não informado"),
        "product_price": bot_risee_price(row_get(product, "sale_price", 0)) if product else "valor sob consulta",
        "product_status": row_get(product, "status", "não informado"),
        "product_measurements": row_get(product, "measurements", "ainda não cadastradas"),
        "product_condition": row_get(product, "condition", "não informada"),
        "product_color": row_get(product, "color", "não informada"),
        "product_brand": row_get(product, "brand", "não informada"),
        "order_code": row_get(order, "order_code", "sem código"),
        "order_status": row_get(order, "status", "não localizado"),
        "order_total": bot_risee_price(row_get(order, "total", 0)) if order else "valor sob consulta",
        "customer_name": row_get(customer, "name", "cliente"),
    }
    safe_answer = answer
    for key, value in placeholders.items():
        safe_answer = safe_answer.replace("{" + key + "}", str(value or "não informado"))
    return safe_answer


def init_bot_risee_schema(con: sqlite3.Connection | None = None) -> None:
    own_connection = con is None
    if own_connection:
        con_ctx = get_db()
        con = con_ctx.__enter__()
    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS bot_risee_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bot_risee_faqs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faq_key TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL DEFAULT 'geral',
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                keywords TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 0,
                usage_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_bot_risee_faqs_active ON bot_risee_faqs(active, category, priority DESC);
            """
        )
        now = now_iso()
        defaults = {
            "enabled": os.getenv("BOT_RISEE_ENABLED", "1"),
            "min_score": os.getenv("BOT_RISEE_MIN_SCORE", "2"),
            "handoff_on_unknown": os.getenv("BOT_RISEE_HANDOFF_ON_UNKNOWN", "0"),
            "product_search_enabled": os.getenv("BOT_RISEE_PRODUCT_SEARCH_ENABLED", "1"),
            "product_search_max_results": os.getenv("BOT_RISEE_PRODUCT_SEARCH_MAX_RESULTS", "5"),
            "name": os.getenv("BOT_RISEE_NAME", "Bot BRECHORISEE"),
        }
        for key, value in defaults.items():
            exists = con.execute("SELECT 1 FROM bot_risee_settings WHERE key=?", (key,)).fetchone()
            if not exists:
                con.execute("INSERT INTO bot_risee_settings(key, value, updated_at) VALUES(?,?,?)", (key, value, now))
        for idx, (faq_key, category, question, answer, keywords) in enumerate(BOT_RISEE_FAQS):
            exists = con.execute("SELECT 1 FROM bot_risee_faqs WHERE faq_key=?", (faq_key,)).fetchone()
            if not exists:
                con.execute(
                    """
                    INSERT INTO bot_risee_faqs(faq_key, category, question, answer, keywords, active, priority, usage_count, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (faq_key, category, question, answer, keywords, 1, max(0, 200 - idx), 0, now, now),
                )

        # Correção de intenção: "gostei de uma blusa/peça que vi" é busca de peça,
        # não avaliação pós-venda. Atualiza bancos já existentes também.
        con.execute(
            """
            UPDATE bot_risee_faqs
            SET keywords=?, updated_at=?
            WHERE faq_key='posvenda_001'
            """,
            ("avaliar avaliação feedback nota opiniao opinião pós venda posvenda atendimento encerrado", now),
        )
        con.execute(
            """
            UPDATE bot_risee_faqs
            SET answer=?, keywords=?, updated_at=?
            WHERE faq_key='fallback_001'
            """,
            (
                "Posso te ajudar com reserva, preço, tamanho, pagamento, entrega, pedido ou peça da live. Se estiver procurando uma peça, me diga tipo, cor, tamanho ou envie foto/print.",
                "ajuda duvida dúvida reserva preco preço tamanho pagamento entrega pedido peca peça live produto procurar buscar foto print",
                now,
            ),
        )
        con.execute(
            """
            INSERT INTO bot_risee_faqs(faq_key, category, question, answer, keywords, active, priority, usage_count, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(faq_key) DO UPDATE SET
                category=excluded.category,
                question=excluded.question,
                answer=excluded.answer,
                keywords=excluded.keywords,
                active=1,
                priority=excluded.priority,
                updated_at=excluded.updated_at
            """,
            (
                "produto_interesse_001",
                "produto",
                "Gostei de uma peça que vi.",
                "Claro 😊 Posso te ajudar a localizar essa peça. Você lembra a cor, tamanho, marca, valor aproximado ou em qual live/post viu? Se tiver foto ou print, envie aqui.",
                "gostei gostei muito vi ontem peça peca blusa vestido calça saia live post reels stories foto print localizar encontrar procurar",
                1,
                240,
                0,
                now,
                now,
            ),
        )
        if own_connection:
            con.commit()
    finally:
        if own_connection:
            con_ctx.__exit__(None, None, None)


@app.on_event("startup")
def startup_bot_risee() -> None:
    init_bot_risee_schema()


def bot_risee_setting(con: sqlite3.Connection, key: str, default: str = "") -> str:
    init_bot_risee_schema(con)
    row = con.execute("SELECT value FROM bot_risee_settings WHERE key=?", (key,)).fetchone()
    return str(row["value"] if row else default)


def bot_risee_is_enabled(con: sqlite3.Connection) -> bool:
    return bot_risee_setting(con, "enabled", "1").strip().lower() not in {"0", "false", "nao", "não", "off", "desligado"}


def bot_risee_score(question: str, row: sqlite3.Row) -> int:
    q_norm = bot_risee_normalize(question)
    q_tokens = bot_risee_tokens(question)
    keywords = bot_risee_normalize(row["keywords"])
    keyword_tokens = bot_risee_tokens(keywords)
    question_tokens = bot_risee_tokens(row["question"])
    score = 0
    for phrase in [p.strip() for p in keywords.split() if len(p.strip()) >= 3]:
        if phrase in q_norm:
            score += 1
    score += len(q_tokens & keyword_tokens) * 3
    score += len(q_tokens & question_tokens) * 2
    if row["category"] in {"live", "reserva", "pagamento", "entrega", "produto", "pedido"} and row["category"] in q_norm:
        score += 2
    return int(score)


def bot_risee_pick_faq(con: sqlite3.Connection, body: str) -> sqlite3.Row | None:
    init_bot_risee_schema(con)
    normalized = bot_risee_normalize(body)
    if not normalized:
        return None
    rows = con.execute("SELECT * FROM bot_risee_faqs WHERE active=1 ORDER BY priority DESC, id").fetchall()
    best = None
    best_score = -1
    for row in rows:
        score = bot_risee_score(normalized, row)
        if score > best_score:
            best = row
            best_score = score
    try:
        min_score = int(bot_risee_setting(con, "min_score", "2") or "2")
    except Exception:
        min_score = 2
    if best and best_score >= min_score:
        return best
    fallback = con.execute("SELECT * FROM bot_risee_faqs WHERE faq_key='fallback_001' AND active=1").fetchone()
    return fallback


def bot_risee_needs_human(body: str) -> bool:
    tokens = bot_risee_tokens(body)
    human_terms = {"atendente", "humano", "pessoa", "gerente", "dona", "vendedora", "suporte", "problema", "erro", "reclamar", "reclamacao"}
    return bool(tokens & human_terms)




# =============================================================================
# BOT RISEE - BUSCADOR INTELIGENTE DE PEÇAS / LISTA DE DESEJOS
# =============================================================================

PRODUCT_SEARCH_TYPE_SYNONYMS: dict[str, set[str]] = {
    "vestido": {"vestido", "vestidos", "dress"},
    "blusa": {"blusa", "blusas", "cropped", "croppeds", "regata", "regatas", "body", "bodies", "top", "tops"},
    "camisa": {"camisa", "camisas", "camiseta", "camisetas", "tshirt", "t-shirt"},
    "calça": {"calca", "calças", "calça", "calças", "jeans", "pantalona", "legging", "leggings", "short", "shorts", "bermuda", "bermudas"},
    "saia": {"saia", "saias"},
    "casaco": {"casaco", "casacos", "jaqueta", "jaquetas", "blazer", "blazers", "cardigan", "cardigans", "moletom", "moletons", "kimono", "kimonos"},
    "macacão": {"macacao", "macacões", "macacão", "macacões", "jardineira", "jardineiras"},
    "bolsa": {"bolsa", "bolsas", "mochila", "mochilas", "carteira", "carteiras"},
    "sapato": {"sapato", "sapatos", "sandalia", "sandalias", "sandália", "sandálias", "bota", "botas", "tenis", "tênis", "sapatilha", "sapatilhas"},
    "acessório": {"acessorio", "acessorios", "acessório", "acessórios", "cinto", "cintos", "brinco", "brincos", "colar", "colares", "lenço", "lenco", "óculos", "oculos"},
}

PRODUCT_SEARCH_COLORS: dict[str, set[str]] = {
    "preto": {"preto", "preta", "black"},
    "branco": {"branco", "branca", "off", "offwhite", "off-white"},
    "azul": {"azul", "marinho", "royal"},
    "jeans": {"jeans", "denim"},
    "vermelho": {"vermelho", "vermelha", "vinho", "bordo", "bordô"},
    "rosa": {"rosa", "pink"},
    "verde": {"verde", "militar"},
    "amarelo": {"amarelo", "amarela", "mostarda"},
    "laranja": {"laranja"},
    "roxo": {"roxo", "roxa", "lilas", "lilás"},
    "marrom": {"marrom", "caramelo", "bege", "nude", "camel"},
    "cinza": {"cinza", "grafite"},
    "dourado": {"dourado", "dourada"},
    "prata": {"prata", "prateado", "prateada"},
    "estampado": {"estampado", "estampada", "floral", "animal", "listrado", "listrada", "poa", "poá", "xadrez"},
}

PRODUCT_SEARCH_STYLE_SYNONYMS: dict[str, set[str]] = {
    "festa": {"festa", "formatura", "casamento", "evento", "noite", "balada"},
    "trabalho": {"trabalho", "escritorio", "escritório", "social", "alfaiataria", "formal"},
    "casual": {"casual", "dia", "diaadia", "dia-a-dia", "basico", "básico"},
    "frio": {"frio", "inverno", "quentinho", "quentinha"},
    "verão": {"verao", "verão", "calor", "praia"},
    "plus size": {"plus", "plussize", "plus-size", "gg", "xg", "xgg", "g1", "g2", "g3"},
    "infantil": {"infantil", "crianca", "criança", "menina", "menino", "kids"},
    "gestante": {"gestante", "gravida", "grávida"},
    "academia": {"academia", "fitness", "esporte", "esportivo"},
}

PRODUCT_SEARCH_INTENT_TERMS = {
    "tem", "tens", "temos", "procuro", "procurando", "busco", "buscando", "quero", "queria",
    "gostaria", "preciso", "encontra", "encontrar", "ache", "acha", "manda", "mostrar",
    "mostra", "disponivel", "disponível", "disponiveis", "opcoes", "opções", "peca", "peça", "roupa", "look"
}


def init_product_search_schema(con: sqlite3.Connection | None = None) -> None:
    own_connection = con is None
    if own_connection:
        con_ctx = get_db()
        con = con_ctx.__enter__()
    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS customer_product_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_account_id INTEGER,
                chat_thread_id INTEGER,
                raw_query TEXT NOT NULL,
                normalized_query TEXT NOT NULL,
                criteria_json TEXT NOT NULL,
                matched_product_ids TEXT NOT NULL DEFAULT '',
                matched_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'aberta',
                source TEXT NOT NULL DEFAULT 'chat_risee',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id),
                FOREIGN KEY (chat_thread_id) REFERENCES chat_threads(id)
            );

            CREATE INDEX IF NOT EXISTS idx_customer_product_searches_customer ON customer_product_searches(customer_account_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_customer_product_searches_status ON customer_product_searches(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_customer_product_searches_thread ON customer_product_searches(chat_thread_id);
            """
        )
        product_search_columns = {row["name"] for row in con.execute("PRAGMA table_info(customer_product_searches)").fetchall()}
        product_search_alters = {
            "desired_summary": "desired_summary TEXT NOT NULL DEFAULT ''",
            "acquisition_status": "acquisition_status TEXT NOT NULL DEFAULT 'procurar'",
            "acquisition_priority": "acquisition_priority TEXT NOT NULL DEFAULT 'normal'",
            "acquisition_notes": "acquisition_notes TEXT NOT NULL DEFAULT ''",
            "desired_by": "desired_by TEXT NOT NULL DEFAULT ''",
            "max_price": "max_price REAL",
            "found_product_id": "found_product_id INTEGER",
            "notified_at": "notified_at TEXT",
            "acquired_at": "acquired_at TEXT",
            "reserved_at": "reserved_at TEXT",
            "archived_at": "archived_at TEXT",
        }
        for col_name, ddl in product_search_alters.items():
            if col_name not in product_search_columns:
                con.execute(f"ALTER TABLE customer_product_searches ADD COLUMN {ddl}")
        con.execute("CREATE INDEX IF NOT EXISTS idx_customer_product_searches_acquisition ON customer_product_searches(acquisition_status, acquisition_priority, created_at)")
        con.execute("UPDATE customer_product_searches SET acquisition_status=CASE WHEN status='desejo' THEN 'procurar' WHEN status='respondida' THEN 'respondida' ELSE COALESCE(NULLIF(acquisition_status,''),'procurar') END WHERE acquisition_status='' OR acquisition_status IS NULL")
        if own_connection:
            con.commit()
    finally:
        if own_connection:
            con_ctx.__exit__(None, None, None)


@app.on_event("startup")
def startup_product_search_schema() -> None:
    init_product_search_schema()


def bot_risee_product_search_enabled(con: sqlite3.Connection) -> bool:
    return bot_risee_setting(con, "product_search_enabled", "1").strip().lower() not in {"0", "false", "nao", "não", "off", "desligado"}


def product_search_parse_price(text_value: str) -> float | None:
    text_norm = bot_risee_normalize(text_value)
    patterns = [
        r"(?:ate|até|maximo|max|menos de|abaixo de|por ate|por até)\s*(?:r\s*\$)?\s*(\d{1,5}(?:[\.,]\d{1,2})?)",
        r"(?:r\s*\$)\s*(\d{1,5}(?:[\.,]\d{1,2})?)",
        r"(\d{1,5}(?:[\.,]\d{1,2})?)\s*(?:reais|real)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text_norm, flags=re.I)
        if not m:
            continue
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except Exception:
            continue
    return None


def product_search_detect_sizes(raw_body: str) -> list[str]:
    raw = str(raw_body or "")
    normalized = bot_risee_normalize(raw)
    sizes: set[str] = set()
    for m in re.finditer(r"\b(?:tam|tamanho|numero|número|n)\s*[:\-]?\s*(pp|p|m|g|gg|xg|xgg|g1|g2|g3|\d{2})\b", normalized, flags=re.I):
        sizes.add(m.group(1).upper())
    for m in re.finditer(r"\b(pp|p|m|g|gg|xg|xgg|g1|g2|g3)\b", normalized, flags=re.I):
        token = m.group(1).upper()
        # Evita considerar a letra "p" solta em mensagens comuns; aceita quando há intenção de peça.
        if token in {"PP", "P", "M", "G", "GG", "XG", "XGG", "G1", "G2", "G3"}:
            sizes.add(token)
    for m in re.finditer(r"\b(3[4-9]|4[0-9]|5[0-8])\b", normalized):
        sizes.add(m.group(1))
    return sorted(sizes)


def product_search_extract_terms(body: str) -> dict[str, Any] | None:
    raw = chat_clean_text(body, 500)
    normalized = bot_risee_normalize(raw)
    if not normalized:
        return None
    tokens = bot_risee_tokens(normalized)
    product_types: list[str] = []
    colors: list[str] = []
    styles: list[str] = []
    for label, synonyms in PRODUCT_SEARCH_TYPE_SYNONYMS.items():
        if tokens & {bot_risee_normalize(s) for s in synonyms}:
            product_types.append(label)
        else:
            for syn in synonyms:
                if len(syn) >= 5 and bot_risee_normalize(syn) in normalized:
                    product_types.append(label)
                    break
    for label, synonyms in PRODUCT_SEARCH_COLORS.items():
        if tokens & {bot_risee_normalize(s) for s in synonyms}:
            colors.append(label)
        else:
            for syn in synonyms:
                if len(syn) >= 4 and bot_risee_normalize(syn) in normalized:
                    colors.append(label)
                    break
    for label, synonyms in PRODUCT_SEARCH_STYLE_SYNONYMS.items():
        if tokens & {bot_risee_normalize(s) for s in synonyms}:
            styles.append(label)
        else:
            for syn in synonyms:
                if len(syn) >= 5 and bot_risee_normalize(syn) in normalized:
                    styles.append(label)
                    break
    sizes = product_search_detect_sizes(raw)
    max_price = product_search_parse_price(raw)
    words_all = set(normalized.split())
    has_intent = bool(words_all & {bot_risee_normalize(t) for t in PRODUCT_SEARCH_INTENT_TERMS})
    has_intent = has_intent or any(bot_risee_normalize(t) in normalized for t in PRODUCT_SEARCH_INTENT_TERMS if len(t) >= 4)
    product_interest_terms = {
        "gostei", "gostou", "interessei", "interessada", "interessado", "vi", "visto",
        "ontem", "live", "post", "reels", "story", "stories", "print", "foto", "mostrar"
    }
    if product_types and (words_all & product_interest_terms):
        has_intent = True
    if product_types and any(phrase in normalized for phrase in ["vi ontem", "que vi", "na live", "do post", "dos stories", "do reels"]):
        has_intent = True
    signals = len(product_types) + len(colors) + len(styles) + len(sizes) + (1 if max_price else 0)
    # Precisa parecer busca de catálogo; evita responder como busca em perguntas de Pix/entrega.
    if not has_intent and signals < 2:
        return None
    if signals == 0:
        return None
    if any(term in normalized for term in ["pix", "entrega", "retirada", "troca", "pagamento", "comprovante"]) and not product_types:
        return None
    return {
        "raw": raw,
        "normalized": normalized,
        "product_types": sorted(set(product_types)),
        "colors": sorted(set(colors)),
        "sizes": sorted(set(sizes)),
        "styles": sorted(set(styles)),
        "max_price": max_price,
        "tokens": sorted(tokens),
        "signals": signals,
    }


def product_search_status_available(status: Any) -> bool:
    s = bot_risee_normalize(status)
    return not s or s in {"disponivel", "disponível", "ativo", "a venda", "vitrine"}


def product_search_row_text(row: sqlite3.Row | dict[str, Any]) -> str:
    fields = [
        row_get(row, "code", ""),
        row_get(row, "title", ""),
        row_get(row, "category", ""),
        row_get(row, "garment_type", ""),
        row_get(row, "size", ""),
        row_get(row, "brand", ""),
        row_get(row, "color", ""),
        row_get(row, "condition", ""),
        row_get(row, "measurements", ""),
        row_get(row, "characteristics", ""),
        row_get(row, "style_tags", ""),
        row_get(row, "season", ""),
        row_get(row, "target_audience", ""),
        row_get(row, "trend_label", ""),
    ]
    return bot_risee_normalize(" ".join(str(v or "") for v in fields))


def product_search_score(row: sqlite3.Row | dict[str, Any], criteria: dict[str, Any]) -> int:
    normalized = product_search_row_text(row)
    score = 0
    for label in criteria.get("product_types", []):
        variants = PRODUCT_SEARCH_TYPE_SYNONYMS.get(label, {label})
        if any(bot_risee_normalize(v) in normalized for v in variants | {label}):
            score += 18
    for color in criteria.get("colors", []):
        variants = PRODUCT_SEARCH_COLORS.get(color, {color})
        if any(bot_risee_normalize(v) in normalized for v in variants | {color}):
            score += 14
    row_size = bot_risee_normalize(row_get(row, "size", ""))
    for size in criteria.get("sizes", []):
        s = bot_risee_normalize(size)
        if s and (s == row_size or re.search(rf"\b{re.escape(s)}\b", row_size)):
            score += 16
        elif s and s in normalized:
            score += 8
    for style in criteria.get("styles", []):
        variants = PRODUCT_SEARCH_STYLE_SYNONYMS.get(style, {style})
        if any(bot_risee_normalize(v) in normalized for v in variants | {style}):
            score += 8
    token_hits = 0
    ignored = PRODUCT_SEARCH_INTENT_TERMS | {"tem", "quero", "procuro", "peca", "peça", "roupa", "look", "ate", "até", "reais"}
    for token in criteria.get("tokens", []):
        if len(token) < 3 or token in {bot_risee_normalize(i) for i in ignored}:
            continue
        if token in normalized:
            token_hits += 1
    score += min(token_hits, 8) * 2
    try:
        max_price = criteria.get("max_price")
        if max_price and float(row_get(row, "sale_price", 0) or 0) <= float(max_price):
            score += 6
    except Exception:
        pass
    return int(score)


def product_search_find_matches(con: sqlite3.Connection, criteria: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    max_price = criteria.get("max_price")
    params: list[Any] = []
    where = ["1=1"]
    if max_price:
        where.append("COALESCE(sale_price, 0) <= ?")
        params.append(float(max_price))
    rows = con.execute(
        f"""
        SELECT * FROM products
        WHERE {' AND '.join(where)}
        ORDER BY id DESC
        LIMIT 500
        """,
        params,
    ).fetchall()
    scored: list[tuple[int, sqlite3.Row]] = []
    for row in rows:
        if not product_search_status_available(row_get(row, "status", "")):
            continue
        score = product_search_score(row, criteria)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: (item[0], float(row_get(item[1], "sale_price", 0) or 0)), reverse=True)
    matches: list[dict[str, Any]] = []
    for score, row in scored[: max(1, int(limit or 5))]:
        data = row_to_dict(row)
        data["score"] = score
        data["price_label"] = money(data.get("sale_price"))
        data["image_url"] = chat_product_image_url(data)
        data["public_url"] = f"/loja/produto/{quote_plus(str(data.get('code') or data.get('id')))}?origem=bot-risee"
        matches.append(data)
    return matches


def product_search_format_criteria(criteria: dict[str, Any]) -> str:
    parts: list[str] = []
    if criteria.get("product_types"):
        parts.append("tipo: " + ", ".join(criteria["product_types"]))
    if criteria.get("colors"):
        parts.append("cor: " + ", ".join(criteria["colors"]))
    if criteria.get("sizes"):
        parts.append("tamanho: " + ", ".join(criteria["sizes"]))
    if criteria.get("styles"):
        parts.append("estilo: " + ", ".join(criteria["styles"]))
    if criteria.get("max_price"):
        parts.append("até " + money(criteria["max_price"]))
    return "; ".join(parts) or "busca aberta"


def product_search_acquisition_priority(criteria: dict[str, Any]) -> str:
    """Define prioridade comercial do desejo para aquisição/garimpo."""
    score = 0
    if criteria.get("product_types"):
        score += 2
    if criteria.get("sizes"):
        score += 2
    if criteria.get("colors"):
        score += 1
    if criteria.get("styles"):
        score += 1
    if criteria.get("max_price"):
        score += 1
    styles = {bot_risee_normalize(v) for v in criteria.get("styles", [])}
    if styles & {"festa", "trabalho", "plus size", "frio"}:
        score += 1
    if score >= 5:
        return "alta"
    if score >= 3:
        return "media"
    return "normal"


def product_search_desired_summary(criteria: dict[str, Any]) -> str:
    summary = product_search_format_criteria(criteria)
    return summary if summary != "busca aberta" else "Peça desejada pela cliente"


def product_search_format_bot_answer(criteria: dict[str, Any], matches: list[dict[str, Any]]) -> str:
    """Resposta mais humana para busca de peças no chat.

    Mantém a lógica offline/local, mas melhora a precisão da fala:
    - resume a busca da cliente;
    - mostra preço/tamanho/código quando encontrou;
    - oferece ação clara;
    - quando não encontra, registra desejo e pede refinamento.
    """
    summary = product_search_format_criteria(criteria)
    if matches:
        plural = "opção parecida" if len(matches) == 1 else "opções parecidas"
        lines = [
            f"Encontrei {len(matches)} {plural} com o que você procura 😊",
            f"Busca entendida: {summary}",
            "",
            "Separei as melhores opções do estoque agora:",
        ]
        for i, p in enumerate(matches, 1):
            title = str(p.get("title") or "Peça").strip()
            code = str(p.get("code") or p.get("id") or "-").strip()
            size = str(p.get("size") or "tamanho não informado").strip()
            color = str(p.get("color") or "").strip()
            status = str(p.get("status") or "disponível").strip()
            price_label = str(p.get("price_label") or money(p.get("sale_price"))).strip()
            line = f"{i}. {title} — {price_label} — {size}"
            if color:
                line += f" — cor {color}"
            line += f" — cód. {code}"
            lines.append(line)
            lines.append(f"   Status: {status}. Ver peça: {p.get('public_url')}")
        lines += [
            "",
            "Quer que eu reserve alguma para você?",
            "Pode me mandar o código da peça ou tocar no link. Se quiser, também posso procurar outra cor, tamanho ou faixa de preço.",
        ]
        return "\n".join(lines)

    lines = [
        "Eu procurei no estoque e ainda não encontrei uma peça disponível exatamente com essas características 😕",
        f"Busca entendida: {summary}",
        "",
        "Para não perder seu pedido, já salvei isso em Desejos e Aquisições da loja.",
        "Quando uma peça parecida chegar ou for cadastrada, a equipe consegue te avisar por aqui no Chat BRECHORISEE.",
        "",
        "Se quiser, posso tentar uma busca mais próxima agora. Me diga:",
        "• cor preferida",
        "• tamanho",
        "• faixa de preço",
        "• se é para você ou para alguém da família",
        "• ocasião: trabalho, festa, casual, igreja, viagem ou presente",
    ]
    return "\n".join(lines)

def product_search_save(
    con: sqlite3.Connection,
    thread: sqlite3.Row | dict[str, Any] | None,
    account: sqlite3.Row | dict[str, Any] | None,
    body: str,
    criteria: dict[str, Any],
    matches: list[dict[str, Any]],
) -> int:
    init_product_search_schema(con)
    now = now_iso()
    product_ids = ",".join(str(m.get("id")) for m in matches if m.get("id"))
    customer_account_id = row_get(thread, "customer_account_id", None) or row_get(account, "id", None)
    desired_summary = product_search_desired_summary(criteria)
    acquisition_status = "respondida" if matches else "procurar"
    acquisition_priority = product_search_acquisition_priority(criteria)
    desired_by = str(row_get(account, "name", "") or row_get(account, "phone", "") or "").strip()
    criteria_clean = {k: v for k, v in criteria.items() if k != "tokens"}
    cur = con.execute(
        """
        INSERT INTO customer_product_searches(customer_account_id, chat_thread_id, raw_query, normalized_query, criteria_json,
                                             matched_product_ids, matched_count, status, source,
                                             desired_summary, acquisition_status, acquisition_priority, desired_by, max_price,
                                             created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            int(customer_account_id) if customer_account_id else None,
            int(row_get(thread, "id", 0)) if thread else None,
            chat_clean_text(body, 500),
            bot_risee_normalize(body),
            json.dumps(criteria_clean, ensure_ascii=False),
            product_ids,
            len(matches),
            "respondida" if matches else "desejo",
            "chat_risee",
            desired_summary,
            acquisition_status,
            acquisition_priority,
            desired_by,
            float(criteria.get("max_price")) if criteria.get("max_price") else None,
            now,
            now,
        ),
    )
    return int(cur.lastrowid)


def bot_risee_product_search_preview(con: sqlite3.Connection, body: str, limit: int | None = None) -> dict[str, Any] | None:
    criteria = product_search_extract_terms(body)
    if not criteria:
        return None
    try:
        configured_limit = int(bot_risee_setting(con, "product_search_max_results", "5") or "5")
    except Exception:
        configured_limit = 5
    max_results = max(1, min(10, int(limit or configured_limit or 5)))
    matches = product_search_find_matches(con, criteria, limit=max_results)
    return {
        "criteria": {k: v for k, v in criteria.items() if k != "tokens"},
        "matches": matches,
        "answer": product_search_format_bot_answer(criteria, matches),
    }


def bot_risee_maybe_product_search_reply(
    con: sqlite3.Connection,
    thread: sqlite3.Row | dict[str, Any],
    body: str,
    account: sqlite3.Row | dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not bot_risee_product_search_enabled(con):
        return None
    preview = bot_risee_product_search_preview(con, body)
    if not preview:
        return None
    criteria = preview["criteria"]
    matches = preview["matches"]
    search_id = product_search_save(con, thread, account, body, criteria, matches)
    sender_name = bot_risee_setting(con, "name", "Bot BRECHORISEE") or "Bot BRECHORISEE"
    message = chat_insert_message(
        con,
        int(row_get(thread, "id", 0)),
        "bot",
        None,
        sender_name,
        body=preview["answer"],
        message_type="product_search",
        metadata={
            "automatic": True,
            "feature": "bot_busca_pecas",
            "search_id": search_id,
            "criteria": criteria,
            "matched_count": len(matches),
            "matched_product_ids": [m.get("id") for m in matches],
        },
    )
    if not matches:
        con.execute(
            "UPDATE chat_threads SET status='pendente', priority='alta', updated_at=? WHERE id=?",
            (now_iso(), int(row_get(thread, "id", 0))),
        )
    payload = row_to_dict(message)
    payload["attachment_url"] = payload.get("attachment_url") or chat_public_attachment_url(payload.get("attachment_filename"))
    return payload


@app.get("/desejos-aquisicoes", response_class=HTMLResponse)
@app.get("/buscas-pecas", response_class=HTMLResponse)
def admin_product_searches_page(request: Request, status: str = "todos") -> Response:
    init_product_search_schema()
    with get_db() as con:
        params: list[Any] = []
        where = "1=1"
        if status and status != "todos":
            where += " AND (cps.status=? OR cps.acquisition_status=?)"
            params.extend([status, status])
        searches = con.execute(
            f"""
            SELECT cps.*, ca.name AS customer_name, ca.phone AS customer_phone
            FROM customer_product_searches cps
            LEFT JOIN customer_accounts ca ON ca.id=cps.customer_account_id
            WHERE {where}
            ORDER BY cps.created_at DESC, cps.id DESC
            LIMIT 200
            """,
            params,
        ).fetchall()
        stats = {
            "total": con.execute("SELECT COUNT(*) FROM customer_product_searches").fetchone()[0],
            "desejo": con.execute("SELECT COUNT(*) FROM customer_product_searches WHERE status='desejo'").fetchone()[0],
            "procurar": con.execute("SELECT COUNT(*) FROM customer_product_searches WHERE acquisition_status IN ('procurar','em_garimpo')").fetchone()[0],
            "respondida": con.execute("SELECT COUNT(*) FROM customer_product_searches WHERE status='respondida' OR acquisition_status='respondida'").fetchone()[0],
            "cliente_avisada": con.execute("SELECT COUNT(*) FROM customer_product_searches WHERE acquisition_status IN ('cliente_avisada','avisada') OR status='avisada'").fetchone()[0],
        }
    return templates.TemplateResponse(
        "admin_product_searches.html",
        {"request": request, "active": "desejos-aquisicoes" if str(request.url.path).startswith("/desejos") else "buscas-pecas", "searches": searches, "stats": stats, "status": status},
    )


@app.get("/api/desejos-aquisicoes")
@app.get("/api/buscas-pecas")
def api_product_searches(status: str = "todos") -> JSONResponse:
    init_product_search_schema()
    with get_db() as con:
        params: list[Any] = []
        where = "1=1"
        if status and status != "todos":
            where += " AND (cps.status=? OR cps.acquisition_status=?)"
            params.extend([status, status])
        rows = con.execute(
            f"""
            SELECT cps.*, ca.name AS customer_name, ca.phone AS customer_phone
            FROM customer_product_searches cps
            LEFT JOIN customer_accounts ca ON ca.id=cps.customer_account_id
            WHERE {where}
            ORDER BY cps.created_at DESC, cps.id DESC
            LIMIT 300
            """,
            params,
        ).fetchall()
    payload = []
    for row in rows:
        data = row_to_dict(row)
        try:
            data["criteria"] = json.loads(data.get("criteria_json") or "{}")
        except Exception:
            data["criteria"] = {}
        payload.append(data)
    return JSONResponse({"ok": True, "count": len(payload), "searches": payload})


@app.post("/api/desejos-aquisicoes/{search_id}/status")
@app.post("/api/buscas-pecas/{search_id}/status")
def api_product_search_update_status(search_id: int, status: str = Form("avisada")) -> JSONResponse:
    init_product_search_schema()
    status_clean = bot_risee_normalize(status).replace(" ", "_")
    allowed = {"aberta", "desejo", "respondida", "avisada", "resolvida", "arquivada",
               "procurar", "em_garimpo", "encontrada", "cliente_avisada", "reservada",
               "adquirida", "nao_encontrada"}
    if status_clean not in allowed:
        return JSONResponse({"ok": False, "message": "Status inválido."}, status_code=400)
    with get_db() as con:
        row = con.execute("SELECT * FROM customer_product_searches WHERE id=?", (int(search_id),)).fetchone()
        if not row:
            return JSONResponse({"ok": False, "message": "Busca não encontrada."}, status_code=404)
        now = now_iso()
        fields = ["status=?", "acquisition_status=?", "updated_at=?"]
        params: list[Any] = [status_clean if status_clean in {"aberta","desejo","respondida","avisada","resolvida","arquivada"} else row_get(row, "status", "desejo"),
                             status_clean, now]
        if status_clean in {"cliente_avisada", "avisada"}:
            fields.append("notified_at=?")
            params.append(now)
        if status_clean == "adquirida":
            fields.append("acquired_at=?")
            params.append(now)
        if status_clean == "reservada":
            fields.append("reserved_at=?")
            params.append(now)
        if status_clean == "arquivada":
            fields.append("archived_at=?")
            params.append(now)
        params.append(int(search_id))
        con.execute(f"UPDATE customer_product_searches SET {', '.join(fields)} WHERE id=?", tuple(params))
    return JSONResponse({"ok": True, "status": status_clean})


@app.post("/api/bot-risee/buscar-pecas")
def api_bot_risee_buscar_pecas(request: Request, message: str = Form(""), limit: int = Form(5)) -> JSONResponse:
    init_product_search_schema()
    init_bot_risee_schema()
    with get_db() as con:
        preview = bot_risee_product_search_preview(con, message, limit=limit)
    if not preview:
        return JSONResponse({"ok": False, "message": "Não identifiquei uma busca de peça. Tente: 'tem vestido preto M até 60 reais?'."})
    return JSONResponse({"ok": True, **preview})


def bot_risee_maybe_reply(
    con: sqlite3.Connection,
    thread: sqlite3.Row | dict[str, Any],
    body: str,
    account: sqlite3.Row | dict[str, Any] | None = None,
    product: sqlite3.Row | dict[str, Any] | None = None,
    order: sqlite3.Row | dict[str, Any] | None = None,
    attachment_present: bool = False,
) -> dict[str, Any] | None:
    init_bot_risee_schema(con)
    if chat_thread_bot_is_paused(thread):
        return None
    if not bot_risee_is_enabled(con):
        return None
    clean_body = chat_clean_text(body, 2500)
    if not clean_body and attachment_present:
        clean_body = "enviei comprovante ou anexo"
    if not clean_body:
        return None

    customer = account
    if not product or not order or not customer:
        p, o, c = chat_get_context_rows(con, thread)
        product = product or p
        order = order or o
        customer = customer or c or account

    product_search_reply = bot_risee_maybe_product_search_reply(con, thread, clean_body, account=account)
    if product_search_reply:
        return product_search_reply

    faq = bot_risee_pick_faq(con, clean_body)
    if not faq:
        return None
    answer = bot_risee_format_answer(str(faq["answer"]), product=product, order=order, customer=customer)
    metadata = {"faq_key": faq["faq_key"], "category": faq["category"], "automatic": True}
    sender_name = bot_risee_setting(con, "name", "Bot BRECHORISEE") or "Bot BRECHORISEE"
    message = chat_insert_message(
        con,
        int(row_get(thread, "id", 0)),
        "bot",
        None,
        sender_name,
        body=answer,
        message_type="text",
        metadata=metadata,
    )
    con.execute("UPDATE bot_risee_faqs SET usage_count=usage_count+1, updated_at=? WHERE id=?", (now_iso(), int(faq["id"])))
    if bot_risee_needs_human(clean_body):
        con.execute("UPDATE chat_threads SET status='pendente', priority='alta', updated_at=? WHERE id=?", (now_iso(), int(row_get(thread, "id", 0))))
    payload = row_to_dict(message)
    payload["attachment_url"] = payload.get("attachment_url") or chat_public_attachment_url(payload.get("attachment_filename"))
    return payload


@app.get("/bot-risee", response_class=HTMLResponse)
def admin_bot_risee_page(request: Request) -> Response:
    init_bot_risee_schema()
    with get_db() as con:
        settings = {r["key"]: r["value"] for r in con.execute("SELECT * FROM bot_risee_settings").fetchall()}
        faqs = con.execute("SELECT * FROM bot_risee_faqs ORDER BY category, priority DESC, id").fetchall()
    return templates.TemplateResponse("admin_bot_risee.html", {"request": request, "settings": settings, "faqs": faqs, "active": "bot-risee"})


@app.get("/api/bot-risee/faqs")
def api_bot_risee_faqs(request: Request) -> JSONResponse:
    init_bot_risee_schema()
    with get_db() as con:
        rows = con.execute("SELECT * FROM bot_risee_faqs ORDER BY category, priority DESC, id").fetchall()
        settings = {r["key"]: r["value"] for r in con.execute("SELECT * FROM bot_risee_settings").fetchall()}
    return JSONResponse({"ok": True, "settings": settings, "count": len(rows), "faqs": [row_to_dict(r) for r in rows]})


@app.post("/api/bot-risee/settings")
def api_bot_risee_settings(
    request: Request,
    enabled: str = Form("1"),
    min_score: int = Form(2),
    product_search_enabled: str = Form("1"),
    product_search_max_results: int = Form(5),
) -> JSONResponse:
    init_bot_risee_schema()
    enabled_clean = "1" if str(enabled).strip().lower() in {"1", "true", "sim", "on", "ligado"} else "0"
    search_enabled_clean = "1" if str(product_search_enabled).strip().lower() in {"1", "true", "sim", "on", "ligado"} else "0"
    min_score_clean = max(1, min(10, int(min_score or 2)))
    max_results_clean = max(1, min(10, int(product_search_max_results or 5)))
    with get_db() as con:
        con.execute("UPDATE bot_risee_settings SET value=?, updated_at=? WHERE key='enabled'", (enabled_clean, now_iso()))
        con.execute("UPDATE bot_risee_settings SET value=?, updated_at=? WHERE key='min_score'", (str(min_score_clean), now_iso()))
        con.execute("UPDATE bot_risee_settings SET value=?, updated_at=? WHERE key='product_search_enabled'", (search_enabled_clean, now_iso()))
        con.execute("UPDATE bot_risee_settings SET value=?, updated_at=? WHERE key='product_search_max_results'", (str(max_results_clean), now_iso()))
    return JSONResponse({
        "ok": True,
        "enabled": enabled_clean,
        "min_score": min_score_clean,
        "product_search_enabled": search_enabled_clean,
        "product_search_max_results": max_results_clean,
    })


@app.post("/api/bot-risee/test")
def api_bot_risee_test(request: Request, message: str = Form("")) -> JSONResponse:
    init_bot_risee_schema()
    init_product_search_schema()
    with get_db() as con:
        product_preview = bot_risee_product_search_preview(con, message)
        if product_preview:
            return JSONResponse({
                "ok": True,
                "type": "product_search",
                "criteria": product_preview["criteria"],
                "matches": product_preview["matches"],
                "answer": product_preview["answer"],
            })
        faq = bot_risee_pick_faq(con, message)
        if not faq:
            return JSONResponse({"ok": False, "message": "Nenhuma resposta encontrada."})
        return JSONResponse({
            "ok": True,
            "type": "faq",
            "faq": row_to_dict(faq),
            "answer": bot_risee_format_answer(str(faq["answer"])),
        })



# ============================================================
# BRECHORISEE v4.9.0 - Módulos 360 / manutenção modular
# ============================================================
# Esta camada foi adicionada sem quebrar o sistema legado. Ela cria módulos
# operacionais independentes para facilitar manutenção:
# - calculadora de preço/margem/consignado
# - carteira/montante da cliente com baixa por código/QR
# - inventário por câmera/código
# - consultor de estilo por Instagram/cliente/família
# - checklist técnico do sistema

def init_brechorisee_490_schema() -> None:
    """Migração segura dos módulos 360."""
    with get_db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS customer_montante_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL UNIQUE,
                balance REAL NOT NULL DEFAULT 0,
                credit_total REAL NOT NULL DEFAULT 0,
                debit_total REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ativo',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS customer_montante_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                product_id INTEGER,
                movement_type TEXT NOT NULL,
                amount REAL NOT NULL,
                balance_after REAL NOT NULL,
                code TEXT,
                origin TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_montante_customer ON customer_montante_movements(customer_id);
            CREATE INDEX IF NOT EXISTS idx_montante_created ON customer_montante_movements(created_at);

            CREATE TABLE IF NOT EXISTS inventory_scan_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'aberta',
                scanned_count INTEGER NOT NULL DEFAULT 0,
                found_count INTEGER NOT NULL DEFAULT 0,
                missing_count INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                closed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS inventory_scan_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                product_id INTEGER,
                code TEXT NOT NULL,
                found INTEGER NOT NULL DEFAULT 0,
                action TEXT NOT NULL DEFAULT 'conferido',
                previous_status TEXT,
                new_status TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES inventory_scan_sessions(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_inventory_scan_session ON inventory_scan_items(session_id);
            CREATE INDEX IF NOT EXISTS idx_inventory_scan_code ON inventory_scan_items(code);

            CREATE TABLE IF NOT EXISTS customer_style_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL UNIQUE,
                instagram_handle TEXT,
                body_notes TEXT,
                family_notes TEXT,
                preferred_styles TEXT,
                avoid_styles TEXT,
                preferred_sizes TEXT,
                preferred_colors TEXT,
                preferred_brands TEXT,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
            """
        )


try:
    init_brechorisee_490_schema()
except Exception as exc:
    logger.warning("Falha ao inicializar módulos 360 v4.9.0: %s", exc)


def _money_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        txt = str(value).strip().replace("R$", "").replace(" ", "")
        if "," in txt and "." in txt:
            txt = txt.replace(".", "").replace(",", ".")
        elif "," in txt:
            txt = txt.replace(",", ".")
        return round(float(txt), 2)
    except Exception:
        return default


async def _request_payload(request: Request) -> dict[str, Any]:
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    try:
        form = await request.form()
        return {k: v for k, v in form.items()}
    except Exception:
        return {}


def _customer_display_name(row: sqlite3.Row | dict[str, Any] | None) -> str:
    if not row:
        return ""
    try:
        return str(row["name"] or "")
    except Exception:
        return str(row.get("name") or "")


def _clean_handle(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.]", "", str(value or "").replace("@", "").strip()).lower()


def _find_customer_by_query(con: sqlite3.Connection, q: str) -> sqlite3.Row | None:
    q = str(q or "").strip()
    if not q:
        return None
    digits = "".join(ch for ch in q if ch.isdigit())
    handle = _clean_handle(q)
    if q.isdigit():
        row = con.execute("SELECT * FROM customers WHERE id=?", (int(q),)).fetchone()
        if row:
            return row
    if digits:
        row = con.execute(
            """
            SELECT * FROM customers
            WHERE REPLACE(REPLACE(REPLACE(REPLACE(phone,' ',''),'(',''),')',''),'-','') LIKE ?
            ORDER BY id DESC LIMIT 1
            """,
            (f"%{digits[-8:]}",),
        ).fetchone()
        if row:
            return row
    if handle:
        row = con.execute(
            "SELECT * FROM customers WHERE lower(replace(instagram,'@','')) LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{handle}%",),
        ).fetchone()
        if row:
            return row
    return con.execute(
        "SELECT * FROM customers WHERE lower(name) LIKE ? ORDER BY id DESC LIMIT 1",
        (f"%{q.lower()}%",),
    ).fetchone()


def _ensure_montante_account(con: sqlite3.Connection, customer_id: int) -> sqlite3.Row:
    now = now_iso()
    row = con.execute("SELECT * FROM customer_montante_accounts WHERE customer_id=?", (int(customer_id),)).fetchone()
    if row:
        return row
    con.execute(
        """
        INSERT INTO customer_montante_accounts(customer_id, balance, credit_total, debit_total, status, notes, created_at, updated_at)
        VALUES(?,0,0,0,'ativo','',?,?)
        """,
        (int(customer_id), now, now),
    )
    return con.execute("SELECT * FROM customer_montante_accounts WHERE customer_id=?", (int(customer_id),)).fetchone()


def _update_montante(
    con: sqlite3.Connection,
    *,
    customer_id: int,
    movement_type: str,
    amount: float,
    product_id: int | None = None,
    code: str = "",
    origin: str = "",
    notes: str = "",
) -> dict[str, Any]:
    amount = round(abs(float(amount or 0)), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Valor inválido.")
    acc = _ensure_montante_account(con, customer_id)
    old_balance = float(acc["balance"] or 0)
    if movement_type in {"credito", "entrada", "ajuste_credito"}:
        new_balance = round(old_balance + amount, 2)
        con.execute(
            """
            UPDATE customer_montante_accounts
            SET balance=?, credit_total=credit_total+?, updated_at=?
            WHERE customer_id=?
            """,
            (new_balance, amount, now_iso(), customer_id),
        )
        mt = "credito"
    elif movement_type in {"debito", "retirada", "compra", "ajuste_debito"}:
        new_balance = round(old_balance - amount, 2)
        con.execute(
            """
            UPDATE customer_montante_accounts
            SET balance=?, debit_total=debit_total+?, updated_at=?
            WHERE customer_id=?
            """,
            (new_balance, amount, now_iso(), customer_id),
        )
        mt = "debito"
    else:
        raise HTTPException(status_code=400, detail="Tipo de movimento inválido.")
    con.execute(
        """
        INSERT INTO customer_montante_movements(customer_id, product_id, movement_type, amount, balance_after, code, origin, notes, created_at)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (customer_id, product_id, mt, amount, new_balance, code, origin, notes, now_iso()),
    )
    return {"old_balance": old_balance, "balance": new_balance, "amount": amount, "movement_type": mt}


def _product_public_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    d = row_to_dict(row)
    try:
        d["image_url"] = url_for_static_upload(d.get("image_filename"))
    except Exception:
        d["image_url"] = ""
    return d


def _suggestion_score(product: dict[str, Any], terms: list[str]) -> int:
    hay = " ".join(str(product.get(k) or "") for k in [
        "title", "category", "garment_type", "size", "brand", "color", "condition", "characteristics", "style_tags", "season", "target_audience"
    ]).lower()
    return sum(1 for t in terms if t and t.lower() in hay)


@app.get("/modulos", response_class=HTMLResponse)
def modulos_360_page(request: Request) -> Response:
    init_brechorisee_490_schema()
    with get_db() as con:
        stats = {
            "customers": con.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"],
            "products_available": con.execute("SELECT COUNT(*) AS n FROM products WHERE status='disponivel'").fetchone()["n"],
            "wallets": con.execute("SELECT COUNT(*) AS n FROM customer_montante_accounts WHERE abs(balance) > 0.009").fetchone()["n"],
            "wallet_balance": con.execute("SELECT COALESCE(SUM(balance),0) AS n FROM customer_montante_accounts").fetchone()["n"],
            "last_scans": con.execute("SELECT COUNT(*) AS n FROM inventory_scan_items WHERE created_at >= datetime('now','-7 day')").fetchone()["n"],
        }
        last_movements = con.execute(
            """
            SELECT m.*, c.name AS customer_name, p.title AS product_title
            FROM customer_montante_movements m
            LEFT JOIN customers c ON c.id=m.customer_id
            LEFT JOIN products p ON p.id=m.product_id
            ORDER BY m.created_at DESC LIMIT 8
            """
        ).fetchall()
    return templates.TemplateResponse(
        "modulos_360.html",
        {"request": request, "active": "modulos", "stats": stats, "last_movements": last_movements},
    )


@app.get("/calculadora", response_class=HTMLResponse)
def calculadora_360_page(request: Request) -> Response:
    return templates.TemplateResponse("calculadora_360.html", {"request": request, "active": "calculadora"})


@app.post("/api/calculadora/preco")
async def api_calculadora_preco(request: Request) -> JSONResponse:
    data = await _request_payload(request)
    cost = _money_float(data.get("cost_price") or data.get("custo"), 0)
    desired_margin_pct = _money_float(data.get("desired_margin_pct") or data.get("margem"), 60)
    commission_pct = _money_float(data.get("commission_pct") or data.get("comissao"), 40)
    fixed_cost = _money_float(data.get("fixed_cost") or data.get("custo_fixo"), 0)
    discount_pct = _money_float(data.get("discount_pct") or data.get("desconto"), 0)

    margin_decimal = max(0.01, min(0.95, desired_margin_pct / 100))
    commission_decimal = max(0, min(0.95, commission_pct / 100))
    discount_decimal = max(0, min(0.9, discount_pct / 100))
    base_cost = cost + fixed_cost
    suggested_price = round(base_cost / (1 - margin_decimal), 2)
    price_after_discount = round(suggested_price * (1 - discount_decimal), 2)
    gross_profit = round(price_after_discount - base_cost, 2)
    consignor_amount = round(price_after_discount * (1 - commission_decimal), 2)
    store_amount = round(price_after_discount * commission_decimal, 2)
    break_even = round(base_cost / max(0.01, (1 - discount_decimal)), 2)

    return JSONResponse({
        "ok": True,
        "cost_price": cost,
        "fixed_cost": fixed_cost,
        "suggested_price": suggested_price,
        "price_after_discount": price_after_discount,
        "gross_profit": gross_profit,
        "gross_margin_pct": round((gross_profit / price_after_discount * 100) if price_after_discount else 0, 2),
        "commission_pct": commission_pct,
        "consignor_amount": consignor_amount,
        "store_amount": store_amount,
        "break_even": break_even,
        "notes": [
            "Preço sugerido considera custo + custo fixo e margem desejada.",
            "Consignado mostra quanto fica para a fornecedora/cliente e quanto fica para o brechó.",
        ],
    })


@app.get("/consignado", response_class=HTMLResponse)
def consignado_page(request: Request, q: str = "") -> Response:
    init_brechorisee_490_schema()
    with get_db() as con:
        customers = con.execute(
            """
            SELECT c.*, COALESCE(a.balance,0) AS balance, COALESCE(a.credit_total,0) AS credit_total, COALESCE(a.debit_total,0) AS debit_total
            FROM customers c
            LEFT JOIN customer_montante_accounts a ON a.customer_id=c.id
            WHERE (?='' OR lower(c.name) LIKE ? OR lower(COALESCE(c.instagram,'')) LIKE ? OR COALESCE(c.phone,'') LIKE ?)
            ORDER BY ABS(COALESCE(a.balance,0)) DESC, c.name
            LIMIT 80
            """,
            (q.strip().lower(), f"%{q.strip().lower()}%", f"%{q.strip().lower().replace('@','')}%", f"%{q.strip()}%"),
        ).fetchall()
        movements = con.execute(
            """
            SELECT m.*, c.name AS customer_name, p.title AS product_title
            FROM customer_montante_movements m
            LEFT JOIN customers c ON c.id=m.customer_id
            LEFT JOIN products p ON p.id=m.product_id
            ORDER BY m.created_at DESC LIMIT 30
            """
        ).fetchall()
    return templates.TemplateResponse(
        "consignado_360.html",
        {"request": request, "active": "consignado", "customers": customers, "movements": movements, "q": q},
    )


@app.get("/api/consignado/clientes")
def api_consignado_clientes(q: str = "") -> JSONResponse:
    init_brechorisee_490_schema()
    with get_db() as con:
        rows = con.execute(
            """
            SELECT c.id, c.name, c.phone, c.instagram, COALESCE(a.balance,0) AS balance
            FROM customers c
            LEFT JOIN customer_montante_accounts a ON a.customer_id=c.id
            WHERE (?='' OR lower(c.name) LIKE ? OR lower(COALESCE(c.instagram,'')) LIKE ? OR COALESCE(c.phone,'') LIKE ?)
            ORDER BY c.name LIMIT 30
            """,
            (q.strip().lower(), f"%{q.strip().lower()}%", f"%{q.strip().lower().replace('@','')}%", f"%{q.strip()}%"),
        ).fetchall()
    return JSONResponse({"ok": True, "customers": [row_to_dict(r) for r in rows]})


@app.get("/api/consignado/saldo/{customer_id}")
def api_consignado_saldo(customer_id: int) -> JSONResponse:
    init_brechorisee_490_schema()
    with get_db() as con:
        customer = con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        if not customer:
            return JSONResponse({"ok": False, "message": "Cliente não encontrada."}, status_code=404)
        acc = _ensure_montante_account(con, customer_id)
        movements = con.execute(
            "SELECT * FROM customer_montante_movements WHERE customer_id=? ORDER BY created_at DESC LIMIT 50",
            (customer_id,),
        ).fetchall()
    return JSONResponse({
        "ok": True,
        "customer": row_to_dict(customer),
        "account": row_to_dict(acc),
        "movements": [row_to_dict(m) for m in movements],
    })


@app.post("/api/consignado/credito")
async def api_consignado_credito(request: Request) -> JSONResponse:
    init_brechorisee_490_schema()
    data = await _request_payload(request)
    customer_id = int(data.get("customer_id") or 0)
    amount = _money_float(data.get("amount") or data.get("valor"), 0)
    notes = str(data.get("notes") or data.get("observacao") or "Entrada de montante").strip()[:300]
    if customer_id <= 0:
        return JSONResponse({"ok": False, "message": "Selecione a cliente."}, status_code=400)
    with get_db() as con:
        customer = con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        if not customer:
            return JSONResponse({"ok": False, "message": "Cliente não encontrada."}, status_code=404)
        result = _update_montante(con, customer_id=customer_id, movement_type="credito", amount=amount, origin="montante_manual", notes=notes)
    return JSONResponse({"ok": True, "message": "Montante adicionado.", **result})


@app.post("/api/consignado/escanear")
async def api_consignado_escanear(request: Request) -> JSONResponse:
    init_brechorisee_490_schema()
    data = await _request_payload(request)
    customer_id = int(data.get("customer_id") or 0)
    code = str(data.get("code") or data.get("codigo") or "").strip().upper()
    amount_override = _money_float(data.get("amount") or data.get("valor"), 0)
    if customer_id <= 0 or not code:
        return JSONResponse({"ok": False, "message": "Informe cliente e código da peça."}, status_code=400)
    with get_db() as con:
        customer = con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        if not customer:
            return JSONResponse({"ok": False, "message": "Cliente não encontrada."}, status_code=404)
        product = con.execute("SELECT * FROM products WHERE upper(code)=?", (code,)).fetchone()
        if not product:
            return JSONResponse({"ok": False, "message": f"Peça {code} não encontrada."}, status_code=404)
        if str(product["status"]) != "disponivel":
            return JSONResponse({"ok": False, "message": f"Peça {code} está com status {product['status']}."}, status_code=400)

        amount = amount_override if amount_override > 0 else _money_float(product["sale_price"], 0)
        result = _update_montante(
            con,
            customer_id=customer_id,
            movement_type="debito",
            amount=amount,
            product_id=int(product["id"]),
            code=code,
            origin="scan_montante",
            notes=f"Baixa por leitura/scan da peça {code}.",
        )

        sale_id, sale_code = create_sale_record(
            con,
            customer=str(customer["name"] or ""),
            payment_method="Montante consignado",
            discount=0,
            total=amount,
            paid=amount,
            customer_account_id=None,
            source="montante_cliente",
            source_ref_id=int(product["id"]),
        )
        con.execute("INSERT INTO sale_items(sale_id, product_id, price) VALUES(?,?,?)", (sale_id, int(product["id"]), amount))
        sold_time = now_iso()
        product_cols = table_columns(con, "products")
        if "sync_updated_at" in product_cols:
            con.execute("UPDATE products SET status='vendido', sold_at=?, sync_updated_at=? WHERE id=?", (sold_time, sold_time, int(product["id"])))
        else:
            con.execute("UPDATE products SET status='vendido', sold_at=? WHERE id=?", (sold_time, int(product["id"])))
        con.execute(
            "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
            (int(product["id"]), "venda_montante", f"Vendido via montante da cliente. Venda {sale_code}.", sold_time),
        )
    return JSONResponse({
        "ok": True,
        "message": f"Peça {code} debitada do montante.",
        "customer": row_to_dict(customer),
        "product": _product_public_dict(product),
        "sale_code": sale_code,
        **result,
    })


@app.get("/inventario-camera", response_class=HTMLResponse)
def inventario_camera_page(request: Request) -> Response:
    init_brechorisee_490_schema()
    with get_db() as con:
        open_sessions = con.execute(
            "SELECT * FROM inventory_scan_sessions WHERE status='aberta' ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
    return templates.TemplateResponse(
        "inventario_camera_360.html",
        {"request": request, "active": "inventario", "open_sessions": open_sessions},
    )


@app.post("/api/inventario/sessao")
async def api_inventario_sessao(request: Request) -> JSONResponse:
    init_brechorisee_490_schema()
    data = await _request_payload(request)
    title = str(data.get("title") or data.get("titulo") or f"Inventário {datetime.now().strftime('%d/%m/%Y %H:%M')}").strip()[:160]
    with get_db() as con:
        cur = con.execute(
            "INSERT INTO inventory_scan_sessions(title, status, notes, created_at) VALUES(?,?,?,?)",
            (title, "aberta", str(data.get("notes") or "")[:300], now_iso()),
        )
        session_id = int(cur.lastrowid)
    return JSONResponse({"ok": True, "session_id": session_id, "title": title})


@app.post("/api/inventario/escanear")
async def api_inventario_escanear(request: Request) -> JSONResponse:
    init_brechorisee_490_schema()
    data = await _request_payload(request)
    session_id = int(data.get("session_id") or 0)
    code = str(data.get("code") or data.get("codigo") or "").strip().upper()
    action = str(data.get("action") or "conferido").strip().lower()[:40]
    if not code:
        return JSONResponse({"ok": False, "message": "Informe o código lido."}, status_code=400)
    with get_db() as con:
        if session_id <= 0:
            cur = con.execute(
                "INSERT INTO inventory_scan_sessions(title, status, notes, created_at) VALUES(?,?,?,?)",
                (f"Inventário {datetime.now().strftime('%d/%m/%Y %H:%M')}", "aberta", "", now_iso()),
            )
            session_id = int(cur.lastrowid)
        product = con.execute("SELECT * FROM products WHERE upper(code)=?", (code,)).fetchone()
        found = 1 if product else 0
        previous_status = str(product["status"]) if product else ""
        new_status = previous_status
        product_id = int(product["id"]) if product else None
        if product and action in {"disponivel", "reservado", "vendido", "perdido", "manutencao"}:
            new_status = action
            cols = table_columns(con, "products")
            if "sync_updated_at" in cols:
                con.execute("UPDATE products SET status=?, sync_updated_at=? WHERE id=?", (new_status, now_iso(), product_id))
            else:
                con.execute("UPDATE products SET status=? WHERE id=?", (new_status, product_id))
            con.execute(
                "INSERT INTO inventory_events(product_id, event_type, notes, created_at) VALUES(?,?,?,?)",
                (product_id, "inventario_status", f"Status ajustado no inventário: {previous_status} -> {new_status}", now_iso()),
            )
        con.execute(
            """
            INSERT INTO inventory_scan_items(session_id, product_id, code, found, action, previous_status, new_status, notes, created_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (session_id, product_id, code, found, action, previous_status, new_status, str(data.get("notes") or "")[:300], now_iso()),
        )
        con.execute(
            """
            UPDATE inventory_scan_sessions
            SET scanned_count=scanned_count+1,
                found_count=found_count+?,
                missing_count=missing_count+?
            WHERE id=?
            """,
            (1 if found else 0, 0 if found else 1, session_id),
        )
    return JSONResponse({
        "ok": True,
        "session_id": session_id,
        "found": bool(found),
        "message": "Peça encontrada." if found else "Código não encontrado no estoque.",
        "product": _product_public_dict(product),
        "previous_status": previous_status,
        "new_status": new_status,
    })


@app.get("/api/inventario/sessao/{session_id}")
def api_inventario_sessao_detalhe(session_id: int) -> JSONResponse:
    init_brechorisee_490_schema()
    with get_db() as con:
        session = con.execute("SELECT * FROM inventory_scan_sessions WHERE id=?", (session_id,)).fetchone()
        if not session:
            return JSONResponse({"ok": False, "message": "Sessão não encontrada."}, status_code=404)
        items = con.execute(
            """
            SELECT i.*, p.title, p.sale_price, p.image_filename
            FROM inventory_scan_items i
            LEFT JOIN products p ON p.id=i.product_id
            WHERE i.session_id=?
            ORDER BY i.created_at DESC LIMIT 300
            """,
            (session_id,),
        ).fetchall()
    return JSONResponse({"ok": True, "session": row_to_dict(session), "items": [row_to_dict(i) for i in items]})


@app.get("/consultor-estilo", response_class=HTMLResponse)
def consultor_estilo_page(request: Request) -> Response:
    return templates.TemplateResponse("consultor_estilo_360.html", {"request": request, "active": "consultor_estilo"})


@app.get("/api/consultor-estilo/sugerir")
def api_consultor_estilo_sugerir(q: str = "", membro: str = "", tamanho: str = "", estilo: str = "", cor: str = "", limite: int = 12) -> JSONResponse:
    init_brechorisee_490_schema()
    limite = max(1, min(30, int(limite or 12)))
    with get_db() as con:
        customer = _find_customer_by_query(con, q)
    profiles = build_customer_intelligence()
    selected_profile = None
    if customer:
        cid = int(customer["id"])
        cname = str(customer["name"] or "").casefold()
        selected_profile = next((p for p in profiles if str(p.get("name") or "").casefold() == cname), None)
        if not selected_profile:
            selected_profile = {
                "name": str(customer["name"] or ""),
                "phone": customer["phone"],
                "instagram": customer["instagram"],
                "preferences": customer["preferences"],
                "notes": customer["notes"],
                "top_types": [],
                "top_styles": [],
                "top_colors": [],
                "top_sizes": [],
                "top_brands": [],
                "top_categories": [],
            }
    terms: list[str] = []
    for raw in [membro, tamanho, estilo, cor]:
        if raw:
            terms.extend([p.strip() for p in re.split(r"[,;/]", str(raw)) if p.strip()])
    if selected_profile:
        for field in ["preferences", "notes", "measurements"]:
            val = str(selected_profile.get(field) or "")
            terms.extend([p.strip() for p in re.split(r"[,;/\n]", val) if p.strip()][:8])
        for field in ["top_types", "top_styles", "top_colors", "top_sizes", "top_brands", "top_categories"]:
            for item in selected_profile.get(field, [])[:3]:
                label = str(item.get("label") or "").strip()
                if label:
                    terms.append(label)

    seen_terms: list[str] = []
    for t in terms:
        if t and t.casefold() not in {x.casefold() for x in seen_terms}:
            seen_terms.append(t)
    suggestions: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    if selected_profile:
        for row in suggested_products_for_customer(selected_profile, limit=limite):
            d = _product_public_dict(row)
            if d and int(d["id"]) not in seen_ids:
                d["score"] = _suggestion_score(d, seen_terms) + 2
                seen_ids.add(int(d["id"]))
                suggestions.append(d)

    for term in seen_terms[:10]:
        if len(suggestions) >= limite:
            break
        for row in search_products_rows(q=term, status="disponivel", limit=limite):
            d = _product_public_dict(row)
            if d and int(d["id"]) not in seen_ids:
                d["score"] = _suggestion_score(d, seen_terms)
                seen_ids.add(int(d["id"]))
                suggestions.append(d)
                if len(suggestions) >= limite:
                    break

    if not suggestions and q:
        for row in search_products_rows(q=q, status="disponivel", limit=limite):
            d = _product_public_dict(row)
            if d:
                suggestions.append(d)

    suggestions.sort(key=lambda item: item.get("score", 0), reverse=True)
    return JSONResponse({
        "ok": True,
        "customer": row_to_dict(customer) if customer else None,
        "profile": selected_profile,
        "terms": seen_terms[:20],
        "suggestions": suggestions[:limite],
        "message": "Sugestões geradas por histórico, preferências e termos informados. Não acessa Instagram privado.",
    })


@app.get("/sistema/checklist", response_class=HTMLResponse)
def sistema_checklist_page(request: Request) -> Response:
    return templates.TemplateResponse("sistema_checklist_360.html", {"request": request, "active": "checklist"})


@app.get("/api/sistema/checklist")
def api_sistema_checklist(request: Request) -> JSONResponse:
    checks: list[dict[str, Any]] = []
    def add(name: str, ok: bool, detail: str, fix: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "fix": fix})
    try:
        with get_db() as con:
            pc = con.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
            cc = con.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"]
            add("Banco de dados", True, f"OK. {pc} peça(s), {cc} cliente(s).")
    except Exception as exc:
        add("Banco de dados", False, f"Falha: {exc}", "Reinicie o servidor ou restaure backup em dados/brechorisee.db.")
    try:
        apk = brechorisee_customer_apk_path()
        ok, msg = validate_customer_apk_file(apk)
        add("APK Cliente público", ok, msg, "Compile pelo BAT no Windows e publique PACOTE_TERMUX_MINI novamente.")
    except Exception as exc:
        add("APK Cliente público", False, f"Falha ao validar: {exc}", "Recompile e publique APK novo.")
    try:
        public_url = get_public_server_url(request)
        placeholder = "SEU-LINK" in public_url.upper()
        add("Link público", bool(public_url and not placeholder), public_url or "sem link público", "Rode CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh com o link lhr.life real.")
    except Exception as exc:
        add("Link público", False, f"Falha: {exc}")
    try:
        init_brechorisee_490_schema()
        add("Módulos 360", True, "Tabelas de montante, inventário e estilo prontas.")
    except Exception as exc:
        add("Módulos 360", False, f"Falha de migração: {exc}", "Atualize o servidor para v4.9.0 e reinicie.")
    return JSONResponse({"ok": all(c["ok"] for c in checks), "version": APP_VERSION, "checks": checks, "generated_at": now_iso()})


# ============================================================
# BRECHORISEE v4.9.2 - Consignado profissional / montante 360
# ============================================================
# Camada incremental: não remove rotas antigas. Acrescenta fechamento, recibo,
# ajustes, devolução, pagamento parcial e relatório de saldo por cliente.

def init_brechorisee_492_schema() -> None:
    """Migração segura para o consignado profissional v4.9.2."""
    init_brechorisee_490_schema()
    with get_db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS consignado_closings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                opening_balance REAL NOT NULL DEFAULT 0,
                credit_total REAL NOT NULL DEFAULT 0,
                debit_total REAL NOT NULL DEFAULT 0,
                adjustment_total REAL NOT NULL DEFAULT 0,
                final_balance REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'aberto',
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_consignado_closings_customer
                ON consignado_closings(customer_id, created_at);
            """
        )


try:
    init_brechorisee_492_schema()
except Exception as exc:
    logger.warning("Falha ao inicializar consignado profissional v4.9.2: %s", exc)


def _consignado_customer_summary(con: sqlite3.Connection, customer_id: int) -> dict[str, Any]:
    customer = con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrada.")
    acc = _ensure_montante_account(con, customer_id)
    movements = con.execute(
        """
        SELECT m.*, p.title AS product_title, p.sale_price AS product_price, p.status AS product_status
        FROM customer_montante_movements m
        LEFT JOIN products p ON p.id=m.product_id
        WHERE m.customer_id=?
        ORDER BY m.created_at DESC
        LIMIT 300
        """,
        (customer_id,),
    ).fetchall()

    credit = sum(float(m["amount"] or 0) for m in movements if str(m["movement_type"]) == "credito")
    debit = sum(float(m["amount"] or 0) for m in movements if str(m["movement_type"]) == "debito")
    balance = float(acc["balance"] or 0)
    sold_items = [m for m in movements if m["product_id"] and str(m["movement_type"]) == "debito"]
    manual_items = [m for m in movements if not m["product_id"]]

    if balance > 0.009:
        status_label = "Saldo a favor da cliente"
        next_action = "A cliente ainda tem crédito para retirar peças ou receber acerto."
    elif balance < -0.009:
        status_label = "Saldo negativo"
        next_action = "Verifique se houve retirada acima do montante ou ajuste manual."
    else:
        status_label = "Fechado"
        next_action = "Montante zerado. Pode finalizar e arquivar o atendimento."

    return {
        "customer": row_to_dict(customer),
        "account": row_to_dict(acc),
        "credit_total": round(credit, 2),
        "debit_total": round(debit, 2),
        "balance": round(balance, 2),
        "sold_count": len(sold_items),
        "manual_count": len(manual_items),
        "status_label": status_label,
        "next_action": next_action,
        "movements": [row_to_dict(m) for m in movements],
    }


@app.get("/consignado-profissional", response_class=HTMLResponse)
def consignado_profissional_page(request: Request, q: str = "") -> Response:
    init_brechorisee_492_schema()
    with get_db() as con:
        customers = con.execute(
            """
            SELECT c.id, c.name, c.phone, c.instagram,
                   COALESCE(a.balance,0) AS balance,
                   COALESCE(a.credit_total,0) AS credit_total,
                   COALESCE(a.debit_total,0) AS debit_total
            FROM customers c
            LEFT JOIN customer_montante_accounts a ON a.customer_id=c.id
            WHERE (?='' OR lower(c.name) LIKE ? OR lower(COALESCE(c.instagram,'')) LIKE ? OR COALESCE(c.phone,'') LIKE ?)
            ORDER BY ABS(COALESCE(a.balance,0)) DESC, c.name
            LIMIT 120
            """,
            (q.strip().lower(), f"%{q.strip().lower()}%", f"%{q.strip().lower().replace('@','')}%", f"%{q.strip()}%"),
        ).fetchall()
        recent_closings = con.execute(
            """
            SELECT f.*, c.name AS customer_name
            FROM consignado_closings f
            LEFT JOIN customers c ON c.id=f.customer_id
            ORDER BY f.created_at DESC
            LIMIT 20
            """
        ).fetchall()
    return templates.TemplateResponse(
        "consignado_profissional_492.html",
        {"request": request, "active": "consignado", "customers": customers, "closings": recent_closings, "q": q},
    )


@app.get("/api/consignado-profissional/resumo/{customer_id}")
def api_consignado_profissional_resumo(customer_id: int) -> JSONResponse:
    init_brechorisee_492_schema()
    with get_db() as con:
        summary = _consignado_customer_summary(con, customer_id)
    return JSONResponse({"ok": True, **summary})


@app.post("/api/consignado-profissional/movimento")
async def api_consignado_profissional_movimento(request: Request) -> JSONResponse:
    init_brechorisee_492_schema()
    data = await _request_payload(request)
    customer_id = int(data.get("customer_id") or 0)
    movement_type = str(data.get("movement_type") or data.get("tipo") or "credito").strip().lower()
    amount = _money_float(data.get("amount") or data.get("valor"), 0)
    notes = str(data.get("notes") or data.get("observacao") or "").strip()[:500]
    if customer_id <= 0:
        return JSONResponse({"ok": False, "message": "Selecione uma cliente."}, status_code=400)
    if amount <= 0:
        return JSONResponse({"ok": False, "message": "Informe um valor maior que zero."}, status_code=400)

    if movement_type in {"devolucao", "pagamento_cliente", "acerto_credito", "credito"}:
        normalized = "credito"
        origin = movement_type
        default_note = "Entrada/acerto de montante."
    elif movement_type in {"retirada", "compra", "taxa", "acerto_debito", "debito"}:
        normalized = "debito"
        origin = movement_type
        default_note = "Saída/acerto de montante."
    else:
        return JSONResponse({"ok": False, "message": "Tipo de movimento inválido."}, status_code=400)

    with get_db() as con:
        customer = con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        if not customer:
            return JSONResponse({"ok": False, "message": "Cliente não encontrada."}, status_code=404)
        result = _update_montante(
            con,
            customer_id=customer_id,
            movement_type=normalized,
            amount=amount,
            origin=origin,
            notes=notes or default_note,
        )
        summary = _consignado_customer_summary(con, customer_id)
    return JSONResponse({"ok": True, "message": "Movimento registrado.", **result, "summary": summary})


@app.post("/api/consignado-profissional/fechamento")
async def api_consignado_profissional_fechamento(request: Request) -> JSONResponse:
    init_brechorisee_492_schema()
    data = await _request_payload(request)
    customer_id = int(data.get("customer_id") or 0)
    notes = str(data.get("notes") or data.get("observacao") or "").strip()[:800]
    if customer_id <= 0:
        return JSONResponse({"ok": False, "message": "Selecione uma cliente."}, status_code=400)

    with get_db() as con:
        summary = _consignado_customer_summary(con, customer_id)
        acc = summary["account"]
        customer = summary["customer"]
        cur = con.execute(
            """
            INSERT INTO consignado_closings(
                customer_id, opening_balance, credit_total, debit_total, adjustment_total,
                final_balance, status, notes, created_at
            )
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                customer_id,
                0,
                float(acc.get("credit_total") or 0),
                float(acc.get("debit_total") or 0),
                0,
                float(acc.get("balance") or 0),
                "fechado" if abs(float(acc.get("balance") or 0)) <= 0.009 else "pendente",
                notes,
                now_iso(),
            ),
        )
        closing_id = int(cur.lastrowid)
        summary = _consignado_customer_summary(con, customer_id)

    receipt = {
        "closing_id": closing_id,
        "customer_name": customer.get("name"),
        "customer_phone": customer.get("phone"),
        "instagram": customer.get("instagram"),
        "credit_total": summary["credit_total"],
        "debit_total": summary["debit_total"],
        "final_balance": summary["balance"],
        "status_label": summary["status_label"],
        "created_at": now_iso(),
        "notes": notes,
    }
    return JSONResponse({"ok": True, "message": "Fechamento gerado.", "receipt": receipt, "summary": summary})


@app.get("/consignado-profissional/recibo/{customer_id}", response_class=HTMLResponse)
def consignado_profissional_recibo(request: Request, customer_id: int) -> Response:
    init_brechorisee_492_schema()
    with get_db() as con:
        summary = _consignado_customer_summary(con, customer_id)
    return templates.TemplateResponse(
        "consignado_recibo_492.html",
        {"request": request, "summary": summary, "generated_at": now_iso()},
    )


@app.get("/api/chat/resposta-humanizada")
def api_chat_resposta_humanizada(
    intencao: str = "disponibilidade",
    peca: str = "",
    cliente: str = "",
    tamanho: str = "",
    cor: str = "",
    preco: str = "",
) -> JSONResponse:
    """Sugestões de respostas mais humanas para Admin usar no atendimento."""
    nome = cliente.strip() or "querida"
    peca_txt = peca.strip() or "essa peça"
    details = []
    if cor.strip():
        details.append(f"cor {cor.strip()}")
    if tamanho.strip():
        details.append(f"tamanho {tamanho.strip()}")
    if preco.strip():
        details.append(f"valor {preco.strip()}")
    extra = f" ({', '.join(details)})" if details else ""

    templates_reply = {
        "disponibilidade": f"{nome}, conferi aqui: {peca_txt}{extra} está disponível neste momento. Posso reservar para você agora?",
        "reserva": f"{nome}, posso reservar {peca_txt}{extra} para você. Me confirme por favor se prefere retirada ou entrega.",
        "pix": f"{nome}, pode enviar o comprovante por aqui. Assim que eu confirmar o pagamento, atualizo seu pedido e te aviso.",
        "entrega": f"{nome}, me envie seu endereço completo com bairro e CEP, ou me diga se prefere retirada. Eu te confirmo a melhor opção.",
        "indisponivel": f"{nome}, essa peça não está mais disponível, mas já posso procurar opções parecidas para você por cor, tamanho, estilo e faixa de preço.",
        "desejo": f"{nome}, registrei seu desejo. Quando entrar uma peça parecida no seu estilo, a loja consegue te avisar por aqui.",
    }
    reply = templates_reply.get(intencao, templates_reply["disponibilidade"])
    return JSONResponse({"ok": True, "reply": reply, "intencao": intencao})


# ============================================================
# BRECHORISEE v4.9.3 - INVENTARIO PROFISSIONAL + TELEGRAM
# Módulo incremental. Mantém compatibilidade com banco antigo.
# ============================================================

def init_brechorisee_493_schema() -> None:
    """Cria tabelas auxiliares do inventário profissional e Telegram sem quebrar versões antigas."""
    try:
        init_brechorisee_492_schema()
    except Exception:
        pass
    with get_db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS inventory_493_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                status TEXT NOT NULL DEFAULT 'aberta',
                operator_name TEXT,
                expected_total INTEGER DEFAULT 0,
                scanned_total INTEGER DEFAULT 0,
                missing_total INTEGER DEFAULT 0,
                extra_total INTEGER DEFAULT 0,
                duplicated_total INTEGER DEFAULT 0,
                notes TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS inventory_493_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                product_id INTEGER,
                product_title TEXT,
                product_status TEXT,
                scan_status TEXT NOT NULL DEFAULT 'ok',
                quantity INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'camera',
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES inventory_493_sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_inventory_493_scans_session
                ON inventory_493_scans(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_inventory_493_scans_code
                ON inventory_493_scans(code);

            CREATE TABLE IF NOT EXISTS inventory_493_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                product_id INTEGER,
                code TEXT,
                old_status TEXT,
                new_status TEXT,
                reason TEXT,
                operator_name TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS telegram_493_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT,
                payload TEXT,
                priority TEXT NOT NULL DEFAULT 'normal',
                status TEXT NOT NULL DEFAULT 'pendente',
                chat_id TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS telegram_493_inbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                username TEXT,
                first_name TEXT,
                text TEXT,
                command TEXT,
                payload TEXT,
                processed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS telegram_493_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )
        con.commit()


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "sim", "on", "ativo", "enabled"}


def _telegram_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _telegram_admin_chat_id() -> str:
    return os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()


def _telegram_allowed_chat_ids() -> set[str]:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    ids = {x.strip() for x in raw.replace(";", ",").split(",") if x.strip()}
    admin = _telegram_admin_chat_id()
    if admin:
        ids.add(admin)
    return ids


def _telegram_enabled() -> bool:
    return bool(_telegram_token()) and _env_bool("BRECHORISEE_TELEGRAM_SEND_REAL", False)


def _telegram_api_call(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = _telegram_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado")
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _telegram_keyboard(kind: str = "painel") -> dict[str, Any]:
    if kind == "inventario":
        rows = [
            [{"text": "📷 Inventário", "callback_data": "inventario_status"}, {"text": "⚠️ Divergências", "callback_data": "inventario_divergencias"}],
            [{"text": "📊 Resumo", "callback_data": "resumo"}, {"text": "🏠 Painel", "callback_data": "painel"}],
        ]
    elif kind == "atendimento":
        rows = [
            [{"text": "💬 Mensagens", "callback_data": "mensagens"}, {"text": "🛒 Reservas", "callback_data": "reservas"}],
            [{"text": "🔴 Live", "callback_data": "live"}, {"text": "🏠 Painel", "callback_data": "painel"}],
        ]
    else:
        rows = [
            [{"text": "📊 Resumo", "callback_data": "resumo"}, {"text": "📦 Estoque", "callback_data": "estoque"}],
            [{"text": "📷 Inventário", "callback_data": "inventario_status"}, {"text": "💰 Consignado", "callback_data": "consignado"}],
            [{"text": "💬 Chats", "callback_data": "mensagens"}, {"text": "🔴 Live", "callback_data": "live"}],
        ]
    return {"inline_keyboard": rows}


def _telegram_store_message(direction: str, chat_id: str, text: str, command: str = "", status: str = "pendente", payload: Any = None, error: str = "") -> None:
    try:
        with get_db() as con:
            con.execute(
                """INSERT INTO telegram_messages(direction, chat_id, text, command, payload, status, error, created_at, sent_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (direction, str(chat_id or ""), text, command, json.dumps(payload, ensure_ascii=False) if payload is not None else None, status, error, now_iso(), now_iso() if status == "enviado" else None),
            )
            con.commit()
    except Exception:
        pass


def telegram_send_message(text: str, chat_id: str | None = None, keyboard: dict[str, Any] | None = None, parse_mode: str = "") -> dict[str, Any]:
    init_brechorisee_493_schema()
    chat = str(chat_id or _telegram_admin_chat_id()).strip()
    if not chat:
        raise RuntimeError("TELEGRAM_ADMIN_CHAT_ID não configurado")
    payload = {"chat_id": chat, "text": text}
    if keyboard:
        payload["reply_markup"] = keyboard
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if not _telegram_enabled():
        _telegram_store_message("outbound", chat, text, status="simulado", payload=payload)
        return {"ok": True, "simulated": True, "payload": payload}
    try:
        res = _telegram_api_call("sendMessage", payload)
        _telegram_store_message("outbound", chat, text, status="enviado", payload=payload)
        return res
    except Exception as exc:
        _telegram_store_message("outbound", chat, text, status="erro", payload=payload, error=str(exc))
        raise


def telegram_queue_event(event_type: str, title: str, message: str, priority: str = "normal", payload: Any = None, send_now: bool = False) -> dict[str, Any]:
    init_brechorisee_493_schema()
    with get_db() as con:
        cur = con.execute(
            """INSERT INTO telegram_493_events(event_type, title, message, payload, priority, status, chat_id, created_at)
               VALUES (?, ?, ?, ?, ?, 'pendente', ?, ?)""",
            (event_type, title, message, json.dumps(payload, ensure_ascii=False) if payload is not None else None, priority, _telegram_admin_chat_id(), now_iso()),
        )
        event_id = cur.lastrowid
        con.commit()
    sent = None
    if send_now:
        try:
            sent = telegram_send_message(f"🔔 {title}\n\n{message}", keyboard=_telegram_keyboard("painel"))
            with get_db() as con:
                con.execute("UPDATE telegram_493_events SET status='enviado', sent_at=? WHERE id=?", (now_iso(), event_id))
                con.commit()
        except Exception as exc:
            with get_db() as con:
                con.execute("UPDATE telegram_493_events SET status='erro', error=? WHERE id=?", (str(exc), event_id))
                con.commit()
    return {"ok": True, "event_id": event_id, "sent": sent}


def _inventory493_get_session(con, session_id: int | None = None):
    if session_id:
        row = con.execute("SELECT * FROM inventory_493_sessions WHERE id=?", (session_id,)).fetchone()
        if row:
            return row
    row = con.execute("SELECT * FROM inventory_493_sessions WHERE status='aberta' ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        return row
    cur = con.execute(
        "INSERT INTO inventory_493_sessions(name, operator_name, started_at) VALUES (?, ?, ?)",
        (f"Inventário {datetime.now().strftime('%d/%m/%Y %H:%M')}", "BRECHORISEE", now_iso()),
    )
    con.commit()
    return con.execute("SELECT * FROM inventory_493_sessions WHERE id=?", (cur.lastrowid,)).fetchone()


def _inventory493_find_product(con, code: str):
    code = (code or "").strip()
    if not code:
        return None
    row = con.execute(
        """SELECT id, code, title, category, garment_type, size, color, sale_price, status, image_filename
           FROM products
           WHERE lower(code)=lower(?) OR lower(title)=lower(?)
           LIMIT 1""",
        (code, code),
    ).fetchone()
    if row:
        return row
    # busca aproximada quando a leitura veio parcial
    like = f"%{code}%"
    return con.execute(
        """SELECT id, code, title, category, garment_type, size, color, sale_price, status, image_filename
           FROM products
           WHERE lower(code) LIKE lower(?) OR lower(title) LIKE lower(?)
           ORDER BY id DESC LIMIT 1""",
        (like, like),
    ).fetchone()


def _inventory493_summary(con, session_id: int | None = None) -> dict[str, Any]:
    session = _inventory493_get_session(con, session_id)
    sid = int(session["id"])
    scans = con.execute("SELECT * FROM inventory_493_scans WHERE session_id=? ORDER BY created_at DESC LIMIT 50", (sid,)).fetchall()
    counts = con.execute(
        """SELECT scan_status, COUNT(*) total FROM inventory_493_scans
           WHERE session_id=? GROUP BY scan_status""",
        (sid,),
    ).fetchall()
    by_status = {r["scan_status"]: int(r["total"]) for r in counts}
    product_total = con.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
    available_total = con.execute("SELECT COUNT(*) c FROM products WHERE status='disponivel'").fetchone()["c"]
    return {
        "session": dict(session),
        "recent_scans": [dict(r) for r in scans],
        "counts": by_status,
        "product_total": int(product_total or 0),
        "available_total": int(available_total or 0),
        "scanned_total": sum(by_status.values()),
        "ok_total": by_status.get("ok", 0),
        "not_found_total": by_status.get("nao_encontrada", 0),
        "duplicate_total": by_status.get("duplicada", 0),
        "sold_seen_total": by_status.get("vendida_encontrada", 0),
    }


def _telegram_metrics() -> dict[str, Any]:
    init_brechorisee_493_schema()
    with get_db() as con:
        def count(sql: str, args: tuple = ()) -> int:
            try:
                row = con.execute(sql, args).fetchone()
                return int(row[0] or 0) if row else 0
            except Exception:
                return 0
        inv = _inventory493_summary(con)
        return {
            "messages_pending": count("SELECT COUNT(*) FROM chat_messages WHERE direction='inbound' AND created_at >= datetime('now','-1 day')"),
            "reservations_open": count("SELECT COUNT(*) FROM reservations WHERE status NOT IN ('cancelada','finalizada','entregue')"),
            "products_available": count("SELECT COUNT(*) FROM products WHERE status='disponivel'"),
            "products_new": count("SELECT COUNT(*) FROM products WHERE created_at >= datetime('now','-2 day')"),
            "live_active": count("SELECT COUNT(*) FROM live_sessions WHERE status='ativa'"),
            "orders_open": count("SELECT COUNT(*) FROM online_orders WHERE status NOT IN ('cancelado','entregue','finalizado')"),
            "consignado_open": count("SELECT COUNT(*) FROM customer_montante_accounts WHERE status='aberta'"),
            "inventory": inv,
            "telegram_enabled": _telegram_enabled(),
            "telegram_real_send": _env_bool("BRECHORISEE_TELEGRAM_SEND_REAL", False),
            "telegram_chat_configured": bool(_telegram_admin_chat_id()),
        }


def _telegram_status_text() -> str:
    m = _telegram_metrics()
    inv = m["inventory"]
    return (
        "📊 BRECHORISEE - Resumo agora\n\n"
        f"💬 Mensagens últimas 24h: {m['messages_pending']}\n"
        f"🛒 Reservas abertas: {m['reservations_open']}\n"
        f"📦 Peças disponíveis: {m['products_available']}\n"
        f"✨ Peças novas: {m['products_new']}\n"
        f"🔴 Lives ativas: {m['live_active']}\n"
        f"📋 Pedidos abertos: {m['orders_open']}\n"
        f"💰 Montantes abertos: {m['consignado_open']}\n\n"
        f"📷 Inventário atual: sessão #{inv['session']['id']}\n"
        f"Escaneadas: {inv['scanned_total']} | OK: {inv['ok_total']} | Não achadas: {inv['not_found_total']} | Duplicadas: {inv['duplicate_total']}"
    )


@app.get("/inventario-profissional", response_class=HTMLResponse)
def inventario_profissional_page(request: Request) -> HTMLResponse:
    init_brechorisee_493_schema()
    return templates.TemplateResponse("inventario_profissional_493.html", {"request": request})


@app.get("/inventario-profissional/relatorio/{session_id}", response_class=HTMLResponse)
def inventario_profissional_relatorio(request: Request, session_id: int) -> HTMLResponse:
    init_brechorisee_493_schema()
    with get_db() as con:
        summary = _inventory493_summary(con, session_id)
    return templates.TemplateResponse("inventario_relatorio_493.html", {"request": request, "summary": summary, "generated_at": now_iso()})


@app.post("/api/inventario-profissional/sessao")
async def api_inventario_profissional_sessao(request: Request) -> JSONResponse:
    init_brechorisee_493_schema()
    data = await request.json()
    name = (data.get("name") or f"Inventário {datetime.now().strftime('%d/%m/%Y %H:%M')}").strip()
    operator = (data.get("operator_name") or "BRECHORISEE").strip()
    with get_db() as con:
        cur = con.execute(
            "INSERT INTO inventory_493_sessions(name, operator_name, started_at, notes) VALUES (?, ?, ?, ?)",
            (name, operator, now_iso(), data.get("notes", "")),
        )
        con.commit()
        summary = _inventory493_summary(con, cur.lastrowid)
    return JSONResponse({"ok": True, "summary": summary})


@app.get("/api/inventario-profissional/resumo")
def api_inventario_profissional_resumo(session_id: int | None = None) -> JSONResponse:
    init_brechorisee_493_schema()
    with get_db() as con:
        summary = _inventory493_summary(con, session_id)
    return JSONResponse({"ok": True, "summary": summary})


@app.post("/api/inventario-profissional/scan")
async def api_inventario_profissional_scan(request: Request) -> JSONResponse:
    init_brechorisee_493_schema()
    data = await request.json()
    code = str(data.get("code") or "").strip()
    source = str(data.get("source") or "camera").strip()
    session_id = data.get("session_id")
    if not code:
        return JSONResponse({"ok": False, "error": "Informe ou escaneie um código."}, status_code=400)
    with get_db() as con:
        session = _inventory493_get_session(con, int(session_id) if session_id else None)
        sid = int(session["id"])
        product = _inventory493_find_product(con, code)
        duplicate_count = con.execute("SELECT COUNT(*) c FROM inventory_493_scans WHERE session_id=? AND lower(code)=lower(?)", (sid, code)).fetchone()["c"]
        scan_status = "ok"
        product_id = None
        title = ""
        pstatus = ""
        if not product:
            scan_status = "nao_encontrada"
        else:
            product_id = int(product["id"])
            title = product["title"]
            pstatus = product["status"]
            if duplicate_count:
                scan_status = "duplicada"
            elif str(pstatus).lower() in {"vendido", "vendida", "cancelado", "excluido"}:
                scan_status = "vendida_encontrada"
        con.execute(
            """INSERT INTO inventory_493_scans(session_id, code, product_id, product_title, product_status, scan_status, source, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sid, code, product_id, title, pstatus, scan_status, source, data.get("notes", ""), now_iso()),
        )
        con.execute(
            """UPDATE inventory_493_sessions SET
               scanned_total=(SELECT COUNT(*) FROM inventory_493_scans WHERE session_id=?),
               missing_total=(SELECT COUNT(*) FROM inventory_493_scans WHERE session_id=? AND scan_status='nao_encontrada'),
               duplicated_total=(SELECT COUNT(*) FROM inventory_493_scans WHERE session_id=? AND scan_status='duplicada')
               WHERE id=?""",
            (sid, sid, sid, sid),
        )
        con.commit()
        summary = _inventory493_summary(con, sid)
    if scan_status in {"nao_encontrada", "vendida_encontrada", "duplicada"}:
        try:
            telegram_queue_event("inventario_alerta", "Alerta no inventário", f"Código {code}: {scan_status.replace('_',' ')}", priority="alta", send_now=False)
        except Exception:
            pass
    return JSONResponse({"ok": True, "scan_status": scan_status, "product": dict(product) if product else None, "summary": summary})


@app.post("/api/inventario-profissional/ajustar-status")
async def api_inventario_profissional_ajustar_status(request: Request) -> JSONResponse:
    init_brechorisee_493_schema()
    data = await request.json()
    code = str(data.get("code") or "").strip()
    new_status = str(data.get("new_status") or "").strip()
    reason = str(data.get("reason") or "Ajuste por inventário").strip()
    if not code or not new_status:
        return JSONResponse({"ok": False, "error": "Informe código e novo status."}, status_code=400)
    with get_db() as con:
        product = _inventory493_find_product(con, code)
        if not product:
            return JSONResponse({"ok": False, "error": "Peça não encontrada."}, status_code=404)
        old_status = product["status"]
        con.execute("UPDATE products SET status=? WHERE id=?", (new_status, product["id"]))
        con.execute(
            """INSERT INTO inventory_493_adjustments(session_id, product_id, code, old_status, new_status, reason, operator_name, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (data.get("session_id"), product["id"], product["code"], old_status, new_status, reason, data.get("operator_name", "BRECHORISEE"), now_iso()),
        )
        con.commit()
    try:
        telegram_queue_event("estoque_ajuste", "Status de peça ajustado", f"{product['code']} - {product['title']}\n{old_status} → {new_status}\nMotivo: {reason}", send_now=False)
    except Exception:
        pass
    return JSONResponse({"ok": True, "old_status": old_status, "new_status": new_status, "product": dict(product)})


@app.post("/api/inventario-profissional/fechar")
async def api_inventario_profissional_fechar(request: Request) -> JSONResponse:
    init_brechorisee_493_schema()
    data = await request.json()
    session_id = int(data.get("session_id") or 0)
    with get_db() as con:
        summary = _inventory493_summary(con, session_id if session_id else None)
        sid = int(summary["session"]["id"])
        con.execute("UPDATE inventory_493_sessions SET status='fechada', finished_at=?, notes=? WHERE id=?", (now_iso(), data.get("notes", ""), sid))
        con.commit()
        summary = _inventory493_summary(con, sid)
    try:
        telegram_queue_event("inventario_fechado", "Inventário fechado", f"Sessão #{sid} fechada.\nEscaneadas: {summary['scanned_total']}\nDivergências: {summary['not_found_total'] + summary['duplicate_total']}", send_now=True)
    except Exception:
        pass
    return JSONResponse({"ok": True, "summary": summary, "report_url": f"/inventario-profissional/relatorio/{sid}"})


@app.get("/telegram", response_class=HTMLResponse)
def telegram_dashboard_page(request: Request) -> HTMLResponse:
    init_brechorisee_493_schema()
    return templates.TemplateResponse("telegram_dashboard_493.html", {"request": request, "enabled": _telegram_enabled()})


@app.get("/api/telegram/status")
def api_telegram_status() -> JSONResponse:
    return JSONResponse({"ok": True, "metrics": _telegram_metrics(), "text": _telegram_status_text()})


@app.post("/api/telegram/enviar")
async def api_telegram_enviar(request: Request) -> JSONResponse:
    data = await request.json()
    text = str(data.get("text") or "").strip()
    chat_id = str(data.get("chat_id") or _telegram_admin_chat_id()).strip()
    with_buttons = bool(data.get("buttons", True))
    if not text:
        return JSONResponse({"ok": False, "error": "Informe a mensagem."}, status_code=400)
    res = telegram_send_message(text, chat_id=chat_id, keyboard=_telegram_keyboard("painel") if with_buttons else None)
    return JSONResponse({"ok": True, "result": res})


@app.post("/api/telegram/teste")
def api_telegram_teste() -> JSONResponse:
    msg = _telegram_status_text()
    res = telegram_send_message(msg, keyboard=_telegram_keyboard("painel"))
    return JSONResponse({"ok": True, "result": res})


@app.post("/api/telegram/avisar")
async def api_telegram_avisar(request: Request) -> JSONResponse:
    data = await request.json()
    title = str(data.get("title") or "Aviso BRECHORISEE").strip()
    message = str(data.get("message") or "").strip()
    priority = str(data.get("priority") or "normal").strip()
    send_now = bool(data.get("send_now", True))
    if not message:
        return JSONResponse({"ok": False, "error": "Informe a mensagem do aviso."}, status_code=400)
    return JSONResponse(telegram_queue_event("manual", title, message, priority=priority, payload=data, send_now=send_now))


@app.get("/api/telegram/eventos")
def api_telegram_eventos(limit: int = 50) -> JSONResponse:
    init_brechorisee_493_schema()
    with get_db() as con:
        rows = con.execute("SELECT * FROM telegram_493_events ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 200),)).fetchall()
    return JSONResponse({"ok": True, "events": [dict(r) for r in rows]})


@app.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> JSONResponse:
    init_brechorisee_493_schema()
    expected = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if expected and not hmac.compare_digest(secret, expected):
        raise HTTPException(status_code=403, detail="Webhook inválido")
    update = await request.json()
    message = update.get("message") or update.get("edited_message") or {}
    callback = update.get("callback_query") or {}
    if callback:
        message = callback.get("message") or {}
        text = callback.get("data") or ""
    else:
        text = message.get("text") or ""
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    allowed = _telegram_allowed_chat_ids()
    if allowed and chat_id not in allowed:
        _telegram_store_message("inbound", chat_id, text, command="bloqueado", status="bloqueado", payload=update)
        return JSONResponse({"ok": True, "ignored": True})
    command = text.split()[0].lower() if text.startswith("/") else text.lower().strip()
    with get_db() as con:
        con.execute(
            """INSERT INTO telegram_493_inbox(chat_id, username, first_name, text, command, payload, processed, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (chat_id, chat.get("username"), chat.get("first_name"), text, command, json.dumps(update, ensure_ascii=False), now_iso()),
        )
        con.commit()
    reply = _telegram_status_text()
    keyboard_kind = "painel"
    if command in {"/start", "/menu", "painel"}:
        reply = "👋 BRECHORISEE conectado.\nEscolha uma opção:"
    elif command in {"/estoque", "estoque"}:
        m = _telegram_metrics()
        reply = f"📦 Estoque\nDisponíveis: {m['products_available']}\nPeças novas: {m['products_new']}"
    elif command in {"/inventario", "inventario_status"}:
        m = _telegram_metrics()
        inv = m["inventory"]
        reply = f"📷 Inventário sessão #{inv['session']['id']}\nEscaneadas: {inv['scanned_total']}\nOK: {inv['ok_total']}\nNão achadas: {inv['not_found_total']}\nDuplicadas: {inv['duplicate_total']}"
        keyboard_kind = "inventario"
    elif command in {"/ajuda", "ajuda"}:
        reply = "Comandos: /resumo, /estoque, /inventario, /live, /consignado, /mensagens, /ajuda"
    try:
        telegram_send_message(reply, chat_id=chat_id, keyboard=_telegram_keyboard(keyboard_kind))
    except Exception:
        pass
    return JSONResponse({"ok": True})


@app.post("/api/telegram/webhook/configurar")
def api_telegram_webhook_configurar() -> JSONResponse:
    base_url = os.getenv("BRECHORISEE_PUBLIC_BASE_URL") or os.getenv("PUBLIC_BASE_URL") or ""
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not base_url or not secret:
        return JSONResponse({"ok": False, "error": "Configure PUBLIC_BASE_URL e TELEGRAM_WEBHOOK_SECRET no .env."}, status_code=400)
    webhook_url = base_url.rstrip("/") + f"/telegram/webhook/{secret}"
    if not _telegram_enabled():
        return JSONResponse({"ok": True, "simulated": True, "webhook_url": webhook_url, "message": "Telegram em modo simulado ou token ausente."})
    res = _telegram_api_call("setWebhook", {"url": webhook_url})
    return JSONResponse({"ok": True, "webhook_url": webhook_url, "result": res})


@app.get("/api/telegram/comandos")
def api_telegram_comandos() -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "commands": [
            {"command": "/start", "description": "Abrir painel BRECHORISEE"},
            {"command": "/resumo", "description": "Resumo geral"},
            {"command": "/estoque", "description": "Resumo do estoque"},
            {"command": "/inventario", "description": "Inventário por câmera/QR"},
            {"command": "/live", "description": "Status da live"},
            {"command": "/consignado", "description": "Montantes e consignado"},
            {"command": "/mensagens", "description": "Chats e atendimentos"},
            {"command": "/ajuda", "description": "Ajuda"},
        ],
    })
