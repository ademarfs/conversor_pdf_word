"""Correspondência entre nomes de fonte do PDF e fontes instaladas no Windows."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

# Fontes-padrão do PDF ("base 14") e nomes PostScript comuns, com o equivalente
# métrico no Windows (mesma largura de caracteres => mesmo posicionamento).
EQUIVALENTES = {
    "helvetica": "Arial",
    "arial": "Arial",
    "helveticaneue": "Arial",
    "times": "Times New Roman",
    "timesroman": "Times New Roman",
    "timesnewroman": "Times New Roman",
    "courier": "Courier New",
    "couriernew": "Courier New",
    "symbol": "Symbol",
}

SUFIXOS_POSTSCRIPT = ("psmt", "mt", "ps")
FLAG_ITALICO = 2
FLAG_NEGRITO = 16


@dataclass(frozen=True)
class FonteWord:
    familia: str
    negrito: bool
    italico: bool
    instalada: bool


def mapear_fonte(nome_pdf: str, flags: int) -> FonteWord:
    """Converte o nome da fonte do PDF (ex.: 'ABCDEF+Arial-BoldMT') para o Word."""
    nome = re.sub(r"^[A-Z]{6}\+", "", nome_pdf)  # remove prefixo de subconjunto
    familia, estilo = _dividir(nome)
    negrito = bool(flags & FLAG_NEGRITO) or _eh_negrito(nome)
    italico = bool(flags & FLAG_ITALICO) or _eh_italico(nome, estilo)

    instaladas = fontes_instaladas()
    for candidato in (_normalizar(nome), _normalizar(familia)):
        candidato = _sem_sufixo_postscript(candidato)
        encontrada = EQUIVALENTES.get(candidato) or instaladas.get(candidato)
        if encontrada:
            # 'Segoe UI Semibold' já é pesada: aplicar negrito engrossaria de novo.
            return FonteWord(encontrada, negrito and not _eh_negrito(encontrada), italico, True)
    # Sem registro de fontes (fora do Windows) não há como afirmar que falta.
    return FonteWord(_separar_maiusculas(familia), negrito, italico, not instaladas)


@lru_cache(maxsize=1)
def fontes_instaladas() -> dict[str, str]:
    """Famílias instaladas no Windows: nome normalizado -> nome da família."""
    try:
        import winreg
    except ImportError:
        return {}
    familias: dict[str, str] = {}
    chave = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            registro = winreg.OpenKey(raiz, chave)
        except OSError:
            continue
        with registro:
            for nome in _valores_do_registro(winreg, registro):
                for parte in re.sub(r"\s*\(.*\)$", "", nome).split(" & "):
                    familia = _remover_estilo(parte.strip())
                    familias.setdefault(_normalizar(familia), familia)
    return familias


def _valores_do_registro(winreg, registro):
    indice = 0
    while True:
        try:
            yield winreg.EnumValue(registro, indice)[0]
        except OSError:
            return
        indice += 1


def _dividir(nome: str) -> tuple[str, str]:
    """'Arial-BoldItalicMT' -> ('Arial', 'bolditalicmt'); 'Arial,Bold' -> ('Arial', 'bold')."""
    partes = re.split(r"[-,]", nome, maxsplit=1)
    return partes[0], (partes[1].lower() if len(partes) > 1 else "")


def _eh_negrito(nome: str) -> bool:
    return any(p in nome.lower() for p in ("bold", "black", "heavy", "demi"))


def _eh_italico(nome: str, estilo: str) -> bool:
    minusculo = nome.lower()
    return "italic" in minusculo or "oblique" in minusculo or estilo.endswith("it")


def _remover_estilo(nome: str) -> str:
    """'Arial Bold Italic' -> 'Arial'. Pesos como Light/Black são famílias próprias no Word."""
    padrao = r"(\s+(Bold|Italic|Oblique|Regular))+$"
    return re.sub(padrao, "", nome, flags=re.IGNORECASE) or nome


def _normalizar(nome: str) -> str:
    return re.sub(r"[^a-z0-9]", "", nome.lower())


def _sem_sufixo_postscript(nome: str) -> str:
    for sufixo in SUFIXOS_POSTSCRIPT:
        if nome.endswith(sufixo) and len(nome) > len(sufixo) + 2:
            return nome[: -len(sufixo)]
    return nome


def _separar_maiusculas(nome: str) -> str:
    """'SegoeUI' -> 'Segoe UI' (forma mais provável do nome da família)."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", nome)
