#!/usr/bin/env python3
"""Mede velocidade (ms por nó) e acerto tático do Xeque-LFM nesta máquina."""
import argparse, os, sys, time
import chess
AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
from motor.modelo import ModeloXadrez
from motor.busca import Busca

TESTES = [  # (descrição, FEN, lance esperado)
    ("Mate em 1 (pastor)", "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", "h5f7"),
    ("Mate do corredor", "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", "d1d8"),
    ("Garfo de cavalo", "r3k2r/ppp2ppp/2n5/1N1q4/8/8/PPP2PPP/R3K2R w KQkq - 0 1", "b5c7"),
    ("Captura dama pendurada", "rnb1kbnr/pppp1ppp/8/4p1q1/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 1 3", "c1g5"),
    ("Defender mate em 1", "rnbqkbnr/pppp1ppp/8/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR b KQkq - 3 3", None),
]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--rapido", action="store_true")
    ap.add_argument("--tempo", type=float, default=10); ap.add_argument("--threads", type=int)
    a = ap.parse_args()
    nome = "XequeLFM-230M.Q8_0.gguf"
    cam = os.path.join(AQUI, "modelo", nome)
    if not os.path.exists(cam): cam = os.path.join(AQUI, "modelo", "LFM2.5-230M-Chess.Q8_0.gguf")
    m = ModeloXadrez(cam, threads=a.threads)
    b = chess.Board(); m.analisar(b)
    t = time.perf_counter(); n = 40
    for i in range(n):
        m.cache.clear(); m.analisar(b, com_politica=(i % 2 == 0))
    ms = (time.perf_counter() - t) / n * 1000
    print(f"Velocidade: {ms:.0f} ms por nó  (threads={m.llm.n_threads})")
    print(f"Estimativa: profundidade 3 (~400 nós) em ~{400*ms/1000:.0f}s")
    busca = Busca(m)
    ok = 0
    for desc, fen, exp in TESTES[: 3 if a.rapido else None]:
        bd = chess.Board(fen)
        mv, info = busca.melhor_lance(bd, a.tempo)
        bd2 = bd.copy(); bd2.push(mv)
        if exp is None:
            # o adversário não pode ter mate em 1
            acerto = True
            for x in list(bd2.legal_moves):
                bd2.push(x); mate = bd2.is_checkmate(); bd2.pop()
                if mate: acerto = False; break
        else:
            acerto = mv.uci() == exp
        ok += acerto
        print(f"  [{'OK ' if acerto else 'ERRO'}] {desc}: {bd.san(mv)} (prof {info.get('prof')}, {info.get('tempo',0):.1f}s)")
    print(f"Acertos: {ok}/{len(TESTES[: 3 if a.rapido else None])}")

if __name__ == "__main__":
    main()
