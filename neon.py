"""Compact CustomTkinter desktop UI. Ingest and persistence stay in app.py."""
import math
import time
import tkinter as tk
from pathlib import Path
from datetime import datetime
import customtkinter as ctk
from PIL import Image, ImageDraw
import app as core

BG = "#0e101b"
PANEL = "#191c2b"
FIELD = "#101320"
LINE = "#3d405b"
TEXT = "#f6f4ff"
MUTED = "#a5a8bf"
PURPLE = "#9416e3"
CYAN = "#13e6d4"


def icon(kind, color=TEXT, size=32):
    im = Image.new("RGBA", (64, 64))
    d = ImageDraw.Draw(im)
    if kind == "logo":
        for i in range(6):
            a = i * math.pi / 3
            pts = [(32 + r * math.cos(a + t), 30 + r * math.sin(a + t))
                   for r, t in [(29, 0), (29, .92), (12, 1.4), (12, .45)]]
            d.polygon(pts, fill=["#e398ff", "#c365f6", "#a441ec", "#8624df", "#6921c4", "#ac52ed"][i])
        d.polygon([(42, 32), (52, 32), (52, 47), (61, 47), (47, 62), (33, 47), (42, 47)], fill=CYAN)
    elif kind == "jpg":
        d.rounded_rectangle((6, 10, 58, 54), 5, outline=color, width=4)
        d.ellipse((16, 18, 24, 26), fill=color)
        d.line([(9, 47), (27, 30), (37, 40), (45, 31), (56, 46)], fill=color, width=4)
    elif kind == "raw":
        d.rounded_rectangle((5, 18, 59, 53), 6, outline=color, width=4)
        d.rectangle((18, 10, 36, 18), fill=color)
        d.ellipse((23, 24, 45, 46), outline=color, width=4)
    elif kind == "video":
        d.rounded_rectangle((5, 15, 43, 50), 5, outline=color, width=4)
        d.polygon([(47, 25), (60, 17), (60, 49), (47, 41)], fill=color)
        d.polygon([(19, 24), (19, 42), (32, 33)], fill=color)
    elif kind == "audio":
        for x, h in [(10, 12), (21, 30), (32, 48), (43, 32), (54, 16)]:
            d.line((x, 32-h/2, x, 32+h/2), fill=color, width=5)
    elif kind == "disk":
        d.polygon([(16, 13), (48, 13), (58, 43), (6, 43)], outline=color, width=4)
        d.rounded_rectangle((6, 40, 58, 54), 3, outline=color, width=4)
        d.ellipse((44, 45, 48, 49), fill=color)
    elif kind == "card":
        d.line([(12, 57), (12, 18), (23, 7), (50, 7), (54, 12), (54, 57), (12, 57)], fill=color, width=4)
        for x in (24, 33, 42):
            d.line((x, 14, x, 27), fill=color, width=4)
        d.line((33, 32, 33, 48), fill=color, width=4)
        d.line([(24, 41), (33, 50), (42, 41)], fill=color, width=4)
    else:
        d.line((32, 9, 32, 43), fill=color, width=4)
        d.line([(19, 32), (32, 45), (45, 32)], fill=color, width=4)
        d.line([(10, 43), (10, 56), (54, 56), (54, 43)], fill=color, width=4)
    return ctk.CTkImage(im, im, size=(size, size))


class Button(ctk.CTkButton):
    # The engine uses Tk's config spelling.
    def config(self, **kw):
        return self.configure(**kw)


class Meter(ctk.CTkProgressBar):
    """Keep byte-valued engine progress separate from CTk's normalized value."""
    def __init__(self, master, maximum=100, changed=None, **kw):
        super().__init__(master, height=12, fg_color="#343b57", progress_color=CYAN, **kw)
        self.maximum, self.value, self.changed = maximum, 0, changed
        self.set(0)

    def __setitem__(self, key, value):
        if key == "maximum":
            self.maximum = value
        elif key == "value":
            self.value = value
        else:
            raise KeyError(key)
        self.set(max(0, min(1, self.value / max(1, self.maximum))))
        if self.changed:
            self.changed()

    def __getitem__(self, key):
        return {"value": self.value, "maximum": self.maximum}[key]


