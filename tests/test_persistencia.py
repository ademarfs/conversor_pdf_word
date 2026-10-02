from pathlib import Path

from conversor.persistencia import Repositorio, Status


def test_conversao_aprovada_e_reaproveitada_pelo_hash(tmp_path):
    repo = Repositorio(tmp_path / "t.db")
    docx = tmp_path / "saida.docx"
    docx.write_bytes(b"x")
    cid = repo.iniciar_conversao("a.pdf", "abc", "1.0.0", tmp_path / "a.pdf")
    repo.finalizar_conversao(cid, status=Status.APROVADO, motor="tabela", caminho_docx=docx,
                             relatorio={"texto_identico": True}, avisos=["aviso"])

    encontrado = repo.buscar_reaproveitavel("abc", "1.0.0", None)
    assert encontrado.id == cid and encontrado.avisos == ["aviso"]
    assert repo.buscar_reaproveitavel("abc", "2.0.0", None) is None      # outra versão
    assert repo.buscar_reaproveitavel("abc", "1.0.0", "absoluto") is None  # outro motor


def test_conversao_sem_arquivo_nao_e_reaproveitada(tmp_path):
    repo = Repositorio(tmp_path / "t.db")
    cid = repo.iniciar_conversao("a.pdf", "abc", "1.0.0", tmp_path / "a.pdf")
    repo.finalizar_conversao(cid, status=Status.APROVADO, caminho_docx=Path(tmp_path / "sumiu.docx"))
    assert repo.buscar_reaproveitavel("abc", "1.0.0", None) is None


def test_calibracao_e_acumulada_por_motor(tmp_path):
    repo = Repositorio(tmp_path / "t.db")
    repo.salvar_calibracao("tabela", {"Arial|--|12": (-0.1, 0.2)})
    repo.salvar_calibracao("tabela", {"Arial|--|12": (-0.05, 0.1)})
    assert repo.calibracao("tabela") == {"Arial|--|12": (-0.05, 0.1)}
    assert repo.calibracao("absoluto") == {}


def test_perfil_so_troca_de_motor_quando_aprovado(tmp_path):
    repo = Repositorio(tmp_path / "t.db")
    repo.atualizar_perfil("SAP|Arial", "tabela", aprovado=True)
    repo.atualizar_perfil("SAP|Arial", "absoluto", aprovado=False)
    assert repo.motor_preferido("SAP|Arial") == "tabela"
    repo.atualizar_perfil("SAP|Arial", "absoluto", aprovado=True)
    assert repo.motor_preferido("SAP|Arial") == "absoluto"


def test_ajustes_por_palavra_do_mesmo_arquivo_sao_recuperados(tmp_path):
    repo = Repositorio(tmp_path / "t.db")
    antiga = repo.iniciar_conversao("a.pdf", "abc", "1.0.0", tmp_path / "a.pdf")
    repo.finalizar_conversao(antiga, status=Status.APROVADO, motor="tabela", ajustes={"espacos": {"1:4": 0.5}})
    nova = repo.iniciar_conversao("a.pdf", "abc", "1.0.0", tmp_path / "a.pdf")
    repo.finalizar_conversao(nova, status=Status.COM_DIFERENCAS, motor="tabela", ajustes={"espacos": {}})
    assert repo.ajustes_anteriores("abc", "1.0.0", "tabela") == {"espacos": {"1:4": 0.5}}
    assert repo.ajustes_anteriores("abc", "1.0.0", "absoluto") == {}
