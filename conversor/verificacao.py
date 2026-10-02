"""Verificação de fidelidade: original (PDF) × resultado (Word renderizado em PDF).

Três medidas independentes:
1. Texto: todas as palavras do original existem no resultado e nada sobra.
2. Posição: para cada palavra, a distância entre onde está no original e onde
   o Word a desenhou (início, fim e linha de base).
3. Visual: porcentagem de pixels diferentes entre as páginas renderizadas
   (pega linhas, imagens e formas, que não são texto).
"""
from __future__ import annotations

import logging
import zipfile
from collections import Counter
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree

import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .calibracao import Desvio
from .config import Config
from .modelo import Documento, Trecho
from .palavras import Letra, dividir, letras_da_pagina

log = logging.getLogger(__name__)

DPI_COMPARACAO = 100          # 1 pixel = 0,72 pt
LIMIAR_PIXEL = 64            # diferença de tom (0-255) que conta como pixel diferente
MARGEM_TEXTO_PT = 1.0        # folga ao mascarar as áreas de texto
DPI_PREVIA = 70
FLAGS_TEXTO = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP


@dataclass(frozen=True)
class Palavra:
    pagina: int
    texto: str
    x0: float
    x1: float
    base: float
    trecho: Trecho | None = None
    indice: int = 0                  # caractere do trecho onde a palavra começa
    indice_fim: int | None = None    # último caractere (None se a palavra cruza trechos)
    primeira_do_trecho: bool = False


@dataclass
class Relatorio:
    paginas_original: int
    paginas_resultado: int
    total_palavras: int
    faltando: list[str] = field(default_factory=list)
    sobrando: list[str] = field(default_factory=list)
    desvios: list[Desvio] = field(default_factory=list)
    pixels_diferentes: list[float] = field(default_factory=list)
    visual_verificado: bool = True

    @property
    def texto_identico(self) -> bool:
        return not self.faltando and not self.sobrando and self.paginas_original == self.paginas_resultado

    @property
    def desvio_maximo(self) -> float:
        return max((_distancia(d) for d in self.desvios), default=0.0)

    @property
    def desvio_medio(self) -> float:
        return sum(_distancia(d) for d in self.desvios) / len(self.desvios) if self.desvios else 0.0

    @property
    def pixels_maximo(self) -> float:
        return max(self.pixels_diferentes, default=0.0)

    def aprovado(self, config: Config) -> bool:
        if not self.texto_identico:
            return False
        if not self.visual_verificado:
            return True
        return (self.desvio_maximo <= config.tolerancia_posicao_pt
                and self.pixels_maximo <= config.tolerancia_pixels_pct)

    def pontuacao(self) -> tuple:
        """Maior é melhor; usada para escolher a melhor tentativa."""
        return (self.texto_identico, -len(self.faltando) - len(self.sobrando),
                -round(self.desvio_maximo, 1), -self.pixels_maximo, -self.desvio_medio)

    def resumo(self) -> dict:
        return {
            "texto_identico": self.texto_identico,
            "total_palavras": self.total_palavras,
            "faltando": self.faltando[:50],
            "sobrando": self.sobrando[:50],
            "desvio_maximo_pt": round(self.desvio_maximo, 2),
            "desvio_medio_pt": round(self.desvio_medio, 3),
            "pixels_diferentes_pct": [round(p, 2) for p in self.pixels_diferentes],
            "visual_verificado": self.visual_verificado,
        }


def _distancia(d: Desvio) -> float:
    return max(abs(d.dx_inicio), abs(d.dx_fim), abs(d.dy))


# ------------------------------------------------------------- verificação

def verificar(documento: Documento, pdf_resultado: Path) -> Relatorio:
    """Verificação completa contra o PDF exportado pelo Word."""
    originais = palavras_do_documento(documento)
    with pymupdf.open(pdf_resultado) as resultado, pymupdf.open(documento.caminho) as original:
        pares, faltando, sobrando = _parear(originais, palavras_do_pdf(resultado))
        return Relatorio(
            paginas_original=len(documento.paginas),
            paginas_resultado=resultado.page_count,
            total_palavras=len(originais),
            faltando=[p.texto for p in faltando],
            sobrando=[p.texto for p in sobrando],
            desvios=[_desvio(o, g) for o, g in pares],
            pixels_diferentes=[_diferenca_pixels(original[i], resultado[i])
                               for i in range(min(original.page_count, resultado.page_count))],
        )


