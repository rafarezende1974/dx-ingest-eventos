#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
DX Ingest Eventos v1.0.0 — protótipo
Descarga de cartões em eventos, para Windows.

Regras da v1 (confirmadas pelo Rafael em 2026-10-28):
- Tudo normalmente na unidade D:, reservada para isso.
- JPG  -> pasta de sincronização com o 2º editor + cópia na mesma unidade
- Vídeo -> pasta de sincronização (outra, diferente da de fotos) + cópia
- RAW  -> só pasta de backup
- Copia, NUNCA move. Não apaga nem formata o cartão.
- Não sobe nada para o Drive por conta própria: só deixa os arquivos
  nas pastas de sincronização; a ferramenta de sync existente faz o resto.
- Subpasta por profissional, para não sobrescrever DSC_0001 de outro
  fotógrafo/cinegrafista.
- Ao final, confere por quantidade e tamanho e gera relatório.

Estrutura criada por evento:
  <base>\<AAAA-MM-DD>_<Nome do evento>\
    01_Fotos_JPG_Sincronizar\<Profissional>\
    02_Fotos_JPG_Copia\<Profissional>\
    03_Videos_Sincronizar\<Profissional>\
    04_Videos_Copia\<Profissional>\
    05_RAW_Backup\<Profissional>\
    relatorio-descarga.txt
"""

import os
import re
import shutil
import threading
import queue
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

VERSION = "1.0.0"

JPG_EXTS = {".jpg", ".jpeg"}
RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".raf", ".dng", ".rw2",
            ".orf", ".pef", ".x3f", ".3fr", ".mos", ".erf"}
VIDEO_EXTS = {".mp4", ".mov", ".mxf", ".mts", ".m2ts", ".avi",
              ".wmv", ".mkv", ".mpg", ".mpeg"}

FOLDERS = {
    "jpg_sync": "01_Fotos_JPG_Sincronizar",
    "jpg_copy": "02_Fotos_JPG_Copia",
    "video_sync": "03_Videos_Sincronizar",
    "video_copy": "04_Videos_Copia",
    "raw_backup": "05_RAW_Backup",
}


def classify(path):
    ext = Path(path).suffix.lower()
    if ext in JPG_EXTS:
        return "jpg"
    if ext in RAW_EXTS:
        return "raw"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def sanitize(name):
    """Deixa um nome seguro para pasta no Windows."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name.strip())
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name).strip("._")
    return name or "Sem_nome"


def event_folder(base, date_str, event_name):
    return Path(base) / f"{date_str}_{sanitize(event_name)}"


def scan_source(source):
    """Varre o cartão recursivamente. Retorna (arquivos, outros)."""
    source = Path(source)
    files = []  # (caminho, tipo, tamanho)
    others = 0
    for root, _dirs, names in os.walk(source):
        for name in sorted(names):
            p = Path(root) / name
            try:
                size = p.stat().st_size
            except OSError:
                continue
            kind = classify(p)
            if kind is None:
                others += 1
            else:
                files.append((p, kind, size))
    return files, others


def destinations_for(event_root, professional):
    prof = sanitize(professional)
    return {
        "jpg_sync": event_root / FOLDERS["jpg_sync"] / prof,
        "jpg_copy": event_root / FOLDERS["jpg_copy"] / prof,
        "video_sync": event_root / FOLDERS["video_sync"] / prof,
        "video_copy": event_root / FOLDERS["video_copy"] / prof,
        "raw_backup": event_root / FOLDERS["raw_backup"] / prof,
    }


def needed_bytes(files, copy_jpg=True, copy_video=True):
    total = 0
    for _p, kind, size in files:
        if kind == "jpg":
            total += size * (2 if copy_jpg else 1)
        elif kind == "video":
            total += size * (2 if copy_video else 1)
        else:  # raw: só 1 destino
            total += size
    return total


def free_space_for(path):
    """Espaço livre no ancestral existente mais próximo."""
    p = Path(path)
    while not p.exists():
        if p.parent == p:
            return None
        p = p.parent
    try:
        return shutil.disk_usage(str(p)).free
    except OSError:
        return None


