"""Presentation layer; all ingest commands remain owned by app.App."""
import customtkinter as ctk
from tkinter import ttk


def mount_sidebar(app):
    ctk.set_appearance_mode("dark")
    side = ctk.CTkFrame(app.root, width=210, corner_radius=0, fg_color="#101622")
    side.pack(side="left", fill="y")
    side.pack_propagate(False)
    ctk.CTkLabel(side, text="EDITOR\nASSISTENTE", font=("Segoe UI", 23, "bold"),
                 anchor="w", justify="left").pack(padx=22, pady=(32, 4), anchor="w")
    ctk.CTkLabel(side, text="ESTÚDIO DE INGESTÃO · 2.0", text_color="#94a3b8",
                 font=("Segoe UI", 10)).pack(padx=22, pady=(0, 30), anchor="w")
    for title, target in [("Visão geral", "header_frame"), ("Evento e origens", "ent_event"),
                          ("Discos e cópias", "card_p_frame"), ("Fila de cartões", "queue_list"),
                          ("Histórico e registro", "checklist_list")]:
        ctk.CTkButton(side, text=title, anchor="w", height=42, fg_color="transparent",
                      hover_color="#263449", command=lambda t=target: scroll_to(app, t)).pack(
                          fill="x", padx=12, pady=4)
    ctk.CTkLabel(side, text="Copia. Confere. Organiza.\nSeu cartão é preservado.",
                 text_color="#94a3b8", justify="left").pack(side="bottom", padx=20, pady=25)


def scroll_to(app, target):
    app.root.update_idletasks()
    widget = getattr(app, target)
    frame = app.header_frame.master
    y = widget.winfo_rooty() - frame.winfo_rooty()
    app._canvas.yview_moveto(max(0, y - 16) / max(1, frame.winfo_height()))


def mount_media_cards(app, parent):
    panel = ctk.CTkFrame(parent, fg_color="transparent")
    panel.pack(fill="x", pady=(0, 16))
    app.media_labels = {}
    for col, (kind, title, color) in enumerate([
        ("jpg", "JPG", "#60a5fa"), ("raw", "RAW", "#c084fc"),
        ("video", "VÍDEO", "#fb923c"), ("audio", "ÁUDIO", "#2dd4bf")
    ]):
        panel.grid_columnconfigure(col, weight=1, uniform="media")
        card = ctk.CTkFrame(panel, fg_color="#1b2535", corner_radius=14)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0))
        ctk.CTkLabel(card, text=title, text_color=color, font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=18, pady=(12, 0))
        count = ctk.CTkLabel(card, text="—", font=("Segoe UI", 28, "bold"))
        count.pack(anchor="w", padx=18)
        size = ctk.CTkLabel(card, text="Aguardando análise", text_color="#94a3b8")
        size.pack(anchor="w", padx=18, pady=(0, 12))
        app.media_labels[kind] = (count, size)


def update_media_cards(app, fmt_bytes):
    for kind, (count, size) in app.media_labels.items():
        entries = [s for _p, k, s in app.scan if k == kind]
        count.configure(text=str(len(entries)))
        size.configure(text=fmt_bytes(sum(entries)))


def polish_styles(root):
    style = ttk.Style(root)
    style.configure(".", font=("Segoe UI", 10))
    style.configure("TButton", padding=(12, 8), borderwidth=0)
    style.map("TButton", background=[("active", "#334155"), ("disabled", "#263244")],
              foreground=[("disabled", "#94a3b8")])
    style.map("Accent.TButton", background=[("active", "#15803d"), ("disabled", "#263244")])
    style.configure("TEntry", padding=7)
    style.configure("TCombobox", padding=7)
    style.map("TCombobox", fieldbackground=[("readonly", "#253247")],
              foreground=[("readonly", "#f8fafc")])
