# Como a conversão funciona

Princípio: **não adivinhar**. Conversores comuns tentam deduzir parágrafos, colunas e estilos e
"refluem" o texto — é aí que o layout desconfigura. Aqui cada elemento é **medido** no PDF e
**recolocado** no Word na mesma coordenada; depois o resultado é **conferido** no próprio Word.

Unidade: ponto tipográfico (1 pt = 1/72 pol ≈ 0,353 mm). Origem no canto superior esquerdo, y para baixo.

```
PDF ─► 1 Extração ─► 2 Layout (motor) ─► 3 Escrita .docx ─► 4 Word renderiza ─► 5 Verificação
                          ▲                                                          │
                          └──────── 6 Recalibração (se não aprovado) ◄───────────────┘
                                         │
                                         ▼
                                7 Persistência (banco SQLite)
```

## 1. Extração (`extracao.py`)

Com o PyMuPDF, para cada página:

| Elemento | O que é lido |
|---|---|
| **Trechos de texto** | texto exato (espaços inclusive), fonte, tamanho, negrito/itálico, cor, posição da **linha de base** e de cada caractere |
| **Segmentos** | linhas retas horizontais/verticais (bordas, sublinhados), espessura, cor, tracejado, opacidade |
| **Formas** | desenhos livres (curvas, diagonais, áreas preenchidas) |
| **Imagens** | na resolução original, com transparência |
| **Ordem de pintura** | a posição de cada desenho/imagem na sequência de desenho da página (quem cobre quem) |

Regras importantes:

- **Fonte**: nomes do PDF viram a família equivalente do Windows (`Helvetica` → Arial,
  `Times-Italic` → Times New Roman itálico, `ABCDEF+Calibri-Light` → Calibri Light). As
  equivalentes têm **as mesmas larguras de caracteres**, por isso o texto ocupa o mesmo espaço.
  Fonte ausente gera aviso.
- **Retângulo preenchido muito fino** (≤ 2 pt) é uma linha desenhada como retângulo: vira segmento.
- **Elemento com opacidade 0** existe no PDF mas não aparece: é ignorado.
- **Máscara de estêncil** (imagem de 1 bit pintada com a cor de preenchimento, comum em logotipos
  de sistemas como o SAP): é recortada da página já com a cor e a transparência corretas
  (exportá-la "crua" faria o Word mostrá-la invertida, como um bloco preto).
- **Caractere sem Unicode** (o PDF não diz qual letra é): o trecho é preservado como imagem.
- **Fonte de símbolos** (Symbol/Wingdings) com caractere Unicode real (ex.: "•"): usa
  *Segoe UI Symbol*, porque o Word só mostra Symbol com códigos privados.

## 2. Layout — os motores (`layout/`)

### Medição que sustenta tudo

Com espaçamento de linha **"Exatamente L"**, o Word desenha a linha de base a **0,8 · L** do
topo da linha, para qualquer fonte (medido no Word 16 com Arial e Times de 7 a 20 pt, erro < 0,1 pt).
Então, para um texto com base em `y`, basta a linha começar em `y − 0,8·L`. Posição horizontal:
recuo do parágrafo e tabulações, em vigésimos de ponto.

### Motor **tabela** (`grade.py`) — mais editável

A página vira **uma tabela invisível** com linhas de altura exata:

1. **Cortes horizontais** (fronteiras entre linhas da tabela): cada traço horizontal e as pontas
   dos traços verticais; e o meio de cada vão vertical entre blocos de texto. Um corte é
   proibido se atravessar um texto ou se obrigar um texto a subir mais de 0,5 pt.
2. **Células**: em cada linha, as pontas dos traços da borda inferior e as linhas verticais
   que a atravessam definem as colunas. Cada texto vai para a célula onde começa; se não
   couber com folga, as células são fundidas (o Word **corta**, não quebra, texto que encosta na borda).
3. **Bordas**: traço que cobre a célula inteira vira borda da célula; o que sobra é desenhado
   como forma vetorial (nada se perde).
4. **Dentro da célula**: um parágrafo por linha visual, com recuo até o 1º trecho, tabulação
   para os demais e "espaço antes" calculado para cair na linha de base exata.

Comportamentos do Word medidos e compensados:

| Comportamento do Word | Compensação |
|---|---|
| Borda inferior é desenhada **abaixo** do limite da célula (de y a y+espessura) | o limite sobe meia espessura, centrando a borda no traço original |
| O conteúdo da linha seguinte começa **depois** da espessura dessa borda | o "espaço antes" desconta a espessura |
| Borda vertical é centrada na divisa | as colunas seguem a posição exata das linhas verticais |
| Colunas muito estreitas (< ~1 pt) desalinham a tabela inteira (até 6 pt!) | coordenadas a menos de 1 pt viram a mesma coluna |
| Linha de altura exata **corta** a tinta que passa do limite (pernas de g, p, ç, vírgula) | o texto sobe até 0,5 pt; se precisar mais, aquele traço vira forma e não corta |
| Máximo de 63 colunas por tabela | página que exigiria mais é feita pelo motor absoluto |

