import pymupdf

from conversor.extracao import extrair
from conversor.verificacao import verificar


def test_o_proprio_original_e_identico_a_si_mesmo(pdf_formulario, config):
    relatorio = verificar(extrair(pdf_formulario), pdf_formulario)
    assert relatorio.texto_identico
    assert relatorio.desvio_maximo == 0
    assert relatorio.pixels_maximo == 0
    assert relatorio.aprovado(config)


def test_detecta_palavra_faltando_e_sobrando(pdf_formulario, tmp_path):
    alterado = pymupdf.open(pdf_formulario)
    pagina = alterado[0]
    pagina.add_redact_annot(pagina.search_for("PQ-0042")[0])
    pagina.apply_redactions()
    pagina.insert_text((300, 500), "intrusa", fontname="helv", fontsize=12)
    caminho = tmp_path / "alterado.pdf"
    alterado.save(caminho)

    relatorio = verificar(extrair(pdf_formulario), caminho)
    assert "PQ-0042" in relatorio.faltando
    assert "intrusa" in relatorio.sobrando
    assert not relatorio.texto_identico


def test_detecta_texto_deslocado(pdf_formulario, tmp_path, config):
    deslocado = pymupdf.open()
    pagina = deslocado.new_page(width=595, height=842)
    pagina.show_pdf_page(pagina.rect + (3, 0, 3, 0), pymupdf.open(pdf_formulario), 0)
    caminho = tmp_path / "deslocado.pdf"
    deslocado.save(caminho)

    relatorio = verificar(extrair(pdf_formulario), caminho)
    assert relatorio.texto_identico
    assert relatorio.desvio_maximo > 2.5
    assert not relatorio.aprovado(config)
