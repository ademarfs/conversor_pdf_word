# Arquitetura

## Visão geral

```
                 ┌──────────── web/app.py (Flask + waitress, 127.0.0.1) ───────────┐
 navegador ─────►│ upload · resultado · prévias · histórico · download              │
                 └──────────────────────────────┬──────────────────────────────────┘
 converter.bat ─► __main__.py (CLI) ────────────┤
                                                ▼
                                  servico.py  ServicoConversao
             ┌──────────────┬───────────────┬───┴──────────┬──────────────┬───────────────┐
             ▼              ▼               ▼              ▼              ▼               ▼
        extracao.py   layout/grade.py  gerador/       word.py        verificacao.py  persistencia.py
        (PyMuPDF)     layout/absoluto  escritor.py    (Word COM)     palavras.py     (SQLite)
             │        layout/paragrafos ooxml.py                      calibracao.py
             ▼              │               ▲
        modelo.py ──────────┴─► layout/plano.py
```

Dependências apontam para dentro: `modelo` e `plano` não conhecem PyMuPDF, Word nem banco.
Cada motor recebe um `Documento` e devolve um `PlanoDocumento`; o escritor só traduz o plano.

## Módulos

| Módulo | Responsabilidade |
|---|---|
| `config.py` | Configuração (dataclass) + leitura do `config.json`; constante medida `FATOR_BASE_WORD` |
| `modelo.py` | Modelo neutro do PDF: `Documento`, `Pagina`, `Trecho`, `Segmento`, `Forma`, `Imagem` |
| `extracao.py` | PDF → modelo (texto, desenhos, imagens, ordem de pintura, avisos) |
| `fontes.py` | Nome de fonte do PDF → família do Windows; detecção de fonte ausente (registro do Windows) |
| `layout/plano.py` | Plano de montagem resolvido em pontos (linhas, células, quadros, runs) |
| `layout/paragrafos.py` | Agrupamento em linhas, montagem de parágrafo (recuo/tabulação/runs), empilhamento vertical |
| `layout/grade.py` | Motor **tabela** |
| `layout/absoluto.py` | Motor **absoluto** |
| `gerador/ooxml.py` | Construtores de XML WordprocessingML (sem regra de negócio) |
| `gerador/escritor.py` | Plano → `.docx` (uma seção por página, objetos ancorados na ordem de pintura) |
| `word.py` | `.docx` → PDF pelo Word (COM), instância exclusiva, serializada por trava |
| `palavras.py` | Regra única de divisão em palavras (original e resultado) |
| `verificacao.py` | Relatório: texto, desvios por palavra, diferença visual; prévias |
| `calibracao.py` | `Ajustes` (por fonte, por palavra) e recalibração a partir dos desvios |
| `persistencia.py` | Repositório SQLite |
| `servico.py` | Orquestração: reaproveitamento, motores, iterações, escolha, publicação, limpeza |
| `registro.py` | Logs (console + arquivo rotativo) |
| `__main__.py` | Linha de comando |
| `web/` | Interface (Flask), templates Jinja e CSS |

## Fluxo de uma conversão

1. `extrair(pdf)` → `Documento` (+ SHA-256 e avisos).
2. Existe conversão aprovada do mesmo SHA-256 na mesma `VERSAO`? Devolve-a.
3. Registra a conversão e arquiva uma cópia do PDF em `dados/entrada/<id>.pdf`.
4. Ordem dos motores: escolhido pelo usuário, ou o preferido do perfil de layout, ou `tabela → absoluto`.
5. Para cada motor, até `max_iteracoes`: `planejar` → `salvar .docx` → `docx_para_pdf` →
   `verificar` → aprovado? senão `recalibrar` e repete. Grava cada tentativa.
6. Melhor tentativa → `dados/saida/<id>/<nome>.docx` + prévias; atualiza perfil e calibração.
7. Remove `dados/trabalho/<id>` (salvo `manter_arquivos_trabalho`).

## Banco de dados (`dados/conversor.db`)

