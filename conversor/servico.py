"""Orquestra a conversão: extrai, gera, verifica, recalibra, escolhe o melhor e persiste.

Fluxo (docs/ALGORITMO.md):
1. Extrai o PDF e calcula o SHA-256.
2. Se o mesmo arquivo já foi aprovado nesta versão do conversor, reaproveita.
3. Escolhe a ordem dos motores (preferência do perfil de layout, se houver).
4. Para cada motor: gera o .docx com a calibração aprendida, pede ao Word para
   renderizar, compara com o original e, se não aprovar, recalibra e tenta de novo.
5. Fica com a melhor tentativa, gera prévias, grava tudo no banco.
"""
from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import VERSAO
from .calibracao import Ajustes, recalibrar
from .config import Config
from .erros import ErroConversao
from .extracao import extrair
from .gerador.escritor import EscritorDocx
from .layout.absoluto import MotorAbsoluto
from .layout.grade import MotorTabela, PlanoInviavel
from .modelo import Documento
from .persistencia import RegistroConversao, Repositorio, Status
from .verificacao import Relatorio, gerar_previas, verificar, verificar_somente_texto
from .word import docx_para_pdf, word_disponivel

log = logging.getLogger(__name__)

MOTORES = {MotorTabela.nome: MotorTabela, MotorAbsoluto.nome: MotorAbsoluto}
ORDEM_PADRAO = [MotorTabela.nome, MotorAbsoluto.nome]   # tabela é mais editável; absoluto, mais fiel


@dataclass
class Tentativa:
    motor: str
    iteracao: int
    docx: Path
    pdf: Path | None
    relatorio: Relatorio
    ajustes: Ajustes            # usados para gerar esta tentativa
    aprendidos: Ajustes         # corrigidos a partir do que foi medido nela
    duracao: float


@dataclass
class Resultado:
    conversao_id: int
    status: str
    docx: Path | None
    motor: str | None = None
    relatorio: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    reaproveitado: bool = False

    @property
    def aprovado(self) -> bool:
        return self.status in (Status.APROVADO, Status.SEM_VERIFICACAO_VISUAL)


