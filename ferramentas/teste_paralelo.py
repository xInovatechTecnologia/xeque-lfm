import os, sys, time, multiprocessing as mp
import numpy as np
AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, AQUI)
_m = None
def init(caminho, th):
    global _m
    from motor.modelo import ModeloXadrez
    _m = ModeloXadrez(caminho, threads=th)
def valor(fen_moves):
    import chess
    fen, mv = fen_moves
    b = chess.Board(fen); [b.push_uci(x) for x in mv]
    _m.cache.clear()
    return _m.analisar(b, com_politica=False)[0]
if __name__ == "__main__":
    import chess
    cam = os.path.join(AQUI, "modelo", "XequeLFM-230M.Q8_0.gguf")
    b = chess.Board(); jobs = []
    for m1 in list(b.legal_moves)[:12]:
        b.push(m1)
        for m2 in list(b.legal_moves)[:6]:
            jobs.append((chess.STARTING_FEN, [m1.uci(), m2.uci()]))
        b.pop()
    for w, th in [(1, 11), (2, 6), (3, 4), (4, 3), (6, 2), (12, 1)]:
        with mp.Pool(w, initializer=init, initargs=(cam, th)) as p:
            p.map(valor, jobs[:w * 2])
            t = time.perf_counter(); p.map(valor, jobs, chunksize=2); dt = time.perf_counter() - t
        print(f"workers={w:2d} threads={th:2d}: {dt/len(jobs)*1000:6.1f} ms/nó efetivo", flush=True)