def verificar_somente_texto(documento: Documento, docx: Path) -> Relatorio:
    """Sem o Word instalado: confere apenas se todos os caracteres estão no .docx."""
    originais = palavras_do_documento(documento)
    esperado = Counter(c for p in originais for c in p.texto)
    obtido = Counter(c for c in _texto_do_docx(docx) if not c.isspace())
    return Relatorio(
        paginas_original=len(documento.paginas),
        paginas_resultado=len(documento.paginas),
        total_palavras=len(originais),
        faltando=sorted((esperado - obtido).elements()),
        sobrando=sorted((obtido - esperado).elements()),
        visual_verificado=False,
    )


def gerar_previas(original: Path, resultado: Path, pasta: Path) -> list[tuple[str, str]]:
    """Imagens lado a lado (original, resultado) de cada página, para a interface."""
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos = []
    with pymupdf.open(original) as a, pymupdf.open(resultado) as b:
        for i in range(max(a.page_count, b.page_count)):
            nomes = (f"original_{i + 1}.png", f"resultado_{i + 1}.png")
            for documento, nome in ((a, nomes[0]), (b, nomes[1])):
                if i < documento.page_count:
                    documento[i].get_pixmap(dpi=DPI_PREVIA).save(pasta / nome)
            caminhos.append(nomes)
    return caminhos


# --------------------------------------------------------------- palavras

def palavras_do_documento(documento: Documento) -> list[Palavra]:
    palavras = []
    for pagina in documento.paginas:
        palavras += [_palavra(pagina.numero, grupo) for grupo in dividir(letras_da_pagina(pagina))]
    return _marcar_primeiras(palavras)


def palavras_do_pdf(pdf) -> list[Palavra]:
    palavras = []
    for pagina in pdf:
        letras = [
            Letra(c["c"], c["bbox"][0], c["bbox"][2], c["origin"][1], span["size"])
            for bloco in pagina.get_text("rawdict", flags=FLAGS_TEXTO)["blocks"]
            for linha in bloco.get("lines", [])
            for span in linha["spans"]
            for c in span["chars"]
        ]
        palavras += [_palavra(pagina.number + 1, grupo) for grupo in dividir(letras)]
    return palavras


def _palavra(numero: int, letras: list[Letra]) -> Palavra:
    primeira, ultima = letras[0], letras[-1]
    mesmo_trecho = all(letra.trecho is primeira.trecho for letra in letras)
    return Palavra(numero, "".join(letra.texto for letra in letras), primeira.x0, ultima.x1,
                   primeira.base, primeira.trecho, primeira.indice,
                   ultima.indice if mesmo_trecho and primeira.trecho else None)


def _marcar_primeiras(palavras: list[Palavra]) -> list[Palavra]:
    """Marca a primeira palavra de cada trecho (mede o posicionamento do trecho)."""
    menor_indice: dict[int, int] = {}
    for p in palavras:
        if p.trecho is not None:
            menor_indice[p.trecho.id] = min(p.indice, menor_indice.get(p.trecho.id, p.indice))
    return [replace(p, primeira_do_trecho=p.trecho is not None and p.indice == menor_indice[p.trecho.id])
            for p in palavras]


def _parear(originais: list[Palavra], geradas: list[Palavra]):
    """Pareia as palavras na ordem de leitura, página a página (alinhamento de sequência).

    Respeitar a ordem evita parear errado palavras repetidas (ex.: letras de um título
    espaçado) mesmo quando o resultado está bem deslocado.
    """
    pares, faltando, sobrando = [], [], []
    paginas = sorted({p.pagina for p in originais} | {p.pagina for p in geradas})
    for numero in paginas:
        a = [p for p in originais if p.pagina == numero]
        b = [p for p in geradas if p.pagina == numero]
        comparador = SequenceMatcher(None, [p.texto for p in a], [p.texto for p in b], autojunk=False)
        usados_a, usados_b = set(), set()
        for bloco in comparador.get_matching_blocks():
            for k in range(bloco.size):
                pares.append((a[bloco.a + k], b[bloco.b + k]))
                usados_a.add(bloco.a + k)
                usados_b.add(bloco.b + k)
        restantes_a = [p for i, p in enumerate(a) if i not in usados_a]
        restantes_b = [p for j, p in enumerate(b) if j not in usados_b]
        extras, sem_par_a, sem_par_b = _parear_por_proximidade(restantes_a, restantes_b)
        pares += extras
        faltando += sem_par_a
        sobrando += sem_par_b
    return pares, faltando, sobrando


