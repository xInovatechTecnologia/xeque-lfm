#!/usr/bin/env python3
"""Protocolo UCI — para testar o Xeque-LFM em Arena, Cute Chess, BanksiaGUI etc."""
import os, sys, time
import chess
AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
from motor.modelo import ModeloXadrez
from motor.busca import Busca
from motor.reserva import lance_reserva

def main():
    caminho = sys.argv[1] if len(sys.argv) > 1 else None
    if not caminho:
        for n in ("XequeLFM-230M.Q8_0.gguf", "LFM2.5-230M-Chess.Q8_0.gguf"):
            p = os.path.join(AQUI, "modelo", n)
            if os.path.exists(p): caminho = p; break
    modelo = busca = None
    board = chess.Board()
    out = lambda s: (sys.stdout.write(s + "\n"), sys.stdout.flush())
    for linha in sys.stdin:
        tk = linha.split()
        if not tk: continue
        c = tk[0]
        if c == "uci":
            out("id name Xeque-LFM 1.0"); out("id author Equipe iCEV"); out("uciok")
        elif c == "isready":
            if modelo is None:
                modelo = ModeloXadrez(caminho); busca = Busca(modelo)
            out("readyok")
        elif c == "ucinewgame":
            board = chess.Board()
        elif c == "position":
            if "startpos" in tk: board = chess.Board()
            elif "fen" in tk:
                i = tk.index("fen"); board = chess.Board(" ".join(tk[i+1:i+7]))
            if "moves" in tk:
                for u in tk[tk.index("moves")+1:]: board.push_uci(u)
        elif c == "go":
            a = dict(zip(tk[1::2], tk[2::2]))
            if "movetime" in a: t = int(a["movetime"]) / 1000 * 0.9
            else:
                rest = int(a.get("wtime" if board.turn else "btime", 60000)) / 1000
                inc = int(a.get("winc" if board.turn else "binc", 0)) / 1000
                t = max(0.1, min(rest / max(15, 40 - board.fullmove_number * 0.5) + inc * 0.8, rest * 0.3))
            try:
                if modelo is None: modelo = ModeloXadrez(caminho); busca = Busca(modelo)
                mv, info = busca.melhor_lance(board, t)
                out(f"info depth {info.get('prof',0)} nodes {info.get('nos',0)} "
                    f"score cp {int((info.get('valor',0.5)-0.5)*800)}")
            except Exception:
                mv = lance_reserva(board, min(t, 2))
            out(f"bestmove {mv.uci()}")
        elif c == "quit":
            break

if __name__ == "__main__":
    main()
