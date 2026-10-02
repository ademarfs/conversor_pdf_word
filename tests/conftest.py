"""PDFs sintéticos para os testes (gerados com PyMuPDF; nenhum arquivo real é usado)."""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from conversor.config import Config
from conversor.word import word_disponivel

A4 = (595, 842)


def _logo_png() -> bytes:
    """Imagem 40x20 com transparência (canal alfa)."""
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 20), True)
    pix.clear_with(0)
    for x in range(40):
        for y in range(20):
            if (x - 20) ** 2 + (y - 10) ** 2 < 80:
                pix.set_pixel(x, y, (200, 30, 30, 255))
    return pix.tobytes("png")


@pytest.fixture
def pdf_formulario(tmp_path: Path) -> Path:
    """Formulário típico: título, campos sublinhados, tabela, imagem e um retângulo invisível."""
    doc = pymupdf.open()
    pagina = doc.new_page(width=A4[0], height=A4[1])
    pagina.insert_text((180, 60), "Certificado de Teste", fontname="helv", fontsize=20)
    campos = [("Cliente", "EMPRESA EXEMPLO LTDA", 120), ("Pedido", "PQ-0042 grupo", 140),
              ("Data", "2026-10-02", 160)]
    for rotulo, valor, base in campos:
        pagina.insert_text((40, base), rotulo, fontname="helv", fontsize=12)
        pagina.insert_text((140, base), valor, fontname="tiit", fontsize=12)
        pagina.draw_line((140, base + 1.5), (540, base + 1.5), width=0.75)
    # Tabela 3x3 com grade completa
    xs, ys = [40, 200, 360, 520], [200, 224, 248, 272]
    for x in xs:
        pagina.draw_line((x, ys[0]), (x, ys[-1]), width=0.75)
    for y in ys:
        pagina.draw_line((xs[0], y), (xs[-1], y), width=0.75)
    for i, linha in enumerate([("Medida", "1", "2"), ("19,993", "19,988", "19,987"), ("0,5", "0,53", "0,43")]):
        for j, texto in enumerate(linha):
            pagina.insert_text((xs[j] + 8, ys[i] + 16), texto, fontname="tiro", fontsize=10)
    pagina.insert_image(pymupdf.Rect(460, 30, 540, 70), stream=_logo_png())
    # Retângulo totalmente transparente: existe no PDF, mas não aparece
    forma = pagina.new_shape()
    forma.draw_rect(pymupdf.Rect(40, 700, 540, 720))
    forma.finish(fill=(0, 0, 0), color=None, fill_opacity=0)
    forma.commit()
    pagina.insert_text((40, 800), "BR.2026.10.0001-00-1/1", fontname="tiit", fontsize=8)
    caminho = tmp_path / "formulario.pdf"
    doc.save(caminho)
    return caminho


@pytest.fixture
def pdf_justificado(tmp_path: Path) -> Path:
    """Um único trecho com os espaços esticados (operador Tw), como em texto justificado."""
    doc = pymupdf.open()
    pagina = doc.new_page(width=A4[0], height=A4[1])
    pagina.insert_text((40, 100), "Planejamento e coordenacao das areas de tesouraria e controladoria",
                       fontname="helv", fontsize=11)
    xref = pagina.get_contents()[0]
    doc.update_stream(xref, doc.xref_stream(xref).replace(b"BT", b"BT 4 Tw", 1))
    caminho = tmp_path / "justificado.pdf"
    doc.save(caminho)
    return caminho


@pytest.fixture
def config(tmp_path: Path) -> Config:
    configuracao = Config(pasta_dados=tmp_path / "dados")
    configuracao.criar_pastas()
    return configuracao


precisa_word = pytest.mark.skipif(not word_disponivel(), reason="Microsoft Word não instalado")
