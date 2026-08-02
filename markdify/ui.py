"""CustomTkinter tabanlı ana pencere."""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import __version__, environment
from .config import APP_NAME, ICON_PATH, LOG_PATH, LOGO_PATH, Settings, logger
from .conversion import (
    ConversionError,
    ConversionOptions,
    ConversionService,
    OutputFormat,
    PdfBackend,
    is_supported,
    supported_extensions,
    warm_extension_cache,
)
from .markdown_view import MarkdownView
from .source_view import SourceView

# Sürükle-bırak isteğe bağlıdır; tkinterdnd2 yoksa uygulama yine çalışır.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    class _Root(ctk.CTk, TkinterDnD.DnDWrapper):  # type: ignore[misc]
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)

    DND_AVAILABLE = True
except Exception:  # pragma: no cover - ortama bağlı
    _Root = ctk.CTk  # type: ignore[assignment,misc]
    DND_AVAILABLE = False

# Biçimli çizim pahalıdır; çok büyük belgelerde önizleme kısaltılır.
# Düzenleyici HER ZAMAN tam metni tutar — aksi hâlde kaydetme veri kaybettirirdi.
PREVIEW_CHAR_LIMIT = 200_000

MODE_PREVIEW = "Önizleme"
MODE_EDIT = "Düzenle"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def icon(self) -> str:
        return {
            JobStatus.PENDING: "•",
            JobStatus.RUNNING: "▶",
            JobStatus.DONE: "✓",
            JobStatus.FAILED: "✗",
            JobStatus.CANCELLED: "⊘",
        }[self]

    @property
    def color(self) -> tuple[str, str]:
        return {
            JobStatus.PENDING: ("gray45", "gray60"),
            JobStatus.RUNNING: ("#1f6aa5", "#4aa3df"),
            JobStatus.DONE: ("#1a7f37", "#3fb950"),
            JobStatus.FAILED: ("#c0392b", "#f85149"),
            JobStatus.CANCELLED: ("gray45", "gray60"),
        }[self]


@dataclass
class FileJob:
    """Listedeki tek bir dosyanın durumu ve sonucu."""

    path: Path
    status: JobStatus = JobStatus.PENDING
    output: str = ""
    original_output: str = ""  # dönüşümün ham hâli; "Sıfırla" buna döner
    error: str = ""
    duration: float = 0.0
    row: "FileRow | None" = field(default=None, repr=False, compare=False)

    @property
    def edited(self) -> bool:
        return self.status is JobStatus.DONE and self.output != self.original_output


class FileRow(ctk.CTkFrame):
    """Dosya listesindeki tek satır. Tüm listeyi yeniden kurmadan güncellenir."""

    def __init__(self, master, job: FileJob, on_select, on_remove) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)
        self._job = job

        self.status_label = ctk.CTkLabel(self, text="", width=20)
        self.status_label.grid(row=0, column=0, padx=(4, 0))

        self.name_button = ctk.CTkButton(
            self,
            text=job.path.name,
            anchor="w",
            height=28,
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=("gray82", "gray28"),
            command=on_select,
        )
        self.name_button.grid(row=0, column=1, sticky="ew")

        self.remove_button = ctk.CTkButton(
            self, text="✕", width=26, height=26,
            fg_color="transparent", text_color=("gray45", "gray60"),
            hover_color=("#c0392b", "#f85149"), command=on_remove,
        )
        self.remove_button.grid(row=0, column=2, padx=(0, 4))
        self.refresh()

    def refresh(self, selected: bool = False) -> None:
        self.status_label.configure(
            text=self._job.status.icon, text_color=self._job.status.color
        )
        self.name_button.configure(
            fg_color=("gray78", "gray32") if selected else "transparent"
        )


