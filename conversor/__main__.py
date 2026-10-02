"""Linha de comando.

    python -m conversor arquivo.pdf [outro.pdf ...] [--saida PASTA] [--motor tabela|absoluto] [--forcar]
    python -m conversor --diagnostico
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import VERSAO
from .config import carregar_config
from .fontes import fontes_instaladas
from .persistencia import Repositorio
from .registro import configurar_logs
from .servico import MOTORES, ServicoConversao
from .word import word_disponivel


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conversor",
                                     description="Converte PDF em Word com verificação de fidelidade.")
    parser.add_argument("pdfs", nargs="*", type=Path, help="arquivos PDF")
    parser.add_argument("--saida", type=Path, help="pasta de destino (padrão: a pasta de cada PDF)")
    parser.add_argument("--motor", choices=sorted(MOTORES), help="força um motor (padrão: automático)")
    parser.add_argument("--forcar", action="store_true", help="refaz mesmo se o arquivo já foi convertido")
    parser.add_argument("--diagnostico", action="store_true", help="verifica o ambiente e sai")
    args = parser.parse_args(argumentos)

    if args.diagnostico:
        return _diagnostico()
    if not args.pdfs:
        parser.print_help()
        return 2

    config = carregar_config()
    configurar_logs(config)
    servico = ServicoConversao(config, Repositorio(config.banco))
    falhas = 0
    for pdf in args.pdfs:
        resultado = servico.converter(pdf.resolve(), pdf.name, motor=args.motor, forcar=args.forcar)
        if resultado.docx:
            destino = (args.saida or pdf.parent) / resultado.docx.name
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resultado.docx, destino)
            print(f"{pdf.name}: {resultado.status} (motor {resultado.motor}) -> {destino}")
        else:
            print(f"{pdf.name}: {resultado.status}")
        for aviso in resultado.avisos:
            print(f"  aviso: {aviso}")
        falhas += not resultado.aprovado
    return 1 if falhas else 0


def _diagnostico() -> int:
    print(f"Conversor PDF->Word {VERSAO}")
    print(f"Python {sys.version.split()[0]}")
    word = word_disponivel()
    print(f"Microsoft Word: {'OK' if word else 'NÃO ENCONTRADO (só verificação de texto)'}")
    print(f"Fontes instaladas: {len(fontes_instaladas())}")
    config = carregar_config()
    print(f"Pasta de dados: {config.pasta_dados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
