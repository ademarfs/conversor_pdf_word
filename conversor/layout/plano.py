"""Plano de montagem: o que o escritor de .docx deve gerar, já resolvido em pontos.

Os motores de layout transformam o `Documento` (modelo do PDF) em um
`PlanoDocumento`; o escritor apenas traduz o plano para OOXML, sem decidir nada.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..modelo import Forma, Imagem, Segmento


@dataclass
class RunPlano:
    texto: str
    fonte: str
    tamanho: float
    negrito: bool
    italico: bool
    cor: str
    trecho_id: int
    tab_antes: bool = False
    elevacao: float = 0.0       # pt; positivo sobe o texto em relação à linha de base
    espacamento: float = 0.0    # pt adicionados entre caracteres


@dataclass
class ParagrafoPlano:
    runs: list[RunPlano]
    recuo: float                          # pt a partir da borda esquerda da célula/quadro
    tabulacoes: list[float]               # posições (pt) relativas à mesma borda
    altura_linha: float                   # espaçamento "Exatamente"
    base: float                           # linha de base desejada (coordenada da página)
    espaco_antes: float = 0.0
    deslocamento: float = 0.0             # pt que o texto teve de subir/descer para caber


@dataclass(frozen=True)
class Borda:
    espessura: float
    cor: str
    tracejado: bool = False


@dataclass
class CelulaPlano:
    x0: float
    x1: float
    paragrafos: list[ParagrafoPlano] = field(default_factory=list)
    borda_inferior: Borda | None = None
    borda_esquerda: Borda | None = None
    borda_direita: Borda | None = None


@dataclass
class LinhaPlano:
    y0: float
    y1: float
    celulas: list[CelulaPlano]


@dataclass
class QuadroPlano:
    """Parágrafo posicionado de forma absoluta na página (motor absoluto)."""

    x: float
    y: float
    largura: float
    paragrafo: ParagrafoPlano


@dataclass
class PlanoPagina:
    largura: float
    altura: float
    linhas: list[LinhaPlano] = field(default_factory=list)
    quadros: list[QuadroPlano] = field(default_factory=list)
    segmentos: list[Segmento] = field(default_factory=list)   # desenhados como formas
    formas: list[Forma] = field(default_factory=list)
    imagens: list[Imagem] = field(default_factory=list)

    @property
    def colunas(self) -> list[float]:
        """Grade de colunas da tabela (todas as bordas de célula, ordenadas)."""
        return sorted({x for linha in self.linhas for c in linha.celulas for x in (c.x0, c.x1)})


@dataclass
class PlanoDocumento:
    motor: str
    paginas: list[PlanoPagina]

    @property
    def trechos_deslocados(self) -> set[int]:
        """Trechos que não puderam ficar na posição exata (excluídos da calibração)."""
        ids = set()
        for pagina in self.paginas:
            paragrafos = [p for linha in pagina.linhas for c in linha.celulas for p in c.paragrafos]
            paragrafos += [q.paragrafo for q in pagina.quadros]
            for p in paragrafos:
                if abs(p.deslocamento) > 0.05:
                    ids.update(r.trecho_id for r in p.runs)
        return ids
