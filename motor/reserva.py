"""Motor de reserva (sem rede neural): material + tabelas de casas, alfa-beta 2-3 plies.
Usado apenas se o modelo falhar ao carregar ou lançar exceção durante a partida."""
import time
import chess

VAL = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}
CENTRO = [0, 1, 2, 3, 3, 2, 1, 0]


def avaliar(b: chess.Board) -> int:
    if b.is_checkmate():
        return -100000
    if b.is_stalemate() or b.is_insufficient_material():
        return 0
    s = 0
    for sq, p in b.piece_map().items():
        v = VAL[p.piece_type]
        if p.piece_type in (chess.KNIGHT, chess.BISHOP, chess.PAWN):
            v += 4 * (CENTRO[chess.square_file(sq)] + CENTRO[chess.square_rank(sq)])
        s += v if p.color == b.turn else -v
    return s


def _ab(b, d, a, beta, prazo):
    if d == 0 or b.is_game_over() or time.monotonic() > prazo:
        return avaliar(b)
    mvs = sorted(b.legal_moves, key=lambda m: not b.is_capture(m))
    for m in mvs:
        b.push(m)
        s = -_ab(b, d - 1, -beta, -a, prazo)
        b.pop()
        if s >= beta:
            return s
        a = max(a, s)
    return a


def lance_reserva(b: chess.Board, tempo_s: float = 3.0) -> chess.Move:
    prazo = time.monotonic() + tempo_s
    melhor, mv_best = -10**9, next(iter(b.legal_moves))
    for prof in (2, 3):
        melhor_d, mv_d = -10**9, mv_best
        for m in sorted(b.legal_moves, key=lambda m: not b.is_capture(m)):
            b.push(m)
            s = -_ab(b, prof - 1, -10**9, 10**9, prazo)
            b.pop()
            if s > melhor_d:
                melhor_d, mv_d = s, m
        if time.monotonic() > prazo and prof > 2:
            break
        mv_best = mv_d
    return mv_best
