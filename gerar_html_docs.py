"""Gera um .html ao lado de cada .md do projeto (conversão direta, CSS mínimo, sem JavaScript).

Edite apenas os .md e rode de novo:
    .venv\\Scripts\\python gerar_html_docs.py
"""
from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path

import markdown

RAIZ = Path(__file__).resolve().parent
DOCUMENTOS = [RAIZ / "README.md", *sorted((RAIZ / "docs").glob("*.md"))]

CSS = """
body { max-width: 960px; margin: 0 auto; padding: 24px 16px 48px; font: 15px/1.6 "Segoe UI", Arial, sans-serif;
       color: #1d2329; background: #fff; }
h1, h2, h3 { line-height: 1.3; margin-top: 1.6em; }
h1 { margin-top: 0; border-bottom: 1px solid #d9dee3; padding-bottom: 6px; }
h2 { border-bottom: 1px solid #eceff2; padding-bottom: 4px; }
a { color: #1f5fbf; }
code { font: 13px Consolas, monospace; background: #f3f4f6; padding: 1px 4px; border-radius: 3px; }
pre { background: #f3f4f6; padding: 12px; overflow-x: auto; border-radius: 4px; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; display: block; overflow-x: auto; }
th, td { border: 1px solid #d9dee3; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #f6f7f9; }
nav { font-size: 13px; color: #5c6670; margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 4px 12px; }

"""


def ancora(texto: str, separador: str) -> str:
    """Âncora no padrão do GitHub (mantém acentos), para os links entre documentos funcionarem."""
    texto = unicodedata.normalize("NFC", texto).strip().lower()
    texto = re.sub(r"[^\w\s-]", "", texto)
    return re.sub(r"\s", separador, texto)


def converter(arquivo: Path) -> Path:
    texto = arquivo.read_text(encoding="utf-8")
    texto = re.sub(r"\]\(([^)#]+?)\.md(#[^)]*)?\)", r"](\1.html\2)", texto)  # links .md -> .html
    corpo = markdown.markdown(texto, extensions=["tables", "fenced_code", "toc"],
                              extension_configs={"toc": {"slugify": ancora}})
    titulo = re.search(r"^# (.+)$", texto, re.MULTILINE)
    destino = arquivo.with_suffix(".html")
    destino.write_text(
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(titulo.group(1) if titulo else arquivo.stem)}</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n{_navegacao(arquivo)}\n{corpo}\n</body>\n</html>\n",
        encoding="utf-8",
    )
    return destino


def _navegacao(atual: Path) -> str:
    links = []
    for documento in DOCUMENTOS:
        relativo = Path(*([".."] if atual.parent != RAIZ else [])) / documento.relative_to(RAIZ)
        links.append(f'<a href="{relativo.with_suffix(".html").as_posix()}">{documento.stem}</a>')
    return "<nav>" + "".join(links) + "</nav>"


if __name__ == "__main__":
    for documento in DOCUMENTOS:
        print(converter(documento).relative_to(RAIZ))
