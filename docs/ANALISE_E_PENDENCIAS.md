# Análise: limitações, riscos e informações que faltam

Levantamento feito ao fim da versão 1.0.0 (2 de outubro de 2026), depois de testar com 5 PDFs
reais de origens diferentes (SAP, Word, Canva, CAD, escaneado) e 49 testes automatizados.

## 1. Perguntas em aberto (precisam de decisão)

| # | Pergunta | Por que importa | Padrão adotado até a resposta |
|---|---|---|---|
| P1 | **Quem vai usar e onde?** Só nesta máquina, ou vários usuários pela rede? | A Microsoft não suporta automação do Word em servidor sem usuário (instabilidade e licenciamento). Uso em rede exige outra arquitetura: um posto Windows dedicado com fila de conversões, ou motor de verificação sem Word. | Uso local, um usuário por máquina; a interface só aceita `127.0.0.1`. |
| P2 | **Retenção e LGPD**: por quanto tempo guardar PDFs e Words (certificados de clientes, currículos)? | A pasta `dados/` guarda cópias dos documentos. | 30 dias (`dias_retencao`); o histórico sem arquivos fica. |
| P3 | **PDFs escaneados precisam virar texto editável (OCR)?** | Hoje a página escaneada vira imagem no Word: visualmente idêntica, mas não editável. OCR (ex.: Tesseract) introduz erros de reconhecimento e contradiz o "sem alteração nenhuma". | Imagem, com aviso. |
| P4 | **Prioridade: fidelidade visual ou edição livre?** | Os dois motores mantêm cada linha na posição exata. Isso é o que garante fidelidade, mas, se você digitar muito texto a mais numa célula ou moldura, ele não "empurra" o resto como num documento comum. | Fidelidade. |
| P5 | **Onde o Word deve ser entregue?** Download, pasta de rede, e-mail, integração com SAP/Protheus? | Define se vale um modo "pasta monitorada" (converte tudo o que cair numa pasta). | Download pela interface, ou ao lado do PDF via `converter.bat`. |
| P6 | **Versões do Office na empresa.** | Testado no Word 16 (Microsoft 365). Word 2013 ou anterior não foi testado (a medida 0,8·L e o tratamento de bordas foram medidos no 16). | Word 2016+. |
| P7 | **Política de TI**: o PowerShell pode rodar scripts? Há proxy? O `winget` é permitido? | O instalador usa `-ExecutionPolicy Bypass` só no próprio processo, `pip` (internet) e, sem Python, `winget`. | Instalação por usuário, sem administrador. |
| P8 | **Volume**: quantos PDFs por dia e de quantas páginas? | Cada tentativa abre o Word (≈ 3–10 s). As conversões são feitas uma de cada vez. Lotes grandes pedem uma fila e um processo em segundo plano. | Conversão sob demanda. |

## 2. Limitações conhecidas (o que pode sair "Com diferenças")

A verificação **detecta** todos estes casos e marca a conversão como "Com diferenças". Nenhum
passa despercebido.

| Situação no PDF | Comportamento atual | Possível evolução |
|---|---|---|
| Fonte não instalada no Windows | Usa substituta e corrige o espaçamento palavra a palavra; o formato das letras muda. Aviso com o nome da fonte. | Extrair a fonte embutida no PDF e embuti-la no .docx (subconjuntos de fonte têm restrições de licença). |
| Degradês, padrões e sombras (*shadings*) | Não extraídos (o PyMuPDF não os entrega como desenho). | Rasterizar a área do degradê como imagem. |
| Máscaras de recorte (*clipping*) em desenhos vetoriais | O desenho aparece inteiro, sem o recorte. Comum em PDFs de Canva/Illustrator. | Aplicar o recorte ou rasterizar a área recortada. |
| Texto coberto por desenho (ex.: tarja sobre texto) | O texto fica sempre por cima dos desenhos no Word. | Rasterizar o desenho que cobre o texto como imagem por cima. |
| Texto inclinado ou vertical | Posicionado na horizontal (aviso). | Caixa de texto girada. |
| Página com rotação (`/Rotate`) | Aviso; pode ficar deslocada. | Aplicar a matriz de rotação. |
| Links, marcadores, comentários, campos de formulário, assinatura digital | Não são levados ao Word (o texto visível é). A assinatura digital não pode ser transferida por natureza. | Converter links em hiperlinks do Word. |
| Cabeçalho e rodapé repetidos | Vão como conteúdo de cada página, não como cabeçalho/rodapé do Word. | Detectar elementos repetidos e mover para o cabeçalho/rodapé. |
| Idiomas da direita para a esquerda (árabe, hebraico) | Não tratados. | — |
| Página com mais de 63 colunas lógicas | O motor tabela não se aplica; vai o absoluto (automático). | — |

## 3. Riscos e mitigações

| Risco | Mitigação implementada |
|---|---|
| Alterar ou perder o PDF original | O serviço só lê o original e trabalha numa cópia; a limpeza só apaga dentro de `dados/` (há teste para isso). |
| Word travar ou ficar aberto em segundo plano | Instância exclusiva e invisível, fechada em `finally`; conversões serializadas por trava. Ponto de atenção: um diálogo inesperado do Word (licença, recuperação de arquivo) pode travar a automação. Nesse caso, encerre o `WINWORD.EXE` pelo Gerenciador de Tarefas. |
| Acesso indevido à interface | Servidor só em `127.0.0.1`, recusa cabeçalho `Host` estranho (proteção contra *DNS rebinding*), valida a assinatura `%PDF-` e o tamanho do upload. |
| Resultado "aprovado" errado | Três medidas independentes (texto, posição, pixels); tolerâncias configuráveis; prévias lado a lado para conferência humana. |
| Mudança de versão alterar resultados | `VERSAO` entra na chave de reaproveitamento; subir a versão invalida resultados antigos. |
| Banco corrompido ou perdido | Arquivo único `dados/conversor.db`. **Recomendado**: incluir `dados/` na rotina de backup. |

## 4. Itens de projeto ainda não feitos (sugestões de próximos passos)

1. **Controle de versão**: a pasta ainda não é um repositório Git. Recomendo `git init` e um
   repositório interno (o `.gitignore` já exclui `.venv/` e `dados/`).
2. **Assinatura dos scripts** (`instalar.ps1`), se a política de TI exigir *AllSigned*.
3. **Fila e processamento em segundo plano** na interface, se o volume (P8) justificar; hoje a
   página espera a conversão terminar.
4. **Modo pasta monitorada** (P5).
5. **Painel de qualidade**: taxa de aprovação por tipo de documento, a partir do banco
   (as consultas estão em [ARQUITETURA.md](ARQUITETURA.md#banco-de-dados-dadosconversordb)).
6. **Testes com mais PDFs reais** da operação: coloque-os numa pasta e rode
   `set PASTA_EXEMPLOS=C:\pasta && .venv\Scripts\python -m pytest -k reais`.
