import pytest

from conversor.calibracao import Ajustes
from conversor.config import FATOR_BASE_WORD
from conversor.extracao import extrair
from conversor.layout.absoluto import MotorAbsoluto
from conversor.layout.grade import MotorTabela
from conversor.layout.paragrafos import empilhar
from conversor.layout.plano import ParagrafoPlano


def _textos_no_plano(pagina):
    paragrafos = [p for linha in pagina.linhas for c in linha.celulas for p in c.paragrafos]
    paragrafos += [q.paragrafo for q in pagina.quadros]
    return sorted("".join(r.texto for r in p.runs if r.trecho_id == t)
                  for p in paragrafos for t in {r.trecho_id for r in p.runs})


@pytest.mark.parametrize("motor", [MotorTabela, MotorAbsoluto])
def test_nenhum_texto_se_perde_nem_se_duplica(pdf_formulario, config, motor):
    documento = extrair(pdf_formulario)
    plano = motor(config).planejar(documento, Ajustes())
    esperado = sorted(t.texto for t in documento.paginas[0].trechos)
    assert _textos_no_plano(plano.paginas[0]) == esperado


def test_tabela_usa_sublinhados_como_bordas_de_celula(pdf_formulario, config):
    plano = MotorTabela(config).planejar(extrair(pdf_formulario), Ajustes()).paginas[0]
    celula_cliente = next(c for linha in plano.linhas for c in linha.celulas
                          if any(r.texto == "EMPRESA EXEMPLO LTDA" for p in c.paragrafos for r in p.runs))
    assert celula_cliente.borda_inferior is not None
    assert len(plano.colunas) - 1 <= config.max_colunas_tabela


def test_grade_da_tabela_vira_bordas_e_nao_formas_soltas(pdf_formulario, config):
    plano = MotorTabela(config).planejar(extrair(pdf_formulario), Ajustes()).paginas[0]
    bordas_verticais = sum(1 for linha in plano.linhas for c in linha.celulas if c.borda_esquerda)
    assert bordas_verticais >= 9
    assert not [s for s in plano.segmentos if s.vertical]


def test_motor_absoluto_cria_um_quadro_por_linha_de_texto(pdf_formulario, config):
    plano = MotorAbsoluto(config).planejar(extrair(pdf_formulario), Ajustes()).paginas[0]
    bases = {round(q.paragrafo.base, 1) for q in plano.quadros}
    assert len(plano.quadros) == len(bases)


def test_empilhar_respeita_a_linha_de_base_desejada():
    paragrafo = ParagrafoPlano([], 0, [], altura_linha=12, base=50)
    empilhar([paragrafo], [0.4], y_topo=30, y_fundo=60)
    topo = 30 + paragrafo.espaco_antes
    assert topo + FATOR_BASE_WORD * 12 == pytest.approx(50)
    assert paragrafo.deslocamento == 0


def test_empilhar_sobe_o_texto_que_seria_cortado_pela_borda():
    paragrafo = ParagrafoPlano([], 0, [], altura_linha=12, base=58)
    empilhar([paragrafo], [2.6], y_topo=30, y_fundo=60)
    assert paragrafo.deslocamento == pytest.approx(-0.6)
