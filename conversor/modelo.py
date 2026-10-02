"""Modelo de dados neutro extraído do PDF.

Todas as medidas estão em pontos tipográficos (1 pt = 1/72 pol), com a origem
no canto superior esquerdo da página e o eixo Y crescendo para baixo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import FATOR_BASE_WORD


@dataclass(frozen=True)
class Caractere:
    """Um caractere com sua posição horizontal (usado na verificação)."""

    texto: str
    x0: float
    x1: float


@dataclass
class Trecho:
    """Trecho de texto contínuo com a mesma formatação (span do PDF)."""

    id: int
    texto: str
    fonte: str
    fonte_pdf: str
    tamanho: float
    negrito: bool
    italico: bool
    cor: str
    x0: float
    x1: float
    base: float
    caracteres: list[Caractere] = field(default_factory=list)

    @property
    def topo(self) -> float:
        """Topo da caixa de linha que o Word usará (ver config.FATOR_BASE_WORD)."""
        return self.base - FATOR_BASE_WORD * self.tamanho

    @property
    def fundo(self) -> float:
        return self.base + (1 - FATOR_BASE_WORD) * self.tamanho


@dataclass
class Segmento:
    """Linha reta horizontal ou vertical (traço, sublinhado, borda de tabela)."""

    x0: float
    y0: float
    x1: float
    y1: float
    espessura: float
    cor: str
    tracejado: bool = False
    opacidade: float = 1.0
    ordem: int = 0           # posição na ordem de pintura da página (quem fica por cima)

    @property
    def horizontal(self) -> bool:
        return abs(self.y1 - self.y0) < 0.01

    @property
    def vertical(self) -> bool:
        return abs(self.x1 - self.x0) < 0.01 and not self.horizontal


@dataclass
class Forma:
    """Desenho vetorial genérico (curvas, preenchimentos, diagonais).

    `itens` usa o formato do PyMuPDF: ("l", p1, p2), ("c", p1, c1, c2, p2),
    com cada ponto como tupla (x, y). Retângulos já chegam convertidos em linhas.
    """

    itens: list[tuple]
    cor_traco: str | None
    cor_preenchimento: str | None
    espessura: float
    fechado: bool
    tracejado: bool = False
    opacidade_traco: float = 1.0
    opacidade_preenchimento: float = 1.0
    ordem: int = 0


@dataclass
class Imagem:
    x0: float
    y0: float
    x1: float
    y1: float
    png: bytes
    ordem: int = 0


@dataclass
class Pagina:
    numero: int
    largura: float
    altura: float
    trechos: list[Trecho] = field(default_factory=list)
    segmentos: list[Segmento] = field(default_factory=list)
    formas: list[Forma] = field(default_factory=list)
    imagens: list[Imagem] = field(default_factory=list)


@dataclass
class Documento:
    caminho: str
    sha256: str
    produtor: str
    paginas: list[Pagina]
    avisos: list[str] = field(default_factory=list)

    @property
    def assinatura_layout(self) -> str:
        """Identifica documentos do mesmo 'tipo' (mesmo gerador, fontes e formato)."""
        fontes = sorted({t.fonte_pdf for p in self.paginas for t in p.trechos})
        formatos = sorted({(round(p.largura), round(p.altura)) for p in self.paginas})
        return f"{self.produtor}|{','.join(fontes)}|{formatos}"

    @property
    def total_trechos(self) -> int:
        return sum(len(p.trechos) for p in self.paginas)
