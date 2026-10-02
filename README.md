# Conversor PDF → Word

Converte PDF em Word (`.docx`) **idêntico ao original** e **prova** que ficou idêntico: o próprio
Microsoft Word renderiza o arquivo gerado, o sistema compara com o PDF palavra por palavra e pixel
por pixel e, se algo divergir, corrige e tenta de novo automaticamente.

Feito para documentos de layout fixo (certificados, laudos, formulários, relatórios de sistemas
como SAP/Protheus), onde conversores comuns "desconfiguram" o arquivo.

## Requisitos

| Item | Observação |
|---|---|
| Windows 10/11 | testado no Windows 11 Pro |
| Microsoft Word 2016 ou superior / Microsoft 365 | usado para a verificação visual (sem ele, converte, mas só confere o texto) |
| Python 3.10+ | o instalador baixa o 3.12 via `winget` se não houver |
| Internet na instalação | para baixar as dependências (`pip`) |

## Instalação (uma vez)

1. Copie a pasta `ConversorPDFWord` para onde quiser (ex.: `C:\Ferramentas\ConversorPDFWord`).
2. Dê **duplo clique em `instalar.bat`**.

O instalador encontra (ou instala) o Python, cria o ambiente isolado `.venv`, instala as
dependências, verifica o Word e cria o atalho **"Conversor PDF para Word"** na área de trabalho.
Não precisa de administrador. Pode ser executado de novo para atualizar.

## Uso

### Pela interface (recomendado)

1. Abra o atalho **Conversor PDF para Word** (ou `iniciar.bat`). O navegador abre sozinho.
2. Arraste o PDF para a área indicada e clique em **Converter**.
3. Na tela de resultado: situação, métricas de fidelidade, comparação página a página
   (original × Word) e o botão **Baixar Word (.docx)**.

Mantenha a janela preta aberta enquanto usar; fechá-la encerra o conversor.
A interface só atende a própria máquina (`127.0.0.1`), e os arquivos não saem dela.

### Arrastando arquivos

Arraste um ou mais PDFs sobre **`converter.bat`**: o `.docx` é salvo ao lado de cada PDF.

### Linha de comando

```bat
.venv\Scripts\python -m conversor arquivo.pdf outro.pdf --saida C:\Saida
.venv\Scripts\python -m conversor arquivo.pdf --motor absoluto --forcar
.venv\Scripts\python -m conversor --diagnostico
```

Código de saída `0` = todos aprovados; `1` = algum com diferença ou erro.

## Como ler o resultado

| Situação | Significado |
|---|---|
| **Idêntico ao original** | Todo o texto confere, nenhuma palavra fora de posição além da tolerância (1 pt ≈ 0,35 mm) e nenhuma diferença visual relevante em linhas, imagens e formas. |
| **Texto idêntico (sem verificação visual)** | Word não encontrado: o texto foi conferido, a aparência não. |
| **Com diferenças** | Entregue a melhor tentativa; veja "Diferenças de texto", os avisos e a comparação visual. |
| **Erro** | PDF inválido, protegido por senha etc. A mensagem explica. |

**Motores**: *Automático* tenta primeiro o motor **tabela** (o Word fica estruturado em tabela
invisível, mais fácil de editar) e, se não ficar idêntico, o **absoluto** (cada linha de texto
numa moldura na posição exata — máxima fidelidade, funciona com qualquer PDF).

## O que fica guardado (persistência)

Tudo em `dados\` (fora do controle de versão):

| Caminho | Conteúdo |
|---|---|
| `dados\conversor.db` | Banco SQLite: histórico, tentativas, calibração aprendida e perfis de documento |
| `dados\entrada\` | Cópia de cada PDF convertido (o original nunca é alterado) |
| `dados\saida\<n>\` | Word gerado e prévias da conversão `n` |
| `dados\logs\conversor.log` | Registro detalhado (rotativo) |

O sistema **aprende**: o desvio que o Word introduz em cada fonte é gravado e aplicado às próximas
conversões; o motor que funcionou para cada "tipo" de documento é tentado primeiro da próxima vez;
um arquivo já convertido é reaproveitado (mesmo SHA-256) e, se reconvertido, parte dos ajustes
que já deram certo. Arquivos com mais de 30 dias são apagados automaticamente (o histórico fica).

## Configuração

Copie `config.exemplo.json` para `config.json` e altere o que precisar (porta, tolerâncias,
número de tentativas, dias de retenção). Chaves e significado: [docs/ARQUITETURA.md](docs/ARQUITETURA.md#configuração).

## Solução de problemas

| Sintoma | Causa provável / solução |
|---|---|
| Instalação falha no `pip` | Sem internet ou proxy corporativo. Configure `HTTPS_PROXY` e execute `instalar.bat` de novo. |
| "Microsoft Word não encontrado" | Word ausente ou não registrado. Abra o Word uma vez e rode `python -m conversor --diagnostico`. |
| Aviso "Fonte X não está instalada" | O PDF usa uma fonte que o Windows não tem. Instale a fonte e reconverta (botão **Reconverter**). |
| Conversão lenta | Cada tentativa abre o Word em segundo plano (≈ 3–10 s por tentativa). PDFs com centenas de páginas levam minutos. |
| Porta 8765 ocupada | Defina outra `porta` no `config.json`. |
| Resultado "Com diferenças" | Veja [docs/ANALISE_E_PENDENCIAS.md](docs/ANALISE_E_PENDENCIAS.md) (limitações conhecidas). Tente o motor **absoluto**. |

## Documentação

- [docs/ALGORITMO.md](docs/ALGORITMO.md) — como a conversão funciona, passo a passo, e as medições feitas no Word.
- [docs/ARQUITETURA.md](docs/ARQUITETURA.md) — módulos, fluxo, banco de dados, configuração, padrões de código.
- [docs/ANALISE_E_PENDENCIAS.md](docs/ANALISE_E_PENDENCIAS.md) — limitações, riscos e informações que faltam definir.

Cada `.md` tem uma versão `.html` ao lado, para leitura no navegador. Edite só o `.md` e regere com
`.venv\Scripts\python gerar_html_docs.py`.

## Desenvolvimento

```bat
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest              :: testes (os marcados "word" usam o Word real)
.venv\Scripts\python -m ruff check conversor tests
set PASTA_EXEMPLOS=C:\pdfs-reais && .venv\Scripts\python -m pytest -k reais
```

## Desinstalar

`desinstalar.bat` remove o ambiente `.venv` e o atalho. A pasta `dados` é mantida; apague a pasta
do projeto para remover tudo.