class ServicoConversao:
    def __init__(self, config: Config, repositorio: Repositorio, usar_word: bool | None = None):
        self.config = config
        self.repositorio = repositorio
        self.usar_word = word_disponivel() if usar_word is None else usar_word

    def converter(self, pdf: Path, nome_original: str, motor: str | None = None,
                  forcar: bool = False, temporario: bool = False) -> Resultado:
        """Converte `pdf` e devolve o resultado. Erros esperados viram status 'erro'.

        `temporario=True` indica um arquivo recebido por upload, que pode ser movido para
        o arquivo de entradas; qualquer outro é apenas copiado (o original não é tocado).
        """
        if motor and motor not in MOTORES:
            raise ValueError(f"Motor desconhecido: {motor}")
        inicio = time.monotonic()
        try:
            documento = extrair(pdf)
        except ErroConversao as erro:
            conversao_id = self.repositorio.iniciar_conversao(nome_original, "", VERSAO, pdf)
            self.repositorio.finalizar_conversao(conversao_id, status=Status.ERRO, mensagem_erro=str(erro))
            return Resultado(conversao_id, Status.ERRO, None, avisos=[str(erro)])

        if not forcar:
            anterior = self.repositorio.buscar_reaproveitavel(documento.sha256, VERSAO, motor)
            if anterior:
                log.info("Reaproveitando conversão %s (mesmo arquivo)", anterior.id)
                return _resultado_do_registro(anterior, reaproveitado=True)

        conversao_id = self.repositorio.iniciar_conversao(nome_original, documento.sha256, VERSAO, pdf)
        try:
            documento.caminho = str(self._arquivar_entrada(conversao_id, pdf, temporario))
            return self._executar(conversao_id, documento, nome_original, motor, inicio)
        except Exception as erro:
            log.exception("Falha na conversão %s", conversao_id)
            self.repositorio.finalizar_conversao(conversao_id, status=Status.ERRO,
                                                 mensagem_erro=f"{type(erro).__name__}: {erro}")
            return Resultado(conversao_id, Status.ERRO, None, avisos=[f"Erro inesperado: {erro}"])

    # ----------------------------------------------------------------- etapas

    def _arquivar_entrada(self, conversao_id: int, pdf: Path, temporario: bool) -> Path:
        """Guarda uma cópia própria do PDF (o original do usuário nunca é tocado)."""
        destino = self.config.pasta_entrada / f"{conversao_id}.pdf"
        if temporario:
            pdf.replace(destino)
        else:
            shutil.copyfile(pdf, destino)
        self.repositorio.finalizar_conversao(conversao_id, caminho_pdf=destino)
        return destino

    def _executar(self, conversao_id: int, documento: Documento, nome_original: str,
                  motor: str | None, inicio: float) -> Resultado:
        trabalho = self.config.pasta_trabalho / str(conversao_id)
        trabalho.mkdir(parents=True, exist_ok=True)
        avisos = list(documento.avisos)
        if not self.usar_word:
            avisos.append("Microsoft Word não encontrado: foi verificado apenas o texto, "
                          "sem a comparação visual.")

        tentativas = []
        for nome in self._ordem_motores(documento, motor):
            tentativas += self._tentar_motor(conversao_id, nome, documento, trabalho, avisos)
            if tentativas and _melhor(tentativas).relatorio.aprovado(self.config):
                break
        if not tentativas:
            raise ErroConversao("Nenhum motor conseguiu montar o documento.")

        melhor = _melhor(tentativas)
        destino = self._publicar(conversao_id, melhor, nome_original)
        status = self._status(melhor.relatorio)
        self.repositorio.atualizar_perfil(documento.assinatura_layout, melhor.motor,
                                          status == Status.APROVADO)
        self.repositorio.finalizar_conversao(
            conversao_id, status=status, paginas=len(documento.paginas), motor=melhor.motor,
            iteracoes=len(tentativas), texto_identico=int(melhor.relatorio.texto_identico),
            desvio_maximo_pt=round(melhor.relatorio.desvio_maximo, 3),
            desvio_medio_pt=round(melhor.relatorio.desvio_medio, 3),
            pixels_maximo_pct=round(melhor.relatorio.pixels_maximo, 3),
            relatorio=melhor.relatorio.resumo(), ajustes=melhor.ajustes.para_json(),
            avisos=avisos, caminho_docx=destino, duracao_s=round(time.monotonic() - inicio, 1),
            previas=self._previas(conversao_id, documento, melhor),
        )
        if not self.config.manter_arquivos_trabalho:
            shutil.rmtree(trabalho, ignore_errors=True)
        return Resultado(conversao_id, status, destino, melhor.motor, melhor.relatorio.resumo(), avisos)

    def _ordem_motores(self, documento: Documento, motor: str | None) -> list[str]:
        if motor:
            return [motor]
        preferido = self.repositorio.motor_preferido(documento.assinatura_layout)
        if preferido in MOTORES:
            return [preferido] + [m for m in ORDEM_PADRAO if m != preferido]
        return list(ORDEM_PADRAO)

    def _tentar_motor(self, conversao_id: int, nome: str, documento: Documento, trabalho: Path,
                      avisos: list[str]) -> list[Tentativa]:
        motor = MOTORES[nome](self.config)
        # Parte do que já foi aprendido: calibração da fonte (todas as conversões) e,
        # se este mesmo arquivo já passou por aqui, os ajustes por palavra daquela vez.
        ajustes = Ajustes(por_fonte=self.repositorio.calibracao(nome))
        ajustes.carregar_json(self.repositorio.ajustes_anteriores(documento.sha256, VERSAO, nome))
        tentativas: list[Tentativa] = []
        for iteracao in range(1, self.config.max_iteracoes + 1):
            inicio = time.monotonic()
            try:
                plano = motor.planejar(documento, ajustes)
            except PlanoInviavel as motivo:
                avisos.append(f"Motor '{nome}' não aplicável a este PDF ({motivo}).")
                break
            docx = trabalho / f"{nome}_{iteracao}.docx"
            EscritorDocx().salvar(plano, docx, titulo=Path(documento.caminho).stem)
            pdf, relatorio = self._verificar(documento, docx)
            aprendidos = recalibrar(ajustes, relatorio.desvios, plano.trechos_deslocados)
            tentativa = Tentativa(nome, iteracao, docx, pdf, relatorio, ajustes, aprendidos,
                                  time.monotonic() - inicio)
            tentativas.append(tentativa)
            self._registrar(conversao_id, tentativa)
            if relatorio.aprovado(self.config) or not self.usar_word:
                break
            ajustes = aprendidos

        if tentativas and self.usar_word:
            # O desvio por fonte medido na melhor tentativa vale para os próximos documentos.
            self.repositorio.salvar_calibracao(nome, _melhor(tentativas).aprendidos.por_fonte)
        return tentativas

    def _verificar(self, documento: Documento, docx: Path) -> tuple[Path | None, Relatorio]:
        if not self.usar_word:
            return None, verificar_somente_texto(documento, docx)
        pdf = docx.with_suffix(".pdf")
        docx_para_pdf(docx, pdf)
        return pdf, verificar(documento, pdf)

    def _registrar(self, conversao_id: int, t: Tentativa) -> None:
        r = t.relatorio
        log.info("Conversão %s | %s #%s | texto=%s desvio=%.2fpt pixels=%.2f%% | %.1fs",
                 conversao_id, t.motor, t.iteracao, r.texto_identico, r.desvio_maximo,
                 r.pixels_maximo, t.duracao)
        self.repositorio.registrar_tentativa(conversao_id, t.motor, t.iteracao, r.aprovado(self.config),
                                             r.texto_identico, r.desvio_maximo, r.pixels_maximo,
                                             t.duracao)

    def _publicar(self, conversao_id: int, melhor: Tentativa, nome_original: str) -> Path:
        pasta = self.config.pasta_saida / str(conversao_id)
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"{Path(nome_original).stem}.docx"
        shutil.copyfile(melhor.docx, destino)
        return destino

    def _previas(self, conversao_id: int, documento: Documento, melhor: Tentativa) -> list:
        if melhor.pdf is None:
            return []
        pasta = self.config.pasta_saida / str(conversao_id) / "previas"
        return [list(par) for par in gerar_previas(Path(documento.caminho), melhor.pdf, pasta)]

    def _status(self, relatorio: Relatorio) -> str:
        if not relatorio.aprovado(self.config):
            return Status.COM_DIFERENCAS
        return Status.APROVADO if relatorio.visual_verificado else Status.SEM_VERIFICACAO_VISUAL

    # ------------------------------------------------------------- manutenção

    def limpar_expiradas(self) -> int:
        """Apaga arquivos de conversões mais antigas que `dias_retencao` (o histórico fica)."""
        removidas = 0
        for registro in self.repositorio.expiradas(self.config.dias_retencao):
            shutil.rmtree(self.config.pasta_saida / str(registro.id), ignore_errors=True)
            entrada = Path(registro.caminho_pdf)
            if _dentro_de(entrada, self.config.pasta_entrada):  # nunca apaga fora de dados/
                entrada.unlink(missing_ok=True)
            self.repositorio.finalizar_conversao(registro.id, caminho_docx=None)
            removidas += 1
        return removidas


def _dentro_de(caminho: Path, pasta: Path) -> bool:
    return caminho.resolve().is_relative_to(pasta.resolve())


def _melhor(tentativas: list[Tentativa]) -> Tentativa:
    return max(tentativas, key=lambda t: t.relatorio.pontuacao())


def _resultado_do_registro(registro: RegistroConversao, reaproveitado: bool) -> Resultado:
    return Resultado(registro.id, registro.status, Path(registro.caminho_docx), registro.motor,
                     registro.relatorio, registro.avisos, reaproveitado)
