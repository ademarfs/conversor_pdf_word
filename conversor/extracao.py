"""Leitura do PDF (PyMuPDF) para o modelo neutro: textos, linhas, formas e imagens."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import replace
from pathlib import Path

import pymupdf

from .erros import ErroConversao
from .fontes import mapear_fonte
from .modelo import Caractere, Documento, Forma, Imagem, Pagina, Segmento, Trecho

log = logging.getLogger(__name__)

ESPESSURA_MINIMA = 0.25      # traço "fio de cabelo" (largura 0 no PDF)
RETANGULO_FINO = 2.0         # retângulo preenchido com até 2 pt de altura = linha
DPI_IMAGEM_RECORTADA = 300
DPI_IMAGEM_MAXIMO = 600
ORDEM_TEXTO = 10 ** 9           # texto fica acima de todos os desenhos
SEM_UNICODE = chr(0xFFFD)       # caractere que o PDF não sabe traduzir para texto
FONTES_SIMBOLO = {"Symbol", "Wingdings", "Wingdings 2", "Wingdings 3", "Webdings"}
FONTE_UNICODE_SIMBOLOS = "Segoe UI Symbol"
# Sem TEXT_PRESERVE_LIGATURES: "ﬁ" vira "f"+"i", que é o texto real (editável/pesquisável).
FLAGS_TEXTO = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP


def extrair(caminho: Path) -> Documento:
    """Lê o PDF inteiro para o modelo. Erros esperados viram ErroConversao."""
    try:
        pdf = pymupdf.open(caminho)
    except Exception as erro:
        raise ErroConversao(f"Não foi possível abrir o PDF: {erro}") from erro
    with pdf:
        if pdf.needs_pass:
            raise ErroConversao("O PDF está protegido por senha. Remova a proteção e tente novamente.")
        if pdf.page_count == 0:
            raise ErroConversao("O PDF não tem páginas.")
        avisos: list[str] = []
        proximo_id = iter(range(1_000_000))
        paginas = [_extrair_pagina(pdf, pagina, proximo_id, avisos) for pagina in pdf]
        produtor = (pdf.metadata or {}).get("producer") or ""
    _avisar_fontes_ausentes(paginas, avisos)
    return Documento(
        caminho=str(caminho),
        sha256=hashlib.sha256(Path(caminho).read_bytes()).hexdigest(),
        produtor=produtor,
        paginas=paginas,
        avisos=list(dict.fromkeys(avisos)),  # sem repetições, na ordem em que surgiram
    )


def _extrair_pagina(pdf, pagina, proximo_id, avisos: list[str]) -> Pagina:
    numero = pagina.number + 1
    if pagina.rotation:
        avisos.append(f"Página {numero} está girada {pagina.rotation}°; confira o resultado.")
    resultado = Pagina(numero, pagina.rect.width, pagina.rect.height)
    resultado.trechos, glifos = _extrair_trechos(pagina, proximo_id, avisos)
    resultado.segmentos, resultado.formas = _extrair_desenhos(pagina)
    resultado.imagens = _extrair_imagens(pdf, pagina) + glifos
    if not resultado.trechos and resultado.imagens:
        avisos.append(f"Página {numero} parece digitalizada (só imagem): o Word terá a imagem, "
                      "sem texto editável (OCR não incluído).")
    return resultado


# -------------------------------------------------------------------- textos

def _extrair_trechos(pagina, proximo_id, avisos: list[str]) -> tuple[list[Trecho], list[Imagem]]:
    """Trechos de texto e, à parte, imagens dos trechos cujo texto não é recuperável."""
    trechos, glifos = [], []
    conteudo = pagina.get_text("rawdict", flags=FLAGS_TEXTO)
    for bloco in conteudo["blocks"]:
        for linha in bloco.get("lines", []):
            if linha["dir"] != (1.0, 0.0):
                avisos.append(f"Página {pagina.number + 1}: texto inclinado/vertical será "
                              "posicionado na horizontal.")
            for span in linha["spans"]:
                trecho = _criar_trecho(span, next(proximo_id))
                if trecho is None:
                    continue
                if SEM_UNICODE in trecho.texto:
                    glifos.append(_imagem_do_trecho(pagina, span))
                    avisos.append(f"Página {pagina.number + 1}: caracteres sem código Unicode no PDF "
                                  "foram mantidos como imagem (aparência idêntica, não editáveis).")
                else:
                    trechos.append(trecho)
    return trechos, glifos


def _imagem_do_trecho(pagina, span: dict) -> Imagem:
    caixa = pymupdf.Rect(span["bbox"]) & pagina.rect
    png = pagina.get_pixmap(clip=caixa, dpi=DPI_IMAGEM_MAXIMO, alpha=True).tobytes("png")
    return Imagem(caixa.x0, caixa.y0, caixa.x1, caixa.y1, png, ORDEM_TEXTO)


def _criar_trecho(span: dict, identificador: int) -> Trecho | None:
    chars = span["chars"]
    texto = "".join(c["c"] for c in chars)
    if not texto.strip():
        return None  # espaços isolados não aparecem; a posição dos demais trechos já é absoluta
    fonte = mapear_fonte(span["font"], span["flags"])
    return Trecho(
        id=identificador,
        texto=texto,
        fonte=_fonte_para_o_texto(fonte.familia, texto),
        fonte_pdf=span["font"],
        tamanho=round(span["size"], 2),
        negrito=fonte.negrito,
        italico=fonte.italico,
        cor=f"{span['color']:06X}",
        x0=chars[0]["origin"][0],
        x1=max(c["bbox"][2] for c in chars),
        base=span["origin"][1],
        caracteres=[Caractere(c["c"], c["bbox"][0], c["bbox"][2]) for c in chars],
    )


def _fonte_para_o_texto(familia: str, texto: str) -> str:
    """Fontes de símbolo no Word só exibem códigos privados (U+F0xx). Quando o PDF já
    traz o caractere Unicode real (ex.: '•'), usa uma fonte Unicode de símbolos."""
    if familia in FONTES_SIMBOLO and any(not _codigo_privado(c) for c in texto if not c.isspace()):
        return FONTE_UNICODE_SIMBOLOS
    return familia


def _codigo_privado(caractere: str) -> bool:
    return 0xF000 <= ord(caractere) <= 0xF0FF


def _avisar_fontes_ausentes(paginas: list[Pagina], avisos: list[str]) -> None:
    ausentes = sorted({t.fonte_pdf for p in paginas for t in p.trechos
                       if not mapear_fonte(t.fonte_pdf, 0).instalada})
    for nome in ausentes:
        avisos.append(f"Fonte '{nome}' não está instalada no Windows; o Word usará uma "
                      "substituta e o espaçamento pode variar. Instale a fonte para fidelidade total.")


# ------------------------------------------------------------------ desenhos

def _extrair_desenhos(pagina) -> tuple[list[Segmento], list[Forma]]:
    segmentos: list[Segmento] = []
    formas: list[Forma] = []
    for desenho in pagina.get_drawings():
        opacidade_traco = _opacidade(desenho.get("stroke_opacity"))
        opacidade_preenchimento = _opacidade(desenho.get("fill_opacity"))
        # Elementos totalmente transparentes existem no PDF mas não aparecem.
        traco = _cor(desenho.get("color")) if desenho["type"] in ("s", "fs") and opacidade_traco else None
        preenchimento = (_cor(desenho.get("fill"))
                         if desenho["type"] in ("f", "fs") and opacidade_preenchimento else None)
        if not traco and not preenchimento:
            continue
        espessura = max(desenho.get("width") or 0, ESPESSURA_MINIMA)
        tracejado = (desenho.get("dashes") or "[] 0").replace(" ", "") not in ("[]0", "[]0.0")
        opacidade = opacidade_traco if traco else opacidade_preenchimento
        restantes: list[tuple] = []
        for item in desenho["items"]:
            novos = _item_como_segmentos(item, traco, preenchimento, espessura, tracejado)
            if novos is None:
                restantes.extend(_item_como_linhas(item))
            else:
                segmentos.extend(replace(s, opacidade=opacidade, ordem=desenho["seqno"]) for s in novos)
        if restantes:
            formas.append(Forma(restantes, traco, preenchimento, espessura,
                                bool(desenho.get("closePath")) or bool(preenchimento), tracejado,
                                opacidade_traco, opacidade_preenchimento, desenho["seqno"]))
    return segmentos, formas


def _opacidade(valor) -> float:
    return 1.0 if valor is None else max(0.0, min(1.0, float(valor)))


def _item_como_segmentos(item, traco, preenchimento, espessura, tracejado) -> list[Segmento] | None:
    """Converte o item em segmentos retos, ou None se ele precisar virar forma livre."""
    tipo = item[0]
    if tipo == "l" and traco and not preenchimento:
        p1, p2 = item[1], item[2]
        if abs(p1.y - p2.y) < 0.01 or abs(p1.x - p2.x) < 0.01:
            (x0, y0), (x1, y1) = sorted([(p1.x, p1.y), (p2.x, p2.y)])
            return [Segmento(x0, y0, x1, y1, espessura, traco, tracejado)]
        return None
    retangulo = _retangulo_do_item(item)
    if retangulo is None:
        return None
    if preenchimento and not traco:
        return _retangulo_fino(retangulo, preenchimento)
    if traco and not preenchimento:
        r = retangulo
        return [Segmento(r.x0, r.y0, r.x1, r.y0, espessura, traco, tracejado),
                Segmento(r.x0, r.y1, r.x1, r.y1, espessura, traco, tracejado),
                Segmento(r.x0, r.y0, r.x0, r.y1, espessura, traco, tracejado),
                Segmento(r.x1, r.y0, r.x1, r.y1, espessura, traco, tracejado)]
    return None


def _retangulo_do_item(item) -> pymupdf.Rect | None:
    if item[0] == "re":
        return pymupdf.Rect(item[1])
    if item[0] == "qu" and item[1].is_rectangular:
        return item[1].rect
    return None


def _retangulo_fino(r: pymupdf.Rect, cor: str) -> list[Segmento] | None:
    """Retângulo preenchido muito fino é, visualmente, uma linha."""
    if r.height <= RETANGULO_FINO and r.width > 2 * r.height:
        y = (r.y0 + r.y1) / 2
        return [Segmento(r.x0, y, r.x1, y, r.height, cor)]
    if r.width <= RETANGULO_FINO and r.height > 2 * r.width:
        x = (r.x0 + r.x1) / 2
        return [Segmento(x, r.y0, x, r.y1, r.width, cor)]
    return None


def _item_como_linhas(item) -> list[tuple]:
    """Normaliza o item para ("l", p1, p2) / ("c", p1, c1, c2, p2) com tuplas."""
    tipo = item[0]
    if tipo == "l":
        return [("l", tuple(item[1]), tuple(item[2]))]
    if tipo == "c":
        return [("c",) + tuple(tuple(p) for p in item[1:5])]
    cantos = (item[1].quad if tipo == "re" else item[1])
    pontos = [tuple(cantos.ul), tuple(cantos.ur), tuple(cantos.lr), tuple(cantos.ll)]
    return [("l", pontos[i], pontos[(i + 1) % 4]) for i in range(4)]


def _cor(rgb) -> str | None:
    if rgb is None:
        return None
    return "".join(f"{round(max(0.0, min(1.0, v)) * 255):02X}" for v in rgb[:3])


# ------------------------------------------------------------------- imagens

def _extrair_imagens(pdf, pagina) -> list[Imagem]:
    imagens = []
    ordens = _ordem_das_imagens(pagina)
    for info in pagina.get_image_info(xrefs=True):
        caixa = pymupdf.Rect(info["bbox"]) & pagina.rect
        if caixa.is_empty or caixa.width < 0.5 or caixa.height < 0.5:
            continue
        png = None
        if _sem_rotacao(info) and not _eh_mascara(pdf, info):
            png = _png_original(pdf, info)
        if png is None:
            # Máscaras de estêncil (1 bit pintado com a cor de preenchimento), imagens
            # giradas e formatos exóticos: recorta a área como aparece na página,
            # com fundo transparente e na resolução nativa da imagem.
            png = pagina.get_pixmap(clip=caixa, dpi=_dpi_nativo(info, caixa), alpha=True).tobytes("png")
        ordem = ordens.pop(_mais_proxima(ordens, info["bbox"]))[0] if ordens else 0
        imagens.append(Imagem(caixa.x0, caixa.y0, caixa.x1, caixa.y1, png, ordem))
    return imagens


def _ordem_das_imagens(pagina) -> list[tuple[int, pymupdf.Rect]]:
    """Posição de cada imagem na ordem de pintura (o mesmo índice do 'seqno' dos desenhos)."""
    return [(i, pymupdf.Rect(caixa)) for i, (tipo, caixa) in enumerate(pagina.get_bboxlog())
            if "image" in tipo or "imgmask" in tipo]


def _mais_proxima(ordens: list[tuple[int, pymupdf.Rect]], caixa) -> int:
    alvo = pymupdf.Rect(caixa)
    distancias = [abs(r.x0 - alvo.x0) + abs(r.y0 - alvo.y0) + abs(r.x1 - alvo.x1) + abs(r.y1 - alvo.y1)
                  for _, r in ordens]
    return distancias.index(min(distancias))


def _eh_mascara(pdf, info: dict) -> bool:
    xref = info.get("xref") or 0
    return xref > 0 and pdf.xref_get_key(xref, "ImageMask")[1] == "true"


def _dpi_nativo(info: dict, caixa: pymupdf.Rect) -> int:
    largura_px = info.get("width") or 0
    dpi = largura_px / caixa.width * 72 if caixa.width else DPI_IMAGEM_RECORTADA
    return int(min(DPI_IMAGEM_MAXIMO, max(DPI_IMAGEM_RECORTADA, dpi)))


def _sem_rotacao(info: dict) -> bool:
    a, b, c, d = info["transform"][:4]
    return abs(b) < 1e-6 and abs(c) < 1e-6 and a > 0 and d > 0


def _png_original(pdf, info: dict) -> bytes | None:
    """Imagem na resolução original, com transparência (máscara) preservada."""
    xref = info.get("xref") or 0
    if xref <= 0:
        return None
    try:
        pix = pymupdf.Pixmap(pdf, xref)
        if pix.colorspace and pix.colorspace.n not in (1, 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        mascara = pdf.extract_image(xref).get("smask") or 0
        if mascara and not pix.alpha:
            pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(pdf, mascara))
        return pix.tobytes("png")
    except Exception as erro:  # formatos exóticos: cai no recorte renderizado
        log.info("Imagem xref %s extraída por recorte: %s", xref, erro)
        return None
