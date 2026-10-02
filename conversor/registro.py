"""Configuração de logs: console + arquivo rotativo em dados/logs/conversor.log."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import Config

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configurar_logs(config: Config, nivel: int = logging.INFO) -> None:
    raiz = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in raiz.handlers):
        return  # já configurado
    raiz.setLevel(nivel)
    arquivo = RotatingFileHandler(config.pasta_logs / "conversor.log", maxBytes=2_000_000,
                                  backupCount=5, encoding="utf-8")
    arquivo.setFormatter(logging.Formatter(FORMATO))
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMATO))
    raiz.addHandler(arquivo)
    raiz.addHandler(console)
