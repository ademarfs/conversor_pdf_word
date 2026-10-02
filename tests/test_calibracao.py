import pytest

from conversor.calibracao import Ajustes, Desvio, chave_trecho, recalibrar
from conversor.modelo import Trecho


def _trecho(texto="abc def", id_=1):
    return Trecho(id_, texto, "Arial", "Helvetica", 12, False, False, "000000", 10, 60, 100)


def _desvio(trecho, indice, dx, dy=0.0, dx_fim=None):
    """Palavra de uma letra só (sem correção de largura), salvo se `dx_fim` for dado."""
    return Desvio(trecho=trecho, indice=indice, indice_fim=None, dx_inicio=dx,
                  dx_fim=dx if dx_fim is None else dx_fim, dy=dy, primeira_do_trecho=indice == 0)


def test_desvio_sistematico_da_fonte_e_compensado():
    t = _trecho()
    desvios = [_desvio(t, 0, 0.3, dy=-0.5)]
    novo = recalibrar(Ajustes(), desvios, set())
    assert novo.por_fonte[chave_trecho(t)] == (-0.3, 0.5)


def test_desvio_atipico_nao_contamina_a_fonte():
    t = _trecho()
    novo = recalibrar(Ajustes(), [_desvio(t, 0, 9.0)], set())
    assert chave_trecho(t) not in novo.por_fonte


def test_espaco_antes_da_palavra_compensa_texto_justificado():
    t = _trecho()
    desvios = [_desvio(t, 0, 0.0), _desvio(t, 4, -2.0)]
    novo = recalibrar(Ajustes(), desvios, set())
    assert novo.espacos[(t.id, 4)] == pytest.approx(2.0)
    # o espaço extra vai para o caractere anterior à palavra (o espaço, índice 3)
    assert novo.espacamento_por_caractere(t)[3] == pytest.approx(2.0)


def test_espacamento_e_arredondado_para_a_resolucao_do_word():
    t = _trecho()
    desvios = [_desvio(t, 0, 0.0), _desvio(t, 4, -0.12)]
    novo = recalibrar(Ajustes(), desvios, set())
    assert novo.espacos[(t.id, 4)] == pytest.approx(0.1)


def test_ajustes_sobrevivem_a_ida_e_volta_em_json():
    original = Ajustes(espacos={(1, 4): 0.5}, larguras={(1, 0): (2, -0.05)})
    copia = Ajustes()
    copia.carregar_json(original.para_json())
    assert copia.espacos == original.espacos and copia.larguras == original.larguras


def test_largura_da_palavra_e_distribuida_entre_as_letras():
    t = _trecho()
    desvio = Desvio(trecho=t, indice=0, indice_fim=2, dx_inicio=0.0, dx_fim=-0.4, dy=0.0,
                    primeira_do_trecho=True)
    novo = recalibrar(Ajustes(), [desvio], set())
    assert novo.larguras[(t.id, 0)] == (2, pytest.approx(0.2))
