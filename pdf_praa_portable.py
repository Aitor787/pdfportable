"""Aplicación principal de PDF PRAA Portable."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class DependencyMissingError(RuntimeError):
    """Señala que un paquete opcional es necesario para la acción solicitada."""


def require_dependency(obj, package_name: str):
    """Devuelve ``obj`` o lanza ``DependencyMissingError`` si es ``None``."""

    if obj is None:
        raise DependencyMissingError(
            f"Se requiere el paquete opcional '{package_name}'. Ejecuta build_portable_app.bat para instalarlo."
        )
    return obj


def show_error(title: str, message: str) -> None:
    """Muestra un error en pantalla o escribe en STDERR si no hay entorno gráfico."""

    try:
        messagebox.showerror(title, message)
    except tk.TclError:
        print(f"{title}: {message}", file=sys.stderr)


try:  # Dependencias opcionales cargadas de forma segura
    import pikepdf  # type: ignore
except ImportError:  # pragma: no cover - verificado mediante tests
    pikepdf = None  # type: ignore[assignment]

try:  # type: ignore[import-not-found]
    import fitz  # noqa: F401  # PyMuPDF inicializa el módulo ``fitz``
except ImportError:  # pragma: no cover - la app sigue funcionando sin PyMuPDF
    fitz = None  # type: ignore[assignment]

try:
    import pytesseract  # type: ignore
except ImportError:  # pragma: no cover - cubierto mediante dependencias opcionales
    pytesseract = None  # type: ignore[assignment]

try:
    from pdf2image import convert_from_path  # type: ignore
except ImportError:  # pragma: no cover - cubierto mediante dependencias opcionales
    convert_from_path = None  # type: ignore[assignment]

try:
    from PIL import Image as PIL_Image
except ImportError:  # pragma: no cover - cubierto mediante dependencias opcionales
    PIL_Image = None  # type: ignore[assignment]


# Uso de _MEIPASS cuando PyInstaller está en ejecución
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
RES_DIR = BASE_DIR / "resources"
OUT_DIR = BASE_DIR / "output"
OUT_DIR.mkdir(exist_ok=True)


SUPPORTED_IMAGE_EXTENSIONS: Sequence[str] = (".jpg", ".jpeg", ".png", ".bmp", ".tiff")
SUPPORTED_DOC_EXTENSIONS: Sequence[str] = (
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".odt",
    ".ods",
    ".odp",
)


@dataclass
class ExternalTools:
    """Contenedor de rutas a herramientas externas empaquetadas en ``resources``."""

    poppler_bin: Optional[Path]
    tesseract_exe: Optional[Path]
    ghostscript_exe: Optional[Path]
    libreoffice_exe: Optional[Path]

    @classmethod
    def discover(cls) -> "ExternalTools":
        """Busca de forma recursiva binarios portables dentro de ``resources``."""

        def find_tool(name: str, filename: str) -> Optional[Path]:
            tool_root = RES_DIR / name
            if not tool_root.exists():
                return None
            for root, _dirs, files in os.walk(tool_root):
                if filename in files:
                    return Path(root) / filename
            return None

        libreoffice = None
        libreoffice_root = RES_DIR / "libreoffice"
        if libreoffice_root.exists():
            for root, _dirs, files in os.walk(libreoffice_root):
                if "soffice.exe" in files:
                    libreoffice = Path(root) / "soffice.exe"
                    break

        tools = cls(
            poppler_bin=find_tool("poppler", "pdftoppm.exe"),
            tesseract_exe=find_tool("tesseract", "tesseract.exe"),
            ghostscript_exe=find_tool("ghostscript", "gswin64c.exe"),
            libreoffice_exe=libreoffice,
        )

        if tools.tesseract_exe and pytesseract:
            pytesseract.pytesseract.tesseract_cmd = str(tools.tesseract_exe)

        return tools


TOOLS = ExternalTools.discover()


def _require_tool(tool_path: Optional[Path], tool_name: str) -> Path:
    """Valida que ``tool_path`` apunte a un ejecutable existente."""

    if not tool_path or not tool_path.exists():
        raise FileNotFoundError(
            f"No se encontró el ejecutable de {tool_name}."
        )
    return tool_path


def convert_to_pdf(input_path: Path, output_path: Path) -> bool:
    """Convierte un archivo soportado a PDF.

    Devuelve ``True`` si la conversión fue exitosa. Para entradas PDF se realiza
    simplemente una copia, mientras que imágenes y documentos ofimáticos se
    convierten mediante Pillow y LibreOffice respectivamente.
    """

    extension = input_path.suffix.lower()
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if extension == ".pdf":
            shutil.copy2(input_path, output_path)
            return True

        if extension in SUPPORTED_IMAGE_EXTENSIONS:
            image_lib = require_dependency(PIL_Image, "Pillow")
            with image_lib.open(input_path) as img:  # type: ignore[attr-defined]
                rgb_image = img.convert("RGB")
                rgb_image.save(output_path)
            return True

        if extension in SUPPORTED_DOC_EXTENSIONS:
            libreoffice_path = _require_tool(TOOLS.libreoffice_exe, "LibreOffice")
            libreoffice_root = libreoffice_path.parent
            if (libreoffice_root / "program").exists():
                libreoffice_root = libreoffice_root / "program"

            env = os.environ.copy()
            env["PATH"] = str(libreoffice_root) + os.pathsep + env.get("PATH", "")
            env["URE_BOOTSTRAP"] = f"vnd.sun.star.pathname:{libreoffice_root / 'fundamental.ini'}"
            env["UNO_PATH"] = str(libreoffice_root)
            env["URE_INTERNAL_LIB_DIR"] = str(libreoffice_root)
            env["USERINSTALLMODE"] = "1"

            cmd = [
                str(libreoffice_path),
                "--headless",
                "--nologo",
                "--norestore",
                "--nolockcheck",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_path.parent),
                str(input_path),
            ]
            subprocess.run(cmd, check=True, env=env)

            expected_pdf = output_path.parent / f"{input_path.stem}.pdf"
            if expected_pdf.exists() and expected_pdf != output_path:
                if output_path.exists():
                    output_path.unlink()
                expected_pdf.rename(output_path)
            return output_path.exists()

        show_error("Formato no soportado", f"No se reconoce la extensión de {input_path.name}")
        return False
    except subprocess.CalledProcessError as exc:
        show_error(
            "Error LibreOffice",
            f"Falló la conversión ({exc.returncode}).\n\nComando: {' '.join(exc.cmd)}",
        )
        return False
    except DependencyMissingError as exc:
        show_error("Dependencia faltante", str(exc))
        return False
    except Exception as exc:  # noqa: BLE001
        show_error("Error de conversión", str(exc))
        return False


def merge_pdfs(files: Iterable[Path], output: Path) -> None:
    """Une múltiples PDFs en uno solo usando ``pikepdf``."""

    pdf_lib = require_dependency(pikepdf, "pikepdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    with pdf_lib.Pdf.new() as result:
        for pdf in files:
            with pdf_lib.open(pdf) as src:
                result.pages.extend(src.pages)
        result.save(output)


def compress_pdf(input_pdf: Path, output_pdf: Path) -> None:
    """Optimiza un PDF existente eliminando recursos huérfanos."""

    pdf_lib = require_dependency(pikepdf, "pikepdf")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with pdf_lib.open(input_pdf) as pdf:
        pdf.remove_unreferenced_resources()
        pdf.save(output_pdf, optimize_streams=True)


def process_all(files: Iterable[Path], final_output: Path, update_progress: Callable[[int], None]) -> None:
    """Pipeline que convierte, une y comprime múltiples archivos en un único PDF."""

    temp_dir = Path(tempfile.mkdtemp(prefix="pdfpraa_"))
    temp_files: List[Path] = []
    try:
        files = list(files)
        total = len(files)
        if total == 0:
            raise RuntimeError("No se seleccionaron archivos.")
        for idx, file in enumerate(files, start=1):
            tmp_output = temp_dir / f"{file.stem}_{idx}.pdf"
            if convert_to_pdf(file, tmp_output):
                temp_files.append(tmp_output)
            update_progress(int(idx / total * 50))

        if not temp_files:
            raise RuntimeError("No se pudieron convertir archivos a PDF.")

        merged_pdf = temp_dir / "merged.pdf"
        merge_pdfs(temp_files, merged_pdf)
        update_progress(75)

        compress_pdf(merged_pdf, final_output)
        update_progress(100)
    except Exception as exc:  # noqa: BLE001
        show_error("Proceso TODO", str(exc))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _images_from_input(input_path: Path) -> List["PIL_Image.Image"]:  # type: ignore[name-defined]
    """Convierte cualquier entrada soportada en una lista de imágenes Pillow."""

    extension = input_path.suffix.lower()
    if extension in SUPPORTED_IMAGE_EXTENSIONS:
        image_lib = require_dependency(PIL_Image, "Pillow")
        with image_lib.open(input_path) as image:
            return [image.copy()]

    converter = require_dependency(convert_from_path, "pdf2image")
    poppler = _require_tool(TOOLS.poppler_bin, "Poppler")
    return converter(str(input_path), poppler_path=str(poppler.parent))


def ocr_pdf(input_path: Path, output_path: Path, update_progress: Callable[[int], None]) -> None:
    """Realiza OCR sobre un PDF o imagen y genera un PDF con texto incrustado."""

    try:
        pdf_lib = require_dependency(pikepdf, "pikepdf")
        pytess = require_dependency(pytesseract, "pytesseract")
        images = _images_from_input(input_path)
        total = len(images)
        if total == 0:
            raise RuntimeError("No se pudieron generar imágenes para OCR.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_writer = pdf_lib.Pdf.new()

        for idx, image in enumerate(images, start=1):
            text_bytes = pytess.image_to_pdf_or_hocr(image, extension="pdf")
            with pdf_lib.open(io.BytesIO(text_bytes)) as tmp_pdf:
                pdf_writer.pages.extend(tmp_pdf.pages)
            update_progress(int(idx / total * 100))

        pdf_writer.save(output_path)
    except DependencyMissingError as exc:
        show_error("OCR", str(exc))
        raise
    except Exception as exc:  # noqa: BLE001
        show_error("OCR", str(exc))


class SplashScreen(tk.Toplevel):
    """Pequeña pantalla de carga para evitar bloqueos durante la inicialización."""

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title("Iniciando PDF PRAA Portable")
        self.geometry("500x220")
        self.resizable(False, False)
        self.config(bg="#202020")
        self.progress = tk.DoubleVar(value=0)
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        tk.Label(
            self,
            text="Cargando recursos...",
            bg="#202020",
            fg="#00ffaa",
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=30)
        self.pb = ttk.Progressbar(self, variable=self.progress, maximum=100, length=420)
        self.pb.pack(pady=15)
        self.lbl = tk.Label(self, text="Preparando entorno...", bg="#202020", fg="#ccc")
        self.lbl.pack()
        self.update()
        self.after(30000, self.force_close)

    def set_progress(self, val: float, text: str = "") -> None:
        self.progress.set(val)
        if text:
            self.lbl.config(text=text)
        self.update_idletasks()

    def force_close(self) -> None:
        try:
            self.destroy()
        except Exception:  # noqa: BLE001
            pass


class PDFApp(tk.Tk):
    """Interfaz gráfica principal."""

    def __init__(self):
        super().__init__()
        self.title("PDF PRAA PORTABLE")
        self.geometry("650x500")
        self.config(bg="#1e1e1e")
        style = ttk.Style(self)
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=5)

        tk.Label(
            self,
            text="PDF PRAA PORTABLE",
            bg="#1e1e1e",
            fg="#00ffaa",
            font=("Segoe UI", 16, "bold"),
        ).pack(pady=10)

        actions = [
            ("Transformar a PDF", self.do_transform),
            ("Unir PDFs", self.do_merge),
            ("Comprimir PDFs", self.do_compress),
            ("TODO (Convertir + Unir + Comprimir)", self.do_all),
            ("OCR PDF / Imagen", self.do_ocr),
            ("Salir", self.destroy),
        ]
        for title, callback in actions:
            ttk.Button(self, text=title, command=callback).pack(pady=6, ipadx=6)

        self.status = tk.Label(self, text="Listo.", bg="#1e1e1e", fg="#bbb")
        self.status.pack(side="bottom", fill="x", pady=4)
        self.progressbar = ttk.Progressbar(self, maximum=100, length=600)
        self.progressbar.pack(pady=8)

    def _set_status(self, msg: str) -> None:
        self.status.config(text=msg)
        self.update_idletasks()

    def _choose(self, types: Sequence[tuple[str, str]]) -> List[Path]:
        files = filedialog.askopenfilenames(filetypes=types)
        return [Path(f) for f in files]

    def _saveas(self, title: str) -> Optional[Path]:
        filename = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        return Path(filename) if filename else None

    def _update_progress(self, value: int) -> None:
        self.progressbar["value"] = value
        self.update_idletasks()

    def do_transform(self) -> None:
        files = self._choose([("Docs e Imágenes", "*.pdf *.doc *.docx *.jpg *.jpeg *.png *.bmp *.tiff")])
        if not files:
            return
        out_dir = filedialog.askdirectory(title="Carpeta destino")
        if not out_dir:
            return
        for file in files:
            self._set_status(f"Transformando {file.name}...")
            convert_to_pdf(file, Path(out_dir) / f"{file.stem}.pdf")
        messagebox.showinfo("Hecho", "Transformación completada.")

    def do_merge(self) -> None:
        files = self._choose([("PDF", "*.pdf")])
        if not files:
            return
        output = self._saveas("Guardar PDF unido como")
        if output:
            self._set_status("Uniendo PDFs...")
            merge_pdfs(files, output)
            messagebox.showinfo("Hecho", f"PDF unido guardado:\n{output}")

    def do_compress(self) -> None:
        files = self._choose([("PDF", "*.pdf")])
        if not files:
            return
        for file in files:
            self._set_status(f"Comprimiendo {file.name}...")
            compress_pdf(file, file.with_name(f"{file.stem}_compressed.pdf"))
        messagebox.showinfo("Hecho", "Compresión completada.")

    def do_all(self) -> None:
        files = self._choose([("Todos", "*.pdf *.jpg *.jpeg *.png *.bmp *.tiff *.doc *.docx *.xls *.xlsx *.ppt *.pptx")])
        if not files:
            return
        output = self._saveas("Guardar resultado final como")
        if not output:
            return
        self._set_status("Procesando TODO...")

        def run_all() -> None:
            process_all(files, output, self._update_progress)
            messagebox.showinfo("Hecho", "Proceso completado.")

        threading.Thread(target=run_all, daemon=True).start()

    def do_ocr(self) -> None:
        files = self._choose([("PDF o Imagen", "*.pdf *.jpg *.jpeg *.png *.bmp *.tiff")])
        if not files:
            return
        out_dir = filedialog.askdirectory(title="Destino OCR")
        if not out_dir:
            return

        def run_ocr() -> None:
            for file in files:
                self._set_status(f"OCR {file.name}...")
                target_name = Path(out_dir) / f"{file.stem}_OCR.pdf"
                ocr_pdf(file, target_name, self._update_progress)
            messagebox.showinfo("Hecho", "OCR completado.")

        threading.Thread(target=run_ocr, daemon=True).start()


def check_libreoffice() -> None:
    try:
        _require_tool(TOOLS.libreoffice_exe, "LibreOffice")
    except FileNotFoundError as exc:
        show_error("Error LibreOffice", str(exc))
        sys.exit(1)


def main() -> None:
    root = PDFApp()
    splash = SplashScreen(root)

    def close_splash() -> None:
        splash.force_close()

    root.after(1500, close_splash)
    threading.Thread(target=check_libreoffice, daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
