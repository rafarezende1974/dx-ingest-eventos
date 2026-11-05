#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Editor Assistente — descarga de cartões em eventos
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

Estrutura criada por evento (v1.3, numeração global):
  Primário, em <base>\<AAAA-MM-DD>_<Nome do evento>\
    01_Fotos_JPG\<Profissional>\
    03_Videos\<Profissional>\
    05_RAW\<Profissional>\
  Cópias, em <pasta-de-copias>\<AAAA-MM-DD>_<Nome do evento>\
  (ou no próprio primário, se a pasta de cópias não for definida)
    02_Fotos_JPG_Copia\<Profissional>\Cartao_N\
    04_Videos_Copia\<Profissional>\Cartao_N\
    06_RAW_Copia\<Profissional>\Cartao_N\
  (v1.5) Leva Cartao_1, Cartao_2... SÓ em 01_Fotos_JPG; as pastas
  02 a 06 ficam planas por profissional. JPG já presente numa leva
  anterior não é duplicado em 01, mas a cópia plana em 02 é
  garantida. Checklist em checklist-descargas.csv.
  Relatório: relatorio-descarga.txt na pasta primária.
"""

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import queue
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

VERSION = "2.0.0-dev.1"

# Visual v1.7 (inspirado no Descarrega: cartões, cabeçalho, cor por pessoa).
# Só visual — nenhuma função muda.
PROF_COLORS = ["#2563EB", "#16A34A", "#D97706", "#DB2777", "#7C3AED", "#0891B2"]
ACCENT = "#22C55E"

THEMES = {
    "claro": {"bg": "#F4F5F7", "card": "#FFFFFF", "fg": "#111827",
              "muted": "#6B7280", "entry": "#FFFFFF", "list": "#FFFFFF",
              "list_fg": "#111827", "bar_bg": "#E5E7EB", "border": "#E5E7EB"},
    "escuro": {"bg": "#111827", "card": "#1F2937", "fg": "#F9FAFB",
               "muted": "#9CA3AF", "entry": "#374151", "list": "#1F2937",
               "list_fg": "#F9FAFB", "bar_bg": "#374151", "border": "#374151"},
}


def prof_color(name):
    """Cor determinística por profissional (mesmo nome, sempre a mesma)."""
    if not name:
        return "#6B7280"
    return PROF_COLORS[sum(name.encode("utf-8")) % len(PROF_COLORS)]

JPG_EXTS = {".jpg", ".jpeg"}
RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".raf", ".dng", ".rw2",
            ".orf", ".pef", ".x3f", ".3fr", ".mos", ".erf"}
VIDEO_EXTS = {".mp4", ".mov", ".mxf", ".mts", ".m2ts", ".avi",
              ".wmv", ".mkv", ".mpg", ".mpeg", ".insv"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".aif", ".aiff",
              ".ogg", ".opus"}

FOLDERS = {
    # Numeração global: ímpar = primário (D:), par = cópia (outra unidade/pasta).
    "jpg_sync": "01_Fotos_JPG",
    "jpg_copy": "02_Fotos_JPG_Copia",
    "video_sync": "03_Videos",
    "video_copy": "04_Videos_Copia",
    "raw_backup": "05_RAW",
    "raw_copy": "06_RAW_Copia",
    "audio_primary": "07_Audio",
    "audio_copy": "08_Audio_Copia",
}


def classify(path):
    ext = Path(path).suffix.lower()
    if ext in JPG_EXTS:
        return "jpg"
    if ext in RAW_EXTS:
        return "raw"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
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


def destinations_for(event_root, professional, copy_event_root=None, leva=None):
    """Destinos primários (01, 03, 05) em event_root e cópias
    (02, 04, 06) em copy_event_root — ou em event_root, se a pasta
    de cópias não for definida (fallback para D:).
    Leva (v1.5): SÓ a 01 (JPG) tem Cartao_N, para o 2º profissional
    trabalhar por leva. As pastas 02 a 06 ficam planas, só por
    profissional: .../<Profissional>/<arquivo>."""
    prof = sanitize(professional)
    copy_root = copy_event_root if copy_event_root is not None else event_root
    jpg_sub = Path(prof) / f"Cartao_{leva}" if leva is not None else Path(prof)
    return {
        "jpg_sync": event_root / FOLDERS["jpg_sync"] / jpg_sub,
        "jpg_copy": copy_root / FOLDERS["jpg_copy"] / prof,
        "video_sync": event_root / FOLDERS["video_sync"] / prof,
        "video_copy": copy_root / FOLDERS["video_copy"] / prof,
        "raw_backup": event_root / FOLDERS["raw_backup"] / prof,
        "raw_copy": copy_root / FOLDERS["raw_copy"] / prof,
        "audio_primary": event_root / FOLDERS["audio_primary"] / prof,
        "audio_copy": copy_root / FOLDERS["audio_copy"] / prof,
    }


def next_leva_number(event_root, professional):
    """Próximo Cartao_N para o profissional no evento (1 se nenhum).
    A leva é contada só pela 01 (JPG), que é a única pasta com Cartao_N."""
    prof = sanitize(professional)
    max_n = 0
    for key in ("jpg_sync",):
        prof_dir = event_root / FOLDERS[key] / prof
        if not prof_dir.is_dir():
            continue
        for d in prof_dir.iterdir():
            if d.is_dir() and d.name.startswith("Cartao_"):
                try:
                    max_n = max(max_n, int(d.name.split("_", 1)[1]))
                except (ValueError, IndexError):
                    pass
    return max_n + 1


def _same_file(path, size, src_hash):
    if not path.is_file():
        return False
    try:
        if path.stat().st_size != size:
            return False
    except OSError:
        return False
    if src_hash is None:
        return True
    try:
        return file_hash(path) == src_hash
    except OSError:
        return False


def list_removable_drives():
    """Unidades removíveis plugadas (Windows). [] fora do Windows."""
    if os.name != "nt":
        return []
    try:
        import ctypes
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if bitmask & (1 << i):
                letter = chr(ord("A") + i) + ":\\"
                # DRIVE_REMOVABLE = 2
                if ctypes.windll.kernel32.GetDriveTypeW(letter) == 2:
                    drives.append(letter)
        return drives
    except Exception:
        return []


def split_needed(files, copy_jpg=True, copy_video=True, copy_raw=True, copy_audio=True):
    """Retorna (bytes primário, bytes cópia)."""
    primary = sum(s for _p, _k, s in files)
    copy_total = 0
    for _p, kind, s in files:
        if kind == "jpg" and copy_jpg:
            copy_total += s
        elif kind == "video" and copy_video:
            copy_total += s
        elif kind == "raw" and copy_raw:
            copy_total += s
        elif kind == "audio" and copy_audio:
            copy_total += s
    return primary, copy_total


def needed_bytes(files, copy_jpg=True, copy_video=True, copy_audio=True):
    total = 0
    for _p, kind, size in files:
        if kind == "jpg":
            total += size * (2 if copy_jpg else 1)
        elif kind == "video":
            total += size * (2 if copy_video else 1)
        elif kind == "audio":
            total += size * (2 if copy_audio else 1)
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


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_chunked(src, dest, progress_cb=None):
    """Copia em blocos de 1 MB, chamando progress_cb(n_bytes) a cada bloco.

    Equivalente a shutil.copy2 (conteúdo + metadados)."""
    total = 0
    with open(src, "rb") as fh_in, open(dest, "wb") as fh_out:
        for chunk in iter(lambda: fh_in.read(1024 * 1024), b""):
            fh_out.write(chunk)
            total += len(chunk)
            if progress_cb:
                progress_cb(len(chunk))
    try:
        shutil.copystat(str(src), str(dest))
    except OSError:
        pass
    return total


def copy_one(src, dest_dir, src_hash=None, progress_cb=None):
    """Copia um arquivo com verificação por tamanho (e por hash, se dado).

    Retorna (ação, destino): copied, skipped ou failed. Nunca sobrescreve.
    progress_cb, quando dado, recebe os bytes escritos (para a barra).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    src_size = src.stat().st_size
    dest = dest_dir / src.name
    if dest.exists():
        try:
            if dest.stat().st_size == src_size:
                if src_hash is None or file_hash(dest) == src_hash:
                    if progress_cb:
                        progress_cb(src_size)
                    return "skipped", dest
                # Mesmo nome e tamanho, conteúdo diferente (corrompido):
                # apaga e recopia no mesmo nome, em vez de pular.
                try:
                    dest.unlink()
                    copy_chunked(src, dest, progress_cb)
                    if dest.stat().st_size == src_size and (src_hash is None or file_hash(dest) == src_hash):
                        return "copied", dest
                except Exception:
                    pass
                return "failed", dest
        except OSError:
            pass
        # Mesmo nome, conteúdo diferente: não sobrescreve, cria sufixo.
        # Se o sufixo já existir com o mesmo tamanho e hash, é a mesma
        # cópia: pula (isso deixa a 2ª descarga idempotente).
        stem, suffix = src.stem, src.suffix
        i = 1
        while True:
            dest = dest_dir / f"{stem}_{i}{suffix}"
            if not dest.exists():
                break
            try:
                if dest.stat().st_size == src_size and (src_hash is None or file_hash(dest) == src_hash):
                    if progress_cb:
                        progress_cb(src_size)
                    return "skipped", dest
            except OSError:
                pass
            i += 1
    copy_chunked(src, dest, progress_cb)
    try:
        if dest.stat().st_size != src_size:
            raise OSError("tamanho divergente após cópia")
        if src_hash is not None and file_hash(dest) != src_hash:
            raise OSError("hash divergente após cópia")
    except Exception:
        try:
            dest.unlink()
        except OSError:
            pass
        return "failed", dest
    return "copied", dest


