"""Construtores de XML WordprocessingML (OOXML) de baixo nível.

Cada função gera exatamente um elemento, na ordem exigida pelo schema do Word.
Nenhuma regra de layout fica aqui: só tradução de valores em pontos para XML.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn

from ..layout.plano import Borda, ParagrafoPlano, RunPlano

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"

EMU_POR_PT = 12700


def twips(pontos: float) -> int:
    """Converte pontos para vigésimos de ponto (unidade usada pelo Word)."""
    return round(pontos * 20)


def emu(pontos: float) -> int:
    return round(pontos * EMU_POR_PT)


def _el(tag: str, **atributos) -> OxmlElement:
    elemento = OxmlElement(tag)
    for nome, valor in atributos.items():
        elemento.set(qn(f"w:{nome}"), str(valor))
    return elemento


# --------------------------------------------------------------------- texto

def run_xml(run: RunPlano) -> OxmlElement:
    r = _el("w:r")
    rpr = _el("w:rPr")
    rpr.append(_el("w:rFonts", ascii=run.fonte, hAnsi=run.fonte, cs=run.fonte, eastAsia=run.fonte))
    if run.negrito:
        rpr.append(_el("w:b"))
    if run.italico:
        rpr.append(_el("w:i"))
    rpr.append(_el("w:noProof"))
    rpr.append(_el("w:color", val=run.cor))
    if twips(run.espacamento):
        rpr.append(_el("w:spacing", val=twips(run.espacamento)))
    meios_pontos = round(run.elevacao * 2)
    if meios_pontos:
        rpr.append(_el("w:position", val=meios_pontos))
    tamanho = round(run.tamanho * 2)
    rpr.append(_el("w:sz", val=tamanho))
    rpr.append(_el("w:szCs", val=tamanho))
    r.append(rpr)
    if run.tab_antes:
        r.append(_el("w:tab"))
    t = _el("w:t")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = run.texto
    r.append(t)
    return r


def paragrafo_xml(plano: ParagrafoPlano | None, quadro: OxmlElement | None = None) -> OxmlElement:
    """Parágrafo com espaçamento exato; `plano=None` gera um parágrafo mínimo (1 pt)."""
    p = _el("w:p")
    ppr = _el("w:pPr")
    if quadro is not None:
        ppr.append(quadro)
    ppr.append(_el("w:widowControl", val=0))
    if plano and plano.tabulacoes:
        tabs = _el("w:tabs")
        for posicao in plano.tabulacoes:
            tabs.append(_el("w:tab", val="left", pos=twips(posicao)))
        ppr.append(tabs)
    ppr.append(_el("w:snapToGrid", val=0))
    altura = plano.altura_linha if plano else 1
    antes = plano.espaco_antes if plano else 0
    ppr.append(_el("w:spacing", before=twips(antes), after=0, line=twips(altura), lineRule="exact"))
    ppr.append(_el("w:ind", left=twips(plano.recuo if plano else 0), right=0, firstLine=0))
    ppr.append(_el("w:jc", val="left"))
    if plano is None:
        rpr = _el("w:rPr")
        rpr.append(_el("w:sz", val=2))
        ppr.append(rpr)
    p.append(ppr)
    for run in plano.runs if plano else []:
        p.append(run_xml(run))
    return p


def quadro_xml(x: float, y: float, largura: float, altura: float) -> OxmlElement:
    """Moldura (frame) com posição absoluta na página."""
    return _el(
        "w:framePr", w=twips(largura), h=twips(altura), hRule="atLeast", wrap="around",
        hAnchor="page", vAnchor="page", x=twips(x), y=twips(y), hSpace=0, vSpace=0,
    )


# -------------------------------------------------------------------- tabela

def _borda_xml(lado: str, borda: Borda | None) -> OxmlElement:
    if borda is None:
        return _el(f"w:{lado}", val="nil")
    oitavos = min(96, max(2, round(borda.espessura * 8)))
    return _el(f"w:{lado}", val="dashed" if borda.tracejado else "single",
               sz=oitavos, space=0, color=borda.cor)


def tabela_xml(colunas: list[float], linhas) -> OxmlElement:
    """Tabela de layout fixo, sem margens internas, alinhada à coordenada x=0.

    `colunas` são as coordenadas x de todas as bordas; `linhas` são LinhaPlano.
    """
    pos = [twips(x) for x in colunas]
    tbl = _el("w:tbl")
    tblpr = _el("w:tblPr")
    tblpr.append(_el("w:tblW", w=pos[-1] - pos[0], type="dxa"))
    tblpr.append(_el("w:tblInd", w=pos[0], type="dxa"))
    bordas = _el("w:tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        bordas.append(_el(f"w:{lado}", val="nil"))
    tblpr.append(bordas)
    tblpr.append(_el("w:tblLayout", type="fixed"))
    margens = _el("w:tblCellMar")
    for lado in ("top", "left", "bottom", "right"):
        margens.append(_el(f"w:{lado}", w=0, type="dxa"))
    tblpr.append(margens)
    tblpr.append(_el("w:tblLook", val="0000"))
    tbl.append(tblpr)

    grade = _el("w:tblGrid")
    for a, b in zip(pos, pos[1:]):
        grade.append(_el("w:gridCol", w=b - a))
    tbl.append(grade)

    indice = {x: i for i, x in enumerate(colunas)}
    for linha in linhas:
        tr = _el("w:tr")
        trpr = _el("w:trPr")
        trpr.append(_el("w:cantSplit"))
        trpr.append(_el("w:trHeight", val=twips(linha.y1) - twips(linha.y0), hRule="exact"))
        tr.append(trpr)
        for celula in linha.celulas:
            i0, i1 = indice[celula.x0], indice[celula.x1]
            tc = _el("w:tc")
            tcpr = _el("w:tcPr")
            tcpr.append(_el("w:tcW", w=pos[i1] - pos[i0], type="dxa"))
            if i1 - i0 > 1:
                tcpr.append(_el("w:gridSpan", val=i1 - i0))
            tcb = _el("w:tcBorders")
            tcb.append(_borda_xml("top", None))
            tcb.append(_borda_xml("left", celula.borda_esquerda))
            tcb.append(_borda_xml("bottom", celula.borda_inferior))
            tcb.append(_borda_xml("right", celula.borda_direita))
            tcpr.append(tcb)
            tcpr.append(_el("w:vAlign", val="top"))
            tc.append(tcpr)
            paragrafos = celula.paragrafos or [None]
            for plano in paragrafos:
                tc.append(paragrafo_xml(plano))
            tr.append(tc)
        tbl.append(tr)
    return tbl


# ---------------------------------------------------- objetos ancorados (página)

def _ancora(conteudo: str, uri: str, x: float, y: float, largura: float, altura: float,
            id_objeto: int, z: int) -> str:
    return (
        f'<wp:anchor xmlns:wp="{NS_WP}" xmlns:a="{NS_A}" distT="0" distB="0" distL="0" distR="0" '
        f'simplePos="0" relativeHeight="{z}" behindDoc="1" locked="1" layoutInCell="0" allowOverlap="1">'
        '<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="page"><wp:posOffset>{emu(x)}</wp:posOffset></wp:positionH>'
        f'<wp:positionV relativeFrom="page"><wp:posOffset>{emu(y)}</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{max(1, emu(largura))}" cy="{max(1, emu(altura))}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/>'
        f'<wp:docPr id="{id_objeto}" name="Objeto {id_objeto}"/><wp:cNvGraphicFramePr/>'
        f'<a:graphic><a:graphicData uri="{uri}">{conteudo}</a:graphicData></a:graphic>'
        '</wp:anchor>'
    )


def _run_desenho(ancora: str) -> OxmlElement:
    return parse_xml(f'<w:r xmlns:w="{NS_W}"><w:drawing>{ancora}</w:drawing></w:r>')


def imagem_ancorada(r_id: str, x0: float, y0: float, x1: float, y1: float,
                    id_objeto: int, z: int) -> OxmlElement:
    cx, cy = max(1, emu(x1 - x0)), max(1, emu(y1 - y0))
    pic = (
        f'<pic:pic xmlns:pic="{NS_PIC}" xmlns:r="{NS_R}">'
        f'<pic:nvPicPr><pic:cNvPr id="{id_objeto}" name="imagem{id_objeto}.png"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{escape(r_id)}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
    )
    return _run_desenho(_ancora(pic, NS_PIC, x0, y0, x1 - x0, y1 - y0, id_objeto, z))


def _preenchimento(cor: str | None, opacidade: float = 1.0) -> str:
    if not cor:
        return "<a:noFill/>"
    alfa = f'<a:alpha val="{round(opacidade * 100000)}"/>' if opacidade < 0.999 else ""
    return f'<a:solidFill><a:srgbClr val="{cor}">{alfa}</a:srgbClr></a:solidFill>'


def forma_ancorada(caminhos: list[list[tuple]], fechado: bool, cor_traco: str | None,
                   cor_preenchimento: str | None, espessura: float, tracejado: bool,
                   id_objeto: int, z: int, opacidade_traco: float = 1.0,
                   opacidade_preenchimento: float = 1.0) -> OxmlElement:
    """Desenho vetorial livre. `caminhos` são listas de comandos:
    ("M", (x, y)) mover, ("L", (x, y)) reta, ("C", p1, p2, p3) curva de Bézier."""
    pontos = [p for caminho in caminhos for comando in caminho for p in comando[1:]]
    min_x = min(p[0] for p in pontos)
    min_y = min(p[1] for p in pontos)
    largura = max(p[0] for p in pontos) - min_x
    altura = max(p[1] for p in pontos) - min_y

    def pt(p):
        return f'<a:pt x="{emu(p[0] - min_x)}" y="{emu(p[1] - min_y)}"/>'

    tags = {"M": "a:moveTo", "L": "a:lnTo", "C": "a:cubicBezTo"}
    xml_caminhos = []
    for caminho in caminhos:
        partes = "".join(f"<{tags[c[0]]}>{''.join(pt(p) for p in c[1:])}</{tags[c[0]]}>" for c in caminho)
        if fechado:
            partes += "<a:close/>"
        atributos = f'w="{max(1, emu(largura))}" h="{max(1, emu(altura))}"'
        if not cor_preenchimento:
            atributos += ' fill="none"'
        if not cor_traco:
            atributos += ' stroke="0"'
        xml_caminhos.append(f"<a:path {atributos}>{partes}</a:path>")

    traco = '<a:ln><a:noFill/></a:ln>'
    if cor_traco:
        tracos = '<a:prstDash val="dash"/>' if tracejado else ""
        traco = f'<a:ln w="{emu(espessura)}">{_preenchimento(cor_traco, opacidade_traco)}{tracos}</a:ln>'
    wsp = (
        f'<wps:wsp xmlns:wps="{NS_WPS}"><wps:cNvSpPr/><wps:spPr>'
        f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{max(1, emu(largura))}" cy="{max(1, emu(altura))}"/></a:xfrm>'
        '<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="r" b="b"/>'
        f'<a:pathLst>{"".join(xml_caminhos)}</a:pathLst></a:custGeom>'
        f'{_preenchimento(cor_preenchimento, opacidade_preenchimento)}{traco}</wps:spPr><wps:bodyPr/></wps:wsp>'
    )
    return _run_desenho(_ancora(wsp, NS_WPS, min_x, min_y, largura, altura, id_objeto, z))
