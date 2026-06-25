from __future__ import annotations

import socket


def get_lan_ip() -> str:
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


if __name__ == "__main__":
    ip = get_lan_ip()
    print()
    print("==============================================")
    print(" brechorisee aberto")
    print(" Computador: http://127.0.0.1:8000")
    print(f" Celular:    http://{ip}:8000")
    print(f" App Android: usar este endereco no app -> http://{ip}:8000")
    print(" Ajuda:      http://127.0.0.1:8000/celular")
    print(" Android:    http://127.0.0.1:8000/android")
    print("==============================================")
    print()
    print("Para usar no celular: conecte o celular no mesmo Wi-Fi e abra o endereço acima.")
    print("Fotos usam a camera do celular/app. O banco fica local no computador e o app acessa pela rede Wi-Fi.")
    print()
