"""Ponto de entrada do executável (imports relativos não resolvem no ``__main__``).

No Linux o PyInstaller aponta ``LD_LIBRARY_PATH`` para as bibliotecas embutidas,
e os programas abertos pelas teclas as herdariam. Restaurar aqui não afeta o
Polpad: o carregador só lê a variável na partida.
"""

import os
import sys

if sys.platform.startswith("linux"):
    original = os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is not None:
        os.environ["LD_LIBRARY_PATH"] = original
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)

# Importado só depois de limpar o ambiente.
from polpad.__main__ import main

raise SystemExit(main())
