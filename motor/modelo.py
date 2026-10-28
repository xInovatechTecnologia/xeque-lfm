"""
Camada do modelo: codifica a posição no prompt de 80 tokens que o
LFM2.5-230M-Chess espera e devolve (a) a probabilidade de vitória do lado
que joga e (b) a distribuição de probabilidade SOMENTE sobre lances legais.

Formato (descoberto empiricamente e validado: ~98% da massa de probabilidade
cai em lances legais sem máscara):

  <BOS> <|pos|> 64x<c:X> (a8..h8, a7..h7, ..., a1..h1)
        <stm:w|b> <cast:KQkq|-> <ep:arquivo|-> <hm:0..25> <rep:0..2>
        <|hist|> 8x(<m:uci> | <|pad|> à esquerda)
        <|eval|>  -> modelo prevê <v:k>   (k/64 = P(vitória) do lado que joga)
        <v:k> <|bestmove|> -> modelo prevê <m:uci>
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict

import chess
import llama_cpp
import numpy as np

N_HIST = 8


class ModeloXadrez:
    def __init__(self, caminho_gguf: str, threads: int | None = None, cache_max: int = 200_000):
        from llama_cpp import Llama  # import tardio: permite rodar o fallback sem a lib

        if threads is None:
            threads = max(1, (os.cpu_count() or 2) - 1)
        self.llm = Llama(
            model_path=caminho_gguf,
            n_ctx=128,
            n_batch=128,
            n_threads=threads,
            n_threads_batch=threads,
            logits_all=False,
            verbose=False,
        )
        self.lock = threading.Lock()
        self._mapear_tokens()
        self.cache: OrderedDict = OrderedDict()
        self.cache_max = cache_max
        self.nos_avaliados = 0

    # ------------------------------------------------------------------ tokens
    def _tid(self, texto: str) -> int:
        ids = self.llm.tokenize(texto.encode(), add_bos=False, special=True)
        if len(ids) != 1:
            raise ValueError(f"token especial ausente no GGUF: {texto}")
        return ids[0]

    def _mapear_tokens(self):
        t = self._tid
        self.BOS = self.llm.token_bos()
        self.POS, self.HIST, self.EVAL, self.BEST, self.PAD = (
            t("<|pos|>"), t("<|hist|>"), t("<|eval|>"), t("<|bestmove|>"), t("<|pad|>"))
        self.CELL = {s: t(f"<c:{s}>") for s in ".PNBRQKpnbrqk"}
        self.STM = {True: t("<stm:w>"), False: t("<stm:b>")}
        self.CAST = {}
        for c in ["-"] + ["".join(x for x, on in zip("KQkq", bits) if on)
                          for bits in __import__("itertools").product([0, 1], repeat=4)][1:]:
            self.CAST[c] = t(f"<cast:{c}>")
        self.EP = {f: t(f"<ep:{f}>") for f in "-abcdefgh"}
        self.HM = [t(f"<hm:{i}>") for i in range(26)]
        self.REP = [t(f"<rep:{i}>") for i in range(3)]
        self.V = np.array([t(f"<v:{k}>") for k in range(64)])
        # mapa uci -> id (1968 lances geometricamente possíveis)
        vocab_n = self.llm.n_vocab()
        self.MOVE = {}
        for i in range(vocab_n - 2200, vocab_n):
            s = self.llm.detokenize([i], special=True).decode("utf8", "replace")
            if s.startswith("<m:") and s.endswith(">"):
                self.MOVE[s[3:-1]] = i
        if len(self.MOVE) < 1900:
            raise RuntimeError("vocabulário de lances não encontrado — GGUF errado?")
        self.BINS = (np.arange(64) + 0.5) / 64.0
        self.n_vocab = vocab_n

    # ---------------------------------------------------------------- encoding
    def codificar(self, board: chess.Board) -> list[int]:
        ids = [self.BOS, self.POS]
        pm = board.piece_map()
        for rank in range(7, -1, -1):
            for file in range(8):
                p = pm.get(chess.square(file, rank))
                ids.append(self.CELL[p.symbol() if p else "."])
        ids.append(self.STM[board.turn])
        ids.append(self.CAST[board.castling_xfen()])
        ep = "-"
        if board.ep_square is not None and board.has_legal_en_passant():
            ep = chess.square_name(board.ep_square)[0]
        ids.append(self.EP[ep])
        ids.append(self.HM[min(board.halfmove_clock, 25)])
        rep = 2 if board.is_repetition(3) else (1 if board.is_repetition(2) else 0)
        ids.append(self.REP[rep])
        ids.append(self.HIST)
        hist = [self.MOVE[m.uci()] for m in board.move_stack[-N_HIST:] if m.uci() in self.MOVE]
        ids.extend([self.PAD] * (N_HIST - len(hist)) + hist)
        ids.append(self.EVAL)
        return ids

    # --------------------------------------------------------------- inference
    def _ultimos_logits(self) -> np.ndarray:
        # llama-cpp-python não preenche .scores com logits_all=False;
        # lemos os logits do último token direto do contexto (sem cópia).
        ptr = llama_cpp.llama_get_logits_ith(self.llm._ctx.ctx, -1)
        return np.ctypeslib.as_array(ptr, shape=(self.n_vocab,))

    def _softmax(self, x):
        x = np.asarray(x, dtype=np.float64)
        x = np.exp(x - x.max())
        return x / x.sum()

    def analisar(self, board: chess.Board, com_politica: bool = True):
        """Retorna (p_vitoria_lado_que_joga, {chess.Move: prob}) — política só se pedida."""
        ids = self.codificar(board)
        chave = (tuple(ids), com_politica)
        if chave in self.cache:
            self.cache.move_to_end(chave)
            return self.cache[chave]
        if not com_politica and (tuple(ids), True) in self.cache:
            return self.cache[(tuple(ids), True)][0], None
        with self.lock:
            llm = self.llm
            llm.reset()
            llm.eval(ids)
            lv = np.array(self._ultimos_logits()[self.V])
            pv = self._softmax(lv)
            valor = float((pv * self.BINS).sum())
            politica = None
            if com_politica:
                k = int(pv.argmax())
                llm.eval([int(self.V[k]), self.BEST])
                logits = self._ultimos_logits()
                legais = [m for m in board.legal_moves if m.uci() in self.MOVE]
                if legais:
                    lm = np.array([logits[self.MOVE[m.uci()]] for m in legais])
                    pm = self._softmax(lm)
                    politica = dict(zip(legais, pm.tolist()))
                else:
                    politica = {}
        self.nos_avaliados += 1
        res = (valor, politica)
        self.cache[chave] = res
        if len(self.cache) > self.cache_max:
            self.cache.popitem(last=False)
        return res
