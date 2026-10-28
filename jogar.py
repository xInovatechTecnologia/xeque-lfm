#!/usr/bin/env python3
"""
Xeque-LFM — interface de partida para tabuleiro físico (Chess Challenge iCEV).

Uso:
  python jogar.py --cor brancas            # nova partida, motor joga de brancas
  python jogar.py --cor pretas             # motor joga de pretas
  python jogar.py --retomar                # retoma a última partida após queda
Comandos durante a partida: ajuda | tabuleiro | desfazer | tempo MM:SS | fen | pgn | sair
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import traceback

import chess
import chess.pgn

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from motor.reserva import lance_reserva  # noqa: E402

ESTADO = os.path.join(AQUI, "partidas", "estado.json")
MODELO_PADRAO = os.path.join(AQUI, "modelo", "XequeLFM-230M.Q8_0.gguf")
MODELO_ORIGINAL = os.path.join(AQUI, "modelo", "LFM2.5-230M-Chess.Q8_0.gguf")

PT2EN = {"R": "K", "D": "Q", "T": "R", "B": "B", "C": "N"}
EN2PT = {"K": "R", "Q": "D", "R": "T", "B": "B", "N": "C"}
NOME_PT = {chess.PAWN: "o peão", chess.KNIGHT: "o cavalo", chess.BISHOP: "o bispo",
           chess.ROOK: "a torre", chess.QUEEN: "a dama", chess.KING: "o rei"}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# --------------------------------------------------------------------- util
def san_pt(san: str) -> str:
    """Converte SAN inglês (Nf3, exd8=Q) para português (Cf3, exd8=D)."""
    if san and san[0] in EN2PT:
        san = EN2PT[san[0]] + san[1:]
    return re.sub(r"=([QRBN])", lambda g: "=" + EN2PT[g.group(1)], san)


def ler_lance(board: chess.Board, txt: str, notacao: str):
    t = txt.strip().replace(" ", "").replace("-", "").replace("x", "x")
    if re.fullmatch(r"[0Oo]{2,3}[+#]?", t):
        t = t.upper().replace("0", "O")
    # coordenadas: e2e4 / e2-e4 / e2 e4 / e7e8q
    m = re.fullmatch(r"([a-h][1-8])([a-h][1-8])([qrbndtc]?)", t.lower())
    if m:
        promo = {"d": "q", "t": "r", "c": "n"}.get(m.group(3), m.group(3))
        mv = chess.Move.from_uci(m.group(1) + m.group(2) + promo)
        if mv in board.legal_moves:
            return mv
        # promoção sem peça informada -> dama
        mv = chess.Move.from_uci(m.group(1) + m.group(2) + "q")
        if mv in board.legal_moves:
            return mv
        return None
    if t.rstrip("+#") in ("OO", "OOO"):
        t = "O-O" if t.rstrip("+#") == "OO" else "O-O-O"
    tentativas = []
    if notacao == "pt":
        tt = (PT2EN.get(t[0], t[0]) + t[1:]) if t and t[0] in PT2EN else t
        tt = re.sub(r"=?([DTCB])$", lambda g: "=" + PT2EN[g.group(1)], tt) if re.search(r"[18]=?[DTCB]$", tt) else tt
        tentativas.append(tt)
    tentativas.append(t)
    for c in tentativas:
        try:
            return board.parse_san(c)
        except ValueError:
            continue
    return None


def instrucoes(board: chess.Board, mv: chess.Move) -> list[str]:
    """Como executar o lance no tabuleiro físico."""
    p = board.piece_at(mv.from_square)
    de, para = chess.square_name(mv.from_square), chess.square_name(mv.to_square)
    linhas = [f"Mova {NOME_PT[p.piece_type]} de {de.upper()} para {para.upper()}"]
    if board.is_en_passant(mv):
        alvo = chess.square(chess.square_file(mv.to_square), chess.square_rank(mv.from_square))
        linhas.append(f"EN PASSANT: retire o peão adversário em {chess.square_name(alvo).upper()}")
    elif board.is_capture(mv):
        cap = board.piece_at(mv.to_square)
        linhas.append(f"CAPTURA: retire {NOME_PT[cap.piece_type]} adversári{NOME_PT[cap.piece_type][0]} de {para.upper()}")
    if board.is_castling(mv):
        if chess.square_file(mv.to_square) == 6:
            t0, t1 = ("h1", "f1") if board.turn else ("h8", "f8")
        else:
            t0, t1 = ("a1", "d1") if board.turn else ("a8", "d8")
        linhas.append(f"ROQUE: mova também a torre de {t0.upper()} para {t1.upper()}")
    if mv.promotion:
        linhas.append("PROMOÇÃO: troque o peão por " + {chess.QUEEN: "uma DAMA", chess.ROOK: "uma TORRE", chess.BISHOP: "um BISPO", chess.KNIGHT: "um CAVALO"}[mv.promotion])
    b2 = board.copy(); b2.push(mv)
    if b2.is_checkmate():
        linhas.append("*** XEQUE-MATE ***")
    elif b2.is_check():
        linhas.append("(xeque)")
    return linhas


def fmt_tempo(s: float) -> str:
    s = max(0, int(s)); return f"{s // 60:02d}:{s % 60:02d}"


def desenhar(board: chess.Board, cor_motor: bool):
    linhas = str(board).split("\n")
    ranks = "87654321"
    if cor_motor == chess.BLACK:   # mostra do ponto de vista do operador do motor
        linhas = [l[::-1] for l in linhas[::-1]]; ranks = ranks[::-1]
    files = "a b c d e f g h" if cor_motor == chess.WHITE else "h g f e d c b a"
    print()
    for r, l in zip(ranks, linhas):
        print(f"  {r} | {l}")
    print(f"      {'-' * 15}\n      {files}\n")


# ------------------------------------------------------------------- estado
def salvar(estado):
    os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
    tmp = ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ESTADO)


def exportar_pgn(board, estado):
    jogo = chess.pgn.Game.from_board(board)
    jogo.headers["Event"] = "Chess Challenge III - iCEV"
    jogo.headers["Date"] = estado["inicio"][:10].replace("-", ".")
    eu = "Xeque-LFM"
    jogo.headers["White"] = eu if estado["cor"] == "brancas" else "Adversário"
    jogo.headers["Black"] = eu if estado["cor"] == "pretas" else "Adversário"
    nome = os.path.join(AQUI, "partidas", f"partida_{estado['inicio'].replace(':', '-')}.pgn")
    with open(nome, "w", encoding="utf-8") as f:
        print(jogo, file=f)
    return nome


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Xeque-LFM — partida no tabuleiro físico")
    ap.add_argument("--cor", choices=["brancas", "pretas"])
    ap.add_argument("--retomar", action="store_true", help="retoma a partida salva")
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--minutos", type=float, default=25.0, help="tempo total do motor")
    ap.add_argument("--overhead", type=float, default=10.0,
                    help="segundos gastos por lance digitando/movendo peças (descontados do relógio)")
    ap.add_argument("--notacao", choices=["pt", "en"], default="pt",
                    help="notação algébrica aceita: pt (R D T B C) ou en (K Q R B N)")
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--fen", default=None, help="posição inicial (FEN)")
    ap.add_argument("--sem-ponder", action="store_true", help="não pensar no tempo do adversário")
    a = ap.parse_args()

    if a.retomar and os.path.exists(ESTADO):
        estado = json.load(open(ESTADO, encoding="utf-8"))
        print(f"Retomando partida de {estado['inicio']} ({len(estado['lances'])} lances).")
    else:
        if not a.cor:
            r = input("O motor joga de (b)rancas ou (p)retas? ").strip().lower()
            a.cor = "pretas" if r.startswith("p") else "brancas"
        estado = {"cor": a.cor, "lances": [], "fen_inicial": a.fen or chess.STARTING_FEN,
                  "restante": a.minutos * 60, "inicio": dt.datetime.now().isoformat(timespec="seconds"),
                  "overhead": a.overhead, "notacao": a.notacao}
        salvar(estado)

    board = chess.Board(estado["fen_inicial"])
    for u in estado["lances"]:
        board.push_uci(u)
    cor_motor = chess.WHITE if estado["cor"] == "brancas" else chess.BLACK
    notacao = estado.get("notacao", a.notacao)

    # ----- carrega o modelo (com fallback)
    caminho = a.modelo or (MODELO_PADRAO if os.path.exists(MODELO_PADRAO) else MODELO_ORIGINAL)
    busca = None
    ponder = None
    try:
        from motor.modelo import ModeloXadrez
        from motor.busca import Busca, Ponderador
        print(f"Carregando modelo: {os.path.basename(caminho)} ...")
        t0 = time.time()
        modelo = ModeloXadrez(caminho, threads=a.threads)
        busca = Busca(modelo, log=print)
        if not a.sem_ponder:
            ponder = Ponderador(modelo)
        modelo.analisar(chess.Board())   # aquecimento
        print(f"Modelo pronto em {time.time()-t0:.1f}s.")
    except Exception as e:
        print("!!! FALHA AO CARREGAR O MODELO — usando motor de reserva !!!")
        print("   ", repr(e))

    print("\n=== XEQUE-LFM ===  motor de", estado["cor"].upper(),
          f"| relógio do motor: {fmt_tempo(estado['restante'])} | digite 'ajuda'")
    desenhar(board, cor_motor)

    while not board.is_game_over(claim_draw=False):
        if board.turn == cor_motor:
            # ------------------------------------------------ vez do motor
            n_lance = board.fullmove_number
            restante = estado["restante"]
            faltam = max(15, 40 - n_lance * 0.5)
            orcamento = (restante - 45) / faltam - estado["overhead"]
            orcamento = max(0.3, min(orcamento, 60.0))
            if restante < 90:
                orcamento = min(orcamento, 1.0)
            print(f"\nPensando... (orçamento {orcamento:.1f}s, relógio {fmt_tempo(restante)})")
            t0 = time.monotonic()
            try:
                if busca is None:
                    raise RuntimeError("sem modelo")
                mv, info = busca.melhor_lance(board, orcamento)
                extra = (f"prof={info.get('prof')} vitória≈{info.get('valor', 0.5)*100:.0f}% "
                         f"nós={info.get('nos', 0)}")
            except Exception as e:
                traceback.print_exc()
                print("!!! erro no motor principal — usando reserva")
                mv = lance_reserva(board, min(3.0, orcamento)); extra = "reserva"
            gasto = time.monotonic() - t0
            estado["restante"] -= gasto + estado["overhead"]
            san = board.san(mv)
            linhas = instrucoes(board, mv)
            board.push(mv); estado["lances"].append(mv.uci()); salvar(estado)
            print("\n" + "=" * 52)
            print(f"   LANCE DO MOTOR:  {san_pt(san) if notacao=='pt' else san}    ({mv.uci()})")
            for l in linhas:
                print("   " + l)
            print(f"   [{gasto:.1f}s | {extra} | relógio ≈ {fmt_tempo(estado['restante'])}]")
            print("=" * 52)
            print("   >> Mova a peça e APERTE O RELÓGIO <<")
            continue

        # ---------------------------------------------------- vez do adversário
        if ponder is not None and ponder.thread is None:
            ponder.iniciar(board)
        try:
            txt = input("\nLance do ADVERSÁRIO (ex: e7e5, Cf6, O-O): ").strip()
        except EOFError:
            break
        if not txt:
            continue
        cmd = txt.lower()
        if cmd in ("sair", "exit", "quit"):
            print("Partida salva. Use --retomar para continuar."); return
        if cmd == "ajuda":
            print(__doc__); print("Formatos aceitos: e2e4 | e2-e4 | Cf3 (pt) | O-O | e7e8d (promoção)"); continue
        if cmd == "tabuleiro":
            desenhar(board, cor_motor); continue
        if cmd == "fen":
            print(board.fen()); continue
        if cmd == "pgn":
            print(exportar_pgn(board, estado)); continue
        if cmd == "desfazer":
            if ponder is not None:
                ponder.parar()
            if estado["lances"]:
                board.pop(); estado["lances"].pop()
                if board.turn == cor_motor and estado["lances"]:
                    board.pop(); estado["lances"].pop()
                salvar(estado); print("Desfeito."); desenhar(board, cor_motor)
            continue
        if cmd.startswith("tempo"):
            m = re.search(r"(\d+):(\d+)", cmd)
            if m:
                estado["restante"] = int(m.group(1)) * 60 + int(m.group(2)); salvar(estado)
                print("Relógio do motor ajustado para", fmt_tempo(estado["restante"]))
            continue
        mv = ler_lance(board, txt, notacao)
        if mv is None:
            legais = ", ".join(sorted(m.uci() for m in board.legal_moves))
            print(f"  Lance inválido/ilegal: '{txt}'. Legais: {legais}")
            continue
        if ponder is not None:
            ponder.parar()
        print(f"  Adversário: {san_pt(board.san(mv)) if notacao=='pt' else board.san(mv)} ({mv.uci()})")
        board.push(mv); estado["lances"].append(mv.uci()); salvar(estado)

    desenhar(board, cor_motor)
    print("FIM DE JOGO:", board.result(), "-", board.outcome().termination.name if board.outcome() else "")
    print("PGN salvo em:", exportar_pgn(board, estado))


if __name__ == "__main__":
    main()