def move_one(staged, dest_dir):
    """Move (renomeia, na mesma unidade) um arquivo do staging ao destino.

    Se o destino já existir com o mesmo tamanho, apaga o staged e
    retorna skipped. Nunca sobrescreve.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        size = staged.stat().st_size
    except OSError:
        return "failed", dest_dir / staged.name
    dest = dest_dir / staged.name
    if dest.exists():
        try:
            if dest.stat().st_size == size:
                try:
                    staged.unlink()
                except OSError:
                    pass
                return "skipped", dest
        except OSError:
            pass
        stem, suffix = staged.stem, staged.suffix
        i = 1
        while True:
            dest = dest_dir / f"{stem}_{i}{suffix}"
            if not dest.exists():
                break
            try:
                if dest.stat().st_size == size:
                    try:
                        staged.unlink()
                    except OSError:
                        pass
                    return "skipped", dest
            except OSError:
                pass
            i += 1
    try:
        shutil.move(str(staged), str(dest))
        if dest.stat().st_size != size:
            return "failed", dest
    except Exception:
        return "failed", dest
    return "copied", dest


def pair_alert(files):
    """Conta JPG sem RAW e RAW sem JPG (mesmo nome base)."""
    jpg = {Path(p).stem.lower() for p, k, _s in files if k == "jpg"}
    raw = {Path(p).stem.lower() for p, k, _s in files if k == "raw"}
    return len(jpg - raw), len(raw - jpg)


def corruption_alerts(files, source_root=None):
    """Arquivos que PODEM estar corrompidos/interrompidos (alerta, não laudo).

    Sinais: tamanho 0; vídeo MP4/MOV sem o átomo 'moov' nem no início
    nem no fim (lê só o 1º e o último 1 MB); vídeo com menos de 1 KB;
    arquivo .rsv/.tmp/.part no cartão. O arquivo é copiado mesmo assim:
    o alerta é para não formatar o cartão antes de ver.
    Retorna [(nome, motivo)]."""
    alerts = []
    for path, kind, size in files:
        name = Path(path).name
        if size == 0:
            alerts.append((name, "tamanho 0"))
            continue
        if kind == "video" and size < 1024:
            alerts.append((name, "vídeo com menos de 1 KB"))
            continue
        if kind == "video" and Path(path).suffix.lower() in (".mp4", ".mov"):
            try:
                found = False
                with open(path, "rb") as fh:
                    head = fh.read(1024 * 1024)
                    if b"moov" in head:
                        found = True
                    else:
                        fh.seek(max(0, size - 1024 * 1024))
                        if b"moov" in fh.read():
                            found = True
                if not found:
                    alerts.append((name, "sem índice moov no início nem no fim (pode estar interrompido)"))
            except OSError:
                pass
    # Arquivos de gravação interrompida que o classify() conta como Outros.
    if source_root is not None:
        for root, _dirs, names in os.walk(source_root):
            for name in sorted(names):
                if Path(name).suffix.lower() in (".rsv", ".tmp", ".part"):
                    alerts.append((name, "arquivo de gravação interrompida (.rsv/.tmp/.part)"))
    return alerts


def rollover_split(files):
    """Detecta a virada do contador (ex.: C9999 -> C0001).

    Agrupa por (prefixo, tipo), ordena por data de modificação e procura
    a queda do número de >=9900 para <=100. Retorna
    {nome_do_arquivo: "ZEROU - A PARTIR DE <prefixo><numero>"} só para os
    arquivos PÓS-virada, e a lista de avisos [(prefixo, primeiro_pós)].
    Nada é renomeado; os pós-virada vão para uma subpasta com esse nome."""
    from collections import defaultdict
    groups = defaultdict(list)
    for path, kind, _size in files:
        stem = Path(path).stem
        m = re.search(r"(\d+)$", stem)
        if not m:
            continue
        groups[(stem[:m.start()], kind)].append((path, int(m.group(1))))
    post = {}
    warnings = []
    for (prefix, _kind), items in groups.items():
        ordered = sorted(items, key=lambda x: (Path(x[0]).stat().st_mtime, Path(x[0]).name))
        for i in range(1, len(ordered)):
            prev_num = ordered[i - 1][1]
            curr_num = ordered[i][1]
            if prev_num >= 9900 and curr_num <= 100 and curr_num < prev_num:
                first = ordered[i]
                sub = f"ZEROU - A PARTIR DE {prefix}{curr_num:04d}"
                warnings.append((prefix, curr_num))
                for path, _num in ordered[i:]:
                    post[Path(path).name] = sub
                break
    return post, warnings


def manifest_path(event_root):
    return Path(event_root) / "manifest-descarga.json"


def load_manifest(event_root):
    try:
        data = json.loads(manifest_path(event_root).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_manifest(event_root, manifest):
    try:
        manifest_path(event_root).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def manifest_key(professional, kind, name, size):
    return f"{sanitize(professional)}|{kind}|{name}|{size}"


def manifest_entry(manifest, key):
    entry = manifest.get(key)
    return entry if isinstance(entry, dict) else None


def is_verified(manifest, key, dest_paths, size, src_hash):
    """Já conferido só se o manifest disser E os destinos existirem
    no HD com o mesmo tamanho (e mesmo hash, quando há hash).
    Quem decide é o HD, não a memória do programa."""
    entry = manifest_entry(manifest, key)
    if entry is None:
        return False
    if src_hash is not None and entry.get("hash") != src_hash:
        return False
    for dest in dest_paths:
        try:
            if not dest.is_file() or dest.stat().st_size != size:
                return False
        except OSError:
            return False
    return True


def config_path():
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    return base / "dx-ingest-config.json"


def load_config():
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(data):
    try:
        config_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def process_card(files, dests, event_root, professional, copy_jpg=True,
                 copy_video=True, copy_raw=True, copy_audio=True, verify_hash=False, log=None,
                 manifest=None, rollover_post=None, suspects=None, progress_cb=None):
    """Descarga com staging (v1.5: leva Cartao_N só em 01).

    1) Copia cada arquivo do cartão para .staging (fora das pastas de sync).
    2) Depois da conferência, move (renomeia, rápido, na mesma unidade)
       para a pasta primária (01, 03, 05).
    3) Só então copia para a pasta de cópia (02, 04, 06).
    O editor/sync só vê o arquivo quando ele já está completo no destino.
    Retorna relatório (dict).
    """
    report = {"copied": 0, "skipped": 0, "failed": 0, "errors": []}
    prof = sanitize(professional)
    staging_root = event_root / ".staging" / prof
    manifest = manifest if manifest is not None else {}
    rollover_post = rollover_post or {}
    suspects = suspects or {}

    def emit(msg):
        if log:
            log(msg)

    def _done_bytes(n):
        if progress_cb:
            progress_cb(n)

    def tally(action, src, dest_dir):
        if action == "copied":
            report["copied"] += 1
        elif action == "skipped":
            report["skipped"] += 1
        else:
            report["failed"] += 1
            if not any(src.name in e and str(dest_dir) in e for e in report["errors"]):
                report["errors"].append(f"{src.name} -> {dest_dir}")

    for src, kind, _size in files:
        if src.name in (suspects or {}):
            emit(f"ALERTA — pode estar corrompido/interrompido: {src.name} ({suspects[src.name]}). "
                 "Vai ser copiado mesmo assim; não formate o cartão antes de ver.")
        # Destinos efetivos (pós-virada do contador vão para subpasta ZEROU).
        if kind == "jpg":
            _base_primary, _base_secondary = dests["jpg_sync"], (dests["jpg_copy"] if copy_jpg else None)
        elif kind == "video":
            _base_primary, _base_secondary = dests["video_sync"], (dests["video_copy"] if copy_video else None)
        elif kind == "audio":
            _base_primary, _base_secondary = dests["audio_primary"], (dests["audio_copy"] if copy_audio else None)
        else:
            _base_primary, _base_secondary = dests["raw_backup"], (dests["raw_copy"] if copy_raw else None)
        _sub = rollover_post.get(src.name)
        # 0) retomada persistente: já conferido (manifest + HD) pula sem recopiar.
        _eff_primary = _base_primary / _sub if _sub else _base_primary
        _eff_secondary = _base_secondary / _sub if (_sub and _base_secondary is not None) else _base_secondary
        _dest_paths = [_eff_primary / src.name]
        if _eff_secondary is not None:
            _dest_paths.append(_eff_secondary / src.name)
        _key = manifest_key(prof, kind, src.name, _size)
        _src_hash_check = file_hash(src) if verify_hash else None
        if is_verified(manifest, _key, _dest_paths, _size, _src_hash_check):
            report["skipped"] += 1
            _done_bytes(_size * len(_dest_paths))
            emit(f"Já conferido (retomada): {src.name}")
            continue
        # 1) staging
        staged_dir = staging_root / kind
        src_hash = _src_hash_check
        try:
            action, staged = copy_one(src, staged_dir, src_hash=src_hash, progress_cb=progress_cb)
        except Exception as exc:  # noqa: BLE001
            report["failed"] += 1
            report["errors"].append(f"{src.name} -> staging: {exc}")
            emit(f"FALHOU staging: {src.name} ({exc})")
            continue
        if action == "failed":
            tally("failed", src, staged_dir)
            continue
        if action == "skipped":
            # Já estava no staging de uma tentativa anterior: usa ele.
            pass
        # 2) move para o destino principal (com subpasta ZEROU, se for o caso)
        primary_dir, secondary_dir = _base_primary, _base_secondary
        if _sub:
            primary_dir = primary_dir / _sub
            if secondary_dir is not None:
                secondary_dir = secondary_dir / _sub
        # JPG, leva só em 01: se o JPG já está numa leva anterior,
        # não duplica em 01, mas garante a cópia plana em 02.
        if kind == "jpg" and primary_dir.name.startswith("Cartao_"):
            prof_dir = primary_dir.parent
            prev_found = False
            if prof_dir.is_dir():
                for sibling in prof_dir.iterdir():
                    if (sibling.is_dir() and sibling.name.startswith("Cartao_")
                            and sibling.name != primary_dir.name
                            and _same_file(sibling / src.name, _size, src_hash)):
                        prev_found = True
                        break
            if prev_found:
                tally("skipped", src, primary_dir)
                _done_bytes(_size)
                _ok_secondary = True
                if secondary_dir is not None:
                    try:
                        sec_hash = src_hash
                        action2, _d = copy_one(staged, secondary_dir, src_hash=sec_hash, progress_cb=progress_cb)
                    except Exception as exc:  # noqa: BLE001
                        action2 = "failed"
                        report["errors"].append(f"{src.name} -> {secondary_dir}: {exc}")
                    tally(action2, src, secondary_dir)
                    _ok_secondary = action2 in ("copied", "skipped")
                if _ok_secondary:
                    manifest[_key] = {"hash": src_hash, "dest": [str(primary_dir / src.name)] +
                                      ([str(secondary_dir / src.name)] if secondary_dir is not None else [])}
                try:
                    staged.unlink()
                except OSError:
                    pass
                emit(f"Já em leva anterior: {src.name} (pulou em 01)")
                continue
        try:
            action, primary = move_one(staged, primary_dir)
        except Exception as exc:  # noqa: BLE001
            report["failed"] += 1
            report["errors"].append(f"{src.name} -> {primary_dir}: {exc}")
            continue
        tally(action, src, primary_dir)
        if action == "failed":
            continue
        # 3) cópia secundária (a partir do arquivo já verificado)
        _ok_secondary = True
        if secondary_dir is not None:
            try:
                sec_hash = file_hash(primary) if verify_hash else None
                action2, _d = copy_one(primary, secondary_dir, src_hash=sec_hash, progress_cb=progress_cb)
            except Exception as exc:  # noqa: BLE001
                action2 = "failed"
                report["errors"].append(f"{src.name} -> {secondary_dir}: {exc}")
            tally(action2, src, secondary_dir)
            _ok_secondary = action2 in ("copied", "skipped")
        if action in ("copied", "skipped") and _ok_secondary:
            manifest[_key] = {"hash": src_hash, "dest": [str(primary_dir / src.name)] +
                              ([str(secondary_dir / src.name)] if secondary_dir is not None else [])}
    # Limpa o staging se ficou vazio (o normal); se sobrou arquivo
    # com falha, mantém para investigação e registra no log.
    try:
        if staging_root.exists() and not any(p.is_file() for p in staging_root.rglob("*")):
            shutil.rmtree(staging_root, ignore_errors=True)
        parent = event_root / ".staging"
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except Exception:
        pass
    return report


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


def write_report(event_root, professional, source, files, report, leva=None,
                 suspects=None, rollover_warnings=None, verified_count=0,
                 mode_label="Profissional"):
    event_root.mkdir(parents=True, exist_ok=True)
    path = event_root / "relatorio-descarga.txt"
    counts = {}
    for _p, kind, _s in files:
        counts[kind] = counts.get(kind, 0) + 1
    lines = [
        "",
        "=" * 60,
        f"Descarga: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"{mode_label}: {professional}" + (f"  •  Leva: Cartao_{leva}" if leva is not None else ""),
        f"Origem (cartão): {source}",
        f"Evento: {event_root}",
        f"Encontrados: JPG={counts.get('jpg', 0)} "
        f"RAW={counts.get('raw', 0)} Vídeo={counts.get('video', 0)} Áudio={counts.get('audio', 0)}",
        f"Resultado: copiados={report['copied']} "
        f"pulados (já existiam)={report['skipped']} "
        f"falhas={report['failed']}",
    ]
    if verified_count:
        lines.append(f"Já conferidos (retomada, sem recopiar): {verified_count}")
    if suspects:
        lines.append("ALERTA — podem estar corrompidos/interrompidos (copiados mesmo assim; não formate o cartão antes de ver):")
        lines.extend(f"  - {name} ({reason})" for name, reason in suspects[:20])
    if rollover_warnings:
        lines.append("Contador zerado (C9999 -> C0001): arquivos pós-virada foram para a subpasta ZEROU:")
        lines.extend(f"  - {prefix} a partir de {num:04d}" for prefix, num in rollover_warnings)
    if report["errors"]:
        lines.append("Falhas:")
        lines.extend(f"  - {e}" for e in report["errors"][:50])
    lines.append("Obs.: cópia, não move. Cartão NÃO foi apagado/formatado.")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


HISTORY_HEADER = ["data_hora", "profissional", "leva", "origem",
                  "jpg", "raw", "video", "audio", "copiados", "pulados", "falhas", "devolvido"]


def history_path(event_root):
    return Path(event_root) / "checklist-descargas.csv"


def append_history(event_root, professional, leva, source, files, report):
    """Registra a descarga no checklist do evento (CSV, legível no Excel)."""
    try:
        event_root.mkdir(parents=True, exist_ok=True)
        path = history_path(event_root)
        counts = {}
        for _p, kind, _s in files:
            counts[kind] = counts.get(kind, 0) + 1
        new_file = not path.exists()
        with open(path, "a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            if new_file:
                w.writerow(HISTORY_HEADER)
            w.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                professional, f"Cartao_{leva}", source,
                counts.get("jpg", 0), counts.get("raw", 0), counts.get("video", 0),
                counts.get("audio", 0),
                report["copied"], report["skipped"], report["failed"], "não",
            ])
    except OSError:
        pass


def read_history(event_root):
    path = history_path(event_root)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        return [r for r in rows if r.get("profissional")]
    except (OSError, csv.Error):
        return []


def mark_history_returned(event_root, index):
    """Marca a linha `index` do checklist como cartão devolvido."""
    path = history_path(event_root)
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        if len(rows) < 2 or index + 1 >= len(rows):
            return False
        header = rows[0]
        dev_idx = header.index("devolvido") if "devolvido" in header else len(header) - 1
        rows[index + 1][dev_idx] = "sim"
        with open(path, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows(rows)
        return True
    except (OSError, csv.Error, ValueError):
        return False


def resource_path(rel):
    """Caminho de um asset, no dev e dentro do .exe (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return Path(base) / rel


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


class App:
    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.queue_items = []  # [(origem, profissional)]
        self.last_success = False
        root.title(f"Editor Assistente v{VERSION}")
        # Ícone derivado do logo (diafragma + seta de descarga), se existir.
        try:
            icon_png = resource_path("assets/icon.png")
            if icon_png.exists():
                photo = tk.PhotoImage(file=str(icon_png))
                root.iconphoto(True, photo)
                root._icon_photo = photo
        except Exception:
            pass
        root.geometry("1280x900")
        root.minsize(1100, 650)
        self.scan = []
        self.others = 0
        self.suspects = []
        self.rollover_post = {}
        self.rollover_warnings = []
        self.verified_count = 0
        self.msg_queue = queue.Queue()
        self.copying = False
        self._build()

    # ---------- interface ----------
    def _build(self):
        from dashboard import mount_sidebar, mount_media_cards
        mount_sidebar(self)
        pad = {"padx": 8, "pady": 4}
        # Janela rolável: o conteúdo é mais alto que a janela e, sem rolagem,
        # os cartões de destino e o progresso grande ficavam cortados (v1.8.1).
        self._canvas = tk.Canvas(self.root, highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        frm = ttk.Frame(self._canvas, padding=10)
        self._frame_id = self._canvas.create_window((0, 0), window=frm, anchor="nw")
        frm.bind("<Configure>", lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(self._frame_id, width=e.width))
        self._canvas.bind_all("<MouseWheel>", lambda e: self._canvas.yview_scroll(-1 * int(e.delta / 120), "units"))
        cfg = self.config
        profs = cfg.get("professionals") or ["Fotografo_01", "Cinegrafista_01"]
        self.theme_var = tk.StringVar(value=cfg.get("theme_v2", "escuro"))

        # Cabeçalho do evento (visual v1.7): cartão com evento, data e selo do profissional.
        self.header_frame = tk.Frame(frm, relief="flat", bd=0, highlightthickness=1,
                                     highlightbackground="#E5E7EB")
        self.header_frame.pack(fill="x", pady=(0, 10))
        _hleft = ttk.Frame(self.header_frame, style="Card.TFrame")
        _hleft.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        self.header_title = ttk.Label(_hleft, text="Editor Assistente", style="Title.Card.TLabel", anchor="w")
        self.header_title.pack(anchor="w")
        self.header_sub = ttk.Label(_hleft, text="", style="Muted.Card.TLabel", anchor="w")
        self.header_sub.pack(anchor="w")
        self.header_badge = tk.Label(self.header_frame, text="—", font=("Segoe UI", 11, "bold"),
                                     bg="#6B7280", fg="white", padx=14, pady=6)
        self.header_badge.pack(side="right", padx=12)
        ttk.Button(self.header_frame, text="Tema: claro/escuro", command=self._toggle_theme).pack(side="right", padx=(0, 4))

        mount_media_cards(self, frm)
        overview_anchor = ttk.Frame(frm)
        overview_anchor.pack(fill="x")

        # 1) Evento em primeiro: é o que define a pasta do evento e não muda
        # durante o dia — por isso tem o botão de travar (v1.8.3).
        ttk.Label(frm, text="1) Evento").pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.ent_date = ttk.Entry(row, textvariable=self.date_var, width=14)
        self.ent_date.pack(side="left", **pad)
        self.event_var = tk.StringVar(value=cfg.get("event", ""))
        self.ent_event = ttk.Entry(row, textvariable=self.event_var)
        self.ent_event.pack(side="left", fill="x", expand=True, **pad)
        self.event_locked_var = tk.BooleanVar(value=cfg.get("event_locked", False))
        self.btn_lock_event = ttk.Button(row, text="Travar", command=self._toggle_event_lock)
        self.btn_lock_event.pack(side="left", **pad)
        ttk.Label(row, text="(ex.: Fenalaw 2026)").pack(side="left", **pad)

        ttk.Label(frm, text="2) Cartão / pasta de origem").pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.source_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.source_var).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(row, text="Procurar...", command=self._pick_source).pack(side="left", **pad)
        ttk.Button(row, text="Cartões plugados...", command=self._pick_removable).pack(side="left", **pad)

        self.mode_var = tk.StringVar(value=cfg.get("mode", "equipe"))
        mrow = ttk.Frame(frm)
        mrow.pack(fill="x")
        ttk.Label(mrow, text="Modo:").pack(side="left", **pad)
        self.mode_combo = ttk.Combobox(mrow, textvariable=self.mode_var, values=["equipe", "multicam"], width=12, state="readonly")
        self.mode_combo.pack(side="left", **pad)
        ttk.Label(mrow, text="equipe = por profissional  •  multicam = por câmera (fíxa, sem operador)").pack(side="left", **pad)
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._toggle_mode())
        self.prof_label = ttk.Label(frm, text="3) Profissional (vira subpasta)")
        self.prof_label.pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.prof_var = tk.StringVar(value=profs[0])
        self.prof_combo = ttk.Combobox(row, textvariable=self.prof_var, values=profs)
        self.prof_combo.pack(side="left", fill="x", expand=True, **pad)
        ttk.Label(row, text="ex.: Fotografo_01, Cinegrafista_01").pack(side="left", **pad)
        for _var in (self.event_var, self.date_var, self.prof_var):
            _var.trace_add("write", lambda *_a: self._refresh_header())

        ttk.Label(frm, text="4) Pasta base de destino (normalmente D:\\Eventos)").pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.base_var = tk.StringVar(value=cfg.get("base", r"D:\Eventos"))
        ttk.Entry(row, textvariable=self.base_var).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(row, text="Procurar...", command=self._pick_base).pack(side="left", **pad)

        # Chave mestra das cópias ANTES da pasta das cópias: com ela desligada,
        # a pasta das cópias e os checkboxes por tipo ficam ocultos (v1.8.3).
        opts = ttk.Frame(frm)
        opts.pack(fill="x", pady=4)
        self.copy_enabled_var = tk.BooleanVar(value=cfg.get("copy_enabled", True))
        self.copy_jpg_var = tk.BooleanVar(value=cfg.get("copy_jpg", True))
        self.copy_video_var = tk.BooleanVar(value=cfg.get("copy_video", True))
        self.copy_raw_var = tk.BooleanVar(value=cfg.get("copy_raw", True))
        self.copy_audio_var = tk.BooleanVar(value=cfg.get("copy_audio", True))
        self.hash_var = tk.BooleanVar(value=cfg.get("verify_hash", False))
        ttk.Checkbutton(opts, text="Fazer cópias em outra unidade (02, 04, 06, 08)",
                        variable=self.copy_enabled_var).pack(anchor="w", **pad)
        ttk.Label(opts, text="Desmarque para descarregar mais rápido e fazer o backup depois.",
                  style="Muted.TLabel").pack(anchor="w", padx=8)

        self.copies_frame = ttk.Frame(frm)
        ttk.Label(self.copies_frame, text="5) Pasta das cópias (02, 04, 06, 08) — outra unidade/pasta (ex.: E:\\Copias). Se vazia, as cópias ficam em D:", wraplength=740, justify="left").pack(anchor="w")
        row = ttk.Frame(self.copies_frame)
        row.pack(fill="x")
        self.external_var = tk.StringVar(value=cfg.get("external_base", ""))
        ttk.Entry(row, textvariable=self.external_var).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(row, text="Procurar...", command=self._pick_external).pack(side="left", **pad)
        opts2 = ttk.Frame(self.copies_frame)
        opts2.pack(fill="x", pady=0)
        self.chk_copy_jpg = ttk.Checkbutton(opts2, text="Cópia do JPG (02)", variable=self.copy_jpg_var)
        self.chk_copy_jpg.pack(side="left", **pad)
        self.chk_copy_video = ttk.Checkbutton(opts2, text="Cópia do vídeo (04)", variable=self.copy_video_var)
        self.chk_copy_video.pack(side="left", **pad)
        self.chk_copy_raw = ttk.Checkbutton(opts2, text="Cópia do RAW (06)", variable=self.copy_raw_var)
        self.chk_copy_raw.pack(side="left", **pad)
        self.chk_copy_audio = ttk.Checkbutton(opts2, text="Cópia do áudio (08)", variable=self.copy_audio_var)
        self.chk_copy_audio.pack(side="left", **pad)
        self._hash_frame = ttk.Frame(frm)
        self._hash_frame.pack(fill="x", pady=0)
        ttk.Checkbutton(self._hash_frame, text="Verificação completa por hash (mais lenta)", variable=self.hash_var).pack(side="left", **pad)
        self.copy_enabled_var.trace_add("write", lambda *_a: self._toggle_copy_options())
        self._toggle_copy_options()

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=6, before=overview_anchor)
        self.btn_scan = ttk.Button(btns, text="Analisar cartão", command=self.analyze)
        self.btn_scan.pack(side="left", **pad)
        self.btn_copy = ttk.Button(btns, text="Descarregar", command=self.start_copy, style="Accent.TButton")
        self.btn_copy.pack(side="left", **pad)
        self.btn_open = ttk.Button(btns, text="Abrir pasta do evento", command=self.open_event)
        self.btn_open.pack(side="left", **pad)
        self.btn_eject = ttk.Button(btns, text="Ejetar com segurança", command=self.eject_card, state="disabled")
        self.btn_eject.pack(side="left", **pad)

        # Cartões de destino (visual do mockup): cartão branco com título dentro,
        # texto de espaço e barra verde — sem o LabelFrame antigo.
        cards = ttk.Frame(frm)
        cards.pack(fill="x", pady=4, before=overview_anchor)
        self.card_p_frame = tk.Frame(cards, relief="flat", bd=0, highlightthickness=1,
                                     highlightbackground="#E5E7EB")
        self.card_p_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))
        ttk.Label(self.card_p_frame, text="DISCO PRIMÁRIO · 01 / 03 / 05 / 07", style="CardTitle.TLabel").pack(anchor="w", padx=10, pady=(8, 0))
        self.space_var = tk.StringVar(value="Espaço: analise o cartão para ver quanto cabe.")
        ttk.Label(self.card_p_frame, textvariable=self.space_var, wraplength=330, justify="left", style="Card.TLabel").pack(anchor="w", fill="x", padx=10, pady=4)
        self.space_bar = ttk.Progressbar(self.card_p_frame, mode="determinate", maximum=100, style="Space.Horizontal.TProgressbar")
        self.space_bar.pack(fill="x", padx=10, pady=(0, 10))
        self.card_c_frame = tk.Frame(cards, relief="flat", bd=0, highlightthickness=1,
                                     highlightbackground="#E5E7EB")
        self.card_c_frame.pack(side="left", fill="both", expand=True, padx=(4, 0))
        ttk.Label(self.card_c_frame, text="Cópias (outra unidade) — 02, 04, 06, 08", style="CardTitle.TLabel").pack(anchor="w", padx=10, pady=(8, 0))
        self.space_copy_var = tk.StringVar(value="")
        ttk.Label(self.card_c_frame, textvariable=self.space_copy_var, wraplength=330, justify="left", style="Card.TLabel").pack(anchor="w", fill="x", padx=10, pady=4)
        self.space_copy_bar = ttk.Progressbar(self.card_c_frame, mode="determinate", maximum=100, style="Space.Horizontal.TProgressbar")
        self.space_copy_bar.pack(fill="x", padx=10, pady=(0, 10))

        # Progresso grande (visual v1.7): barra alta + percentual + status.
        prow = ttk.Frame(frm)
        prow.pack(fill="x", pady=6, before=overview_anchor)
        self.progress_var = tk.StringVar(value="0%")
        ttk.Label(prow, textvariable=self.progress_var, font=("Segoe UI", 16, "bold")).pack(side="left", padx=(0, 10))
        self.progress = ttk.Progressbar(prow, mode="determinate", style="Green.Horizontal.TProgressbar")
        self.progress.pack(side="left", fill="x", expand=True)
        self.status_var = tk.StringVar(value="Pronto.")
        ttk.Label(frm, textvariable=self.status_var, wraplength=900, justify="left").pack(anchor="w", fill="x", before=overview_anchor, pady=(0, 18))

        ttk.Label(frm, text="Fila de cartões (um atrás do outro, mesmo evento)").pack(anchor="w")
        qrow = ttk.Frame(frm)
        qrow.pack(fill="x")
        self.queue_list = tk.Listbox(qrow, height=4)
        self.queue_list.pack(side="left", fill="x", expand=True, **pad)
        qbtns = ttk.Frame(qrow)
        qbtns.pack(side="left")
        ttk.Button(qbtns, text="Adicionar à fila", command=self.add_to_queue).pack(fill="x", **pad)
        ttk.Button(qbtns, text="Remover", command=self.remove_from_queue).pack(fill="x", **pad)
        ttk.Button(qbtns, text="Limpar fila", command=self.clear_queue).pack(fill="x", **pad)
        ttk.Button(qbtns, text="Descarregar fila", command=self.start_queue).pack(fill="x", **pad)

        ttk.Label(frm, text="Checklist do evento — quem já descarregou").pack(anchor="w")
        crow = ttk.Frame(frm)
        crow.pack(fill="x")
        self.checklist_list = tk.Listbox(crow, height=4)
        self.checklist_list.pack(side="left", fill="x", expand=True, **pad)
        cbtns = ttk.Frame(crow)
        cbtns.pack(side="left")
        ttk.Button(cbtns, text="Atualizar", command=self.refresh_checklist).pack(fill="x", **pad)
        ttk.Button(cbtns, text="Marcar cartão devolvido", command=self.mark_returned_selected).pack(fill="x", **pad)

        self.preview_var = tk.StringVar(value="Clique em “Analisar cartão” para ver o que será copiado.")
        ttk.Label(frm, textvariable=self.preview_var, wraplength=720, justify="left").pack(anchor="w", fill="x")

        ttk.Label(frm, text="Registro").pack(anchor="w")
        self.log = tk.Text(frm, height=6, wrap="word")
        self.log.pack(fill="both", expand=True)
        scroll = ttk.Scrollbar(frm, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self._toggle_mode()
        self._apply_event_lock()
        self._toggle_copy_options()
        self._apply_theme()

    # ---------- ações ----------
    def _pick_source(self):
        d = filedialog.askdirectory(title="Escolha o cartão / pasta de origem")
        if d:
            self.source_var.set(d)

    def _pick_base(self):
        d = filedialog.askdirectory(title="Escolha a pasta base de destino")
        if d:
            self.base_var.set(d)

    def _pick_external(self):
        d = filedialog.askdirectory(title="Escolha a pasta base das cópias (02, 04, 06)")
        if d:
            self.external_var.set(d)

    def _pick_removable(self):
        drives = list_removable_drives()
        if not drives:
            messagebox.showinfo("Cartões", "Nenhuma unidade removível encontrada. Use “Procurar...” para escolher a pasta do cartão.")
            return
        win = tk.Toplevel(self.root)
        win.title("Cartões plugados")
        lst = tk.Listbox(win, height=min(8, len(drives)))
        lst.pack(fill="both", expand=True, padx=10, pady=10)
        for d in drives:
            lst.insert("end", d)
        lst.selection_set(0)

        def use_selected():
            sel = lst.curselection()
            if sel:
                self.source_var.set(drives[sel[0]])
                win.destroy()

        lst.bind("<Double-Button-1>", lambda _e: use_selected())
        ttk.Button(win, text="Usar selecionado", command=use_selected).pack(pady=(0, 10))

    def refresh_checklist(self):
        try:
            root = self._event_root()
        except ValueError:
            return
        self.checklist_list.delete(0, "end")
        for r in read_history(root):
            self.checklist_list.insert(
                "end",
                f"{r.get('data_hora', '')}  |  {r.get('profissional', '')}  |  {r.get('leva', '')}  |  "
                f"JPG={r.get('jpg', '')} RAW={r.get('raw', '')} Vídeo={r.get('video', '')} Áudio={r.get('audio', '')}  |  "
                f"falhas={r.get('falhas', '')}  |  Devolvido: {r.get('devolvido', '')}")

    def mark_returned_selected(self):
        sel = self.checklist_list.curselection()
        if not sel:
            messagebox.showinfo("Checklist", "Selecione uma linha do checklist primeiro.")
            return
        try:
            root = self._event_root()
        except ValueError as exc:
            messagebox.showerror("Evento", str(exc))
            return
        if mark_history_returned(root, sel[0]):
            self.refresh_checklist()
            self._log("Checklist: cartão marcado como devolvido.")
        else:
            messagebox.showerror("Checklist", "Não foi possível marcar essa linha.")

    def _log(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def _copy_flags(self):
        """(jpg, vídeo, raw, áudio) efetivos: a chave mestra desliga as 4 cópias."""
        enabled = self.copy_enabled_var.get()
        return (enabled and self.copy_jpg_var.get(),
                enabled and self.copy_video_var.get(),
                enabled and self.copy_raw_var.get(),
                enabled and self.copy_audio_var.get())

    def _toggle_copy_options(self):
        """Chave mestra das cópias: desligada, esconde a pasta das cópias,
        os checkboxes por tipo e o cartão de destino das cópias."""
        enabled = self.copy_enabled_var.get()
        if hasattr(self, "copies_frame"):
            if enabled:
                if hasattr(self, "_hash_frame"):
                    self.copies_frame.pack(fill="x", before=self._hash_frame)
                else:
                    self.copies_frame.pack(fill="x")
            else:
                self.copies_frame.pack_forget()
        if hasattr(self, "card_c_frame"):
            if enabled:
                self.card_c_frame.pack(side="left", fill="both", expand=True, padx=(4, 0))
            else:
                self.card_c_frame.pack_forget()

    def _toggle_event_lock(self):
        """Trava/destrava a data e o nome do evento: travado, não dá para
        apagar sem querer durante o uso no dia (v1.8.3)."""
        self.event_locked_var.set(not self.event_locked_var.get())
        self._apply_event_lock()
        self._save_current_config()

    def _apply_event_lock(self):
        locked = self.event_locked_var.get()
        state = "disabled" if locked else "normal"
        for ent in (self.ent_date, self.ent_event):
            ent.configure(state=state)
        self.btn_lock_event.configure(text="Destravar" if locked else "Travar")

    def _mode_label(self):
        return "Câmera" if self.mode_var.get() == "multicam" else "Profissional"

    def _toggle_mode(self):
        is_cam = self.mode_var.get() == "multicam"
        self.prof_label.configure(text="3) Câmera (vira subpasta — ex.: Camera_Palco, Camera_Baterista)" if is_cam
                                  else "3) Profissional (vira subpasta)")
        cams = list(self.config.get("cameras") or ["Camera_Palco", "Camera_Baterista", "Camera_Teclado", "Camera_Geral"])
        profs = list(self.config.get("professionals") or ["Fotografo_01", "Cinegrafista_01"])
        self.prof_combo.configure(values=cams if is_cam else profs)
        if is_cam and self.prof_var.get() not in cams:
            self.prof_var.set(cams[0])
        elif not is_cam and self.prof_var.get() not in profs:
            self.prof_var.set(profs[0])
        self._refresh_header()

    # ---------- visual v1.7 ----------
    def _apply_theme(self):
        mode = self.theme_var.get() if hasattr(self, "theme_var") else "claro"
        th = THEMES.get(mode, THEMES["claro"])
        self.root.configure(bg=th["bg"])
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=th["bg"])
        style.configure("TLabel", background=th["bg"], foreground=th["fg"])
        style.configure("Card.TFrame", background=th["card"])
        style.configure("Card.TLabel", background=th["card"], foreground=th["fg"])
        style.configure("Card.TLabelframe", background=th["card"], foreground=th["fg"])
        style.configure("Card.TLabelframe.Label", background=th["card"], foreground=th["fg"])
        style.configure("Title.Card.TLabel", background=th["card"], foreground=th["fg"], font=("Segoe UI", 14, "bold"))
        style.configure("CardTitle.TLabel", background=th["card"], foreground=th["fg"], font=("Segoe UI", 10, "bold"))
        style.configure("Muted.Card.TLabel", background=th["card"], foreground=th["muted"])
        style.configure("Muted.TLabel", background=th["bg"], foreground=th["muted"])
        from dashboard import polish_styles
        polish_styles(self.root)
        self._canvas.configure(bg=th["bg" ])
        style.configure("TButton", background=th["card"], foreground=th["fg"])
        style.configure("Accent.TButton", background=ACCENT, foreground="white")
        style.configure("TCheckbutton", background=th["bg"], foreground=th["fg"])
        style.configure("TEntry", fieldbackground=th["entry"], foreground=th["fg"])
        style.configure("TCombobox", fieldbackground=th["entry"], foreground=th["fg"])
        style.configure("Green.Horizontal.TProgressbar", background=ACCENT, troughcolor=th["bar_bg"], thickness=22)
        style.configure("Space.Horizontal.TProgressbar", background=ACCENT, troughcolor=th["bar_bg"], thickness=10)
        for w in (getattr(self, "queue_list", None), getattr(self, "checklist_list", None)):
            if w is not None:
                w.configure(bg=th["list"], fg=th["list_fg"])
        if hasattr(self, "log"):
            self.log.configure(bg=th["list"], fg=th["list_fg"], insertbackground=th["fg"])
        if hasattr(self, "header_frame"):
            self.header_frame.configure(bg=th["card"], highlightbackground=th["border"])
        for _f in (getattr(self, "card_p_frame", None), getattr(self, "card_c_frame", None)):
            if _f is not None:
                _f.configure(bg=th["card"], highlightbackground=th["border"])
        self._refresh_header()

    def _toggle_theme(self):
        self.theme_var.set("escuro" if self.theme_var.get() == "claro" else "claro")
        self._save_current_config()
        self._apply_theme()

    def _refresh_header(self):
        if not hasattr(self, "header_title"):
            return
        event = self.event_var.get().strip() if hasattr(self, "event_var") else ""
        date = self.date_var.get().strip() if hasattr(self, "date_var") else ""
        prof = self.prof_var.get().strip() if hasattr(self, "prof_var") else ""
        self.header_title.configure(text=event or "Editor Assistente")
        self.header_sub.configure(text=f"{date}  •  {prof}" if (date or prof) else "Escolha o cartão, o evento e o profissional")
        self.header_badge.configure(text=prof or "—", bg=prof_color(prof), fg="white")

    def _save_current_config(self):
        prof = self.prof_var.get().strip()
        if self.mode_var.get() == "multicam":
            names = list(self.config.get("cameras") or [])
            if prof and prof not in names:
                names.insert(0, prof)
            self.config["cameras"] = names[:10]
        else:
            profs = list(self.config.get("professionals") or [])
            if prof and prof not in profs:
                profs.insert(0, prof)
            self.config["professionals"] = profs[:10]
        self.config.update({
            "theme_v2": self.theme_var.get(),
            "mode": self.mode_var.get(),
            "base": self.base_var.get().strip(),
            "event": self.event_var.get().strip(),
            "external_base": self.external_var.get().strip(),
            "copy_enabled": self.copy_enabled_var.get(),
            "event_locked": self.event_locked_var.get(),
            "copy_jpg": self.copy_jpg_var.get(),
            "copy_video": self.copy_video_var.get(),
            "copy_raw": self.copy_raw_var.get(),
            "copy_audio": self.copy_audio_var.get(),
            "verify_hash": self.hash_var.get(),
        })
        save_config(self.config)
        if self.mode_var.get() == "multicam":
            self.prof_combo.configure(values=list(self.config.get("cameras") or [])[:10])
        else:
            self.prof_combo.configure(values=list(self.config.get("professionals") or [])[:10])

    def _event_root(self):
        try:
            datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d")
        except ValueError:
            raise ValueError("Data inválida. Use o formato AAAA-MM-DD.")
        return event_folder(self.base_var.get().strip(), self.date_var.get().strip(),
                            self.event_var.get().strip())

    def _check_source_dest(self, source, root):
        try:
            if Path(source).resolve() == root.resolve() or root.resolve() in Path(source).resolve().parents \
                    or Path(source).resolve() in root.resolve().parents:
                return False
        except OSError:
            pass
        return True

    def analyze(self):
        self.scan = []
        source = self.source_var.get().strip()
        if not source or not Path(source).is_dir():
            messagebox.showerror("Origem", "Escolha uma pasta de origem válida (o cartão).")
            return
        try:
            root = self._event_root()
        except ValueError as exc:
            messagebox.showerror("Evento", str(exc))
            return
        if not self._check_source_dest(source, root):
            messagebox.showerror("Origem", "A pasta de destino não pode ficar dentro do cartão, nem o contrário.")
            return
        if Path(source).resolve() == Path(self.base_var.get().strip()).resolve() if Path(self.base_var.get().strip()).exists() else False:
            messagebox.showerror("Origem", "Não use a pasta base D: como origem do cartão.")
            return
        self.scan, self.others = scan_source(source)
        from dashboard import update_media_cards
        update_media_cards(self, fmt_bytes)
        self.suspects = corruption_alerts(self.scan, source)
        self.rollover_post, self.rollover_warnings = rollover_split(self.scan)
        counts = {}
        for _p, kind, _s in self.scan:
            counts[kind] = counts.get(kind, 0) + 1
        _cj, _cv, _cr, _ca = self._copy_flags()
        primary, copy_total = split_needed(self.scan, _cj, _cv, _cr, _ca)
        ext_base = self.external_var.get().strip()
        if ext_base and copy_total > 0:
            d_need, ext_need = primary, copy_total
        else:
            d_need, ext_need = primary + copy_total, 0
        free = free_space_for(self.base_var.get().strip())
        free_txt = fmt_bytes(free) if free is not None else "não foi possível verificar"
        ok = "OK — cabe em D:." if free is None or free >= d_need else "ATENÇÃO — pode faltar espaço em D:!"
        jpg_no_raw, raw_no_jpg = pair_alert(self.scan)
        pair_txt = ""
        if jpg_no_raw or raw_no_jpg:
            pair_txt = f"\nAlerta de par: JPG sem RAW={jpg_no_raw}  •  RAW sem JPG={raw_no_jpg}"
        ext_txt = ""
        if ext_base and copy_total > 0:
            ext_free = free_space_for(ext_base)
            ext_txt = f"\nCópias (02, 04, 06): {fmt_bytes(ext_need)}  •  Livre na pasta de cópias: {fmt_bytes(ext_free) if ext_free is not None else 'não foi possível verificar'}"
        leva_preview = next_leva_number(root, self.prof_var.get().strip())
        # Retomada: quantos já estão conferidos (manifest + HD) e quantos bytes faltam.
        _manifest = load_manifest(root)
        _prof = sanitize(self.prof_var.get().strip())
        _copy_root = (Path(ext_base) / root.name) if ext_base else None
        self.verified_count = 0
        _remaining = 0
        for _path, _kind, _size in self.scan:
            _dests = destinations_for(root, _prof, _copy_root, leva=leva_preview)
            if _kind == "jpg":
                _key_paths = [_dests["jpg_sync"] / Path(_path).name] + ([_dests["jpg_copy"] / Path(_path).name] if _cj else [])
            elif _kind == "video":
                _key_paths = [_dests["video_sync"] / Path(_path).name] + ([_dests["video_copy"] / Path(_path).name] if _cv else [])
            elif _kind == "audio":
                _key_paths = [_dests["audio_primary"] / Path(_path).name] + ([_dests["audio_copy"] / Path(_path).name] if _ca else [])
            else:
                _key_paths = [_dests["raw_backup"] / Path(_path).name] + ([_dests["raw_copy"] / Path(_path).name] if _cr else [])
            if is_verified(_manifest, manifest_key(_prof, _kind, Path(_path).name, _size), _key_paths, _size, None):
                self.verified_count += 1
            else:
                _remaining += _size
        _verified_txt = f"\nJá conferidos (retomada, sem recopiar): {self.verified_count}  •  Falta copiar: {fmt_bytes(_remaining)}" if self.verified_count else ""
        _suspect_txt = ""
        if self.suspects:
            _names = ", ".join(n for n, _r in self.suspects[:3])
            _suspect_txt = f"\nALERTA — {len(self.suspects)} arquivo(s) podem estar corrompidos/interrompidos ({_names}{'...' if len(self.suspects) > 3 else ''}). Serão copiados mesmo assim; não formate o cartão antes de ver."
        _rollover_txt = ""
        if self.rollover_warnings:
            _rollover_txt = "\nContador zerado: " + "; ".join(f"{pre} a partir de {num:04d} (pós-virada vai para subpasta ZEROU)" for pre, num in self.rollover_warnings)
        self.preview_var.set(
            f"Encontrados: JPG={counts.get('jpg', 0)}  RAW={counts.get('raw', 0)}  "
            f"Vídeo={counts.get('video', 0)}  Áudio={counts.get('audio', 0)}  Outros ignorados={self.others}\n"
            f"Leva: Cartao_{leva_preview}  •  Primário em D: (01, 03, 05): {fmt_bytes(primary)}  •  Livre em D:: {free_txt}  •  {ok}{pair_txt}{ext_txt}{_verified_txt}{_suspect_txt}{_rollover_txt}" + ("\nCópias DESLIGADAS — só primário (mais rápido); faça o backup manual depois." if not self.copy_enabled_var.get() else "") + f"\n"
            f"Destino primário: {root}"
        )
        # Barra de espaço ao vivo (D: e, se houver, pasta de cópias).
        try:
            _usage = shutil.disk_usage(str(Path(self.base_var.get().strip()).anchor or self.base_var.get().strip()))
            _used_pct = 100.0 * (_usage.total - _usage.free) / _usage.total if _usage.total else 0
            self.space_bar["value"] = _used_pct
            self.space_var.set(f"Espaço em D:: livre {fmt_bytes(free) if free is not None else '—'} de {fmt_bytes(_usage.total)} "
                               f"({100.0 - _used_pct:.0f}% livre)  •  Necessário no primário: {fmt_bytes(primary)}")
        except Exception:
            self.space_bar["value"] = 0
            self.space_var.set("Espaço em D:: não foi possível medir.")
        if ext_base:
            _ext_free = free_space_for(ext_base)
            try:
                _ext_usage = shutil.disk_usage(str(Path(ext_base).anchor or ext_base))
                self.space_copy_var.set(f"Espaço nas cópias: livre {fmt_bytes(_ext_free) if _ext_free is not None else '—'} de {fmt_bytes(_ext_usage.total)}  •  Necessário: {fmt_bytes(copy_total)}")
            except Exception:
                self.space_copy_var.set(f"Espaço nas cópias: livre {fmt_bytes(_ext_free) if _ext_free is not None else '—'}  •  Necessário: {fmt_bytes(copy_total)}")
        else:
            self.space_copy_var.set("")
        try:
            if ext_base:
                _eu = shutil.disk_usage(str(Path(ext_base).anchor or ext_base))
                self.space_copy_bar["value"] = 100.0 * (_eu.total - _eu.free) / _eu.total if _eu.total else 0
            else:
                self.space_copy_bar["value"] = 0
        except Exception:
            self.space_copy_bar["value"] = 0
        self.status_var.set("Análise pronta — confira os números e clique em “Descarregar”.")
        self._log(f"Análise: {counts} | outros={self.others} | primário={fmt_bytes(primary)} | cópias={fmt_bytes(copy_total)} | livre D:={free_txt} | par JPG/RAW sem par: {jpg_no_raw}/{raw_no_jpg}")

    def add_to_queue(self):
        source = self.source_var.get().strip()
        prof = self.prof_var.get().strip()
        if not source or not Path(source).is_dir():
            messagebox.showerror("Fila", "Escolha primeiro uma pasta de origem válida.")
            return
        if not prof:
            messagebox.showerror("Fila", "Informe o profissional.")
            return
        self.queue_items.append((source, prof))
        self.queue_list.insert("end", f"{source}  |  {prof}")
        self._log(f"Fila: adicionado {prof} <- {source}")

    def remove_from_queue(self):
        sel = self.queue_list.curselection()
        if not sel:
            return
        idx = sel[0]
        del self.queue_items[idx]
        self.queue_list.delete(idx)

    def clear_queue(self):
        self.queue_items = []
        self.queue_list.delete(0, "end")

    def _run_jobs(self, jobs, root):
        """jobs: [(origem, profissional, arquivos, outros)]. Roda em thread."""
        _cj, _cv, _cr, _ca = self._copy_flags()
        total_bytes = 0
        for _s, _p, files, _o in jobs:
            _pr, _cp = split_needed(files, _cj, _cv, _cr, _ca)
            total_bytes += _pr + _cp
        total_bytes = max(1, total_bytes)
        self.msg_queue.put(("total_bytes", total_bytes))
        total_report = {"copied": 0, "skipped": 0, "failed": 0, "errors": []}
        done = [0]
        last_pct = [-1]

        def _on_bytes(n):
            done[0] += n
            pct = 100 * done[0] // total_bytes
            if pct != last_pct[0]:
                last_pct[0] = pct
                self.msg_queue.put(("progress_bytes", done[0]))

        ext_base = self.external_var.get().strip()
        copy_event_root = (Path(ext_base) / root.name) if ext_base else None
        manifest = load_manifest(root)
        allocated = {}
        for source, prof, files, _others in jobs:
            leva = next_leva_number(root, prof) + allocated.get(prof, 0)
            allocated[prof] = allocated.get(prof, 0) + 1
            dests = destinations_for(root, prof, copy_event_root, leva=leva)
            _suspects_map = {n: r for n, r in corruption_alerts(files, source)}
            _rollover_post, _rollover_warnings = rollover_split(files)
            report = process_card(
                files, dests, root, prof,
                copy_jpg=_cj,
                copy_video=_cv,
                copy_raw=_cr,
                copy_audio=_ca,
                verify_hash=self.hash_var.get(),
                log=lambda m: self.msg_queue.put(("log", m)),
                manifest=manifest,
                rollover_post=_rollover_post,
                suspects=_suspects_map,
                progress_cb=_on_bytes,
            )
            save_manifest(root, manifest)
            for k in ("copied", "skipped", "failed"):
                total_report[k] += report[k]
            total_report["errors"].extend(report["errors"])
            write_report(root, prof, source, files, report, leva=leva,
                         suspects=[(n, r) for n, r in corruption_alerts(files, source)],
                         rollover_warnings=_rollover_warnings,
                         mode_label=self._mode_label())
            append_history(root, prof, leva, source, files, report)
            self.msg_queue.put(("log", f"Cartão {prof} / Cartao_{leva} registrado no checklist."))
            self.msg_queue.put(("log", f"Cartão {prof}: copiados={report['copied']} pulados={report['skipped']} falhas={report['failed']}"))
        self.msg_queue.put(("done", (total_report, root / "relatorio-descarga.txt")))

    def _start_jobs(self, jobs):
        if self.copying:
            return
        if not jobs:
            messagebox.showinfo("Nada para copiar", "Nenhum JPG, RAW ou vídeo encontrado.")
            return
        try:
            root = self._event_root()
        except ValueError as exc:
            messagebox.showerror("Evento", str(exc))
            return
        primaries, copies = 0, 0
        _cj, _cv, _cr, _ca = self._copy_flags()
        for _s, _p, files, _o in jobs:
            pr, cp = split_needed(files, _cj, _cv, _cr, _ca)
            primaries += pr
            copies += cp
        ext_base = self.external_var.get().strip()
        d_need = primaries if (ext_base and copies > 0) else primaries + copies
        free = free_space_for(self.base_var.get().strip())
        if free is not None and free < d_need:
            if not messagebox.askyesno("Espaço", f"Espaço livre em D: ({fmt_bytes(free)}) é menor que o necessário "
                                                 f"({fmt_bytes(d_need)}). Continuar mesmo assim?"):
                return
        if ext_base and copies > 0:
            ext_free = free_space_for(ext_base)
            if ext_free is not None and ext_free < copies:
                if not messagebox.askyesno("Espaço nas cópias", f"Espaço livre na pasta de cópias ({fmt_bytes(ext_free)}) é menor que o necessário "
                                                     f"({fmt_bytes(copies)}). Continuar mesmo assim?"):
                    return
        self._save_current_config()
        self.copying = True
        self.last_success = False
        self.btn_eject.config(state="disabled")
        self.btn_copy.config(state="disabled")
        self.btn_scan.config(state="disabled")
        self.progress["maximum"] = max(1, primaries + copies)
        self.progress["value"] = 0
        self.progress_var.set("0%")
        self.status_var.set("Copiando…")
        threading.Thread(target=self._run_jobs, args=(jobs, root), daemon=True).start()
        self.root.after(200, self._poll)

    def start_copy(self):
        if self.copying:
            return
        # A changed source must never reuse a previous card's scan.
        self.scan = []
        if not self.scan:
            self.analyze()
            if not self.scan:
                messagebox.showinfo("Nada para copiar", "Nenhum JPG, RAW ou vídeo encontrado no cartão.")
                return
        self._start_jobs([(self.source_var.get().strip(), self.prof_var.get().strip(), list(self.scan), self.others)])

    def start_queue(self):
        if not self.queue_items:
            messagebox.showinfo("Fila vazia", "Adicione pelo menos um cartão à fila.")
            return
        try:
            root = self._event_root()
        except ValueError as exc:
            messagebox.showerror("Evento", str(exc))
            return
        jobs = []
        for source, prof in self.queue_items:
            if not self._check_source_dest(source, root):
                messagebox.showerror("Fila", f"Destino inválido para {source}.")
                return
            files, others = scan_source(source)
            if files:
                jobs.append((source, prof, files, others))
            else:
                self._log(f"Fila: nenhum arquivo em {source} ({prof}) — pulado.")
        self._start_jobs(jobs)

    def _play_sound(self, ok):
        if os.name != "nt":
            return
        try:
            import winsound
            if ok:
                winsound.Beep(880, 250)
                winsound.Beep(1320, 250)
            else:
                winsound.Beep(220, 400)
        except Exception:
            pass

    def _poll(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "progress_bytes":
                    self.progress["value"] = payload
                    _max = self.progress["maximum"] or 1
                    self.progress_var.set(f"{100 * payload // _max}%")
                elif kind == "total_bytes":
                    self.progress["maximum"] = payload
                elif kind == "progress":
                    self.progress["value"] = payload
                    _max = self.progress["maximum"] or 1
                    self.progress_var.set(f"{100 * payload // _max}%")
                elif kind == "total":
                    self.progress["maximum"] = payload
                elif kind == "log":
                    self._log(payload)
                elif kind == "done":
                    report, report_path = payload
                    self.copying = False
                    self.progress_var.set("100%")
                    self.status_var.set("Concluído." if report["failed"] == 0 else "Concluído com falhas — veja o relatório antes de ejetar.")
                    self.refresh_checklist()
                    self.btn_copy.config(state="normal")
                    self.btn_scan.config(state="normal")
                    self._log(f"Concluído: copiados={report['copied']} pulados={report['skipped']} "
                              f"falhas={report['failed']} | relatório: {report_path}")
                    self._play_sound(report["failed"] == 0)
                    if self.suspects:
                        self._log("ALERTA: " + "; ".join(f"{n} ({r})" for n, r in self.suspects[:10]) +
                                  " — podem estar corrompidos/interrompidos. Não formate o cartão antes de ver.")
                    if report["failed"] == 0:
                        self.last_success = True
                        self.btn_eject.config(state="normal")
                        messagebox.showinfo(
                            "Descarga concluída",
                            f"Copiados: {report['copied']}\nPulados (já existiam): {report['skipped']}\n"
                            f"Falhas: 0\n\nO cartão NÃO foi apagado.\nAs pastas de sincronização só receberam arquivos completos.\n"
                            "Depois de conferir as pastas, use “Ejetar com segurança”.")
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

    def eject_card(self):
        if os.name == "nt":
            try:
                subprocess.run(["rundll32.exe", "shell32.dll,Control_RunDLL", "hotplug.dll"], check=False)
                self._log("Ejetar: janela de remoção segura do Windows aberta — escolha o cartão nela.")
            except Exception as exc:
                messagebox.showerror("Ejetar", f"Não foi possível abrir a remoção segura: {exc}")
        else:
            messagebox.showinfo("Ejetar", "Neste sistema, use a remoção segura do sistema operacional.")

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


def show_splash(root):
    """Splash com o logo completo, sem borda branca, some sozinho.

    Diagnóstico do problema: o logo em si é um círculo branco que
    preenche quase todo o quadrado da imagem (só os cantos são
    transparentes). Na v1.1 a janela e o rótulo eram brancos com
    margem, então o quadrado branco aparecia em volta do círculo.
    Na v1.2 a janela usa uma cor-chave (magenta, que não existe no
    logo) como fundo e -transparentcolor no Windows: os cantos
    transparentes da imagem mostram essa cor, que o Windows torna
    transparente, e só o círculo do logo fica visível, flutuando.
    Se o sistema não suportar -transparentcolor, cai para fundo
    preto, para o círculo branco se destacar sem quadrado branco.
    """
    try:
        path = resource_path("assets/logo.png")
        if not path.exists():
            return None
        splash = tk.Toplevel(root)
        splash.overrideredirect(True)
        key = "#FF00FF"
        splash.configure(bg=key)
        try:
            splash.attributes("-transparentcolor", key)
        except Exception:
            key = "black"
            splash.configure(bg=key)
        try:
            from PIL import Image, ImageTk

            img = Image.open(path).convert("RGBA")
            img.thumbnail((360, 360), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        except Exception:
            photo = tk.PhotoImage(file=str(path))
        label = tk.Label(splash, image=photo, bg=key, bd=0, highlightthickness=0)
        label.image = photo
        label.pack(padx=0, pady=0)
        splash.update_idletasks()
        x = (splash.winfo_screenwidth() - splash.winfo_width()) // 2
        y = (splash.winfo_screenheight() - splash.winfo_height()) // 2
        splash.geometry(f"+{x}+{y}")
        return splash
    except Exception:
        return None


def main():
    root = tk.Tk()
    root.withdraw()
    if "--smoke-test" in sys.argv:
        # Exercise bundled widgets/theme/fonts without reading user configuration.
        global load_config
        load_config = lambda: {}
        App(root)
        root.update_idletasks()
        root.destroy()
        return
    splash = show_splash(root)
    App(root)
    if splash is not None:
        root.after(1500, lambda: (splash.destroy(), root.deiconify()))
    else:
        root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