### Motor **absoluto** (`absoluto.py`) — máxima fidelidade

Cada linha de texto é um parágrafo em **moldura** (*frame*) posicionada na coordenada exata da
página; todas as linhas e formas são desenhos vetoriais ancorados na página. Funciona com qualquer
PDF (plantas, currículos, layouts gráficos). O texto continua editável.

### Comum aos dois

- **Uma seção do Word por página** do PDF, com o mesmo tamanho e margens zero — páginas de
  tamanhos/orientações diferentes no mesmo arquivo funcionam.
- **Imagens e desenhos** ficam atrás do texto, **empilhados na ordem de pintura do PDF**
  (um retângulo branco que cobre linhas no PDF continua cobrindo no Word).

## 3. Escrita do .docx (`gerador/`)

`escritor.py` traduz o plano para WordprocessingML; `ooxml.py` monta cada elemento XML na ordem
exigida pelo esquema (tabela de layout fixo sem margens internas, molduras, desenhos `wps` com
geometria livre, imagens ancoradas). O documento é marcado como Word 2013+ (sem "Modo de Compatibilidade").

## 4. Renderização pelo Word (`word.py`)

O `.docx` é aberto numa instância **invisível e exclusiva** do Word (automação COM) e exportado
em PDF. É exatamente o que o usuário verá ao abrir o arquivo — não uma simulação.

## 5. Verificação (`verificacao.py`, `palavras.py`)

Três medidas independentes:

1. **Texto** — todas as palavras do original existem no resultado e nada sobra. As palavras
   são pareadas na ordem de leitura (alinhamento de sequência, como um *diff*) e, o que sair da
   ordem, pela mesma palavra mais próxima.
2. **Posição** — para cada palavra: desvio do início, do fim e da linha de base. Aprovação:
   **≤ 1 pt** (configurável).
3. **Visual** — páginas renderizadas a 100 dpi, **com as áreas de texto mascaradas** (texto já foi
   medido no item 2; assim a diferença de desenho entre fontes equivalentes não conta como erro),
   tolerando 1 pixel de reamostragem. Pega linha faltando, imagem errada, forma fora do lugar.
   Aprovação: **≤ 0,5 %** dos pixels.

Detalhe medido: o Word exporta cada tabulação como um caractere de espaço que **começa no mesmo
x da letra seguinte**; as letras são ordenadas pelo centro para isso não partir palavras.

## 6. Recalibração (`calibracao.py`)

Se não aprovou, os desvios medidos viram correções e uma nova tentativa é gerada (até 4 por motor):

| Nível | Correção | Vale para |
|---|---|---|
| **Fonte** (família/estilo/tamanho) | deslocamento x/y sistemático (mediana; desvios > 2 pt são ignorados por serem do layout, não da fonte) | **todas as conversões futuras** (gravado no banco) |
| **Espaço antes de cada palavra** | espaçamento extra no caractere anterior — corrige texto **justificado** | este documento |
| **Largura de cada palavra** | espaçamento entre as letras — corrige fonte substituta ou condensada | este documento |

O espaço só responde pelo **vão** entre palavras quando a largura da palavra anterior também
está sendo corrigida — senão o mesmo erro seria corrigido duas vezes. Valores arredondados para
0,05 pt (resolução do Word). Resultado típico: texto justificado com 60 pt de desvio converge para
< 1 pt em 2–3 tentativas; reconversões do mesmo arquivo acertam na 1ª.

## 7. Escolha e persistência (`servico.py`, `persistencia.py`)

- Fica a **melhor tentativa** (texto idêntico > menor desvio > menor diferença visual).
- Se o motor tabela não aprovar, tenta o absoluto. O motor aprovado para aquele **tipo de
  documento** (gerador + fontes + formato) é tentado primeiro da próxima vez.
- Grava: métricas, cada tentativa, ajustes usados (permite reproduzir o mesmo resultado),
  avisos, caminhos e prévias.
- Mesmo arquivo (SHA-256) já aprovado na mesma versão do conversor: o resultado é reaproveitado.

## Resultados de referência (2 de outubro de 2026, Word 16, Windows 11)

| Documento | Motor | Texto | Desvio máx. | Pixels | Tentativas |
|---|---|---|---|---|---|
| Certificado SAP, 2 págs. | tabela | idêntico | 0,69 pt | 0,00 % | 1 |
| Certificado SAP, 4 págs. | tabela | idêntico | 0,69 pt | 0,07 % | 1 |
| Currículo (Canva, fonte ausente) | tabela | idêntico | 0,84 pt | 0,00 % | 3 (1 na reconversão) |
| Planta técnica A3 vetorial (1076 desenhos) | absoluto | idêntico | 0,00 pt | 0,00 % | 1 |
| Página escaneada (imagem JPEG, sem texto) | qualquer | — | — | 0,07 % | 1 |