def _parear_por_proximidade(a: list[Palavra], b: list[Palavra]):
    """Para o que saiu da ordem (ex.: linha muito deslocada): mesma palavra mais próxima."""
    candidatos = sorted(
        (abs(pb.x0 - pa.x0) + abs(pb.base - pa.base), i, j)
        for i, pa in enumerate(a) for j, pb in enumerate(b) if pa.texto == pb.texto
    )
    usados_a, usados_b, pares = set(), set(), []
    for _, i, j in candidatos:
        if i not in usados_a and j not in usados_b:
            usados_a.add(i)
            usados_b.add(j)
            pares.append((a[i], b[j]))
    return (pares, [p for i, p in enumerate(a) if i not in usados_a],
            [p for j, p in enumerate(b) if j not in usados_b])


def _desvio(original: Palavra, gerada: Palavra) -> Desvio:
    return Desvio(
        trecho=original.trecho,
        indice=original.indice,
        indice_fim=original.indice_fim,
        dx_inicio=gerada.x0 - original.x0,
        dx_fim=gerada.x1 - original.x1,
        dy=gerada.base - original.base,
        primeira_do_trecho=original.primeira_do_trecho,
    )


# ------------------------------------------------------------------- pixels

def _diferenca_pixels(pagina_a, pagina_b) -> float:
    """% de pixels diferentes fora das áreas de texto.

    O texto já é medido palavra a palavra; aqui interessa o resto (linhas, imagens,
    formas). Mascarar o texto evita contar como erro a diferença de desenho entre
    fontes equivalentes (ex.: Helvetica do PDF x Arial do Word).
    """
    caixas = _caixas_de_texto(pagina_a) + _caixas_de_texto(pagina_b)
    a = _sem_texto(_imagem_cinza(pagina_a), caixas)
    b = _sem_texto(_imagem_cinza(pagina_b).resize(a.size), caixas)
    diferenca = ImageChops.lighter(_fora_da_vizinhanca(a, b), _fora_da_vizinhanca(b, a))
    diferenca = diferenca.point(lambda v: 255 if v > LIMIAR_PIXEL else 0)
    return 100.0 * diferenca.histogram()[255] / (a.size[0] * a.size[1])


def _fora_da_vizinhanca(x: Image.Image, y: Image.Image) -> Image.Image:
    """Quanto cada pixel de x foge da faixa de tons da vizinhança 3x3 do mesmo ponto
    em y. Tolera 1 pixel de reamostragem (sem isso, imagens escaneadas acusam erro)."""
    acima = ImageChops.subtract(x, y.filter(ImageFilter.MaxFilter(3)))
    abaixo = ImageChops.subtract(y.filter(ImageFilter.MinFilter(3)), x)
    return ImageChops.lighter(acima, abaixo)


def _caixas_de_texto(pagina) -> list[tuple[float, float, float, float]]:
    return [tuple(p[:4]) for p in pagina.get_text("words", flags=FLAGS_TEXTO)]


def _sem_texto(imagem: Image.Image, caixas) -> Image.Image:
    escala = DPI_COMPARACAO / 72
    desenho = ImageDraw.Draw(imagem)
    for x0, y0, x1, y1 in caixas:
        desenho.rectangle([(x0 - MARGEM_TEXTO_PT) * escala, (y0 - MARGEM_TEXTO_PT) * escala,
                           (x1 + MARGEM_TEXTO_PT) * escala, (y1 + MARGEM_TEXTO_PT) * escala], fill=255)
    return imagem


def _imagem_cinza(pagina) -> Image.Image:
    pix = pagina.get_pixmap(dpi=DPI_COMPARACAO, colorspace=pymupdf.csGRAY, alpha=False)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def _texto_do_docx(docx: Path) -> str:
    with zipfile.ZipFile(docx) as pacote:
        raiz = ElementTree.fromstring(pacote.read("word/document.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    return "".join(t.text or "" for t in raiz.iter(f"{ns}t"))
