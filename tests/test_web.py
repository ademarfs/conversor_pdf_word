import io

import pytest

from conversor.web.app import criar_app


@pytest.fixture
def cliente(config):
    app = criar_app(config)
    app.config["TESTING"] = True
    return app.test_client()


LOCAL = {"base_url": "http://127.0.0.1:8765"}


def test_pagina_inicial(cliente):
    resposta = cliente.get("/", **LOCAL)
    assert resposta.status_code == 200
    assert "Converter PDF em Word" in resposta.get_data(as_text=True)


def test_recusa_requisicao_que_nao_e_local(cliente):
    assert cliente.get("/", base_url="http://exemplo.com").status_code == 403


def test_recusa_arquivo_que_nao_e_pdf(cliente, config):
    dados = {"pdf": (io.BytesIO(b"nao sou pdf"), "falso.pdf")}
    resposta = cliente.post("/converter", data=dados, content_type="multipart/form-data",
                            follow_redirects=True, **LOCAL)
    assert "não é um PDF" in resposta.get_data(as_text=True)
    assert not list(config.pasta_entrada.iterdir())


def test_resultado_inexistente(cliente):
    assert cliente.get("/resultado/999", **LOCAL).status_code == 404
