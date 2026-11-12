"""Roda o homebench com o limite de tokens de todas as tarefas elevado para 2048.

As tarefas embutidas têm limites fixos de 60-300 tokens, que modelos com raciocínio
gastam inteiros antes de responder. Uso: python hb_bigtokens.py run ...
"""
import sys

from homebench.quality import tasks

for t in tasks._TASKS:
    t.max_tokens = 2048

from homebench.cli import main

sys.exit(main(sys.argv[1:]))
