"""Motor "tabela": cada página vira uma tabela invisível de linhas com altura exata.

Ideia central (docs/ALGORITMO.md):
1. As linhas horizontais do PDF (sublinhados, bordas) definem os cortes entre as
   linhas da tabela; vazios entre blocos de texto geram cortes extras.
2. Em cada linha da tabela, as extremidades dos traços e as linhas verticais
   definem as células; cada texto vai para a célula onde começa.
3. Um traço que coincide com a borda de uma célula vira borda da célula; o que
   sobra é desenhado como forma vetorial ancorada na página (nada se perde).
4. Dentro da célula, recuo + tabulações + "espaço antes" põem cada texto na
   coordenada exata do original.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field, replace

from ..calibracao import Ajustes
from ..config import Config
from ..modelo import Documento, Pagina, Segmento, Trecho
from .paragrafos import agrupar_linhas, descida, empilhar, montar_paragrafo
from .plano import Borda, CelulaPlano, LinhaPlano, PlanoDocumento, PlanoPagina

ESPACO_FINAL_PT = 3.0      # reserva para o parágrafo de fim de página (quebra de seção)
VAZIO_MINIMO_PT = 1.0      # vão mínimo entre blocos de texto para criar um corte
MARGEM_LARGURA = 0.01      # o Word pode desenhar o texto até 1% mais largo
OPACIDADE_TOTAL = 0.999


class PlanoInviavel(Exception):
    """A página não cabe numa tabela do Word (ex.: mais de 63 colunas)."""


@dataclass
class _Uso:
    """Trechos de um segmento já representados como borda de célula."""

    segmento: Segmento
    cobertos: list[tuple[float, float]] = field(default_factory=list)

    def sobras(self, tolerancia: float) -> list[Segmento]:
        """Partes do traço que nenhuma borda cobre. Lascas menores que a tolerância
        mais a espessura (cantos, já cobertos pela borda perpendicular) são ignoradas."""
        s = self.segmento
        minimo = tolerancia + s.espessura
        inicio, fim = (s.x0, s.x1) if s.horizontal else (s.y0, s.y1)
        livres, cursor = [], inicio
        for a, b in sorted(self.cobertos):
            if a - cursor > minimo:
                livres.append((cursor, a))
            cursor = max(cursor, b)
        if fim - cursor > minimo:
            livres.append((cursor, fim))
        if s.horizontal:
            return [replace(s, x0=a, x1=b) for a, b in livres]
        return [replace(s, y0=a, y1=b) for a, b in livres]


class MotorTabela:
    nome = "tabela"

    def __init__(self, config: Config):
        self.config = config

    def planejar(self, documento: Documento, ajustes: Ajustes) -> PlanoDocumento:
        return PlanoDocumento(self.nome, [self._pagina(p, ajustes) for p in documento.paginas])

    # ------------------------------------------------------------------ página

    def _pagina(self, pagina: Pagina, ajustes: Ajustes) -> PlanoPagina:
        # Bordas de célula não têm transparência: traços translúcidos viram formas.
        opacos = [s for s in pagina.segmentos if s.opacidade >= OPACIDADE_TOTAL]
        horizontais = [s for s in opacos if s.horizontal]
        verticais = [s for s in opacos if s.vertical]
        usos = [_Uso(s) for s in horizontais + verticais]
        uso_de = {id(u.segmento): u for u in usos}

        cortes_y = self._cortes_y(pagina, horizontais, verticais)
        # As linhas verticais mandam na posição das colunas: o Word centraliza a
        # borda vertical na divisa entre células.
        ajustar_x = _agrupador([s.x0 for s in verticais],
                               [x for s in horizontais for x in (s.x0, s.x1)] + [0, pagina.largura],
                               self.config.agrupamento_x_pt)

        # Cada texto vai para a linha que contém sua linha de base; o que estiver
        # fora (antes do 1º ou depois do último corte) fica na linha mais próxima.
        por_linha: list[list[Trecho]] = [[] for _ in cortes_y[1:]]
        for t in pagina.trechos:
            indice = bisect_left(cortes_y, t.base) - 1
            por_linha[max(0, min(len(por_linha) - 1, indice))].append(t)

        linhas: list[LinhaPlano] = []
        for (y0, y1), trechos in zip(zip(cortes_y, cortes_y[1:]), por_linha):
            # O Word só começa o conteúdo depois da borda inferior da linha anterior.
            borda_acima = max((c.borda_inferior.espessura for c in linhas[-1].celulas
                               if c.borda_inferior), default=0.0) if linhas else 0.0
            linhas.append(self._linha(y0, y1, borda_acima, trechos, horizontais, verticais,
                                      uso_de, ajustar_x, pagina.largura, ajustes))

        plano = PlanoPagina(pagina.largura, pagina.altura, linhas=linhas,
                            formas=list(pagina.formas), imagens=list(pagina.imagens))
        plano.segmentos = [sobra for u in usos for sobra in u.sobras(self.config.agrupamento_x_pt)]
        usados = {id(u.segmento) for u in usos}
        plano.segmentos += [s for s in pagina.segmentos if id(s) not in usados]
        if len(plano.colunas) - 1 > self.config.max_colunas_tabela:
            raise PlanoInviavel(f"página {pagina.numero} exigiria {len(plano.colunas) - 1} colunas")
        return plano

    # -------------------------------------------------------- cortes verticais

    def _cortes_y(self, pagina: Pagina, horizontais, verticais) -> list[float]:
        trechos = pagina.trechos
        candidatos = [_limite_da_borda(s) for s in horizontais]
        candidatos += [y for s in verticais for y in (s.y0, s.y1)]
        cortes = {y for y in candidatos if self._corte_permitido(y, trechos)}
        cortes |= self._cortes_entre_blocos(trechos, cortes)

        fim_conteudo = max([t.base + descida(t) + 1 for t in trechos] +
                           [y + 1 for y in cortes] + [1.0])
        fim = min(fim_conteudo, pagina.altura - ESPACO_FINAL_PT)
        cortes = {y for y in cortes if 0 < y < fim} | {0.0, fim}
        return _agrupar_valores(sorted(cortes), self.config.agrupamento_y_pt)

    def _corte_permitido(self, y: float, trechos: list[Trecho]) -> bool:
        """Um corte de linha atravessa a página inteira: não pode passar pelo meio de
        um texto, nem exigir que um texto suba mais que o limite para caber acima."""
        for t in trechos:
            if t.topo + 0.3 < y <= t.base + 0.05:
                return False
            if t.base < y < t.base + descida(t) and t.base + descida(t) - y > self.config.deslocamento_maximo_pt:
                return False
        return True

    @staticmethod
    def _cortes_entre_blocos(trechos: list[Trecho], existentes: set[float]) -> set[float]:
        """Cortes no meio dos vãos verticais entre blocos de texto (estrutura mais limpa)."""
        faixas = sorted((t.topo, t.base + descida(t)) for t in trechos)
        mescladas: list[list[float]] = []
        for topo, fundo in faixas:
            if mescladas and topo <= mescladas[-1][1]:
                mescladas[-1][1] = max(mescladas[-1][1], fundo)
            else:
                mescladas.append([topo, fundo])
        novos = set()
        for (_, fim_acima), (inicio_abaixo, _) in zip(mescladas, mescladas[1:]):
            vao_tem_corte = any(fim_acima <= y <= inicio_abaixo for y in existentes)
            if inicio_abaixo - fim_acima >= VAZIO_MINIMO_PT and not vao_tem_corte:
                novos.add((fim_acima + inicio_abaixo) / 2)
        return novos

    # ------------------------------------------------------------ uma linha

    def _linha(self, y0, y1, borda_acima, trechos, horizontais, verticais, uso_de, ajustar_x,
               largura, ajustes) -> LinhaPlano:
        tol = self.config.agrupamento_y_pt
        no_fundo = [s for s in horizontais if abs(_limite_da_borda(s) - y1) <= tol]
        atravessam = [s for s in verticais if s.y0 <= y0 + tol and s.y1 >= y1 - tol]

        cortes_x = {0.0, largura} | {ajustar_x(x) for s in no_fundo for x in (s.x0, s.x1)}
        cortes_x |= {ajustar_x(s.x0) for s in atravessam}
        cortes_x = sorted(x for x in cortes_x if 0 <= x <= largura)

        grupos = self._celulas_com_texto(cortes_x, trechos)
        celulas = []
        for x0, x1, do_grupo in grupos:
            celula = CelulaPlano(x0, x1)
            self._preencher(celula, do_grupo, y0 + borda_acima, y1, ajustes)
            tol_x = self.config.agrupamento_x_pt
            celula.borda_inferior = _borda_horizontal(no_fundo, x0, x1, tol_x, uso_de)
            celula.borda_esquerda = _borda_vertical(atravessam, x0, y0, y1, tol_x, uso_de)
            celula.borda_direita = _borda_vertical(atravessam, x1, y0, y1, tol_x, uso_de)
            celulas.append(celula)
        return LinhaPlano(y0, y1, celulas)

    def _celulas_com_texto(self, cortes_x: list[float], trechos: list[Trecho]):
        """Distribui os trechos pelas células; funde células quando um texto não cabe."""
        folga = self.config.folga_ancoragem_pt
        n = len(cortes_x) - 1
        fim_do_grupo = list(range(1, n + 1))   # índice do corte final de cada célula
        dono: dict[int, int] = {}
        for t in trechos:
            i = next((k for k in range(n) if cortes_x[k + 1] > t.x0 + folga), n - 1)
            # O Word corta (não quebra) texto que encosta na borda direita da célula;
            # exige uma folga proporcional à largura do texto.
            fim_texto = t.x1 + folga + MARGEM_LARGURA * (t.x1 - t.x0)
            j = i
            while j < n - 1 and fim_texto > cortes_x[j + 1]:
                j += 1
            dono[t.id] = i
            fim_do_grupo[i] = max(fim_do_grupo[i], j + 1)

        grupos, i = [], 0
        while i < n:
            fim = fim_do_grupo[i]
            k = i
            while k < fim:            # uma fusão pode arrastar outras
                fim = max(fim, fim_do_grupo[k])
                k += 1
            membros = [t for t in trechos if i <= dono[t.id] < fim]
            grupos.append((cortes_x[i], cortes_x[fim], membros))
            i = fim
        return grupos

    def _preencher(self, celula: CelulaPlano, trechos: list[Trecho], y0: float, y1: float,
                   ajustes: Ajustes) -> None:
        linhas = agrupar_linhas(trechos)
        celula.paragrafos = [montar_paragrafo(linha, celula.x0, ajustes, self.config) for linha in linhas]
        descidas = [max(descida(t) for t in linha) for linha in linhas]
        empilhar(celula.paragrafos, descidas, y0, y1)


# ------------------------------------------------------------------ bordas

def _borda_horizontal(segmentos, x0, x1, tolerancia, uso_de) -> Borda | None:
    """Borda inferior se os traços cobrem a célula inteira (a menos da tolerância)."""
    cobrindo = [s for s in segmentos if s.x0 < x1 and s.x1 > x0]
    if not cobrindo or _cobertura(((s.x0, s.x1) for s in cobrindo), x0, x1) < (x1 - x0) - 2 * tolerancia:
        return None
    for s in cobrindo:
        uso_de[id(s)].cobertos.append((max(s.x0, x0), min(s.x1, x1)))
    referencia = max(cobrindo, key=lambda s: min(s.x1, x1) - max(s.x0, x0))
    return Borda(referencia.espessura, referencia.cor, referencia.tracejado)


def _borda_vertical(segmentos, x, y0, y1, tolerancia, uso_de) -> Borda | None:
    """Borda lateral se uma linha vertical (que já atravessa a linha da tabela) passa em x."""
    for s in segmentos:
        if abs(s.x0 - x) <= tolerancia:
            uso_de[id(s)].cobertos.append((y0, y1))
            return Borda(s.espessura, s.cor, s.tracejado)
    return None


def _cobertura(intervalos, inicio: float, fim: float) -> float:
    total, cursor = 0.0, inicio
    for a, b in sorted(intervalos):
        a, b = max(a, cursor), min(b, fim)
        if b > a:
            total += b - a
            cursor = b
    return total


# ------------------------------------------------------------- agrupamento

def _agrupar_valores(valores: list[float], tolerancia: float) -> list[float]:
    """Valores ordenados mais próximos que `tolerancia` viram um só (o primeiro)."""
    resultado: list[float] = []
    for v in valores:
        if not resultado or v - resultado[-1] > tolerancia:
            resultado.append(v)
    return resultado


def _limite_da_borda(segmento: Segmento) -> float:
    """O Word desenha a borda inferior da célula *abaixo* do limite (de y a y+espessura).
    Para a borda ficar centrada no traço original, o limite sobe meia espessura."""
    return segmento.y0 - segmento.espessura / 2


def _agrupador(prioritarios: list[float], demais: list[float], tolerancia: float):
    """Função que leva cada coordenada x ao representante do seu grupo.

    Valores `prioritarios` viram representantes; os `demais` só criam um grupo
    novo se estiverem longe de todos eles.
    """
    representantes = _agrupar_valores(sorted(set(prioritarios)), tolerancia)
    for valor in sorted(set(demais)):
        if all(abs(valor - r) > tolerancia for r in representantes):
            representantes.append(valor)
    representantes = _agrupar_valores(sorted(representantes), tolerancia)

    def ajustar(x: float) -> float:
        return min(representantes, key=lambda r: abs(r - x))
    return ajustar
