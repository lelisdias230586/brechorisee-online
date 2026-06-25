from __future__ import annotations
import socket
import tkinter as tk
from pathlib import Path

PORT = 8000

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"

def main():
    ip = get_lan_ip()
    link = f"http://{ip}:{PORT}/apk"
    root = tk.Tk()
    root.title("BRECHORISEE - QR Code APK")
    tk.Label(root, text="BRECHORISEE - baixar app cliente", font=("Arial", 14, "bold")).pack(padx=20, pady=10)
    try:
        import qrcode
        from PIL import ImageTk
        img = qrcode.make(link).resize((360, 360))
        photo = ImageTk.PhotoImage(img)
        lbl = tk.Label(root, image=photo)
        lbl.image = photo
        lbl.pack(padx=20, pady=10)
    except Exception as exc:
        tk.Label(root, text=f"QR Code indisponivel: {exc}", wraplength=420).pack(padx=20, pady=10)
    entry = tk.Entry(root, width=60)
    entry.insert(0, link)
    entry.pack(padx=20, pady=10)
    def copy():
        root.clipboard_clear()
        root.clipboard_append(link)
    tk.Button(root, text="Copiar link", command=copy).pack(pady=8)
    tk.Label(root, text="O servidor precisa estar ligado no notebook/celular.", wraplength=420).pack(padx=20, pady=10)
    root.mainloop()

if __name__ == "__main__":
    main()
