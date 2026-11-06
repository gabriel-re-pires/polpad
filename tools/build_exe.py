"""Gera o executável distribuível do Polpad.

    .venv\\Scripts\\python tools\\build_exe.py      (Windows)
    .venv/bin/python tools/build_exe.py           (Linux)

Produz ``dist/Polpad/Polpad.exe`` (uma pasta) no Windows e ``dist/Polpad``
(arquivo único) no Linux, sem console e sem precisar de Python. No
Windows, ``--instalador`` gera também ``dist/Polpad-Setup.exe`` com o Inno
Setup 6 (``tools/polpad.iss``), que é o que se publica. No Linux,
``dist/Polpad --instalar-no-menu`` coloca o executável no menu de
aplicativos, com o ícone.

Com o aplicativo aberto, o Windows não deixa sobrescrever o ``.exe`` em
execução e o PyInstaller falha com "Acesso negado". Feche o aplicativo
(menu da bandeja → Sair) ou gere em outra pasta::

    .venv\\Scripts\\python tools\\build_exe.py --destino build\\teste

Detalhes que o empacotamento exige:

* ``keyring`` e ``pynput`` escolhem seu backend em tempo de execução,
  importando módulos que o PyInstaller não vê na análise estática; por
  isso são coletados por inteiro (no Linux também o ``Xlib``, que o
  backend xorg do pynput e a detecção do app em foco usam). No Linux o
  backend xorg do pynput vai também por ``--hidden-import``: coletá-lo
  exige importar o pynput, o que sem servidor X falha.
* O ícone (``polvo-roxo.ico``) é copiado antes para build/ e os PNGs
  da janela vão junto com ``--add-data`` (ver ``make_icon.py``). O ícone
  embutido no arquivo só existe no Windows; no Linux quem mostra o ícone
  é o ``.desktop`` instalado.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ICONE = RAIZ / "build" / "polpad.ico"
NOME = "Polpad"
WINDOWS = sys.platform == "win32"
# Backend X11 do pynput, que ele escolhe em tempo de execução (ver main()).
_PYNPUT_XORG = (
    "pynput.keyboard._xorg",
    "pynput.mouse._xorg",
    "pynput._util.xorg",
    "pynput._util.xorg_keysyms",
)


def _run(argv: list[str], descricao: str) -> None:
    print(f"\n>>> {descricao}")
    resultado = subprocess.run(argv, cwd=RAIZ)
    if resultado.returncode != 0:
        raise SystemExit(f"falhou: {descricao} (código {resultado.returncode})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destino",
        type=Path,
        default=RAIZ / "dist",
        help=(
            "pasta onde gravar o executável (padrão: dist/). Útil quando o "
            "aplicativo está aberto: o Windows não deixa sobrescrever um .exe "
            "em execução, e o PyInstaller falha com “Acesso negado”."
        ),
    )
    parser.add_argument(
        "--instalador",
        action="store_true",
        help="Windows: depois do executável, gera dist/Polpad-Setup.exe (Inno Setup 6)",
    )
    args = parser.parse_args()
    destino = args.destino.resolve()
    if args.instalador and not WINDOWS:
        raise SystemExit("--instalador é só para Windows")
    iscc = _iscc() if args.instalador else None

    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit(
            'PyInstaller não encontrado. Instale com: pip install -e ".[dev]"'
        )

    # Separador origem/destino do --add-data: ";" no Windows, ":" no Linux.
    assets = RAIZ / "src" / "polpad" / "ui" / "assets"
    add_assets = f"{assets}{os.pathsep}polpad/ui/assets"
    por_plataforma: list[str] = []
    if WINDOWS:
        _run([sys.executable, str(RAIZ / "tools" / "make_icon.py")], "gerando o ícone")
        por_plataforma += ["--icon", str(ICONE)]
    else:
        por_plataforma += ["--collect-submodules", "Xlib"]
        # O --collect-submodules do pynput precisa importá-lo, e no Linux
        # importar o pynput exige um servidor X. Sem tela (CI, SSH) a coleta
        # falha com só um aviso e o executável sai sem o backend xorg, que
        # fecha ao abrir. --hidden-import analisa sem importar.
        for modulo in _PYNPUT_XORG:
            por_plataforma += ["--hidden-import", modulo]

    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            # Windows: pasta, instalada pelo Inno Setup (abre mais rápido e
            # gera menos falsos alarmes de antivírus). Linux: arquivo único,
            # trocado inteiro pelo atualizador.
            "--onedir" if WINDOWS else "--onefile",
            "--windowed",
            "--name",
            NOME,
            "--distpath",
            str(destino),
            # Intermediários e o .spec ficam em build/, não na raiz do projeto.
            "--workpath",
            str(RAIZ / "build" / "pyinstaller"),
            "--specpath",
            str(RAIZ / "build"),
            "--paths",
            str(RAIZ / "src"),
            # Ícones do aplicativo (janela, bandeja e barra superior).
            "--add-data",
            add_assets,
            # Backends resolvidos em tempo de execução.
            "--collect-submodules",
            "keyring.backends",
            "--collect-submodules",
            "pynput",
            # O esptool resolve a classe do chip pelo nome e lê o stub de
            # gravação de arquivos JSON de dados — nada disso aparece na
            # análise estática do PyInstaller.
            "--collect-submodules",
            "esptool",
            "--collect-data",
            "esptool",
            *por_plataforma,
            # Módulos Qt pesados que o aplicativo não usa.
            "--exclude-module",
            "PySide6.QtWebEngineCore",
            "--exclude-module",
            "PySide6.QtWebEngineWidgets",
            "--exclude-module",
            "PySide6.Qt3DCore",
            "--exclude-module",
            "PySide6.QtMultimedia",
            "--exclude-module",
            "tkinter",
            str(RAIZ / "tools" / "entrypoint.py"),
        ],
        "empacotando com o PyInstaller",
    )

    exe = destino / NOME / f"{NOME}.exe" if WINDOWS else destino / NOME
    if not exe.exists():
        raise SystemExit("o PyInstaller terminou sem produzir o executável")
    print(f"\nPronto: {exe}")
    if iscc is not None:
        licenca = _licenca()
        grande, pequena, desinstalar = _imagens_do_assistente()
        _run(
            [
                iscc,
                f"/DVersao={_versao()}",
                f"/DOrigem={destino / NOME}",
                f"/DIcone={ICONE}",
                f"/DLicenca={licenca}",
                f"/DImagemGrande={grande}",
                f"/DImagemPequena={pequena}",
                f"/DImagemDesinstalar={desinstalar}",
                f"/O{destino}",
                str(RAIZ / "tools" / "polpad.iss"),
            ],
            "gerando o instalador com o Inno Setup",
        )
        setup = destino / f"{NOME}-Setup.exe"
        print(f"Pronto: {setup} ({setup.stat().st_size / 1024 / 1024:.1f} MB)")
    if not WINDOWS:
        print("Para pôr no menu: dist/Polpad --instalar-no-menu")
    return 0


def _licenca() -> Path:
    """Resumo em português seguido do texto oficial da GPL v3.

    UTF-8 com BOM: é como o Inno Setup reconhece o texto acentuado.
    """
    resumo = (RAIZ / "tools" / "licenca-resumo.txt").read_text(encoding="utf-8")
    gpl = (RAIZ / "LICENSE").read_text(encoding="utf-8")
    destino = RAIZ / "build" / "licenca.txt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(resumo + gpl, encoding="utf-8-sig")
    return destino


POLVO_GRANDE = (
    RAIZ / "docs" / "marca" / "polvo-encoder" / "png" / "polvo-roxo" / "polvo-roxo-1024.png"
)
# Degradê roxo-escuro do painel (topo → base), da família do roxo da marca.
ROXO_TOPO = (48, 16, 104)
ROXO_BASE = (22, 7, 52)


def _painel(largura: int, altura: int):
    """Painel roxo com metade do polvo, grande, saindo da borda esquerda."""
    from PIL import Image

    fundo = Image.new("RGBA", (largura, altura))
    for y in range(altura):
        t = y / max(altura - 1, 1)
        cor = tuple(round(a + (b - a) * t) for a, b in zip(ROXO_TOPO, ROXO_BASE))
        fundo.paste((*cor, 255), (0, y, largura, y + 1))
    lado = int(largura * 1.9)
    polvo = Image.open(POLVO_GRANDE).convert("RGBA").resize((lado, lado), Image.LANCZOS)
    camada = Image.new("RGBA", (largura, altura))
    # O centro do polvo fica na borda: aparece só a metade direita.
    camada.paste(polvo, (-lado // 2, int(altura * 0.58) - lado // 2), polvo)
    fundo.alpha_composite(camada)
    return fundo.convert("RGB")


def _imagens_do_assistente() -> tuple[str, str, str]:
    """Imagens do instalador, em 100% e 200% de escala.

    A grande (164x314) fica à esquerda nas páginas de boas-vindas e de
    conclusão; a pequena (55x55) fica no canto das outras páginas, sobre o
    branco do cabeçalho. A de desinstalar (150x260, só em 200%: a tela a
    estica) vai junto do programa, porque o desinstalador não tem as
    imagens do instalador. O Inno Setup lê BMP de 24 bits.
    """
    from PIL import Image

    polvo = Image.open(RAIZ / "src" / "polpad" / "ui" / "assets" / "polvo-roxo-256.png")
    polvo = polvo.convert("RGBA")
    pasta = RAIZ / "build"
    pasta.mkdir(parents=True, exist_ok=True)
    grandes, pequenas = [], []
    for escala in (1, 2):
        caminho = pasta / f"assistente-grande-{escala}x.bmp"
        _painel(164 * escala, 314 * escala).save(caminho)
        grandes.append(str(caminho))

        lado_p = 55 * escala
        fundo_p = Image.new("RGBA", (lado_p, lado_p), (255, 255, 255, 255))
        icone_p = polvo.resize((lado_p - 6 * escala,) * 2, Image.LANCZOS)
        fundo_p.alpha_composite(icone_p, (3 * escala, 3 * escala))
        caminho_p = pasta / f"assistente-pequena-{escala}x.bmp"
        fundo_p.convert("RGB").save(caminho_p)
        pequenas.append(str(caminho_p))
    desinstalar = pasta / "desinstalar.bmp"
    _painel(150 * 2, 260 * 2).save(desinstalar)
    return ",".join(grandes), ",".join(pequenas), str(desinstalar)


def _versao() -> str:
    init = (RAIZ / "src" / "polpad" / "__init__.py").read_text(encoding="utf-8")
    achado = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    if not achado:
        raise SystemExit("versão não encontrada em src/polpad/__init__.py")
    return achado.group(1)


def _iscc() -> str:
    """Compilador do Inno Setup 6: no PATH ou nas pastas de instalação."""
    achado = shutil.which("iscc") or shutil.which("ISCC")
    if achado:
        return achado
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if not base:
            continue
        for pasta in ("Inno Setup 6", os.path.join("Programs", "Inno Setup 6")):
            candidato = Path(base) / pasta / "ISCC.exe"
            if candidato.is_file():
                return str(candidato)
    raise SystemExit(
        "Inno Setup 6 não encontrado. Instale com: winget install JRSoftware.InnoSetup"
    )


if __name__ == "__main__":
    raise SystemExit(main())
