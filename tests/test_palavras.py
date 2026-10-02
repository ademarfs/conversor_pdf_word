from conversor.palavras import Letra, dividir


def _letras(texto, x=0.0, largura=5.0, base=100.0, tamanho=10.0):
    letras = []
    for c in texto:
        letras.append(Letra(c, x, x + largura, base, tamanho))
        x += largura
    return letras


def _textos(palavras):
    return ["".join(letra.texto for letra in p) for p in palavras]


def test_separa_por_espaco():
    assert _textos(dividir(_letras("abc de"))) == ["abc", "de"]


def test_separa_por_vao_sem_espaco():
    letras = _letras("ab") + _letras("cd", x=40)
    assert _textos(dividir(letras)) == ["ab", "cd"]


def test_linhas_diferentes_nao_se_misturam():
    letras = _letras("ab", base=100) + _letras("cd", base=120)
    assert _textos(dividir(letras)) == ["ab", "cd"]


def test_tabulacao_exportada_como_espaco_sobreposto_nao_parte_a_palavra():
    # O Word exporta a tabulação como um espaço que começa no mesmo x da letra seguinte.
    letras = _letras("ab:") + [Letra(" ", 15, 18, 100.1, 11)] + _letras("Direito", x=15)
    assert _textos(dividir(letras)) == ["ab:", "Direito"]
