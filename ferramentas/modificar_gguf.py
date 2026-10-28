#!/usr/bin/env python3
"""
Gera o GGUF da equipe a partir do LFM2.5-230M-Chess original.

O que é modificado (pesos preservados bit a bit):
  - general.name / description / version / organization -> identidade Xeque-LFM
  - tokenizer.chat_template -> template "raw" que repassa o conteúdo das
    mensagens sem os marcadores de chat (<|im_start|> ...). O template
    original é de chat genérico e o modelo NÃO foi treinado em chat; com o
    novo template o modelo funciona via llamafile/llama-server enviando o
    prompt de 80 tokens como texto.
  - xeque.* -> especificação do protocolo de entrada e parâmetros da busca,
    embutidos no próprio arquivo (autodocumentado).

Uso: python ferramentas/modificar_gguf.py ORIGINAL.gguf SAIDA.gguf
"""
import sys
from gguf import GGUFReader, GGUFWriter, GGUFValueType

TEMPLATE_RAW = "{{- bos_token -}}{%- for message in messages -%}{{- message['content'] -}}{%- endfor -%}"

NOVOS = {
    "general.name": "Xeque-LFM 230M",
    "general.version": "1.0",
    "general.organization": "Equipe iCEV - Chess Challenge III",
    "general.description": ("LFM2.5-230M-Chess com protocolo de 80 tokens documentado e busca "
                            "minimax alfa-beta guiada por politica/valor (motor Xeque-LFM)."),
    "tokenizer.chat_template": TEMPLATE_RAW,
    "xeque.prompt_format": ("<BOS><|pos|> 64x<c:X> (a8..h8,...,a1..h1) <stm:w|b> <cast:KQkq|-> "
                            "<ep:file|-> <hm:0..25> <rep:0..2> <|hist|> 8x(<m:uci>|<|pad|> a esquerda) "
                            "<|eval|> -> <v:k> (P(vitoria lado a jogar)=(k+0.5)/64) ; "
                            "+ <v:k><|bestmove|> -> <m:uci> (mascarar ilegais)"),
    "xeque.search": "negamax alfa-beta, aprofundamento iterativo, larguras 12/6/5/4/3, mate-em-1 em todos os lances",
}


def main(src, dst):
    r = GGUFReader(src)
    arch = r.fields["general.architecture"].contents()
    w = GGUFWriter(dst, arch=arch, use_temp_file=False)
    for k, f in r.fields.items():
        if k.startswith("GGUF.") or k == "general.architecture" or k in NOVOS:
            continue
        vt = f.types[0]
        if vt == GGUFValueType.ARRAY:
            w.add_key_value(k, f.contents(), vt, sub_type=f.types[-1])
        else:
            w.add_key_value(k, f.contents(), vt)
    for k, v in NOVOS.items():
        w.add_string(k, v)
    for t in r.tensors:
        w.add_tensor(t.name, t.data, raw_shape=t.data.shape, raw_dtype=t.tensor_type)
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    print("gerado:", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