```sql
conversoes        (id, criado_em, nome_original, sha256, versao_conversor, caminho_pdf, paginas,
                   status, motor, iteracoes, texto_identico, desvio_maximo_pt, desvio_medio_pt,
                   pixels_maximo_pct, relatorio_json, ajustes_json, avisos_json, caminho_docx,
                   previas_json, duracao_s, mensagem_erro)
tentativas        (id, conversao_id → conversoes, motor, iteracao, aprovado, texto_identico,
                   desvio_maximo_pt, pixels_maximo_pct, duracao_s)
calibracao_fontes (motor, chave "Família|NI|tamanho", dx, dy, amostras, atualizado_em)  PK (motor, chave)
perfis_layout     (assinatura "gerador|fontes|formatos", motor_preferido, conversoes, aprovadas, atualizado_em)
esquema           (versao)
```

`status`: `processando`, `aprovado`, `aprovado_sem_word`, `com_diferencas`, `erro`.
Consultas úteis:

```sql
-- taxa de aprovação por motor
SELECT motor, COUNT(*), SUM(status = 'aprovado') FROM conversoes GROUP BY motor;
-- conversões com diferença e o porquê
SELECT id, nome_original, desvio_maximo_pt, pixels_maximo_pct, avisos_json
  FROM conversoes WHERE status = 'com_diferencas' ORDER BY id DESC;
```

## Configuração

`config.json` na raiz (opcional; chaves desconhecidas geram erro):

| Chave | Padrão | Efeito |
|---|---|---|
| `pasta_dados` | `dados` | onde ficam banco, entradas, saídas e logs |
| `porta` / `host` | `8765` / `127.0.0.1` | endereço da interface (mantenha `127.0.0.1`) |
| `tamanho_maximo_mb` | `50` | limite de upload |
| `tolerancia_posicao_pt` | `1.0` | desvio máximo por palavra para aprovar |
| `tolerancia_pixels_pct` | `0.5` | diferença visual máxima (fora do texto) para aprovar |
| `max_iteracoes` | `4` | tentativas por motor |
| `deslocamento_maximo_pt` | `0.5` | quanto o motor tabela pode subir um texto para não ser cortado pela borda |
| `agrupamento_x_pt` / `agrupamento_y_pt` | `1.0` / `0.6` | coordenadas mais próximas que isso se unem (colunas/linhas da tabela) |
| `folga_ancoragem_pt` | `1.0` | tolerância para decidir a célula de um texto |
| `lacuna_tabulacao_pt` | `1.0` | vão mínimo entre trechos para usar tabulação |
| `max_colunas_tabela` | `63` | limite do Word |
| `dias_retencao` | `30` | apaga PDFs/Words mais antigos (histórico permanece) |
| `manter_arquivos_trabalho` | `false` | guarda todas as tentativas em `dados/trabalho` (diagnóstico) |

## Padrões de código (Clean Code)

- **Nomes em português**, do domínio (`Trecho`, `Segmento`, `empilhar`, `recalibrar`), sem abreviações.
- **Uma responsabilidade por módulo**; funções curtas; a regra de layout nunca está no gerador de XML.
- **Sem números mágicos**: toda constante tem nome e comentário com a origem (muitas vieram de
  medição no Word, documentadas em [ALGORITMO.md](ALGORITMO.md)).
- **Dados imutáveis onde possível** (`dataclass(frozen=True)`), cópias com `dataclasses.replace`.
- **Erros esperados** viram `ErroConversao` com mensagem para o usuário; inesperados são logados
  com stack trace e a conversão fica com status `erro`.
- **O arquivo do usuário nunca é alterado**: o serviço trabalha numa cópia; a limpeza só apaga
  dentro de `dados/`.
- **Qualidade verificável**: `ruff` (configuração em `ruff.toml`) e `pytest` (49 testes; os
  marcados `word` usam o Word real; PDFs de teste são sintéticos, gerados no próprio teste).

## Como estender

- **Novo motor**: classe com `nome` e `planejar(documento, ajustes) -> PlanoDocumento`; registrar
  em `servico.MOTORES` e (se quiser) em `ORDEM_PADRAO`. O escritor, a verificação e a persistência
  funcionam sem mudança.
- **Nova fonte equivalente**: incluir em `fontes.EQUIVALENTES`.
- **Mudança que altera o resultado**: suba `VERSAO` em `conversor/__init__.py` para invalidar os
  resultados reaproveitados.