def resolve_destination(dest_dir, filename):
    """
    Retorna (destino_final, ação).
    ação = 'new' (não existe), 'skip' (já existe idêntico em tamanho),
    ou novo nome com sufixo _1, _2... se existe com tamanho diferente
    (nunca sobrescreve).
    """
    dest = dest_dir / filename
    if not dest.exists():
        return dest, "new"
    try:
        return dest, "skip"  # tratado pelo chamador, que compara tamanhos
    except OSError:
        return dest, "new"


def copy_one(src, dest_dir):
    """Copia um arquivo com verificação por tamanho. Retorna ação."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    src_size = src.stat().st_size
    dest = dest_dir / src.name
    if dest.exists():
        try:
            if dest.stat().st_size == src_size:
                return "skipped", dest
        except OSError:
            pass
        # Mesmo nome, conteúdo diferente: não sobrescreve, cria sufixo.
        # Se o sufixo já existir com o mesmo tamanho, é a mesma cópia:
        # pula (isso deixa a 2ª descarga idempotente).
        stem, suffix = src.stem, src.suffix
        i = 1
        while True:
            dest = dest_dir / f"{stem}_{i}{suffix}"
            if not dest.exists():
                break
            try:
                if dest.stat().st_size == src_size:
                    return "skipped", dest
            except OSError:
                pass
            i += 1
    shutil.copy2(str(src), str(dest))
    try:
        if dest.stat().st_size != src_size:
            try:
                dest.unlink()
            except OSError:
                pass
            return "failed", dest
    except OSError:
        return "failed", dest
    return "copied", dest


def run_copy(files, dests, copy_jpg=True, copy_video=True, log=None):
    """Executa a cópia. Retorna relatório (dict)."""
    report = {"copied": 0, "skipped": 0, "failed": 0, "errors": []}

    def emit(msg):
        if log:
            log(msg)

    for src, kind, _size in files:
        if kind == "jpg":
            targets = [dests["jpg_sync"]]
            if copy_jpg:
                targets.append(dests["jpg_copy"])
        elif kind == "video":
            targets = [dests["video_sync"]]
            if copy_video:
                targets.append(dests["video_copy"])
        else:
            targets = [dests["raw_backup"]]
        for dest_dir in targets:
            try:
                action, _dest = copy_one(src, dest_dir)
            except Exception as exc:  # noqa: BLE001 - relatório, não quebra
                action = "failed"
                report["errors"].append(f"{src.name} -> {dest_dir}: {exc}")
                emit(f"FALHOU: {src.name} -> {dest_dir.name} ({exc})")
            if action == "copied":
                report["copied"] += 1
            elif action == "skipped":
                report["skipped"] += 1
            else:
                report["failed"] += 1
                if not any(src.name in e and str(dest_dir) in e for e in report["errors"]):
                    report["errors"].append(f"{src.name} -> {dest_dir} (tamanho divergente após cópia)")
    return report


def write_report(event_root, professional, source, files, report):
    event_root.mkdir(parents=True, exist_ok=True)
    path = event_root / "relatorio-descarga.txt"
    counts = {}
    for _p, kind, _s in files:
        counts[kind] = counts.get(kind, 0) + 1
    lines = [
        "",
        "=" * 60,
        f"Descarga: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Profissional: {professional}",
        f"Origem (cartão): {source}",
        f"Evento: {event_root}",
        f"Encontrados: JPG={counts.get('jpg', 0)} "
        f"RAW={counts.get('raw', 0)} Vídeo={counts.get('video', 0)}",
        f"Resultado: copiados={report['copied']} "
        f"pulados (já existiam)={report['skipped']} "
        f"falhas={report['failed']}",
    ]
    if report["errors"]:
        lines.append("Falhas:")
        lines.extend(f"  - {e}" for e in report["errors"][:50])
    lines.append("Obs.: cópia, não move. Cartão NÃO foi apagado/formatado.")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"DX Ingest Eventos v{VERSION}")
        root.geometry("760x640")
        root.minsize(680, 560)
        self.scan = []
        self.others = 0
        self.msg_queue = queue.Queue()
        self.copying = False
        self._build()

    # ---------- interface ----------
    def _build(self):
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root)
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frm, text="1) Cartão / pasta de origem").pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.source_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.source_var).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(row, text="Procurar...", command=self._pick_source).pack(side="left", **pad)

        ttk.Label(frm, text="2) Evento").pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(row, textvariable=self.date_var, width=14).pack(side="left", **pad)
        self.event_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.event_var).pack(side="left", fill="x", expand=True, **pad)
        ttk.Label(row, text="(ex.: Fenalaw 2026)").pack(side="left", **pad)

        ttk.Label(frm, text="3) Profissional (vira subpasta)").pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.prof_var = tk.StringVar(value="Fotografo_01")
        ttk.Entry(row, textvariable=self.prof_var).pack(side="left", fill="x", expand=True, **pad)
        ttk.Label(row, text="ex.: Fotografo_01, Cinegrafista_01").pack(side="left", **pad)

        ttk.Label(frm, text="4) Pasta base de destino (normalmente D:\\Eventos)").pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.base_var = tk.StringVar(value=r"D:\Eventos")
        ttk.Entry(row, textvariable=self.base_var).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(row, text="Procurar...", command=self._pick_base).pack(side="left", **pad)

        opts = ttk.Frame(frm)
        opts.pack(fill="x", pady=4)
        self.copy_jpg_var = tk.BooleanVar(value=True)
        self.copy_video_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Fazer cópia do JPG (02)", variable=self.copy_jpg_var).pack(side="left", **pad)
        ttk.Checkbutton(opts, text="Fazer cópia do vídeo (04)", variable=self.copy_video_var).pack(side="left", **pad)

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=6)
        self.btn_scan = ttk.Button(btns, text="Analisar cartão", command=self.analyze)
        self.btn_scan.pack(side="left", **pad)
        self.btn_copy = ttk.Button(btns, text="Descarregar", command=self.start_copy)
        self.btn_copy.pack(side="left", **pad)
        self.btn_open = ttk.Button(btns, text="Abrir pasta do evento", command=self.open_event)
        self.btn_open.pack(side="left", **pad)

        self.preview_var = tk.StringVar(value="Clique em “Analisar cartão” para ver o que será copiado.")
        ttk.Label(frm, textvariable=self.preview_var, wraplength=720, justify="left").pack(anchor="w", fill="x")

        self.progress = ttk.Progressbar(frm, mode="determinate")
        self.progress.pack(fill="x", pady=6)

        ttk.Label(frm, text="Registro").pack(anchor="w")
        self.log = tk.Text(frm, height=14, wrap="word")
        self.log.pack(fill="both", expand=True)
        scroll = ttk.Scrollbar(frm, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)

    # ---------- ações ----------
    def _pick_source(self):
        d = filedialog.askdirectory(title="Escolha o cartão / pasta de origem")
        if d:
            self.source_var.set(d)

    def _pick_base(self):
        d = filedialog.askdirectory(title="Escolha a pasta base de destino")
        if d:
            self.base_var.set(d)

    def _log(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def _event_root(self):
        try:
            datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d")
        except ValueError:
            raise ValueError("Data inválida. Use o formato AAAA-MM-DD.")
        return event_folder(self.base_var.get().strip(), self.date_var.get().strip(),
                            self.event_var.get().strip())

    def analyze(self):
        source = self.source_var.get().strip()
        if not source or not Path(source).is_dir():
            messagebox.showerror("Origem", "Escolha uma pasta de origem válida (o cartão).")
            return
        try:
            root = self._event_root()
        except ValueError as exc:
            messagebox.showerror("Evento", str(exc))
            return
        # Evita copiar a pasta dentro dela mesma.
        try:
            if Path(source).resolve() == root.resolve() or root.resolve() in Path(source).resolve().parents \
                    or Path(source).resolve() in root.resolve().parents:
                messagebox.showerror("Origem", "A pasta de destino não pode ficar dentro do cartão, nem o contrário.")
                return
        except OSError:
            pass
        self.scan, self.others = scan_source(source)
        counts = {}
        for _p, kind, _s in self.scan:
            counts[kind] = counts.get(kind, 0) + 1
        need = needed_bytes(self.scan, self.copy_jpg_var.get(), self.copy_video_var.get())
        free = free_space_for(self.base_var.get().strip())
        free_txt = fmt_bytes(free) if free is not None else "não foi possível verificar"
        ok = "OK — cabe no destino." if free is None or free >= need else "ATENÇÃO — pode faltar espaço em D:!"
        self.preview_var.set(
            f"Encontrados: JPG={counts.get('jpg', 0)}  RAW={counts.get('raw', 0)}  "
            f"Vídeo={counts.get('video', 0)}  Outros ignorados={self.others}\n"
            f"Total a copiar (com as cópias): {fmt_bytes(need)}  •  Livre: {free_txt}  •  {ok}\n"
            f"Destino: {root}"
        )
        self._log(f"Análise: {counts} | outros={self.others} | a copiar={fmt_bytes(need)} | livre={free_txt}")

    def start_copy(self):
        if self.copying:
            return
        if not self.scan:
            self.analyze()
            if not self.scan:
                messagebox.showinfo("Nada para copiar", "Nenhum JPG, RAW ou vídeo encontrado no cartão.")
                return
        try:
            root = self._event_root()
        except ValueError as exc:
            messagebox.showerror("Evento", str(exc))
            return
        need = needed_bytes(self.scan, self.copy_jpg_var.get(), self.copy_video_var.get())
        free = free_space_for(self.base_var.get().strip())
        if free is not None and free < need:
            if not messagebox.askyesno("Espaço", f"Espaço livre ({fmt_bytes(free)}) é menor que o necessário "
                                                 f"({fmt_bytes(need)}). Continuar mesmo assim?"):
                return
        self.copying = True
        self.btn_copy.config(state="disabled")
        self.btn_scan.config(state="disabled")
        self.progress["maximum"] = max(1, len(self.scan))
        self.progress["value"] = 0
        dests = destinations_for(root, self.prof_var.get())
        files = list(self.scan)
        source = self.source_var.get().strip()
        prof = self.prof_var.get().strip()

        def worker():
            done = 0
            report = {"copied": 0, "skipped": 0, "failed": 0, "errors": []}
            for src, kind, _size in files:
                if kind == "jpg":
                    targets = [dests["jpg_sync"]]
                    if self.copy_jpg_var.get():
                        targets.append(dests["jpg_copy"])
                elif kind == "video":
                    targets = [dests["video_sync"]]
                    if self.copy_video_var.get():
                        targets.append(dests["video_copy"])
                else:
                    targets = [dests["raw_backup"]]
                for dest_dir in targets:
                    try:
                        action, _d = copy_one(src, dest_dir)
                    except Exception as exc:  # noqa: BLE001
                        action = "failed"
                        report["errors"].append(f"{src.name}: {exc}")
                    if action == "copied":
                        report["copied"] += 1
                    elif action == "skipped":
                        report["skipped"] += 1
                    else:
                        report["failed"] += 1
                done += 1
                self.msg_queue.put(("progress", done))
            report_path = write_report(root, prof, source, files, report)
            self.msg_queue.put(("done", (report, report_path)))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(200, self._poll)

    def _poll(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "progress":
                    self.progress["value"] = payload
                elif kind == "done":
                    report, report_path = payload
                    self.copying = False
                    self.btn_copy.config(state="normal")
                    self.btn_scan.config(state="normal")
                    self._log(f"Concluído: copiados={report['copied']} pulados={report['skipped']} "
                              f"falhas={report['failed']} | relatório: {report_path}")
                    if report["failed"] == 0:
                        messagebox.showinfo(
                            "Descarga concluída",
                            f"Copiados: {report['copied']}\nPulados (já existiam): {report['skipped']}\n"
                            f"Falhas: 0\n\nO cartão NÃO foi apagado.\nDepois de conferir as pastas, "
                            "você pode ejetá-lo e formatá-lo manualmente, se quiser.")
                    else:
                        messagebox.showwarning(
                            "Descarga com falhas",
                            f"Copiados: {report['copied']}\nPulados: {report['skipped']}\n"
                            f"Falhas: {report['failed']}\n\nNÃO ejete/formate o cartão ainda. "
                            f"Veja o relatório em:\n{report_path}")
                    return
        except queue.Empty:
            pass
        if self.copying:
            self.root.after(200, self._poll)

    def open_event(self):
        try:
            root = self._event_root()
        except ValueError as exc:
            messagebox.showerror("Evento", str(exc))
            return
        root.mkdir(parents=True, exist_ok=True)
        os.startfile(str(root)) if os.name == "nt" else None
        if os.name != "nt":
            self._log(f"Pasta do evento: {root}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
