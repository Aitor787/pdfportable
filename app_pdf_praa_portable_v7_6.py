"""Wrapper de compatibilidad para la versión histórica del módulo."""

from __future__ import annotations

import pdf_praa_portable as _impl

__all__ = list(getattr(_impl, "__all__", []))

globals().update({name: getattr(_impl, name) for name in __all__})

if __name__ == "__main__":  # pragma: no cover - punto de entrada de la GUI
    _impl.main()
