"""
Busca: negamax com poda alfa-beta sobre o espaço de probabilidade de vitória.

Modificações em relação ao modelo original (que sozinho só faz 1 passada):
  1. Aprofundamento iterativo (profundidade 1, 2, 3, 4...) com prazo rígido:
     sempre existe um lance pronto, nunca estoura o relógio.
  2. Poda pela política do modelo: só expande os K lances mais prováveis
     (largura decrescente por nível: 12, 6, 5, 4...).
  3. Extensões táticas: xeque-mate em 1 é detectado em TODOS os lances
     (não só nos K da política); capturas e xeques entram na raiz.
  4. Tratamento exato de fim de jogo: mate, afogamento, material insuficiente,
     repetição e regra dos 50 lances.
  5. Tabela de transposição + cache de avaliações do modelo.
  6. Ponderação: pensa durante o tempo do adversário nas respostas mais
     prováveis dele; o cache acelera a busca quando o lance real chega.
"""
from __future__ import annotations

import threading
import time

import chess

LARGURAS = [10, 5, 4, 3, 3]
MATE = 0.0          # pontuação de quem levou mate (lado que joga)
EMPATE = 0.5


class TempoEsgotado(Exception):
    pass


class Busca:
    def __init__(self, modelo, larguras=None, log=None):
        self.m = modelo
        self.larguras = larguras or LARGURAS
        self.log = log or (lambda *a: None)
        self.tt: dict = {}
        self.parar = threading.Event()
        self.prazo = 0.0

    # -------------------------------------------------------------- terminal
    @staticmethod
    def _terminal(board: chess.Board, ply: int):
        if board.is_checkmate():
            return MATE + ply * 1e-4          # mate mais distante é "menos ruim"
        if (board.is_stalemate() or board.is_insufficient_material()
                or board.halfmove_clock >= 100 or board.is_repetition(3)):
            return EMPATE
        if ply > 0 and board.is_repetition(2):
            return EMPATE
        return None

    def _candidatos(self, board, politica, largura, raiz):
        ordenados = sorted(politica.items(), key=lambda kv: -kv[1])
        escolhidos = [m for m, _ in ordenados[:largura]]
        extras = []
        for m in board.legal_moves:
            if m in escolhidos:
                continue
            board.push(m)
            mate = board.is_checkmate()
            board.pop()
            if mate:
                extras.insert(0, m)
            elif raiz and (board.is_capture(m) or board.gives_check(m)):
                extras.append(m)
        return extras[:1] + escolhidos + extras[1:8] if extras else escolhidos

    # ---------------------------------------------------------------- negamax
    def _negamax(self, board, prof, alfa, beta, ply):
        if time.monotonic() > self.prazo or self.parar.is_set():
            raise TempoEsgotado
        t = self._terminal(board, ply)
        if t is not None:
            return t, None
        if prof == 0:
            v, _ = self.m.analisar(board, com_politica=False)
            return v, None

        chave = (board._transposition_key(), prof)
        if chave in self.tt:
            return self.tt[chave]
        alfa_orig = alfa

        v_est, pol = self.m.analisar(board, com_politica=True)
        largura = self.larguras[min(ply, len(self.larguras) - 1)]
        cand = self._candidatos(board, pol, largura, raiz=(ply == 0))
        melhor, melhor_lance = -1.0, None
        for mv in cand:
            board.push(mv)
            try:
                filho, _ = self._negamax(board, prof - 1, 1 - beta, 1 - alfa, ply + 1)
            finally:
                board.pop()
            s = 1.0 - filho
            if s > melhor:
                melhor, melhor_lance = s, mv
            alfa = max(alfa, s)
            if alfa >= beta:
                break
        if alfa_orig < melhor < beta:          # só guarda valores exatos
            self.tt[chave] = (melhor, melhor_lance)
        return melhor, melhor_lance

    # ------------------------------------------------------------------ raiz
    def melhor_lance(self, board: chess.Board, tempo_s: float, prof_max: int | None = None):
        # Profundidade 4 custa ~4x a 3; só tenta quando há orçamento folgado.
        if prof_max is None:
            prof_max = 4 if tempo_s >= 40 else 3
        legais = list(board.legal_moves)
        if len(legais) == 1:
            return legais[0], {"motivo": "único lance", "prof": 0}
        self.prazo = time.monotonic() + tempo_s
        self.tt.clear()
        inicio = time.monotonic()
        nos0 = self.m.nos_avaliados

        v0, pol = self.m.analisar(board, com_politica=True)
        lance = max(pol, key=pol.get)            # política pura = rede de segurança
        info = {"prof": 0, "valor": v0, "lance_politica": lance.uci()}
        for prof in range(1, prof_max + 1):
            try:
                valor, mv = self._negamax(board, prof, -0.01, 1.01, 0)
            except TempoEsgotado:
                break
            if mv is not None:
                lance = mv
                info.update(prof=prof, valor=valor)
            self.log(f"  prof {prof}: {board.san(lance)} valor={valor:.3f} "
                     f"({time.monotonic()-inicio:.1f}s)")
            if valor >= 0.999 or valor <= 0.001:   # mate encontrado
                break
            # não começa uma iteração que provavelmente não termina
            gasto = time.monotonic() - inicio
            if gasto > tempo_s * 0.35:
                break
        info["nos"] = self.m.nos_avaliados - nos0
        info["tempo"] = time.monotonic() - inicio
        return lance, info


class Ponderador:
    """Busca em segundo plano enquanto o adversário pensa (preenche o cache do modelo)."""

    def __init__(self, modelo, larguras=None):
        self.busca = Busca(modelo, larguras)
        self.thread = None

    def iniciar(self, board: chess.Board, n_respostas: int = 3):
        self.parar()
        self.busca.parar.clear()
        b = board.copy()
        self.thread = threading.Thread(target=self._rodar, args=(b, n_respostas), daemon=True)
        self.thread.start()

    def _rodar(self, board, n_respostas):
        try:
            if board.is_game_over():
                return
            _, pol = self.busca.m.analisar(board, com_politica=True)
            respostas = sorted(pol, key=pol.get, reverse=True)[:n_respostas]
            for prof in range(1, 5):            # aprofunda todas as respostas juntas
                for r in respostas:
                    if self.busca.parar.is_set():
                        return
                    board.push(r)
                    try:
                        if not board.is_game_over():
                            self.busca.prazo = float("inf")
                            self.busca.tt.clear()
                            self.busca._negamax(board, prof, -0.01, 1.01, 0)
                    except TempoEsgotado:
                        return
                    finally:
                        board.pop()
        except Exception:
            pass

    def parar(self):
        self.busca.parar.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
            self.thread = None
