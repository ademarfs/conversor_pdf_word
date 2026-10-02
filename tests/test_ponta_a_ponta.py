"""Conversão completa com o Word real: gera, renderiza, compara e aprova."""
import os
from pathlib import Path

import pytest

from conversor.persistencia import Repositorio, Status
from conversor.servico import ServicoConversao

from .conftest import precisa_word

pytestmark = [pytest.mark.word, precisa_word]


@pytest.mark.parametrize("motor", ["tabela", "absoluto"])
def test_formulario_fica_identico_ao_original(pdf_formulario, config, motor):
    servico = ServicoConversao(config, Repositorio(config.banco))
    resultado = servico.converter(pdf_formulario, "formulario.pdf", motor=motor)
    assert resultado.status == Status.APROVADO, resultado.relatorio
    assert resultado.docx.exists()
    assert resultado.relatorio["texto_identico"]
    assert resultado.relatorio["desvio_maximo_pt"] <= config.tolerancia_posicao_pt


def test_texto_justificado_converge_com_ajuste_por_palavra(pdf_justificado, config):
    servico = ServicoConversao(config, Repositorio(config.banco))
    resultado = servico.converter(pdf_justificado, "justificado.pdf", motor="absoluto")
    assert resultado.status == Status.APROVADO, resultado.relatorio


def test_mesmo_arquivo_e_reaproveitado_e_original_nao_e_tocado(pdf_formulario, config):
    conteudo = pdf_formulario.read_bytes()
    servico = ServicoConversao(config, Repositorio(config.banco))
    primeiro = servico.converter(pdf_formulario, "formulario.pdf")
    segundo = servico.converter(pdf_formulario, "formulario.pdf")
    assert segundo.reaproveitado and segundo.conversao_id == primeiro.conversao_id
    assert pdf_formulario.read_bytes() == conteudo


EXEMPLOS = Path(os.environ.get("PASTA_EXEMPLOS", "")) if os.environ.get("PASTA_EXEMPLOS") else None


@pytest.mark.skipif(EXEMPLOS is None, reason="defina PASTA_EXEMPLOS com PDFs reais para este teste")
def test_pdfs_reais_da_pasta_de_exemplos(config):
    servico = ServicoConversao(config, Repositorio(config.banco))
    reprovados = []
    for pdf in sorted(EXEMPLOS.glob("*.pdf")):
        resultado = servico.converter(pdf, pdf.name)
        if not resultado.aprovado:
            reprovados.append((pdf.name, resultado.relatorio))
    assert not reprovados