class MainWindow(_Root):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()

        self.settings = Settings.load()
        self.service = ConversionService()
        self.jobs: list[FileJob] = []
        self.selected_job: FileJob | None = None

        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._cancel = threading.Event()
        self._busy = False
        self._loading_editor = False  # düzenleyiciye program yazarken <<Modified>> susturulur

        ctk.set_appearance_mode(self.settings.appearance)
        ctk.set_default_color_theme("blue")

        self.title(f"{APP_NAME} v{__version__}")
        self.geometry("1460x820")
        self.minsize(1000, 600)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._apply_window_icon()

        self._build_ui()
        self._refresh_environment_banner()
        self._drain_events()
        self._warm_caches()
        logger.info("Ortam: %s", environment.environment_report())

    def _warm_caches(self) -> None:
        """Pahalı ilk yüklemeleri arka planda yapar.

        ``import docling`` yaklaşık 5 saniye sürer. Bu, dosya seçme penceresinin
        uzantı süzgeci için gerekiyordu ve arayüz iş parçacığında yapıldığında
        pencere "yanıt vermiyor" durumuna düşüyordu. Burada açılışta sessizce
        hazırlanır; hazır olana kadar yerleşik yedek liste kullanılır.
        """
        threading.Thread(
            target=warm_extension_cache, daemon=True, name="warm-extensions"
        ).start()

    def _apply_window_icon(self) -> None:
        """Başlık çubuğu, görev çubuğu ve alt pencereler için uygulama ikonu.

        Windows'ta ``.ico`` tercih edilir: çok çözünürlüklü olduğu için her yerde
        (16 px başlık çubuğu, 32 px görev çubuğu, 256 px Alt+Tab) net görünür.
        ``default=True`` ikonu ayarlar penceresi gibi alt pencerelere de taşır.
        PNG yedeği Windows dışı ortamlar ve ``.ico`` okunamazsa devreye girer.
        """
        if ICON_PATH.exists():
            try:
                self.iconbitmap(default=str(ICON_PATH))
                return
            except Exception as exc:
                logger.debug("iconbitmap başarısız (%s), PNG'ye düşülüyor.", exc)

        if LOGO_PATH.exists():
            try:
                self._icon_image = tk.PhotoImage(file=str(LOGO_PATH))
                self.iconphoto(True, self._icon_image)  # referans tutulmalı
                return
            except Exception as exc:
                logger.debug("iconphoto başarısız: %s", exc)

        logger.warning("Uygulama ikonu bulunamadı: %s", ICON_PATH)

    # ================================================================== #
    # Arayüz kurulumu
    # ================================================================== #

    def _build_ui(self) -> None:
        # 0: dosya listesi | 1: kaynak belge (gizlenebilir) | 2: dönüşüm çıktısı
        self.grid_columnconfigure(0, weight=0, minsize=250)
        self.grid_columnconfigure(1, weight=4, minsize=300)
        self.grid_columnconfigure(2, weight=5, minsize=380)
        self.grid_rowconfigure(2, weight=1)

        self._build_toolbar()
        self._build_banner()
        self._build_file_panel()
        self._build_source_panel()
        self._build_preview_panel()
        self._build_statusbar()
        self._apply_source_visibility()

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self)
        bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(12, 6))
        bar.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(bar, text="Dosya Ekle", width=110, command=self.add_files).grid(
            row=0, column=0, padx=(10, 4), pady=10
        )
        ctk.CTkButton(bar, text="Klasör Ekle", width=110, command=self.add_folder).grid(
            row=0, column=1, padx=4, pady=10
        )
        ctk.CTkButton(
            bar, text="Temizle", width=90, command=self.clear_jobs,
            fg_color="transparent", border_width=1, text_color=("gray20", "gray85"),
        ).grid(row=0, column=2, padx=4, pady=10)

        self.format_menu = ctk.CTkOptionMenu(
            bar,
            values=[fmt.label for fmt in OutputFormat],
            width=170,
            command=self._on_format_change,
        )
        self.format_menu.set(OutputFormat(self.settings.output_format).label)
        self.format_menu.grid(row=0, column=4, padx=4, pady=10)

        self.source_toggle = ctk.CTkSwitch(
            bar, text="Kaynak", command=self.toggle_source, width=90
        )
        self.source_toggle.grid(row=0, column=3, padx=(16, 4), pady=10, sticky="w")

        ctk.CTkButton(
            bar, text="⚙", width=40, command=self.open_settings,
            fg_color="transparent", border_width=1, text_color=("gray20", "gray85"),
        ).grid(row=0, column=5, padx=4, pady=10)

        self.convert_button = ctk.CTkButton(
            bar, text="Dönüştür", width=120, command=self.start_conversion
        )
        self.convert_button.grid(row=0, column=6, padx=(4, 10), pady=10)

    def _build_banner(self) -> None:
        """Eksik bağımlılıklar için uyarı şeridi (her şey yolundaysa gizlenir)."""
        self.banner = ctk.CTkFrame(self, fg_color=("#fdf2d0", "#3d3419"))
        self.banner.grid_columnconfigure(0, weight=1)

        self.banner_label = ctk.CTkLabel(
            self.banner, text="", anchor="w", justify="left",
            text_color=("#7a5d00", "#f0c674"), wraplength=760,
        )
        self.banner_label.grid(row=0, column=0, sticky="ew", padx=12, pady=8)

        self.banner_button = ctk.CTkButton(self.banner, text="", width=150)
        self.banner_button.grid(row=0, column=1, padx=(0, 12), pady=8)

    def _build_file_panel(self) -> None:
        panel = ctk.CTkFrame(self)
        panel.grid(row=2, column=0, sticky="nsew", padx=(12, 3), pady=6)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        hint = (
            "Dosyaları buraya sürükleyip bırakın"
            if DND_AVAILABLE
            else "Yukarıdaki düğmelerle dosya veya klasör ekleyin"
        )
        self.drop_hint = ctk.CTkLabel(
            panel, text=hint, height=44, corner_radius=8,
            fg_color=("gray88", "gray22"), text_color=("gray35", "gray65"),
        )
        self.drop_hint.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))

        self.file_list = ctk.CTkScrollableFrame(panel, label_text="Dosyalar")
        self.file_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        self.file_list.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(panel)
        self.progress.set(0)
        self.progress.grid(row=2, column=0, sticky="ew", padx=10, pady=(6, 10))

        if DND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

    def _build_source_panel(self) -> None:
        """Ortadaki sütun: kaynak belgenin (PDF/görüntü) sayfa önizlemesi."""
        self.source_panel = ctk.CTkFrame(self)
        self.source_panel.grid(row=2, column=1, sticky="nsew", padx=3, pady=6)
        self.source_panel.grid_rowconfigure(1, weight=1)
        self.source_panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.source_panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        header.grid_columnconfigure(0, weight=1)

        self.source_title = ctk.CTkLabel(
            header, text="Kaynak belge", anchor="w", font=ctk.CTkFont(weight="bold")
        )
        self.source_title.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header, text="Aç", width=48, height=26, command=self.open_source_file,
            fg_color="transparent", border_width=1, text_color=("gray20", "gray85"),
        ).grid(row=0, column=1)

        self.source_view = SourceView(self.source_panel, on_status=self._set_status)
        self.source_view.grid(row=1, column=0, sticky="nsew", padx=4, pady=(4, 8))

    def _apply_source_visibility(self) -> None:
        """Kaynak sütununu ayarlara göre gösterir/gizler ve genişliği uyarlar."""
        if self.settings.show_source:
            self.source_panel.grid()
            self.grid_columnconfigure(1, weight=4, minsize=300)
            self.source_toggle.select()
        else:
            self.source_panel.grid_remove()
            self.grid_columnconfigure(1, weight=0, minsize=0)
            self.source_toggle.deselect()

    def toggle_source(self) -> None:
        self.settings.show_source = bool(self.source_toggle.get())
        self._apply_source_visibility()
        if self.settings.show_source:
            self.source_view.show(self.selected_job.path if self.selected_job else None)

    def open_source_file(self) -> None:
        """Kaynak dosyayı sistemin varsayılan uygulamasında açar."""
        if self.selected_job is None:
            messagebox.showinfo(APP_NAME, "Önce listeden bir dosya seçin.")
            return
        self._open_path(self.selected_job.path)

    def _build_preview_panel(self) -> None:
        panel = ctk.CTkFrame(self)
        panel.grid(row=2, column=2, sticky="nsew", padx=(6, 12), pady=6)
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        # --- başlık satırı ---
        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))
        header.grid_columnconfigure(0, weight=1)

        self.preview_title = ctk.CTkLabel(
            header, text="Önizleme", anchor="w", font=ctk.CTkFont(weight="bold")
        )
        self.preview_title.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(header, text="Kopyala", width=78, command=self.copy_preview).grid(
            row=0, column=1, padx=(4, 0)
        )
        ctk.CTkButton(header, text="Kaydet", width=78, command=self.save_selected).grid(
            row=0, column=2, padx=(4, 0)
        )
        ctk.CTkButton(header, text="Tümünü Kaydet", width=118, command=self.save_all).grid(
            row=0, column=3, padx=(4, 0)
        )

        # --- mod seçimi + düzenleme araçları ---
        modebar = ctk.CTkFrame(panel, fg_color="transparent")
        modebar.grid(row=1, column=0, sticky="ew", padx=10, pady=(4, 6))
        modebar.grid_columnconfigure(1, weight=1)

        self.mode_switch = ctk.CTkSegmentedButton(
            modebar, values=[MODE_PREVIEW, MODE_EDIT], command=self._on_mode_change, width=200
        )
        self.mode_switch.set(MODE_PREVIEW)
        self.mode_switch.grid(row=0, column=0, sticky="w")

        self.dirty_label = ctk.CTkLabel(
            modebar, text="", anchor="w", text_color=("#b26a00", "#f0c674"),
            font=ctk.CTkFont(size=11),
        )
        self.dirty_label.grid(row=0, column=1, sticky="w", padx=10)

        self.edit_tools = ctk.CTkFrame(modebar, fg_color="transparent")
        self.edit_tools.grid(row=0, column=2, sticky="e")
        for index, (label, width, command) in enumerate((
            ("↶ Geri Al", 86, self.editor_undo),
            ("↷ Yinele", 84, self.editor_redo),
            ("Sıfırla", 76, self.editor_reset),
        )):
            ctk.CTkButton(
                self.edit_tools, text=label, width=width, height=26, command=command,
                fg_color="transparent", border_width=1, text_color=("gray20", "gray85"),
            ).grid(row=0, column=index, padx=(4, 0))
        self.edit_tools.grid_remove()  # önizleme modunda gizli

        # --- gövde: iki görünüm aynı hücrede, biri gösterilir ---
        self.preview_view = MarkdownView(panel)
        self.preview_view.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.editor = ctk.CTkTextbox(
            panel, wrap="word", undo=True, font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.editor.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.editor.grid_remove()
        self.editor.bind("<<Modified>>", self._on_editor_modified)

        self.preview_view.show_plain("Bir dosya ekleyip “Dönüştür”e basın.")

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent", height=26)
        bar.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 10))
        bar.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            bar, text="Hazır.", anchor="w", text_color=("gray35", "gray65")
        )
        self.status_label.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            bar, text="Günlük", width=70, height=24, command=self.open_log,
            fg_color="transparent", text_color=("gray45", "gray60"), hover_color=("gray85", "gray25"),
        ).grid(row=0, column=1, sticky="e")

    # ================================================================== #
    # Ortam bildirimi
    # ================================================================== #

    def _refresh_environment_banner(self) -> None:
        """Eksik bağımlılık varsa şeridi gösterir, yoksa gizler."""
        if not environment.docling_installed():
            self._show_banner(
                "Docling paketi kurulu değil — dönüştürme yapılamaz.",
                "Docling'i Kur",
                self._install_docling,
            )
            self.convert_button.configure(state="disabled")
            return

        self.convert_button.configure(state="normal")

        if environment.find_libreoffice() is None:
            self._show_banner(
                "LibreOffice bulunamadı. Word belgelerindeki çizim ve şekiller "
                "eksik dönüşebilir (PDF'ler bundan etkilenmez).",
                "LibreOffice'i Kur",
                self._install_libreoffice,
            )
            return

        self.banner.grid_remove()

    def _show_banner(self, text: str, button_text: str, command) -> None:
        self.banner_label.configure(text=text)
        self.banner_button.configure(text=button_text, command=command, state="normal")
        self.banner.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 6))

    def _install_docling(self) -> None:
        self._run_installer("Docling", environment.install_docling)

    def _install_libreoffice(self) -> None:
        if not environment.winget_available():
            messagebox.showinfo(
                APP_NAME,
                "winget bulunamadı. LibreOffice'i elle kurabilirsiniz:\n"
                "https://www.libreoffice.org/download/download/",
            )
            return
        self._run_installer("LibreOffice", environment.install_libreoffice)

    def _run_installer(self, name: str, install_fn) -> None:
        self.banner_button.configure(state="disabled", text="Kuruluyor…")
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        def worker() -> None:
            try:
                install_fn(lambda line: self._post("status", f"{name}: {line[:110]}"))
                self._post("install_done", name)
            except Exception as exc:
                logger.exception("%s kurulumu başarısız", name)
                self._post("install_failed", (name, str(exc)))

        threading.Thread(target=worker, daemon=True, name=f"install-{name}").start()

    # ================================================================== #
    # Dosya listesi
    # ================================================================== #

    def _on_drop(self, event) -> None:
        self._add_paths(self.tk.splitlist(event.data))

    @staticmethod
    def _dialog_filetypes() -> list[tuple[str, str]]:
        """Dosya seçme penceresinin süzgeçleri.

        Tek bir devasa desen listesi yerine gruplar sunulur: 70 uzantılık tek
        satır hem okunaksızdır hem de bazı Windows sürümlerinde kırpılır.
        """
        known = supported_extensions()

        def group(*extensions: str) -> str:
            return " ".join(f"*{e}" for e in extensions if e in known)

        groups = [
            ("Tüm desteklenen belgeler", " ".join(f"*{e}" for e in sorted(known))),
            ("PDF", group(".pdf")),
            ("Word", group(".docx", ".doc", ".odt", ".rtf", ".dotx")),
            ("PowerPoint", group(".pptx", ".ppt", ".odp")),
            ("Excel / tablo", group(".xlsx", ".xls", ".ods", ".csv")),
            ("Görüntü", group(".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")),
            ("Metin / işaretleme", group(".md", ".txt", ".html", ".htm", ".xhtml", ".tex", ".adoc")),
            ("E-kitap", group(".epub")),
        ]
        # Bu docling sürümünde karşılığı olmayan grupları gösterme.
        return [(label, patterns) for label, patterns in groups if patterns] + [
            ("Tüm dosyalar", "*.*")
        ]

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Dönüştürülecek dosyaları seçin",
            initialdir=self.settings.last_input_dir or None,
            filetypes=self._dialog_filetypes(),
        )
        if paths:
            self.settings.last_input_dir = str(Path(paths[0]).parent)
            self._add_paths(paths)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Klasör seçin (alt klasörler dâhil taranır)",
            initialdir=self.settings.last_input_dir or None,
        )
        if not folder:
            return
        self.settings.last_input_dir = folder
        found = sorted(p for p in Path(folder).rglob("*") if p.is_file() and is_supported(p))
        if not found:
            messagebox.showinfo(APP_NAME, "Bu klasörde desteklenen dosya bulunamadı.")
            return
        self._add_paths(found)

    def _add_paths(self, paths) -> None:
        known = {job.path for job in self.jobs}
        added = skipped = 0

        for raw in paths:
            path = Path(str(raw)).expanduser()
            if not path.is_file():
                continue
            if not is_supported(path):
                skipped += 1
                continue
            if path in known:
                continue
            job = FileJob(path=path)
            self.jobs.append(job)
            known.add(path)
            self._append_row(job)
            added += 1

        message = f"{added} dosya eklendi (toplam {len(self.jobs)})."
        if skipped:
            message += f" {skipped} dosya desteklenmeyen türde olduğu için atlandı."
        self._set_status(message)

    def _append_row(self, job: FileJob) -> None:
        row = FileRow(
            self.file_list,
            job,
            on_select=lambda j=job: self.select_job(j),
            on_remove=lambda j=job: self.remove_job(j),
        )
        row.grid(row=len(self.jobs) - 1, column=0, sticky="ew", pady=1)
        job.row = row

    def remove_job(self, job: FileJob) -> None:
        if self._busy:
            return
        if job.row is not None:
            job.row.destroy()
        self.jobs.remove(job)
        if self.selected_job is job:
            self.selected_job = None
            self.preview_title.configure(text="Önizleme")
            self.source_title.configure(text="Kaynak belge")
            self.source_view.clear()
            self._refresh_views()
        for index, remaining in enumerate(self.jobs):
            if remaining.row is not None:
                remaining.row.grid(row=index, column=0, sticky="ew", pady=1)
        self._set_status(f"Dosya çıkarıldı (kalan {len(self.jobs)}).")

    def clear_jobs(self) -> None:
        if self._busy:
            return
        for job in self.jobs:
            if job.row is not None:
                job.row.destroy()
        self.jobs.clear()
        self.selected_job = None
        self.progress.set(0)
        self.preview_title.configure(text="Önizleme")
        self.source_title.configure(text="Kaynak belge")
        self.source_view.clear()
        self._refresh_views()
        self._set_status("Liste temizlendi.")

    def select_job(self, job: FileJob) -> None:
        # Başka bir dosyaya geçmeden önce düzenlenmiş metni kaybetme.
        if self.selected_job is not job:
            self._commit_editor()

        self.selected_job = job
        for other in self.jobs:
            if other.row is not None:
                other.row.refresh(selected=other is job)

        self.preview_title.configure(text=f"Önizleme — {job.path.name}")
        self.source_title.configure(text=f"Kaynak — {job.path.name}")
        if self.settings.show_source:
            self.source_view.show(job.path)
        self._refresh_views()

    # ================================================================== #
    # Önizleme / düzenleme modları
    # ================================================================== #

    @property
    def in_edit_mode(self) -> bool:
        return self.mode_switch.get() == MODE_EDIT

    def _on_mode_change(self, _value: str) -> None:
        """Sekme değişimi: düzenlemeden çıkarken metni işle, sonra görünümü değiştir."""
        if not self.in_edit_mode:
            self._commit_editor()
        self._refresh_views()

    def _refresh_views(self) -> None:
        """Seçili işi geçerli moda göre uygun görünüme basar."""
        job = self.selected_job

        if self.in_edit_mode:
            self.preview_view.grid_remove()
            self.editor.grid()
            self.edit_tools.grid()
            self._load_editor(job)
        else:
            self.editor.grid_remove()
            self.edit_tools.grid_remove()
            self.preview_view.grid()
            self._load_preview(job)

        self._refresh_dirty_label()

    def _load_preview(self, job: FileJob | None) -> None:
        if job is None:
            self.preview_view.show_plain("Soldaki listeden bir dosya seçin.")
            return

        if job.status is JobStatus.DONE:
            text = job.output
            if len(text) > PREVIEW_CHAR_LIMIT:
                text = text[:PREVIEW_CHAR_LIMIT] + (
                    "\n\n… (önizleme kısaltıldı — Düzenle sekmesinde ve kayıtta tamamı yer alır)"
                )
            # Markdown yalnızca markdown çıktısında ayrıştırılır; JSON/metin ham gösterilir.
            if OutputFormat.from_label(self.format_menu.get()) is OutputFormat.MARKDOWN:
                self.preview_view.show_markdown(text)
            else:
                self.preview_view.show_plain(text)
        elif job.status is JobStatus.FAILED:
            self.preview_view.show_plain(f"Dönüştürme başarısız:\n\n{job.error}")
        elif job.status is JobStatus.RUNNING:
            self.preview_view.show_plain("Dönüştürülüyor…")
        else:
            self.preview_view.show_plain("(Henüz dönüştürülmedi)")

    def _load_editor(self, job: FileJob | None) -> None:
        """Düzenleyiciye TAM metni yükler (kısaltma yok — veri kaybını önler)."""
        self._loading_editor = True
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")

        if job is None:
            self.editor.insert("1.0", "")
            self.editor.configure(state="disabled")
        elif job.status is JobStatus.DONE:
            self.editor.insert("1.0", job.output)
            self.editor.configure(state="normal")
        else:
            self.editor.insert("1.0", job.error or "(Henüz dönüştürülmedi)")
            self.editor.configure(state="disabled")

        self.editor.edit_reset()   # geri alma geçmişini yeni belge için sıfırla
        self.editor.edit_modified(False)
        self._loading_editor = False

    def _editor_text(self) -> str:
        # Tk metin bileşeni sona daima bir "\n" ekler; onu geri al.
        text = self.editor.get("1.0", "end")
        return text[:-1] if text.endswith("\n") else text

    def _commit_editor(self) -> bool:
        """Düzenleyicideki metni seçili işe yazar. Değişiklik olduysa True döner."""
        job = self.selected_job
        if job is None or job.status is not JobStatus.DONE:
            return False
        if not self.editor.winfo_exists() or str(self.editor.cget("state")) == "disabled":
            return False

        current = self._editor_text()
        if current == job.output:
            return False

        job.output = current
        self.editor.edit_modified(False)  # işlendi: artık "kaydedilmemiş" değil
        logger.debug("Düzenleme işlendi: %s (%d karakter)", job.path.name, len(current))
        return True

    def _on_editor_modified(self, _event=None) -> None:
        self._refresh_dirty_label()

    def _refresh_dirty_label(self) -> None:
        """Kirlilik göstergesini günceller.

        Kaynak olarak Tk'nin kendi ``edit_modified`` bayrağı kullanılır. Bir
        boole bayrağıyla ``<<Modified>>`` olaylarını bastırmak GÜVENİLMEZDİR:
        Tk bu olayı gecikmeli (kuyruğa alarak) gönderir, dolayısıyla olay
        işlendiğinde koruma bayrağı çoktan temizlenmiş olur ve program
        tarafından yapılan yükleme, kullanıcı düzenlemesi gibi görünür.
        """
        job = self.selected_job
        if job is None or job.status is not JobStatus.DONE:
            self.dirty_label.configure(text="")
            return

        if self.in_edit_mode and bool(self.editor.edit_modified()):
            self.dirty_label.configure(text="● düzenlendi (kaydedilmedi)")
        elif job.edited:
            self.dirty_label.configure(text="● düzenlendi")
        else:
            self.dirty_label.configure(text="")

    # ---- düzenleyici eylemleri (CRUD) ---- #

    def editor_undo(self) -> None:
        try:
            self.editor.edit_undo()
        except Exception:
            self._set_status("Geri alınacak bir değişiklik yok.")
        self._refresh_dirty_label(pending=True)

    def editor_redo(self) -> None:
        try:
            self.editor.edit_redo()
        except Exception:
            self._set_status("Yinelenecek bir değişiklik yok.")
        self._refresh_dirty_label(pending=True)

    def editor_reset(self) -> None:
        """Belgeyi dönüşümün ham hâline döndürür."""
        job = self.selected_job
        if job is None or job.status is not JobStatus.DONE:
            return
        if not job.edited and self._editor_text() == job.original_output:
            self._set_status("Belge zaten özgün hâlinde.")
            return
        if not messagebox.askyesno(
            APP_NAME, "Tüm düzenlemeler geri alınıp özgün dönüşüm metni yüklenecek. Onaylıyor musunuz?"
        ):
            return
        job.output = job.original_output
        self._load_editor(job)
        self._refresh_dirty_label()
        self._set_status("Belge özgün hâline döndürüldü.")

    # ================================================================== #
    # Dönüştürme
    # ================================================================== #

    def start_conversion(self) -> None:
        if self._busy:
            self._cancel.set()
            self.convert_button.configure(state="disabled", text="Durduruluyor…")
            return

        if not environment.docling_installed():
            messagebox.showwarning(APP_NAME, "Önce Docling'i kurun.")
            return
        if not self.jobs:
            messagebox.showinfo(APP_NAME, "Önce dönüştürülecek dosya ekleyin.")
            return

        pending = [j for j in self.jobs if j.status is not JobStatus.DONE]
        if not pending:
            if not messagebox.askyesno(
                APP_NAME, "Tüm dosyalar zaten dönüştürülmüş. Yeniden dönüştürülsün mü?"
            ):
                return
            pending = self.jobs

        self._busy = True
        self._cancel.clear()
        self.convert_button.configure(text="Durdur")
        self.progress.configure(mode="determinate")
        self.progress.set(0)

        output_format = OutputFormat.from_label(self.format_menu.get())
        options = ConversionOptions(
            pdf_backend=PdfBackend(self.settings.pdf_backend),
            enable_ocr=self.settings.enable_ocr,
        )

        threading.Thread(
            target=self._conversion_worker,
            args=(pending, output_format, options),
            daemon=True,
            name="conversion",
        ).start()

    def _conversion_worker(
        self, jobs: list[FileJob], output_format: OutputFormat, options: ConversionOptions
    ) -> None:
        """Arka plan dönüştürme döngüsü.

        ``finally`` bloğu, hata ne olursa olsun arayüzün "çalışıyor" durumunda
        kilitli kalmamasını garanti eder.
        """
        try:
            for job in jobs:
                job.status = JobStatus.PENDING
                self._post("job", job)

            self.service.prepare(options, lambda text: self._post("status", text))

            total = len(jobs)
            for index, job in enumerate(jobs):
                if self._cancel.is_set():
                    for remaining in jobs[index:]:
                        remaining.status = JobStatus.CANCELLED
                        self._post("job", remaining)
                    break

                job.status = JobStatus.RUNNING
                self._post("job", job)
                self._post("status", f"Dönüştürülüyor: {job.path.name} ({index + 1}/{total})")

                started = time.monotonic()
                try:
                    job.output = self.service.convert(job.path, output_format)
                    job.original_output = job.output  # "Sıfırla" bu hâle döner
                    job.status = JobStatus.DONE
                    job.error = ""
                except ConversionError as exc:
                    job.status = JobStatus.FAILED
                    job.error = str(exc)
                    logger.warning("Dönüşüm başarısız (%s): %s", job.path.name, exc)
                except Exception as exc:  # beklenmeyen hata: kaydet ama döngüyü sürdür
                    job.status = JobStatus.FAILED
                    job.error = str(exc)
                    logger.exception("Beklenmeyen dönüşüm hatası: %s", job.path)

                job.duration = time.monotonic() - started
                self._post("job", job)
                self._post("progress", (index + 1) / total)

        except Exception as exc:
            logger.exception("Dönüştürme oturumu başarısız")
            self._post("fatal", str(exc))
        finally:
            self._post("finished", None)

    # ================================================================== #
    # Olay kuyruğu (arka plan → arayüz)
    # ================================================================== #

    def _post(self, kind: str, payload: object) -> None:
        self._events.put((kind, payload))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self.after(80, self._drain_events)

    def _handle_event(self, kind: str, payload: object) -> None:
        if kind == "status":
            self._set_status(str(payload))

        elif kind == "progress":
            self.progress.set(float(payload))  # type: ignore[arg-type]

        elif kind == "job":
            job = payload  # type: ignore[assignment]
            if job.row is not None:  # type: ignore[union-attr]
                job.row.refresh(selected=job is self.selected_job)  # type: ignore[union-attr]
            if job is self.selected_job:
                self.select_job(job)  # type: ignore[arg-type]

        elif kind == "finished":
            self._busy = False
            self._cancel.clear()
            self.convert_button.configure(state="normal", text="Dönüştür")
            done = sum(1 for j in self.jobs if j.status is JobStatus.DONE)
            failed = sum(1 for j in self.jobs if j.status is JobStatus.FAILED)
            cancelled = sum(1 for j in self.jobs if j.status is JobStatus.CANCELLED)
            summary = f"Tamamlandı — {done} başarılı, {failed} hatalı"
            if cancelled:
                summary += f", {cancelled} iptal"
            self._set_status(summary + ".")
            if done and self.selected_job is None:
                first = next((j for j in self.jobs if j.status is JobStatus.DONE), None)
                if first:
                    self.select_job(first)

        elif kind == "fatal":
            self._set_status("Dönüştürme başlatılamadı.")
            messagebox.showerror(
                APP_NAME,
                f"Dönüştürme başlatılamadı:\n\n{payload}\n\nAyrıntılar için Günlük'e bakın.",
            )

        elif kind == "install_done":
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(0)
            self._set_status(f"{payload} kuruldu.")
            self._refresh_environment_banner()

        elif kind == "install_failed":
            name, error = payload  # type: ignore[misc]
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(0)
            self.banner_button.configure(state="normal")
            self._set_status(f"{name} kurulumu başarısız.")
            messagebox.showerror(APP_NAME, f"{name} kurulamadı:\n\n{error}")

    # ================================================================== #
    # Çıktı
    # ================================================================== #

    def copy_preview(self) -> None:
        self._commit_editor()
        job = self.selected_job
        if job is None or job.status is not JobStatus.DONE:
            messagebox.showinfo(APP_NAME, "Kopyalanacak bir sonuç yok.")
            return
        self.clipboard_clear()
        self.clipboard_append(job.output)
        self._set_status("Sonuç panoya kopyalandı.")

    def save_selected(self) -> None:
        self._commit_editor()  # düzenlenmiş metin kaydedilsin
        job = self.selected_job
        if job is None or job.status is not JobStatus.DONE:
            messagebox.showinfo(APP_NAME, "Önce başarıyla dönüştürülmüş bir dosya seçin.")
            return

        output_format = OutputFormat.from_label(self.format_menu.get())
        target = filedialog.asksaveasfilename(
            title="Farklı kaydet",
            initialfile=job.path.stem + output_format.extension,
            initialdir=self.settings.last_output_dir or None,
            defaultextension=output_format.extension,
            filetypes=[("Tüm dosyalar", "*.*")],
        )
        if not target:
            return
        try:
            Path(target).write_text(job.output, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Kaydedilemedi:\n{exc}")
            return
        self.settings.last_output_dir = str(Path(target).parent)
        self._set_status(f"Kaydedildi: {target}")

    def save_all(self) -> None:
        self._commit_editor()  # düzenlenmiş metin kaydedilsin
        done = [j for j in self.jobs if j.status is JobStatus.DONE]
        if not done:
            messagebox.showinfo(APP_NAME, "Kaydedilecek başarılı dönüşüm yok.")
            return

        folder = filedialog.askdirectory(
            title="Çıktıların kaydedileceği klasörü seçin",
            initialdir=self.settings.last_output_dir or None,
        )
        if not folder:
            return

        output_format = OutputFormat.from_label(self.format_menu.get())
        directory = Path(folder)
        saved, errors = 0, []
        for job in done:
            target = self._unique_path(directory / (job.path.stem + output_format.extension))
            try:
                target.write_text(job.output, encoding="utf-8")
                saved += 1
            except OSError as exc:
                errors.append(f"{job.path.name}: {exc}")

        self.settings.last_output_dir = folder
        self._set_status(f"{saved} dosya kaydedildi → {folder}")

        if errors:
            messagebox.showwarning(
                APP_NAME, f"{saved} dosya kaydedildi, {len(errors)} hata:\n\n" + "\n".join(errors[:8])
            )
        elif messagebox.askyesno(APP_NAME, f"{saved} dosya kaydedildi.\n\nKlasör açılsın mı?"):
            self._open_path(directory)

    @staticmethod
    def _unique_path(path: Path) -> Path:
        """Var olan dosyanın üzerine yazmamak için ``ad (2).md`` gibi ad üretir."""
        if not path.exists():
            return path
        for counter in range(2, 1000):
            candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
            if not candidate.exists():
                return candidate
        return path

    # ================================================================== #
    # Ayarlar penceresi
    # ================================================================== #

    def open_settings(self) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Ayarlar")
        window.geometry("520x360")
        window.transient(self)
        window.grab_set()
        window.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(
            window, text="Ayarlar", font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 12))

        row += 1
        ctk.CTkLabel(window, text="PDF arka ucu").grid(row=row, column=0, sticky="w", padx=20, pady=8)
        backend_menu = ctk.CTkOptionMenu(window, values=[b.label for b in PdfBackend], width=240)
        backend_menu.set(PdfBackend(self.settings.pdf_backend).label)
        backend_menu.grid(row=row, column=1, sticky="e", padx=20, pady=8)

        row += 1
        resolved = ConversionService.resolve_pdf_backend(PdfBackend(self.settings.pdf_backend))
        note = f"Etkin arka uç: {resolved.value}"
        if not environment.docling_parse_usable():
            note += (
                "\ndocling-parse bu kurulumda kullanılamıyor: kurulum yolunda ASCII "
                "dışı karakter var. pypdfium2 kullanılıyor."
            )
        ctk.CTkLabel(
            window, text=note, anchor="w", justify="left", wraplength=460,
            text_color=("gray40", "gray60"), font=ctk.CTkFont(size=11),
        ).grid(row=row, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 8))

        row += 1
        ocr_switch = ctk.CTkSwitch(
            window, text="OCR uygula (taranmış belgeler için — yavaşlatır)"
        )
        ocr_switch.select() if self.settings.enable_ocr else ocr_switch.deselect()
        ocr_switch.grid(row=row, column=0, columnspan=2, sticky="w", padx=20, pady=10)

        row += 1
        ctk.CTkLabel(window, text="Görünüm").grid(row=row, column=0, sticky="w", padx=20, pady=8)
        appearance_menu = ctk.CTkOptionMenu(
            window, values=["system", "light", "dark"], width=240
        )
        appearance_menu.set(self.settings.appearance)
        appearance_menu.grid(row=row, column=1, sticky="e", padx=20, pady=8)

        row += 1
        window.grid_rowconfigure(row, weight=1)

        row += 1
        actions = ctk.CTkFrame(window, fg_color="transparent")
        actions.grid(row=row, column=0, columnspan=2, sticky="e", padx=20, pady=16)

        def apply_and_close() -> None:
            self.settings.pdf_backend = PdfBackend.from_label(backend_menu.get()).value
            self.settings.enable_ocr = bool(ocr_switch.get())
            self.settings.appearance = appearance_menu.get()
            self.settings.save()
            ctk.set_appearance_mode(self.settings.appearance)
            # Tk bileşenleri CTk temasını kendiliğinden almaz; elle uygula.
            self.preview_view.apply_theme()
            self.source_view.apply_theme()
            if not self.in_edit_mode:
                self._load_preview(self.selected_job)
            # Seçenekler değişti: dönüştürücü yeniden kurulmalı.
            self.service = ConversionService()
            self._set_status("Ayarlar kaydedildi.")
            window.destroy()

        ctk.CTkButton(
            actions, text="Vazgeç", width=90, command=window.destroy,
            fg_color="transparent", border_width=1, text_color=("gray20", "gray85"),
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(actions, text="Kaydet", width=90, command=apply_and_close).grid(row=0, column=1)

    # ================================================================== #
    # Yardımcılar
    # ================================================================== #

    def _on_format_change(self, label: str) -> None:
        self.settings.output_format = OutputFormat.from_label(label).value
        # Markdown mı düz metin mi gösterileceği biçime bağlı: görünümü tazele.
        if not self.in_edit_mode:
            self._load_preview(self.selected_job)

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def open_log(self) -> None:
        if not LOG_PATH.exists():
            messagebox.showinfo(APP_NAME, "Henüz günlük kaydı oluşmadı.")
            return
        self._open_path(LOG_PATH)

    @staticmethod
    def _open_path(path: Path) -> None:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]  # Windows
        except AttributeError:  # pragma: no cover - Windows dışı
            subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            logger.warning("Yol açılamadı (%s): %s", path, exc)

    def _on_close(self) -> None:
        self._commit_editor()
        if any(job.edited for job in self.jobs):
            if not messagebox.askyesno(
                APP_NAME,
                "Kaydedilmemiş düzenlemeler var. Yine de çıkılsın mı?",
                icon="warning",
            ):
                return
        self._cancel.set()
        self.settings.save()
        logger.info("Uygulama kapatılıyor.")
        self.destroy()
