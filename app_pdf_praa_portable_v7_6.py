"""Entry point wrapper for the PDF PRAA Portable GUI.

This thin shim exists to keep backwards compatibility with build scripts
and packaging workflows that expect the legacy ``app_pdf_praa_portable_v7_6``
module name while delegating the actual implementation to
``pdf_praa_portable``.
"""

from pdf_praa_portable import *  # noqa: F401,F403 - re-export for compatibility
from pdf_praa_portable import main


if __name__ == "__main__":  # pragma: no cover - GUI entry point
    main()
