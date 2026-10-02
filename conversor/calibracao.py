"""Ajustes finos aprendidos comparando o original com o que o Word desenhou.

Dois níveis:
- por fonte (família/estilo/tamanho): desvio sistemático do Word nesta máquina;
  é persistido no banco e reaproveitado em todas as conversões seguintes.
- por palavra: espaço extra antes de cada palavra, que compensa texto justificado
  e pequenas diferenças de largura; vale só para o documento atual.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median

from .modelo import Trecho

RESIDUO_MINIMO_PT = 0.05
LIMITE_SISTEMATICO_PT = 2.0   # desvios maiores são do layout, não da fonte
PASSO_ESPACAMENTO_PT = 0.05   # resolução do espaçamento entre caracteres no Word (1 twip)


def chave_fonte(fonte: str, negrito: bool, italico: bool, tamanho: float) -> str:
    return f"{fonte}|{'N' if negrito else '-'}{'I' if italico else '-'}|{round(tamanho * 2) / 2:g}"


def chave_trecho(trecho: Trecho) -> str:
    return chave_fonte(trecho.fonte, trecho.negrito, trecho.italico, trecho.tamanho)


@dataclass
class Ajustes:
    por_fonte: dict[str, tuple[float, float]] = field(default_factory=dict)  # chave -> (dx, dy)
    # (trecho, caractere onde a palavra começa) -> pt extras antes da palavra
    espacos: dict[tuple[int, int], float] = field(default_factory=dict)
    # (trecho, caractere onde a palavra começa) -> (último caractere, pt entre letras)
    larguras: dict[tuple[int, int], tuple[int, float]] = field(default_factory=dict)

    def deslocamento(self, trecho: Trecho) -> tuple[float, float]:
        return self.por_fonte.get(chave_trecho(trecho), (0.0, 0.0))

    def espacamento_por_caractere(self, trecho: Trecho) -> list[float]:
        """Espaço extra (pt) a aplicar depois de cada caractere do trecho."""
        extra = [0.0] * len(trecho.texto)
        for (t, inicio), (fim, valor) in self.larguras.items():
            if t == trecho.id:
                for i in range(inicio, min(fim, len(extra))):
                    extra[i] += valor
        for (t, inicio), valor in self.espacos.items():
            if t == trecho.id and 0 < inicio <= len(extra):
                extra[inicio - 1] += valor
        return [round(v, 2) for v in extra]

    def copia(self) -> Ajustes:
        return Ajustes(dict(self.por_fonte), dict(self.espacos), dict(self.larguras))

    # Serialização (persistência no banco)
    def para_json(self) -> dict:
        return {
            "espacos": {f"{t}:{i}": v for (t, i), v in self.espacos.items()},
            "larguras": {f"{t}:{i}": list(v) for (t, i), v in self.larguras.items()},
        }

    def carregar_json(self, dados: dict) -> None:
        def chave(texto: str) -> tuple[int, int]:
            t, i = texto.split(":")
            return int(t), int(i)
        self.espacos = {chave(k): v for k, v in dados.get("espacos", {}).items()}
        self.larguras = {chave(k): (v[0], v[1]) for k, v in dados.get("larguras", {}).items()}


@dataclass(frozen=True)
class Desvio:
    """Diferença medida para uma palavra: posição no resultado - posição no original."""

    trecho: Trecho
    indice: int
    indice_fim: int | None          # último caractere (None se a palavra cruza trechos)
    dx_inicio: float
    dx_fim: float
    dy: float
    primeira_do_trecho: bool


def recalibrar(ajustes: Ajustes, desvios: list[Desvio], trechos_deslocados: set[int]) -> Ajustes:
    """Novo conjunto de ajustes que anula os desvios medidos."""
    novo = ajustes.copia()
    # Trechos que o layout teve de mover de propósito não medem erro do Word.
    _recalibrar_fontes(novo, [d for d in desvios if d.trecho.id not in trechos_deslocados])
    _recalibrar_espacos(novo, desvios)
    _recalibrar_larguras(novo, desvios)
    return novo


def _recalibrar_fontes(ajustes: Ajustes, desvios: list[Desvio]) -> None:
    """Desvio sistemático por fonte: mediana das palavras que abrem um trecho."""
    por_chave: dict[str, list[Desvio]] = defaultdict(list)
    for d in desvios:
        tipico = abs(d.dx_inicio) <= LIMITE_SISTEMATICO_PT and abs(d.dy) <= LIMITE_SISTEMATICO_PT
        if d.indice == 0 and tipico:
            por_chave[chave_trecho(d.trecho)].append(d)
    for chave, grupo in por_chave.items():
        dx = median(d.dx_inicio for d in grupo)
        dy = median(d.dy for d in grupo)
        if abs(dx) < RESIDUO_MINIMO_PT and abs(dy) < RESIDUO_MINIMO_PT:
            continue
        atual_dx, atual_dy = ajustes.por_fonte.get(chave, (0.0, 0.0))
        ajustes.por_fonte[chave] = (round(atual_dx - dx, 3), round(atual_dy - dy, 3))


def _recalibrar_espacos(ajustes: Ajustes, desvios: list[Desvio]) -> None:
    """Cada palavra deve ter o mesmo desvio da anterior; a diferença vai para o espaço
    que a antecede. A primeira palavra, se o trecho começa com espaços, compara-se
    com o início do trecho (já posicionado no lugar exato)."""
    por_trecho: dict[int, list[Desvio]] = defaultdict(list)
    for d in desvios:
        por_trecho[d.trecho.id].append(d)
    for trecho_id, grupo in por_trecho.items():
        grupo.sort(key=lambda d: d.indice)
        referencias = [None] + grupo[:-1]
        for anterior, atual in zip(referencias, grupo):
            if anterior is None and atual.indice == 0:
                continue  # início do trecho: tratado pela calibração da fonte
            deriva = atual.dx_inicio - _referencia(anterior)
            if abs(deriva) < PASSO_ESPACAMENTO_PT / 2:
                continue
            chave = (trecho_id, atual.indice)
            velho = ajustes.espacos.get(chave, 0.0)
            novo = round((velho - deriva) / PASSO_ESPACAMENTO_PT) * PASSO_ESPACAMENTO_PT
            ajustes.espacos[chave] = round(novo, 2)


def _referencia(anterior: Desvio | None) -> float:
    """Desvio de onde a palavra anterior termina. Se a largura dela também será
    corrigida, o espaço só responde pelo vão (senão o erro seria corrigido duas vezes)."""
    if anterior is None:
        return 0.0
    return anterior.dx_fim if _largura_corrigivel(anterior) else anterior.dx_inicio


def _largura_corrigivel(d: Desvio) -> bool:
    return d.indice_fim is not None and d.indice_fim - d.indice >= 1


def _recalibrar_larguras(ajustes: Ajustes, desvios: list[Desvio]) -> None:
    """Palavra mais larga/estreita que o original: distribui a diferença entre as letras."""
    for d in desvios:
        if not _largura_corrigivel(d):
            continue
        letras = d.indice_fim - d.indice
        erro = d.dx_fim - d.dx_inicio
        if abs(erro) < PASSO_ESPACAMENTO_PT * letras / 2:
            continue
        chave = (d.trecho.id, d.indice)
        _, velho = ajustes.larguras.get(chave, (d.indice_fim, 0.0))
        novo = round((velho - erro / letras) / PASSO_ESPACAMENTO_PT) * PASSO_ESPACAMENTO_PT
        ajustes.larguras[chave] = (d.indice_fim, round(novo, 2))
