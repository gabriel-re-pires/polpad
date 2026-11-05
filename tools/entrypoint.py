"""Ponto de entrada do executável empacotado.

O PyInstaller carrega o script inicial como ``__main__`` de nível
superior, onde os imports relativos de ``macropad/__main__.py`` não
resolveriam. Este arquivo apenas importa o pacote e chama ``main()``.

No Linux o PyInstaller aponta ``LD_LIBRARY_PATH`` para as bibliotecas
embutidas (Qt, OpenSSL...). Os programas que as teclas abrem — terminal,
navegador, ``xdg-open`` — herdariam esse caminho e poderiam carregar
versões incompatíveis. O carregador dinâmico lê a variável só na partida
deste processo, então restaurar o valor original aqui não afeta o Polpad.
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
