"""Interface web local: upload do PDF, conversão, resultado com prévias e histórico.

Executar:  python -m conversor.web      (abre o navegador em http://127.0.0.1:8765)
Atende apenas a própria máquina (127.0.0.1).
"""
from __future__ import annotations

import argparse
import logging
import socket
import threading
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from .. import VERSAO
from ..config import Config, carregar_config
from ..persistencia import Repositorio, Status
from ..registro import configurar_logs
from ..servico import MOTORES, ServicoConversao

log = logging.getLogger(__name__)

ASSINATURA_PDF = b"%PDF-"
ROTULOS_STATUS = {
    Status.APROVADO: "Idêntico ao original",
    Status.SEM_VERIFICACAO_VISUAL: "Texto idêntico (sem verificação visual)",
    Status.COM_DIFERENCAS: "Com diferenças",
    Status.ERRO: "Erro",
    Status.PROCESSANDO: "Processando",
}


def criar_app(config: Config) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.tamanho_maximo_mb * 1024 * 1024
    app.secret_key = uuid.uuid4().hex
    repositorio = Repositorio(config.banco)
    servico = ServicoConversao(config, repositorio)
    hosts_permitidos = {f"127.0.0.1:{config.porta}", f"localhost:{config.porta}"}

    @app.context_processor
    def contexto():
        return {"versao": VERSAO, "rotulos": ROTULOS_STATUS, "word": servico.usar_word}

    @app.before_request
    def somente_local():
        # Protege contra "DNS rebinding": só aceita requisições endereçadas à própria máquina.
        if request.host not in hosts_permitidos:
            abort(403)

    @app.get("/")
    def inicio():
        return render_template("inicio.html", conversoes=repositorio.listar(limite=10),
                               motores=sorted(MOTORES))

    @app.post("/converter")
    def converter():
        arquivo = request.files.get("pdf")
        if not arquivo or not arquivo.filename:
            flash("Selecione um arquivo PDF.")
            return redirect(url_for("inicio"))
        nome = secure_filename(arquivo.filename) or "documento.pdf"
        if not nome.lower().endswith(".pdf") or arquivo.stream.read(5) != ASSINATURA_PDF:
            flash("O arquivo enviado não é um PDF.")
            return redirect(url_for("inicio"))
        arquivo.stream.seek(0)
        recebido = config.pasta_entrada / f"upload_{uuid.uuid4().hex}.pdf"
        arquivo.save(recebido)

        motor = request.form.get("motor") or None
        resultado = servico.converter(recebido, arquivo.filename, motor=motor if motor in MOTORES else None,
                                      forcar=bool(request.form.get("forcar")), temporario=True)
        if resultado.reaproveitado:
            recebido.unlink(missing_ok=True)
            flash("Este arquivo já tinha sido convertido: resultado reaproveitado.")
        return redirect(url_for("resultado", conversao_id=resultado.conversao_id))

    @app.post("/reconverter/<int:conversao_id>")
    def reconverter(conversao_id: int):
        registro = repositorio.obter(conversao_id) or abort(404)
        if not Path(registro.caminho_pdf).exists():
            flash("O PDF original desta conversão já foi removido pela limpeza automática.")
            return redirect(url_for("resultado", conversao_id=conversao_id))
        motor = request.form.get("motor") or None
        resultado = servico.converter(Path(registro.caminho_pdf), registro.nome_original,
                                      motor=motor if motor in MOTORES else None, forcar=True)
        return redirect(url_for("resultado", conversao_id=resultado.conversao_id))

    @app.get("/resultado/<int:conversao_id>")
    def resultado(conversao_id: int):
        registro = repositorio.obter(conversao_id) or abort(404)
        return render_template("resultado.html", c=registro, motores=sorted(MOTORES),
                               tentativas=repositorio.tentativas(conversao_id))

    @app.get("/historico")
    def historico():
        return render_template("historico.html", conversoes=repositorio.listar(limite=500))

    @app.get("/baixar/<int:conversao_id>")
    def baixar(conversao_id: int):
        registro = repositorio.obter(conversao_id) or abort(404)
        if not registro.docx_disponivel:
            abort(404)
        nome = f"{Path(registro.nome_original).stem}.docx"
        return send_file(registro.caminho_docx, as_attachment=True, download_name=nome)

    @app.get("/previa/<int:conversao_id>/<nome>")
    def previa(conversao_id: int, nome: str):
        pasta = config.pasta_saida / str(conversao_id) / "previas"
        arquivo = pasta / secure_filename(nome)
        if not arquivo.exists():
            abort(404)
        return send_file(arquivo, mimetype="image/png")

    @app.errorhandler(413)
    def grande_demais(_):
        flash(f"Arquivo maior que o limite de {config.tamanho_maximo_mb} MB.")
        return redirect(url_for("inicio"))

    return app


def main() -> None:
    from waitress import serve

    parser = argparse.ArgumentParser(prog="conversor.web", description="Interface web do conversor.")
    parser.add_argument("--sem-navegador", action="store_true", help="não abre o navegador ao iniciar")
    args = parser.parse_args()

    config = carregar_config()
    configurar_logs(config)
    endereco = f"http://{config.host}:{config.porta}/"
    if _porta_em_uso(config.host, config.porta):
        # Já está rodando (ex.: atalho aberto duas vezes): só abre o navegador.
        log.info("O conversor já está em execução em %s", endereco)
        if not args.sem_navegador:
            webbrowser.open(endereco)
        return
    app = criar_app(config)
    removidas = ServicoConversao(config, Repositorio(config.banco), usar_word=False).limpar_expiradas()
    if removidas:
        log.info("Limpeza: arquivos de %s conversões antigas removidos", removidas)
    log.info("Conversor PDF->Word %s em %s (feche esta janela para encerrar)", VERSAO, endereco)
    if not args.sem_navegador:
        threading.Timer(1.5, webbrowser.open, args=(endereco,)).start()
    serve(app, host=config.host, port=config.porta, threads=4)


def _porta_em_uso(host: str, porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, porta)) == 0


if __name__ == "__main__":
    main()
