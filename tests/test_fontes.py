import pytest

from conversor.fontes import mapear_fonte


@pytest.mark.parametrize("nome_pdf, flags, familia, negrito, italico", [
    ("Helvetica", 0, "Arial", False, False),
    ("ArialMT", 0, "Arial", False, False),
    ("Arial,Bold", 0, "Arial", True, False),
    ("Times-Italic", 6, "Times New Roman", False, True),
    ("Times-Bold", 20, "Times New Roman", True, False),
    ("TimesNewRomanPS-BoldItalicMT", 0, "Times New Roman", True, True),
    ("ABCDEF+Arial-BoldMT", 0, "Arial", True, False),
    ("Courier", 0, "Courier New", False, False),
])
def test_fontes_padrao_do_pdf_viram_equivalentes_do_windows(nome_pdf, flags, familia, negrito, italico):
    fonte = mapear_fonte(nome_pdf, flags)
    assert (fonte.familia, fonte.negrito, fonte.italico) == (familia, negrito, italico)


def test_familia_que_ja_e_pesada_nao_recebe_negrito_extra():
    fonte = mapear_fonte("Arial-Black", 0)
    if fonte.instalada and fonte.familia == "Arial Black":
        assert not fonte.negrito


def test_fonte_inexistente_e_sinalizada():
    fonte = mapear_fonte("FonteQueNaoExiste-Regular", 0)
    assert fonte.familia == "Fonte Que Nao Existe"
    assert not fonte.instalada
