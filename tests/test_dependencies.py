import tempfile
import unittest
from pathlib import Path

import pdf_praa_portable as app


class DependencyTests(unittest.TestCase):
    def test_merge_requires_pikepdf(self):
        self.assertIsNone(app.pikepdf, "El entorno de pruebas no debe tener pikepdf instalado")
        with self.assertRaises(app.DependencyMissingError):
            app.merge_pdfs([Path("a.pdf")], Path("out.pdf"))

    def test_ocr_requires_pytesseract(self):
        self.assertIsNone(app.pytesseract, "El entorno de pruebas no debe tener pytesseract instalado")
        original_poppler = app.TOOLS.poppler_bin
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_poppler = Path(tmp_dir) / "pdftoppm.exe"
            fake_poppler.write_text("")
            app.TOOLS.poppler_bin = fake_poppler
            try:
                with self.assertRaises(app.DependencyMissingError):
                    app.ocr_pdf(Path("input.pdf"), Path("out.pdf"), lambda _value: None)
            finally:
                app.TOOLS.poppler_bin = original_poppler


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