class QueueRows(ctk.CTkScrollableFrame):
    """Selectable queue rows with a Listbox-compatible controller boundary."""
    def __init__(self, master):
        super().__init__(master, fg_color=PANEL, height=100, corner_radius=0)
        self.items, self.states, self.selected = [], {}, None
        self.redraw()

    def insert(self, where, text):
        self.items.append(text)
        self.redraw()

    def delete(self, first, last=None):
        if last == "end":
            self.items.clear()
        else:
            del self.items[int(first)]
        self.states.clear()
        self.selected = None
        self.redraw()

    def curselection(self):
        return () if self.selected is None else (self.selected,)

    def choose(self, idx):
        self.selected = idx
        self.redraw()

    def redraw(self):
        for w in self.winfo_children():
            w.destroy()
        if not self.items:
            ctk.CTkLabel(self, text="Nenhum cartão na fila. Escolha a origem e adicione um cartão.",
                         text_color=MUTED, font=("Segoe UI", 13)).pack(pady=22)
        for i, item in enumerate(self.items):
            source, _, prof = item.rpartition("  |  ")
            row = ctk.CTkFrame(self, fg_color="#2b1b44" if i == self.selected else FIELD,
                               corner_radius=9, border_width=1,
                               border_color="#b94aff" if i == self.selected else LINE)
            row.pack(fill="x", pady=3)
            row.grid_columnconfigure(2, weight=1)
            state = self.states.get(i, "Aguardando")
            for col, (text, width, color) in enumerate([
                (str(i+1), 32, MUTED), (prof, 175, TEXT), (source, 100, MUTED),
                (state, 180, CYAN if state == "Conferido" else TEXT)
            ]):
                label = ctk.CTkLabel(row, text=text, width=width, anchor="w", text_color=color,
                                     font=("Segoe UI", 13, "bold" if col == 1 else "normal"))
                label.grid(row=0, column=col, sticky="ew", padx=10, pady=8)
                label.bind("<Button-1>", lambda e, n=i: self.choose(n))
            row.bind("<Button-1>", lambda e, n=i: self.choose(n))


def frame(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=13, border_width=1, border_color=LINE, **kw)


def label(parent, text="", size=14, color=TEXT, bold=False, **kw):
    return ctk.CTkLabel(parent, text=text, text_color=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kw)


def button(parent, text, command, primary=False, **kw):
    return Button(parent, text=text, command=command, height=38, corner_radius=9,
                  fg_color=PURPLE if primary else "#232337", hover_color="#6b219f",
                  border_width=1, border_color="#c54aff" if primary else "#696181",
                  font=("Segoe UI", 14, "bold"), **kw)


def entry(parent, variable, **kw):
    return ctk.CTkEntry(parent, textvariable=variable, height=36, fg_color=FIELD,
                        border_color=LINE, text_color=TEXT, font=("Segoe UI", 14), **kw)


