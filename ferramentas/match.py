#!/usr/bin/env python3
"""Partidas de teste: Xeque-LFM x Stockfish com Elo limitado.
Uso: python ferramentas/match.py --modo busca --tempo 8 --elo 1600 --jogos 4"""
import argparse, os, sys, time
import chess, chess.engine, chess.pgn
AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, AQUI)
from motor.modelo import ModeloXadrez
from motor.busca import Busca

ap = argparse.ArgumentParser()
ap.add_argument("--modo", choices=["busca", "politica"], default="busca")
ap.add_argument("--tempo", type=float, default=8.0)
ap.add_argument("--elo", type=int, default=1600)
ap.add_argument("--jogos", type=int, default=2)
ap.add_argument("--sf", default=os.path.join(AQUI, "ferramentas", "sf", "stockfish", "stockfish-windows-x86-64-avx2.exe"))
a = ap.parse_args()

m = ModeloXadrez(os.path.join(AQUI, "modelo", "XequeLFM-230M.Q8_0.gguf"))
busca = Busca(m)
sf = chess.engine.SimpleEngine.popen_uci(a.sf)
sf.configure({"UCI_LimitStrength": True, "UCI_Elo": a.elo, "Threads": 1})
pontos = 0.0
log = os.path.join(AQUI, "partidas", f"match_{a.modo}_{a.elo}.pgn")
for g in range(a.jogos):
    b = chess.Board(); nossa = chess.WHITE if g % 2 == 0 else chess.BLACK
    while not b.is_game_over(claim_draw=True) and b.ply() < 300:
        if b.turn == nossa:
            if a.modo == "politica":
                _, pol = m.analisar(b); mv = max(pol, key=pol.get)
            else:
                mv, _ = busca.melhor_lance(b, a.tempo)
        else:
            mv = sf.play(b, chess.engine.Limit(time=0.3)).move
        b.push(mv)
    r = b.result(claim_draw=True)
    pt = 0.5 if r == "1/2-1/2" else (1.0 if (r == "1-0") == (nossa == chess.WHITE) else 0.0)
    pontos += pt
    jogo = chess.pgn.Game.from_board(b)
    jogo.headers["White"] = "Xeque-LFM" if nossa else f"SF{a.elo}"; jogo.headers["Black"] = f"SF{a.elo}" if nossa else "Xeque-LFM"
    with open(log, "a", encoding="utf-8") as f: print(jogo, "\n", file=f)
    print(f"jogo {g+1}: {'brancas' if nossa else 'pretas'} {r} -> {pt}  ({b.ply()} plies) | total {pontos}/{g+1}", flush=True)
sf.quit()
print(f"RESULTADO {a.modo} vs SF{a.elo}: {pontos}/{a.jogos}")
