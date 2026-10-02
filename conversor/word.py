"""Renderização do .docx pelo próprio Microsoft Word (automação COM).

É o Word instalado na máquina que desenha o documento; por isso a verificação
compara exatamente o que o usuário verá ao abrir o arquivo.
"""
from __future__ import annotations

import importlib.util
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

FORMATO_PDF = 17          # wdExportFormatPDF
NAO_SALVAR = 0            # wdDoNotSaveChanges

_trava_word = threading.Lock()


class WordIndisponivel(RuntimeError):
    pass


def word_disponivel() -> bool:
    """Verifica se o Word pode ser automatizado nesta máquina."""
    if importlib.util.find_spec("win32com") is None:
        return False
    try:
        import winreg
        winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Word.Application").Close()
        return True
    except (ImportError, OSError):
        return False


def docx_para_pdf(docx: Path, pdf: Path) -> None:
    """Abre o .docx numa instância invisível e exclusiva do Word e exporta em PDF."""
    if not word_disponivel():
        raise WordIndisponivel("Microsoft Word não encontrado nesta máquina.")
    import pythoncom
    import win32com.client

    with _trava_word:  # o Word não lida bem com automações simultâneas
        pythoncom.CoInitialize()
        word = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            documento = word.Documents.Open(
                str(docx.resolve()), ReadOnly=True, AddToRecentFiles=False, Visible=False
            )
            try:
                documento.ExportAsFixedFormat(OutputFileName=str(pdf.resolve()), ExportFormat=FORMATO_PDF)
            finally:
                documento.Close(SaveChanges=NAO_SALVAR)
        finally:
            if word is not None:
                try:
                    word.Quit()
                except Exception:  # Word já encerrado
                    log.debug("Word já havia sido encerrado")
            pythoncom.CoUninitialize()
