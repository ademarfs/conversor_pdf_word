"""Divisão em palavras — a mesma regra para o original e para o resultado do Word.

Usar exatamente a mesma regra dos dois lados é o que permite parear as palavras
e medir o desvio de cada uma.
"""
from __future__ import annotations

from dataclasses import dataclass

from .modelo import Pagina, Trecho

SEPARACAO_PALAVRAS = 0.25    # vão (fração do tamanho da fonte) que separa palavras sem espaço
MESMA_LINHA = 0.5            # diferença de base (fração do tamanho) ainda na mesma linha


@dataclass(frozen=True)
class Letra:
    texto: str
    x0: float
    x1: float
    base: float
    tamanho: float
    trecho: Trecho | None = None
    indice: int = 0          # posição do caractere dentro do trecho


def letras_da_pagina(pagina: Pagina) -> list[Letra]:
    return [Letra(c.texto, c.x0, c.x1, t.base, t.tamanho, t, i)
            for t in pagina.trechos for i, c in enumerate(t.caracteres)]


def dividir(letras: list[Letra]) -> list[list[Letra]]:
    """Separa por espaço, mudança de linha, vão horizontal ou retorno no eixo x."""
    palavras: list[list[Letra]] = []
    for linha in _linhas(letras):
        atual: list[Letra] = []
        for letra in linha:
            if letra.texto.isspace():
                _fechar(atual, palavras)
                continue
            if atual and _quebra(atual[-1], letra):
                _fechar(atual, palavras)
            atual.append(letra)
        _fechar(atual, palavras)
    return palavras


def inicios_de_palavra(pagina: Pagina) -> dict[int, list[int]]:
    """Para cada trecho, os índices de caractere onde começa uma palavra."""
    inicios: dict[int, list[int]] = {}
    for palavra in dividir(letras_da_pagina(pagina)):
        primeira = palavra[0]
        inicios.setdefault(primeira.trecho.id, []).append(primeira.indice)
    return {k: sorted(v) for k, v in inicios.items()}


def _linhas(letras: list[Letra]) -> list[list[Letra]]:
    linhas: list[list[Letra]] = []
    for letra in sorted(letras, key=lambda letra: letra.base):
        if linhas and letra.base - linhas[-1][0].base <= MESMA_LINHA * letra.tamanho:
            linhas[-1].append(letra)
        else:
            linhas.append([letra])
    # Ordena pelo centro: o Word exporta cada tabulação como um "espaço" que começa
    # no mesmo x da letra seguinte; pelo centro ele fica antes dela.
    return [sorted(linha, key=lambda letra: (letra.x0 + letra.x1) / 2) for linha in linhas]


def _quebra(anterior: Letra, letra: Letra) -> bool:
    vao = letra.x0 - anterior.x1 > SEPARACAO_PALAVRAS * letra.tamanho
    return vao or letra.x1 < anterior.x1


def _fechar(atual: list[Letra], palavras: list[list[Letra]]) -> None:
    if atual:
        palavras.append(list(atual))
        atual.clear()
