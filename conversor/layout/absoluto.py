"""Motor "absoluto": cada linha de texto é um quadro (frame) na posição exata.

Máxima fidelidade e aplicável a qualquer PDF; o texto continua editável, mas sem
a estrutura de tabela. Todos os traços viram formas vetoriais ancoradas.
"""
from __future__ import annotations

from ..calibracao import Ajustes
from ..config import FATOR_BASE_WORD, Config
from ..modelo import Documento, Pagina
from .paragrafos import agrupar_linhas, montar_paragrafo
from .plano import PlanoDocumento, PlanoPagina, QuadroPlano

TOLERANCIA_BASE_PT = 0.1   # trechos com a mesma linha de base dividem o quadro
FOLGA_LARGURA = 0.5        # fração da página somada à largura do quadro (nunca quebrar linha)


class MotorAbsoluto:
    nome = "absoluto"

    def __init__(self, config: Config):
        self.config = config

    def planejar(self, documento: Documento, ajustes: Ajustes) -> PlanoDocumento:
        return PlanoDocumento(self.nome, [self._pagina(p, ajustes) for p in documento.paginas])

    def _pagina(self, pagina: Pagina, ajustes: Ajustes) -> PlanoPagina:
        plano = PlanoPagina(pagina.largura, pagina.altura, segmentos=list(pagina.segmentos),
                            formas=list(pagina.formas), imagens=list(pagina.imagens))
        for linha in agrupar_linhas(pagina.trechos, tolerancia_base=TOLERANCIA_BASE_PT):
            primeiro = linha[0]
            x = primeiro.x0 + ajustes.deslocamento(primeiro)[0]
            paragrafo = montar_paragrafo(linha, x, ajustes, self.config)
            y = paragrafo.base - FATOR_BASE_WORD * paragrafo.altura_linha
            largura = max(pagina.largura - x, linha[-1].x1 - x) + FOLGA_LARGURA * pagina.largura
            plano.quadros.append(QuadroPlano(x, y, largura, paragrafo))
        return plano
