# Xeque-LFM — Chess Challenge III (iCEV 2026)

Motor de xadrez **100% offline** construído sobre o modelo
`LFM2.5-230M-Chess` (Liquid AI / M. Labonne, licença LFM Open License v1.0),
com **modificações no modelo e no algoritmo de decisão**.

## O que foi modificado

| Camada | Original | Xeque-LFM |
|---|---|---|
| Arquivo GGUF | `LFM2.5-230M-Chess.Q8_0.gguf`, template de *chat* genérico | `XequeLFM-230M.Q8_0.gguf`: identidade própria, template *raw* compatível com llamafile, protocolo de entrada e parâmetros de busca embutidos nos metadados (`xeque.*`). Pesos preservados. |
| Entrada | não documentada no GGUF | Codificador de 80 tokens (posição + 8 lances de histórico), validado: ~98% da probabilidade cai em lances legais sem máscara |
| Decisão | 1 passada da rede (~1450 Elo segundo o autor) | **Busca negamax alfa-beta** sobre a cabeça de valor, podada pela política (larguras 10/5/4/3), aprofundamento iterativo com prazo rígido |
| Uso do tempo | — | **Ponderação**: pensa durante o relógio do adversário nas 3 respostas mais prováveis; o cache torna a busca seguinte mais profunda |
| Tática | nenhuma | Mate-em-1 verificado em **todos** os lances; capturas e xeques sempre considerados na raiz; regras exatas de mate/afogamento/repetição/50 lances |
| Robustez | — | Máscara de legalidade (nunca joga lance ilegal), motor de reserva clássico se a rede falhar, estado salvo a cada lance (`--retomar` após queda) |
| Relógio | — | Gestão de tempo para 25 min incluindo o tempo de digitação/movimento das peças |

## Instalação (Windows)

1. Coloque `LFM2.5-230M-Chess.Q8_0.gguf` em `modelo\`
2. Execute `instalar.bat` (instala dependências, gera o GGUF modificado e roda o benchmark)

## Na partida

- `jogar_brancas.bat` ou `jogar_pretas.bat`
- Digite o lance do adversário: `e7e5`, `e7-e5`, `e5`, `Cf6`, `O-O`, `e7e8d` (promoção)
  - Notação portuguesa: **R**ei, **D**ama, **T**orre, **B**ispo, **C**avalo
- O motor mostra o lance e **como executá-lo no tabuleiro** (captura, roque, en passant, promoção)
- Comandos: `tabuleiro`, `desfazer`, `tempo 12:30` (sincroniza com o relógio físico), `fen`, `pgn`, `sair`
- Se o programa fechar: `retomar.bat` — continua do último lance

Opções: `--minutos 25 --overhead 10 --threads 10 --notacao en`

## Outros modos

- `uci.py` — protocolo UCI para Arena / Cute Chess (treinos contra outros motores)
- `servidor_llamafile.bat` — serve o GGUF modificado pelo llamafile em `127.0.0.1:8080`
- `benchmark.py` — velocidade e testes táticos
- `ferramentas/match.py` — partidas contra Stockfish com Elo limitado (`--modo politica|busca`)

## Desempenho medido (Ryzen 5 5500U, 11 threads)

- ~160 ms por posição avaliada (≈6 nós/s): o custo é de cálculo (80 tokens × 230M parâmetros), não de memória
- Testes táticos (`benchmark.py`): 5/5
- Dica: no dia, notebook **na tomada** e plano de energia **Alto desempenho**

## Formato do prompt (descoberto e documentado pela equipe)

```
<BOS><|pos|> 64×<c:X>  (a8→h8, a7→h7, …, a1→h1; X ∈ . P N B R Q K p n b r q k)
<stm:w|b> <cast:KQkq|…|-> <ep:a..h|-> <hm:0..25> <rep:0..2>
<|hist|> 8×(<m:uci>)  (preenchido à esquerda com <|pad|>)
<|eval|>                    → modelo prevê <v:k>,  P(vitória do lado a jogar) = (k+0.5)/64
<v:k><|bestmove|>           → modelo prevê <m:uci> (logits mascarados para lances legais)
```

## Estrutura

```
motor/modelo.py   codificador + inferência (llama.cpp)
motor/busca.py    negamax alfa-beta, aprofundamento iterativo, extensões táticas
motor/reserva.py  motor clássico de reserva
jogar.py          interface do tabuleiro físico
uci.py            interface UCI
ferramentas/modificar_gguf.py   gera o GGUF da equipe
```

## Créditos e licença

Modelo base: Liquid AI LFM2.5 (LFM Open License v1.0); fine-tune de xadrez por
Maxime Labonne (ChessLFM). Código do motor: equipe iCEV.
