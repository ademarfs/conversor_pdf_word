"""Montagem de parágrafos a partir de trechos (comum aos dois motores)."""
from __future__ import annotations

from ..calibracao import Ajustes
from ..config import FATOR_BASE_WORD, Config
from ..modelo import Trecho
from .plano import ParagrafoPlano, RunPlano

# Caracteres que descem abaixo da linha de base e seriam cortados por uma borda.
DESCENDENTES = set("gjpqyQçÇµ,;()[]{}|/\\_@$§")
DESCIDA_DESCENDENTE = 0.22   # fração do tamanho da fonte
DESCIDA_SEM_DESCENDENTE = 0.03
ELEVACAO_MINIMA_PT = 0.25


def descida(trecho: Trecho) -> float:
    """Quanto a tinta do trecho desce abaixo da linha de base."""
    fator = DESCIDA_DESCENDENTE if DESCENDENTES & set(trecho.texto) else DESCIDA_SEM_DESCENDENTE
    return fator * trecho.tamanho


def agrupar_linhas(trechos: list[Trecho], tolerancia_base: float | None = None) -> list[list[Trecho]]:
    """Agrupa trechos que formam uma mesma linha visual, ordenados por x.

    Sem `tolerancia_base`, junta trechos cujas caixas se sobrepõem verticalmente
    (permite sobrescritos). Com ela, exige linhas de base praticamente iguais.
    """
    linhas: list[list[Trecho]] = []
    for trecho in sorted(trechos, key=lambda t: (t.base, t.x0)):
        destino = next((linha for linha in linhas if _cabe_na_linha(linha, trecho, tolerancia_base)), None)
        if destino is None:
            linhas.append([trecho])
        else:
            destino.append(trecho)
    for linha in linhas:
        linha.sort(key=lambda t: t.x0)
    return sorted(linhas, key=lambda linha: _principal(linha).base)


def _cabe_na_linha(linha: list[Trecho], trecho: Trecho, tolerancia_base: float | None) -> bool:
    if any(t.x0 < trecho.x1 and trecho.x0 < t.x1 for t in linha):
        return False  # sobreposição horizontal: são linhas diferentes
    principal = _principal(linha)
    if tolerancia_base is not None:
        return abs(principal.base - trecho.base) <= tolerancia_base
    sobreposicao = min(principal.fundo, trecho.fundo) - max(principal.topo, trecho.topo)
    menor_altura = min(principal.tamanho, trecho.tamanho)
    return sobreposicao >= 0.6 * menor_altura


def _principal(linha: list[Trecho]) -> Trecho:
    return max(linha, key=lambda t: t.tamanho)


def montar_paragrafo(linha: list[Trecho], x_referencia: float, ajustes: Ajustes,
                     config: Config) -> ParagrafoPlano:
    """Um parágrafo de uma linha: recuo até o 1º trecho e tabulações para os demais."""
    principal = _principal(linha)
    base_principal = principal.base + ajustes.deslocamento(principal)[1]
    runs: list[RunPlano] = []
    tabulacoes: list[float] = []
    recuo = 0.0
    anterior: Trecho | None = None
    for trecho in linha:
        dx, dy = ajustes.deslocamento(trecho)
        x = trecho.x0 + dx - x_referencia
        usa_tab = anterior is not None and trecho.x0 - anterior.x1 >= config.lacuna_tabulacao_pt
        if anterior is None:
            recuo = x
        elif usa_tab:
            tabulacoes.append(x)
        elevacao = base_principal - (trecho.base + dy)
        if abs(elevacao) < ELEVACAO_MINIMA_PT:
            elevacao = 0.0
        runs += _runs_do_trecho(trecho, ajustes.espacamento_por_caractere(trecho), usa_tab, elevacao)
        anterior = trecho
    return ParagrafoPlano(runs, recuo, tabulacoes, principal.tamanho, base_principal)


def _runs_do_trecho(trecho: Trecho, espacamento: list[float], tab_antes: bool,
                    elevacao: float) -> list[RunPlano]:
    """Divide o trecho em runs com o mesmo espaçamento entre caracteres."""
    runs: list[RunPlano] = []
    inicio = 0
    for i in range(1, len(trecho.texto) + 1):
        if i == len(trecho.texto) or espacamento[i] != espacamento[inicio]:
            runs.append(RunPlano(
                texto=trecho.texto[inicio:i], fonte=trecho.fonte, tamanho=trecho.tamanho,
                negrito=trecho.negrito, italico=trecho.italico, cor=trecho.cor,
                trecho_id=trecho.id, elevacao=elevacao, espacamento=espacamento[inicio]))
            inicio = i
    runs[0].tab_antes = tab_antes
    return runs


def empilhar(paragrafos: list[ParagrafoPlano], descidas: list[float], y_topo: float,
             y_fundo: float) -> None:
    """Calcula o espaço antes de cada parágrafo para que a linha de base caia no lugar.

    Restrições: nenhum parágrafo começa acima da célula nem invade o anterior, e a
    tinta do último (inclusive descendentes) não passa de `y_fundo`, onde o Word
    cortaria. Quando é preciso mover um parágrafo, o deslocamento fica registrado.
    """
    alturas = [p.altura_linha for p in paragrafos]
    desejados = [p.base - FATOR_BASE_WORD * a for p, a in zip(paragrafos, alturas)]
    topos = list(desejados)

    # De baixo para cima: o último cabe na célula; cada um termina antes do seguinte.
    for i in reversed(range(len(topos))):
        if i == len(topos) - 1:
            maximo = y_fundo - FATOR_BASE_WORD * alturas[i] - descidas[i]
        else:
            maximo = topos[i + 1] - alturas[i]
        topos[i] = min(topos[i], maximo)

    # De cima para baixo: prevalece não sair da célula nem sobrepor o anterior.
    cursor = y_topo
    for i, paragrafo in enumerate(paragrafos):
        topos[i] = max(topos[i], cursor)
        paragrafo.espaco_antes = topos[i] - cursor
        paragrafo.deslocamento = topos[i] - desejados[i]
        cursor = topos[i] + alturas[i]
