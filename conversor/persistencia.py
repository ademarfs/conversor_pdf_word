"""Persistência em SQLite: histórico, calibração aprendida e perfis de layout.

Tabelas (ver docs/ARQUITETURA.md):
- conversoes: uma linha por conversão, com métricas, ajustes usados e caminhos.
- tentativas: cada iteração de cada motor (auditoria do processo).
- calibracao_fontes: desvio sistemático do Word por fonte/tamanho, aprendido e
  reaplicado nas conversões seguintes.
- perfis_layout: para cada "tipo" de documento (gerador + fontes + formato),
  o motor que deu certo, para tentá-lo primeiro da próxima vez.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

VERSAO_ESQUEMA = 1

ESQUEMA = """
CREATE TABLE IF NOT EXISTS esquema (versao INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS conversoes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em         TEXT NOT NULL,
    nome_original     TEXT NOT NULL,
    sha256            TEXT NOT NULL,
    versao_conversor  TEXT NOT NULL,
    caminho_pdf       TEXT NOT NULL,
    paginas           INTEGER,
    status            TEXT NOT NULL,
    motor             TEXT,
    iteracoes         INTEGER,
    texto_identico    INTEGER,
    desvio_maximo_pt  REAL,
    desvio_medio_pt   REAL,
    pixels_maximo_pct REAL,
    relatorio_json    TEXT,
    ajustes_json      TEXT,
    avisos_json       TEXT,
    caminho_docx      TEXT,
    previas_json      TEXT,
    duracao_s         REAL,
    mensagem_erro     TEXT
);
CREATE INDEX IF NOT EXISTS ix_conversoes_sha ON conversoes (sha256, versao_conversor);

CREATE TABLE IF NOT EXISTS tentativas (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    conversao_id      INTEGER NOT NULL REFERENCES conversoes (id) ON DELETE CASCADE,
    motor             TEXT NOT NULL,
    iteracao          INTEGER NOT NULL,
    aprovado          INTEGER NOT NULL,
    texto_identico    INTEGER NOT NULL,
    desvio_maximo_pt  REAL,
    pixels_maximo_pct REAL,
    duracao_s         REAL
);

CREATE TABLE IF NOT EXISTS calibracao_fontes (
    motor         TEXT NOT NULL,
    chave         TEXT NOT NULL,
    dx            REAL NOT NULL,
    dy            REAL NOT NULL,
    amostras      INTEGER NOT NULL DEFAULT 1,
    atualizado_em TEXT NOT NULL,
    PRIMARY KEY (motor, chave)
);

