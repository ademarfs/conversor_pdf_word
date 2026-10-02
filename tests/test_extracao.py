import pymupdf
import pytest

from conversor.erros import ErroConversao
from conversor.extracao import extrair


def test_extrai_textos_com_fonte_e_posicao(pdf_formulario):
    documento = extrair(pdf_formulario)
    trechos = {t.texto: t for t in documento.paginas[0].trechos}
    cliente = trechos["EMPRESA EXEMPLO LTDA"]
    assert cliente.fonte == "Times New Roman" and cliente.italico
    assert cliente.x0 == pytest.approx(140, abs=0.1)
    assert cliente.base == pytest.approx(120, abs=0.1)
    assert trechos["Certificado de Teste"].tamanho == 20


def test_extrai_linhas_imagem_e_ignora_elementos_invisiveis(pdf_formulario):
    pagina = extrair(pdf_formulario).paginas[0]
    horizontais = [s for s in pagina.segmentos if s.horizontal]
    verticais = [s for s in pagina.segmentos if s.vertical]
    assert len(horizontais) == 3 + 4 and len(verticais) == 4
    assert len(pagina.imagens) == 1
    assert pagina.imagens[0].png.startswith(b"\x89PNG")
    assert not pagina.formas  # o retângulo com opacidade 0 não entra


def test_ordem_de_pintura_e_preservada(pdf_formulario):
    pagina = extrair(pdf_formulario).paginas[0]
    ordens = [s.ordem for s in pagina.segmentos]
    assert ordens == sorted(ordens) and len(set(ordens)) > 1


def test_pdf_protegido_por_senha_e_recusado(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "segredo")
    caminho = tmp_path / "protegido.pdf"
    doc.save(caminho, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="123", owner_pw="456")
    with pytest.raises(ErroConversao, match="senha"):
        extrair(caminho)


def test_arquivo_que_nao_e_pdf_e_recusado(tmp_path):
    caminho = tmp_path / "falso.pdf"
    caminho.write_text("isto não é um PDF")
    with pytest.raises(ErroConversao):
        extrair(caminho)
