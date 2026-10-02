"""Configuração central do conversor.

Os valores padrão podem ser sobrescritos por um arquivo `config.json` na raiz do
projeto (mesmas chaves dos campos abaixo). Ver docs/ARQUITETURA.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

# Medido no Word (docs/ALGORITMO.md, seção "Calibração"): com espaçamento de
# linha "Exatamente L", o Word desenha a linha de base a 0,8·L do topo da linha.
FATOR_BASE_WORD = 0.8


@dataclass
class Config:
    pasta_dados: Path = RAIZ_PROJETO / "dados"
    porta: int = 8765
    host: str = "127.0.0.1"
    tamanho_maximo_mb: int = 50

    # Aprovação da verificação
    tolerancia_posicao_pt: float = 1.0
    tolerancia_pixels_pct: float = 0.5   # fora das áreas de texto
    max_iteracoes: int = 4

    # Layout
    deslocamento_maximo_pt: float = 0.5  # quanto um texto pode subir para caber sobre um sublinhado
    agrupamento_x_pt: float = 1.0        # colunas mais estreitas que isso desalinham a tabela no Word
    agrupamento_y_pt: float = 0.6
    folga_ancoragem_pt: float = 1.0      # tolerância para decidir em que célula um texto começa
    lacuna_tabulacao_pt: float = 1.0     # distância mínima entre trechos para usar tabulação
    max_colunas_tabela: int = 63         # limite do Word

    # Manutenção
    dias_retencao: int = 30               # arquivos (PDF/Word) mais antigos são apagados; o histórico fica
    manter_arquivos_trabalho: bool = False  # guarda cada tentativa (útil para diagnóstico)

    @property
    def pasta_entrada(self) -> Path:
        return self.pasta_dados / "entrada"

    @property
    def pasta_saida(self) -> Path:
        return self.pasta_dados / "saida"

    @property
    def pasta_trabalho(self) -> Path:
        return self.pasta_dados / "trabalho"

    @property
    def pasta_logs(self) -> Path:
        return self.pasta_dados / "logs"

    @property
    def banco(self) -> Path:
        return self.pasta_dados / "conversor.db"

    def criar_pastas(self) -> None:
        for pasta in (self.pasta_entrada, self.pasta_saida, self.pasta_trabalho, self.pasta_logs):
            pasta.mkdir(parents=True, exist_ok=True)


def carregar_config(arquivo: Path | None = None) -> Config:
    """Carrega a configuração padrão, aplicando `config.json` se existir."""
    config = Config()
    arquivo = arquivo or RAIZ_PROJETO / "config.json"
    if arquivo.exists():
        valores = json.loads(arquivo.read_text(encoding="utf-8"))
        conhecidos = {f.name: f.type for f in fields(Config)}
        for chave, valor in valores.items():
            if chave not in conhecidos:
                raise ValueError(f"config.json: chave desconhecida '{chave}'")
            setattr(config, chave, Path(valor) if chave == "pasta_dados" else valor)
    config.criar_pastas()
    return config
