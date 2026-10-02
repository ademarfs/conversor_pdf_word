"""Escreve um PlanoDocumento como arquivo .docx (uma seção do Word por página do PDF)."""
from __future__ import annotations

import copy
import io
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.section import Section
from docx.shared import Pt

from ..layout.plano import PlanoDocumento, PlanoPagina
from ..modelo import Forma, Imagem, Segmento
from . import ooxml

Z_INICIAL = 1000   # camada (relativeHeight) do primeiro objeto ancorado


class EscritorDocx:
    """Traduz o plano para OOXML. Não toma decisões de layout."""

    def salvar(self, plano: PlanoDocumento, destino: Path, titulo: str = "") -> None:
        self._documento = Document()
        self._proximo_id = 1
        self._corpo = self._documento.element.body
        self._ajustar_compatibilidade()
        for indice, pagina in enumerate(plano.paginas):
            ultima = indice == len(plano.paginas) - 1
            self._escrever_pagina(pagina, ultima)
        self._documento.core_properties.title = titulo
        self._documento.core_properties.comments = f"Gerado pelo Conversor PDF→Word (motor {plano.motor})"
        self._documento.save(str(destino))

    # ------------------------------------------------------------------ páginas

    def _escrever_pagina(self, pagina: PlanoPagina, ultima: bool) -> None:
        secao_atual = self._corpo.sectPr
        self._configurar_secao(Section(secao_atual, self._documento.part), pagina)

        if pagina.linhas:
            self._inserir(ooxml.tabela_xml(pagina.colunas, pagina.linhas))
        for quadro in pagina.quadros:
            moldura = ooxml.quadro_xml(quadro.x, quadro.y, quadro.largura, quadro.paragrafo.altura_linha)
            self._inserir(ooxml.paragrafo_xml(quadro.paragrafo, moldura))

        final = ooxml.paragrafo_xml(None)
        for run in self._objetos_ancorados(pagina):
            final.append(run)
        if not ultima:
            # A quebra de seção fica no último parágrafo da página e carrega as
            # propriedades (tamanho, margens) desta página.
            final.find(qn("w:pPr")).append(copy.deepcopy(secao_atual))
        self._inserir(final)

    def _configurar_secao(self, secao: Section, pagina: PlanoPagina) -> None:
        secao.orientation = WD_ORIENT.LANDSCAPE if pagina.largura > pagina.altura else WD_ORIENT.PORTRAIT
        secao.page_width = Pt(pagina.largura)
        secao.page_height = Pt(pagina.altura)
        for margem in ("left_margin", "right_margin", "top_margin", "bottom_margin",
                       "header_distance", "footer_distance", "gutter"):
            setattr(secao, margem, Pt(0))

    def _inserir(self, elemento) -> None:
        self._corpo.insert_element_before(elemento, "w:sectPr")

    # ------------------------------------------------------- objetos ancorados

    def _objetos_ancorados(self, pagina: PlanoPagina):
        """Desenhos e imagens atrás do texto, empilhados na ordem de pintura do PDF."""
        objetos = ([(f.ordem, self._forma, f) for f in pagina.formas]
                   + [(i.ordem, self._imagem, i) for i in pagina.imagens]
                   + [(s.ordem, self._segmento, s) for s in pagina.segmentos])
        objetos.sort(key=lambda o: o[0])
        for z, (_, desenhar, objeto) in enumerate(objetos):
            yield desenhar(objeto, Z_INICIAL + z)

    def _imagem(self, imagem: Imagem, z: int):
        r_id, _ = self._documento.part.get_or_add_image(io.BytesIO(imagem.png))
        return ooxml.imagem_ancorada(r_id, imagem.x0, imagem.y0, imagem.x1, imagem.y1,
                                     self._novo_id(), z)

    def _segmento(self, seg: Segmento, z: int):
        caminho = [("M", (seg.x0, seg.y0)), ("L", (seg.x1, seg.y1))]
        return ooxml.forma_ancorada([caminho], False, seg.cor, None, seg.espessura, seg.tracejado,
                                    self._novo_id(), z, opacidade_traco=seg.opacidade)

    def _forma(self, forma: Forma, z: int):
        return ooxml.forma_ancorada(_caminhos(forma), forma.fechado, forma.cor_traco,
                                    forma.cor_preenchimento, forma.espessura, forma.tracejado,
                                    self._novo_id(), z, forma.opacidade_traco,
                                    forma.opacidade_preenchimento)

    def _novo_id(self) -> int:
        self._proximo_id += 1
        return self._proximo_id

    def _ajustar_compatibilidade(self) -> None:
        """Força o modo de compatibilidade do Word 2013+ (evita 'Modo de Compatibilidade')."""
        configuracoes = self._documento.settings.element
        compat = configuracoes.find(qn("w:compat"))
        if compat is None:
            compat = configuracoes.makeelement(qn("w:compat"), {})
            configuracoes.append(compat)
        for item in compat.findall(qn("w:compatSetting")):
            if item.get(qn("w:name")) == "compatibilityMode":
                compat.remove(item)
        item = compat.makeelement(qn("w:compatSetting"), {
            qn("w:name"): "compatibilityMode",
            qn("w:uri"): "http://schemas.microsoft.com/office/word",
            qn("w:val"): "15",
        })
        compat.append(item)


def _caminhos(forma: Forma) -> list[list[tuple]]:
    """Converte os itens do PyMuPDF em subcaminhos M/L/C contínuos."""
    caminhos: list[list[tuple]] = []
    ultimo = None
    for item in forma.itens:
        tipo, inicio = item[0], item[1]
        if ultimo is None or _distancia(inicio, ultimo) > 0.01:
            caminhos.append([("M", inicio)])
        if tipo == "l":
            caminhos[-1].append(("L", item[2]))
            ultimo = item[2]
        else:  # "c"
            caminhos[-1].append(("C", item[2], item[3], item[4]))
            ultimo = item[4]
    return caminhos


def _distancia(a: tuple, b: tuple) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