class NeonApp(core.App):
    def _build(self):
        ctk.set_appearance_mode("dark")
        self.root.configure(**({"fg_color": BG} if isinstance(self.root, ctk.CTk) else {"bg": BG}))
        self.root.geometry("1440x900")
        self.root.minsize(1180, 780)
        cfg = self.config
        strings = {"theme": "escuro", "date": datetime.now().strftime("%Y-%m-%d"),
                   "event": cfg.get("event", ""), "source": "", "mode": cfg.get("mode", "equipe"),
                   "prof": (cfg.get("professionals") or ["Fotografo_01"])[0],
                   "base": cfg.get("base", r"D:\Eventos"), "external": cfg.get("external_base", ""),
                   "progress": "0%", "status": "Pronto para analisar um cartão.", "space": "Analise o cartão para medir o espaço.",
                   "space_copy": "Analise o cartão para medir o espaço.", "preview": "A análise aparecerá aqui.",
                   "current_file": "Nenhum arquivo em processamento", "rate": "Ritmo: —", "eta": "Tempo restante: —"}
        for name, value in strings.items():
            setattr(self, name + "_var", tk.StringVar(self.root, value=value))
        for name, key, default in [("copy_enabled", "copy_enabled", True), ("copy_jpg", "copy_jpg", True),
                                   ("copy_video", "copy_video", True), ("copy_raw", "copy_raw", True),
                                   ("copy_audio", "copy_audio", True), ("hash", "verify_hash", False),
                                   ("event_locked", "event_locked", False)]:
            setattr(self, name + "_var", tk.BooleanVar(self.root, value=cfg.get(key, default)))
        self._started_at = None
        self._active_queue_index = None
        self._queue_run = False
        self._build_header()
        shell = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        shell.pack(fill="both", expand=True)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(1, weight=1)
        side = ctk.CTkFrame(shell, width=206, fg_color="#111321", corner_radius=0)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(6, weight=1)
        self.nav = {}
        for row, (key, text) in enumerate([("ingest", "↓   Descarregar"), ("queue", "☷   Fila de cartões"),
                                           ("history", "◷   Histórico"), ("reports", "▤   Relatórios"),
                                           ("settings", "⚙   Configurações")]):
            b = button(side, text, lambda k=key: self.show_page(k), width=182, anchor="w")
            b.grid(row=row, column=0, padx=12, pady=(18 if row == 0 else 6, 6), sticky="ew")
            self.nav[key] = b
        label(side, "●  ARQUIVOS PRESERVADOS", 11, CYAN, True).grid(row=7, column=0, padx=12, pady=(10, 0))
        label(side, "Copia e confere.\nNunca apaga seu cartão.", 12, MUTED, justify="left").grid(row=8, column=0, padx=12, pady=(4, 22))
        host = ctk.CTkFrame(shell, fg_color=BG, corner_radius=0)
        host.grid(row=0, column=1, sticky="nsew", padx=16, pady=(0, 14))
        host.grid_rowconfigure(1, weight=1)
        host.grid_columnconfigure(0, weight=1)
        self._build_event(host)
        self.pages = {}
        for key in ("ingest", "settings", "history", "reports"):
            page = ctk.CTkFrame(host, fg_color=BG, corner_radius=0)
            page.grid(row=1, column=0, sticky="nsew")
            self.pages[key] = page
        self._build_ingest(self.pages["ingest"])
        self._build_settings(self.pages["settings"])
        self._build_history(self.pages["history"])
        self._build_reports(self.pages["reports"])
        for var in (self.event_var, self.date_var, self.prof_var):
            var.trace_add("write", lambda *_: self._refresh_header())
        self.copy_enabled_var.trace_add("write", lambda *_: self._toggle_copy_options())
        self.status_var.trace_add("write", lambda *_: self._status_changed())
        self.source_var.trace_add("write", lambda *_: self._invalidate_scan())
        self._toggle_mode()
        self._apply_event_lock()
        self._toggle_copy_options()
        self._refresh_disks()
        self.show_page("ingest")

    def _build_header(self):
        top = ctk.CTkFrame(self.root, fg_color="#121321", corner_radius=0, height=86)
        top.pack(fill="x")
        label(top, image=icon("logo", size=60), width=68).pack(side="left", padx=(20, 10), pady=10)
        label(top, "Editor\nAssistente", 25, bold=True, justify="left").pack(side="left", padx=(0, 28))
        ctk.CTkFrame(top, width=1, height=46, fg_color=LINE).pack(side="left", padx=(0, 24))
        title = ctk.CTkFrame(top, fg_color="transparent")
        title.pack(side="left", fill="x", expand=True)
        label(title, "Gestão de Cartões para Eventos", 22, bold=True).pack(anchor="w")
        label(title, "Descarga, organização e backup de foto, vídeo, RAW e áudio", 13, MUTED).pack(anchor="w")
        label(top, f"v{core.VERSION}", 12, "#d497ff", True).pack(side="right", padx=24)

    def _build_event(self, host):
        bar = frame(host)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        bar.grid_columnconfigure(2, weight=1)
        label(bar, "Evento", 14, MUTED).grid(row=0, column=0, padx=(14, 8), pady=12)
        self.ent_date = entry(bar, self.date_var, width=116)
        self.ent_date.grid(row=0, column=1, padx=4)
        self.ent_event = entry(bar, self.event_var, placeholder_text="Nome do evento")
        self.ent_event.grid(row=0, column=2, sticky="ew", padx=6)
        self.btn_lock_event = button(bar, "Travar evento", self._toggle_event_lock, width=125)
        self.btn_lock_event.grid(row=0, column=3, padx=6)
        self.btn_open = button(bar, "Abrir pasta", self.open_event, width=115)
        self.btn_open.grid(row=0, column=4, padx=(6, 12))

    def _build_ingest(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        upper = ctk.CTkFrame(page, fg_color=BG)
        upper.grid(row=0, column=0, sticky="nsew")
        upper.grid_columnconfigure(1, weight=1)
        origin = frame(upper, width=262)
        origin.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        origin.grid_columnconfigure(0, weight=1)
        label(origin, "Origem e identificação", 17, bold=True, image=icon("card", "#cd73f9", 27), compound="left").grid(row=0, column=0, padx=16, pady=(16, 12), sticky="w")
        label(origin, "Cartão / pasta de origem", 13).grid(row=1, column=0, padx=16, sticky="w")
        entry(origin, self.source_var, width=235).grid(row=2, column=0, sticky="ew", padx=16, pady=(5, 8))
        picks = ctk.CTkFrame(origin, fg_color="transparent")
        picks.grid(row=3, column=0, padx=16, sticky="ew")
        button(picks, "Procurar", self._pick_source, width=108).pack(side="left")
        button(picks, "Cartões", self._pick_removable, width=108).pack(side="right")
        self.prof_label = label(origin, "Profissional", 13)
        self.prof_label.grid(row=4, column=0, padx=16, pady=(14, 4), sticky="w")
        self.prof_combo = ctk.CTkComboBox(origin, variable=self.prof_var, values=["Fotografo_01"], height=36,
                                         fg_color=FIELD, border_color=LINE, button_color=LINE, font=("Segoe UI", 14))
        self.prof_combo.grid(row=5, column=0, padx=16, sticky="ew")
        label(origin, "Modo de operação", 13).grid(row=6, column=0, padx=16, pady=(14, 4), sticky="w")
        self.mode_combo = ctk.CTkComboBox(origin, variable=self.mode_var, values=["equipe", "multicam"],
                                         state="readonly", height=36, fg_color=FIELD, border_color=LINE,
                                         button_color=LINE, command=lambda _: self._toggle_mode())
        self.mode_combo.grid(row=7, column=0, padx=16, sticky="ew")
        self.btn_scan = button(origin, "Analisar cartão", self.analyze, primary=True)
        self.btn_scan.grid(row=8, column=0, sticky="ew", padx=16, pady=(22, 10))
        button(origin, "+ Adicionar à fila", self.add_to_queue).grid(row=9, column=0, sticky="ew", padx=16, pady=(0, 16))
        right = ctk.CTkFrame(upper, fg_color=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        media = ctk.CTkFrame(right, fg_color=BG)
        media.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self.media_labels = {}
        for i, (kind, title, color) in enumerate([("jpg", "JPG", "#42f24a"), ("raw", "RAW", "#23adff"),
                                                   ("video", "Vídeos", "#ce51f6"), ("audio", "Áudio", "#f6c24a")]):
            media.grid_columnconfigure(i, weight=1, uniform="media")
            tile = ctk.CTkFrame(media, fg_color=PANEL, border_color=color, border_width=1, corner_radius=12)
            tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            label(tile, image=icon(kind, color, 28), width=30).pack(side="left", padx=(10, 5))
            values = ctk.CTkFrame(tile, fg_color="transparent")
            values.pack(side="left", fill="x", expand=True, pady=10)
            label(values, title, 16, bold=True).pack(anchor="w")
            count = label(values, "— arquivos", 13)
            count.pack(anchor="w")
            size = label(values, "Não analisado", 11, MUTED)
            size.pack(anchor="w")
            self.media_labels[kind] = count, size
        progress = ctk.CTkFrame(right, fg_color="#19172b", border_color="#b642ef", border_width=2, corner_radius=15)
        progress.grid(row=1, column=0, sticky="nsew", pady=(0, 14))
        progress.grid_columnconfigure(1, weight=1)
        label(progress, image=icon("card", "#d153ff", 66), width=82).grid(row=0, column=0, rowspan=4, padx=(10, 4), pady=18)
        self.phase_label = label(progress, "Pronto para descarregar", 23, bold=True, anchor="w")
        self.phase_label.grid(row=0, column=1, columnspan=2, sticky="ew", padx=12, pady=(18, 6))
        self.progress = Meter(progress, changed=self._telemetry)
        self.progress.grid(row=1, column=1, sticky="ew", padx=12, pady=8)
        label(progress, textvariable=self.progress_var, size=22, bold=True, width=65).grid(row=1, column=2, padx=(0, 14))
        label(progress, textvariable=self.current_file_var, size=13, anchor="w", wraplength=500).grid(row=2, column=1, columnspan=2, sticky="ew", padx=12, pady=3)
        stats = ctk.CTkFrame(progress, fg_color="transparent")
        stats.grid(row=3, column=1, columnspan=2, sticky="ew", padx=12, pady=(4, 14))
        label(stats, textvariable=self.rate_var, size=12, color=MUTED).pack(side="left")
        label(stats, textvariable=self.eta_var, size=12, color=MUTED).pack(side="right", padx=8)
        disks = ctk.CTkFrame(right, fg_color=BG)
        disks.grid(row=2, column=0, sticky="ew")
        for i in range(3):
            disks.grid_columnconfigure(i, weight=1, uniform="disks")
        for i, (title, pathvar, textvar, attr) in enumerate([
            ("Destino primário", self.base_var, self.space_var, "space_bar"),
            ("Destino das cópias", self.external_var, self.space_copy_var, "space_copy_bar")
        ]):
            box = frame(disks)
            box.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            label(box, title, 14, bold=True, image=icon("disk", TEXT, 24), compound="left").pack(anchor="w", padx=12, pady=(12, 0))
            label(box, textvariable=pathvar, size=12, color=MUTED, wraplength=220, anchor="w").pack(fill="x", padx=12)
            meter = Meter(box)
            meter.configure(progress_color="#42e85c")
            meter.pack(fill="x", padx=12, pady=7)
            setattr(self, attr, meter)
            label(box, textvariable=textvar, size=11, color=MUTED, wraplength=220, justify="left", anchor="w").pack(fill="x", padx=12, pady=(0, 10))
        safety = frame(disks)
        safety.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        for text, var in [("Cópias de segurança", self.copy_enabled_var), ("Verificação SHA-256", self.hash_var)]:
            ctk.CTkSwitch(safety, text=text, variable=var, progress_color=CYAN, button_color="#ffffff",
                          font=("Segoe UI", 12), switch_width=34).pack(anchor="w", padx=12, pady=(16, 4))
        button(safety, "Definir destinos", lambda: self.show_page("settings")).pack(fill="x", padx=12, pady=10)
        queuebox = frame(page)
        queuebox.grid(row=1, column=0, sticky="nsew", pady=14)
        queuebox.grid_columnconfigure(0, weight=1)
        queuebox.grid_rowconfigure(1, weight=1)
        self.queue_title = label(queuebox, "Fila de cartões (0)", 17, bold=True)
        self.queue_title.grid(row=0, column=0, sticky="w", padx=16, pady=10)
        tools = ctk.CTkFrame(queuebox, fg_color="transparent")
        tools.grid(row=0, column=1, padx=12, pady=8)
        button(tools, "Remover", self.remove_from_queue, width=90).pack(side="left", padx=4)
        button(tools, "Limpar fila", self.clear_queue, width=100).pack(side="left", padx=4)
        self.queue_list = QueueRows(queuebox)
        self.queue_list.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=(0, 6))
        footer = ctk.CTkFrame(page, fg_color=BG)
        footer.grid(row=2, column=0, sticky="ew")
        self.btn_copy = button(footer, "Descarregar cartão", self.start_copy, primary=True, image=icon("download", size=25), compound="left")
        self.btn_copy.pack(side="left", fill="x", expand=True, padx=(0, 10), ipady=8)
        self.btn_queue = button(footer, "Descarregar fila", self.start_queue)
        self.btn_queue.pack(side="left", padx=(0, 10), ipady=8)
        self.btn_eject = button(footer, "Ejetar com segurança", self.eject_card, state="disabled")
        self.btn_eject.pack(side="left", padx=(0, 10), ipady=8)
        button(footer, "Ver relatório", lambda: self.show_page("reports")).pack(side="right", ipady=8)
        label(page, textvariable=self.status_var, size=12, color=MUTED, anchor="w").grid(row=3, column=0, sticky="ew", pady=(8, 0))

    def _build_settings(self, page):
        label(page, "Destinos e segurança", 25, bold=True).pack(anchor="w", pady=(8, 20))
        for title, var, cmd in [("Pasta primária · 01 / 03 / 05 / 07", self.base_var, self._pick_base),
                                 ("Pasta das cópias · 02 / 04 / 06 / 08", self.external_var, self._pick_external)]:
            box = frame(page)
            box.pack(fill="x", pady=8)
            label(box, title, 16, bold=True).pack(anchor="w", padx=20, pady=(16, 10))
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=(0, 18))
            entry(row, var).pack(side="left", fill="x", expand=True, padx=(0, 12))
            button(row, "Procurar", cmd).pack(side="right")
        self.copies_frame = ctk.CTkFrame(page, fg_color=PANEL)
        self.copies_frame.pack(fill="x", pady=12)
        label(self.copies_frame, "Tipos incluídos nas cópias", 17, bold=True).pack(anchor="w", padx=20, pady=12)
        for text, var in [("JPG · 02", self.copy_jpg_var), ("Vídeo · 04", self.copy_video_var),
                           ("RAW · 06", self.copy_raw_var), ("Áudio · 08", self.copy_audio_var)]:
            ctk.CTkCheckBox(self.copies_frame, text=text, variable=var, fg_color=PURPLE).pack(side="left", padx=20, pady=16)
        self._hash_frame = ctk.CTkFrame(page, fg_color="transparent")
        self._hash_frame.pack(fill="x", pady=12)
        label(self._hash_frame, "Sem pasta de cópias definida, as cópias ficam no primário.\nSHA-256 confere o conteúdo; sem essa opção, a comparação usa tamanho.",
              14, MUTED, justify="left").pack(anchor="w")
        button(page, "Salvar configurações", self._save_current_config, primary=True).pack(anchor="w", pady=20)

    def _build_history(self, page):
        label(page, "Histórico de descargas", 25, bold=True).pack(anchor="w", pady=(8, 20))
        self.checklist_list = tk.Listbox(page, bg=PANEL, fg=TEXT, selectbackground="#5e287e", borderwidth=0,
                                        highlightthickness=0, font=("Segoe UI", 12), height=12)
        self.checklist_list.pack(fill="both", expand=True)
        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x", pady=16)
        button(row, "Atualizar", self.refresh_checklist).pack(side="left", padx=(0, 12))
        button(row, "Marcar cartão devolvido", self.mark_returned_selected).pack(side="left")

    def _build_reports(self, page):
        label(page, "Análise e relatórios", 25, bold=True).pack(anchor="w", pady=(8, 16))
        analysis = ctk.CTkScrollableFrame(page, fg_color=PANEL, height=190)
        analysis.pack(fill="x", pady=(0, 12))
        label(analysis, textvariable=self.preview_var, size=13, wraplength=900, justify="left", anchor="w").pack(fill="x", padx=12, pady=12)
        self.log = ctk.CTkTextbox(page, fg_color=FIELD, text_color=TEXT, font=("Consolas", 12))
        self.log.pack(fill="both", expand=True)
        button(page, "Abrir pasta dos relatórios", self.open_event).pack(anchor="w", pady=14)

    def show_page(self, key):
        actual = "ingest" if key == "queue" else key
        self.pages[actual].tkraise()
        self.active_page = actual
        for name, b in self.nav.items():
            b.configure(fg_color=PURPLE if name == key else "transparent",
                        border_color="#c54aff" if name == key else "#111321")
        if key == "history":
            self.refresh_checklist()
        if key == "queue":
            self.queue_list.focus_set()
        if key == "ingest":
            self._refresh_disks()

    def _refresh_header(self):
        pass  # Event fields remain visible on every page.

    def _apply_theme(self):
        ctk.set_appearance_mode("dark")

    def _toggle_theme(self):
        self._apply_theme()

    def _toggle_mode(self):
        super()._toggle_mode()
        self.prof_label.configure(text="Câmera" if self.mode_var.get() == "multicam" else "Profissional")

    def _apply_event_lock(self):
        super()._apply_event_lock()
        locked = self.event_locked_var.get()
        self.btn_lock_event.configure(text="Evento travado" if locked else "Travar evento",
                                      text_color="#ffd15a" if locked else TEXT)

    def _toggle_copy_options(self):
        if not hasattr(self, "copies_frame"):
            return
        if self.copy_enabled_var.get():
            self.copies_frame.pack(fill="x", pady=12, before=self._hash_frame)
        else:
            self.copies_frame.pack_forget()
            self.space_copy_var.set("Cópias desligadas")
            self.space_copy_bar["value"] = 0

    def _invalidate_scan(self):
        if self.copying:
            return
        self.scan = []
        for count, size in self.media_labels.values():
            count.configure(text="— arquivos")
            size.configure(text="Não analisado")
        self.last_success = False
        self.btn_eject.configure(state="disabled")

    def analyze(self):
        if self.copying:
            return
        super().analyze()
        from dashboard import update_media_cards
        update_media_cards(self, core.fmt_bytes)
        for count, _size in self.media_labels.values():
            count.configure(text=f"{count.cget('text')} arquivos")
        self._refresh_disks()

    def _refresh_disks(self):
        import shutil
        for path, text, meter in [(self.base_var.get(), self.space_var, self.space_bar),
                                  (self.external_var.get() or self.base_var.get(), self.space_copy_var, self.space_copy_bar)]:
            try:
                p = Path(path)
                while not p.exists() and p.parent != p:
                    p = p.parent
                usage = shutil.disk_usage(p)
                text.set(f"{core.fmt_bytes(usage.free)} livres de {core.fmt_bytes(usage.total)}")
                meter["value"] = 100 * usage.free / max(1, usage.total)
            except OSError:
                text.set("Unidade indisponível")
                meter["value"] = 0
        if not self.copy_enabled_var.get():
            self.space_copy_var.set("Cópias desligadas")
            self.space_copy_bar["value"] = 0

    def _status_changed(self):
        status = self.status_var.get()
        if self.copying:
            title = "Descarga em andamento…"
        elif status.startswith("Concluído"):
            title = "Concluído com falhas" if "falhas" in status else "Descarga concluída"
        elif "interrompida" in status:
            title = "Descarga interrompida"
        elif "Análise pronta" in status:
            title = "Cartão analisado"
        else:
            title = "Pronto para descarregar"
        self.phase_label.configure(text=title)
        if not self.copying:
            self.eta_var.set("Tempo restante: —")
            self.btn_queue.configure(state="normal")
            if "interrompida" in status and self._active_queue_index is not None:
                self.queue_list.states[self._active_queue_index] = "Interrompido"
                self.queue_list.redraw()
            self._refresh_disks()

    def _telemetry(self):
        if not self.copying or not self._started_at:
            return
        elapsed = time.monotonic() - self._started_at
        if elapsed < .2 or self.progress.value <= 0:
            return
        rate = self.progress.value / elapsed
        self.rate_var.set(f"Processados: {core.fmt_bytes(rate)}/s")
        seconds = max(0, int((self.progress.maximum - self.progress.value) / rate))
        self.eta_var.set(f"Estimativa: {seconds // 60:02d}:{seconds % 60:02d}")

    def _log(self, msg):
        super()._log(msg)
        if msg.startswith("Arquivo: "):
            self.current_file_var.set(msg[9:])

    def _start_jobs(self, jobs):
        if self.copying:
            return
        self._started_at = time.monotonic()
        self.rate_var.set("Processados: —")
        self.eta_var.set("Estimativa: —")
        super()._start_jobs(jobs)
        if self.copying:
            self.btn_queue.configure(state="disabled")
            self.show_page("ingest")

    def start_copy(self):
        if self.copying:
            return
        self._queue_run = False
        self._active_queue_index = None
        super().start_copy()

    def start_queue(self):
        if self.copying:
            return
        self._queue_run = True
        self._active_queue_index = None
        self.queue_list.states.clear()
        self.queue_list.redraw()
        super().start_queue()

    def _on_job_state(self, payload):
        source, prof, state = payload
        if not self._queue_run:
            return
        if state == "Copiando":
            candidates = [i for i, item in enumerate(self.queue_items)
                          if item == (source, prof) and i not in self.queue_list.states]
            self._active_queue_index = candidates[0] if candidates else None
        if self._active_queue_index is not None:
            self.queue_list.states[self._active_queue_index] = state
            self.queue_list.redraw()

    def add_to_queue(self):
        if not self.copying:
            super().add_to_queue()
            self.queue_title.configure(text=f"Fila de cartões ({len(self.queue_items)})")

    def remove_from_queue(self):
        if not self.copying:
            super().remove_from_queue()
            self.queue_title.configure(text=f"Fila de cartões ({len(self.queue_items)})")

    def clear_queue(self):
        if not self.copying:
            super().clear_queue()
            self.queue_title.configure(text="Fila de cartões (0)")