CREATE TABLE IF NOT EXISTS perfis_layout (
    assinatura      TEXT PRIMARY KEY,
    motor_preferido TEXT NOT NULL,
    conversoes      INTEGER NOT NULL DEFAULT 0,
    aprovadas       INTEGER NOT NULL DEFAULT 0,
    atualizado_em   TEXT NOT NULL
);
"""


class Status:
    PROCESSANDO = "processando"
    APROVADO = "aprovado"
    SEM_VERIFICACAO_VISUAL = "aprovado_sem_word"
    COM_DIFERENCAS = "com_diferencas"
    ERRO = "erro"


@dataclass
class RegistroConversao:
    id: int
    criado_em: str
    nome_original: str
    sha256: str
    caminho_pdf: str
    status: str
    paginas: int | None
    motor: str | None
    iteracoes: int | None
    texto_identico: bool | None
    desvio_maximo_pt: float | None
    desvio_medio_pt: float | None
    pixels_maximo_pct: float | None
    relatorio: dict
    ajustes: dict
    avisos: list[str]
    caminho_docx: str | None
    previas: list[list[str]]
    duracao_s: float | None
    mensagem_erro: str | None

    @property
    def docx_disponivel(self) -> bool:
        return bool(self.caminho_docx) and Path(self.caminho_docx).exists()


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Repositorio:
    def __init__(self, banco: Path):
        self.banco = banco
        with self._conexao() as con:
            con.executescript(ESQUEMA)
            if con.execute("SELECT COUNT(*) FROM esquema").fetchone()[0] == 0:
                con.execute("INSERT INTO esquema (versao) VALUES (?)", (VERSAO_ESQUEMA,))

    @contextmanager
    def _conexao(self):
        con = sqlite3.connect(self.banco, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------ conversões

    def iniciar_conversao(self, nome_original: str, sha256: str, versao: str, caminho_pdf: Path) -> int:
        with self._conexao() as con:
            cursor = con.execute(
                "INSERT INTO conversoes (criado_em, nome_original, sha256, versao_conversor, "
                "caminho_pdf, status) VALUES (?, ?, ?, ?, ?, ?)",
                (_agora(), nome_original, sha256, versao, str(caminho_pdf), Status.PROCESSANDO),
            )
            return cursor.lastrowid

    def finalizar_conversao(self, conversao_id: int, **campos) -> None:
        """Atualiza a conversão; listas/dicionários são gravados como JSON."""
        colunas = {"relatorio": "relatorio_json", "ajustes": "ajustes_json",
                   "avisos": "avisos_json", "previas": "previas_json"}
        valores = {}
        for nome, valor in campos.items():
            if nome in colunas:
                valores[colunas[nome]] = json.dumps(valor, ensure_ascii=False)
            elif isinstance(valor, Path):
                valores[nome] = str(valor)
            else:
                valores[nome] = valor
        atribuicoes = ", ".join(f"{c} = ?" for c in valores)
        with self._conexao() as con:
            con.execute(f"UPDATE conversoes SET {atribuicoes} WHERE id = ?",
                        (*valores.values(), conversao_id))

    def registrar_tentativa(self, conversao_id: int, motor: str, iteracao: int, aprovado: bool,
                            texto_identico: bool, desvio_maximo: float, pixels_maximo: float,
                            duracao: float) -> None:
        with self._conexao() as con:
            con.execute(
                "INSERT INTO tentativas (conversao_id, motor, iteracao, aprovado, texto_identico, "
                "desvio_maximo_pt, pixels_maximo_pct, duracao_s) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (conversao_id, motor, iteracao, int(aprovado), int(texto_identico),
                 desvio_maximo, pixels_maximo, duracao),
            )

    def obter(self, conversao_id: int) -> RegistroConversao | None:
        with self._conexao() as con:
            linha = con.execute("SELECT * FROM conversoes WHERE id = ?", (conversao_id,)).fetchone()
        return _registro(linha) if linha else None

    def listar(self, limite: int = 100) -> list[RegistroConversao]:
        with self._conexao() as con:
            linhas = con.execute("SELECT * FROM conversoes ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [_registro(linha) for linha in linhas]

    def tentativas(self, conversao_id: int) -> list[sqlite3.Row]:
        with self._conexao() as con:
            return con.execute("SELECT * FROM tentativas WHERE conversao_id = ? ORDER BY id",
                               (conversao_id,)).fetchall()

    def buscar_reaproveitavel(self, sha256: str, versao: str, motor: str | None) -> RegistroConversao | None:
        """Conversão aprovada do mesmo arquivo, mesma versão do conversor (e motor, se pedido)."""
        sql = ("SELECT * FROM conversoes WHERE sha256 = ? AND versao_conversor = ? "
               "AND status IN (?, ?)")
        parametros: list = [sha256, versao, Status.APROVADO, Status.SEM_VERIFICACAO_VISUAL]
        if motor:
            sql += " AND motor = ?"
            parametros.append(motor)
        with self._conexao() as con:
            for linha in con.execute(sql + " ORDER BY id DESC", parametros).fetchall():
                registro = _registro(linha)
                if registro.docx_disponivel:
                    return registro
        return None

    def ajustes_anteriores(self, sha256: str, versao: str, motor: str) -> dict:
        """Ajustes por palavra da última conversão deste arquivo com este motor (aprovadas primeiro)."""
        with self._conexao() as con:
            linha = con.execute(
                "SELECT ajustes_json FROM conversoes WHERE sha256 = ? AND versao_conversor = ? "
                "AND motor = ? AND ajustes_json IS NOT NULL "
                "ORDER BY (status = ?) DESC, id DESC LIMIT 1",
                (sha256, versao, motor, Status.APROVADO),
            ).fetchone()
        return json.loads(linha["ajustes_json"]) if linha else {}

    def expiradas(self, dias: int) -> list[RegistroConversao]:
        limite = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
        with self._conexao() as con:
            linhas = con.execute("SELECT * FROM conversoes WHERE criado_em < ? AND caminho_docx IS NOT NULL",
                                 (limite,)).fetchall()
        return [_registro(linha) for linha in linhas]

    # ------------------------------------------------------------ calibração

    def calibracao(self, motor: str) -> dict[str, tuple[float, float]]:
        with self._conexao() as con:
            linhas = con.execute("SELECT chave, dx, dy FROM calibracao_fontes WHERE motor = ?",
                                 (motor,)).fetchall()
        return {linha["chave"]: (linha["dx"], linha["dy"]) for linha in linhas}

    def salvar_calibracao(self, motor: str, por_fonte: dict[str, tuple[float, float]]) -> None:
        with self._conexao() as con:
            for chave, (dx, dy) in por_fonte.items():
                con.execute(
                    "INSERT INTO calibracao_fontes (motor, chave, dx, dy, amostras, atualizado_em) "
                    "VALUES (?, ?, ?, ?, 1, ?) ON CONFLICT (motor, chave) DO UPDATE SET "
                    "dx = excluded.dx, dy = excluded.dy, amostras = amostras + 1, "
                    "atualizado_em = excluded.atualizado_em",
                    (motor, chave, dx, dy, _agora()),
                )

    # ------------------------------------------------------- perfis de layout

    def motor_preferido(self, assinatura: str) -> str | None:
        with self._conexao() as con:
            linha = con.execute("SELECT motor_preferido FROM perfis_layout WHERE assinatura = ?",
                                (assinatura,)).fetchone()
        return linha["motor_preferido"] if linha else None

    def atualizar_perfil(self, assinatura: str, motor: str, aprovado: bool) -> None:
        with self._conexao() as con:
            con.execute(
                "INSERT INTO perfis_layout (assinatura, motor_preferido, conversoes, aprovadas, "
                "atualizado_em) VALUES (?, ?, 1, ?, ?) ON CONFLICT (assinatura) DO UPDATE SET "
                "motor_preferido = CASE WHEN ? THEN excluded.motor_preferido ELSE motor_preferido END, "
                "conversoes = conversoes + 1, aprovadas = aprovadas + excluded.aprovadas, "
                "atualizado_em = excluded.atualizado_em",
                (assinatura, motor, int(aprovado), _agora(), int(aprovado)),
            )


def _registro(linha: sqlite3.Row) -> RegistroConversao:
    def json_ou(coluna, padrao):
        return json.loads(linha[coluna]) if linha[coluna] else padrao

    return RegistroConversao(
        id=linha["id"], criado_em=linha["criado_em"], nome_original=linha["nome_original"],
        sha256=linha["sha256"], caminho_pdf=linha["caminho_pdf"], status=linha["status"],
        paginas=linha["paginas"], motor=linha["motor"], iteracoes=linha["iteracoes"],
        texto_identico=None if linha["texto_identico"] is None else bool(linha["texto_identico"]),
        desvio_maximo_pt=linha["desvio_maximo_pt"], desvio_medio_pt=linha["desvio_medio_pt"],
        pixels_maximo_pct=linha["pixels_maximo_pct"],
        relatorio=json_ou("relatorio_json", {}), ajustes=json_ou("ajustes_json", {}),
        avisos=json_ou("avisos_json", []), caminho_docx=linha["caminho_docx"],
        previas=json_ou("previas_json", []), duracao_s=linha["duracao_s"],
        mensagem_erro=linha["mensagem_erro"],
    )
