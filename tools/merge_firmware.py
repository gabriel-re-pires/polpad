"""Transforma a exportação da Arduino IDE em um binário único gravável.

    .venv\\Scripts\\python tools\\merge_firmware.py <pasta-da-exportacao>

A Arduino IDE (Sketch → *Exportar Binário Compilado*) deixa três arquivos
soltos — bootloader, tabela de partições e aplicação — que precisam ir
para endereços diferentes da memória flash. Este script os funde em um
``firmware-<versao>.bin`` que se grava inteiro em 0x0.

É esse arquivo que se anexa ao *release* do GitHub: o aplicativo o baixa e
grava sem precisar saber nada sobre layout de partições (ver
``src/polpad/device/flasher.py``).

Sem argumentos, procura a exportação dentro de ``firmware/``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKETCH = RAIZ / "firmware" / "macropad_firmware" / "macropad_firmware.ino"
CHIP = "esp32c3"

# Layout do core arduino-esp32 para o ESP32-C3.
BOOTLOADER_ADDR = 0x0
PARTITIONS_ADDR = 0x8000
BOOT_APP0_ADDR = 0xE000
APP_ADDR = 0x10000

FLASH_MODE = "dio"
FLASH_FREQ = "80m"
FLASH_SIZE = "4MB"


def firmware_version() -> str:
    """Lê ``FW_VERSION`` do sketch, para nomear a saída sem duplicar o dado."""
    try:
        texto = SKETCH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "0.0.0"
    match = re.search(r'FW_VERSION\s*\[\s*\]\s*=\s*"([^"]+)"', texto)
    return match.group(1) if match else "0.0.0"


def _localizar(pasta: Path, sufixo: str) -> Path:
    candidatos = sorted(pasta.glob(f"*{sufixo}"))
    if not candidatos:
        raise SystemExit(
            f"não encontrei um arquivo *{sufixo} em {pasta}.\n"
            "Rode Sketch → Exportar Binário Compilado na Arduino IDE e aponte "
            "para a pasta gerada (build/ dentro da pasta do sketch)."
        )
    if len(candidatos) > 1:
        raise SystemExit(
            f"há mais de um *{sufixo} em {pasta}: "
            + ", ".join(c.name for c in candidatos)
            + "\nDeixe apenas a exportação mais recente na pasta."
        )
    return candidatos[0]


def _app_bin(pasta: Path) -> Path:
    """A aplicação é o ``.ino.bin`` que não é bootloader nem partições."""
    candidatos = [
        caminho
        for caminho in sorted(pasta.glob("*.ino.bin"))
        if not caminho.name.endswith((".bootloader.bin", ".partitions.bin"))
    ]
    if len(candidatos) != 1:
        raise SystemExit(
            f"esperava exatamente um *.ino.bin (a aplicação) em {pasta}, "
            f"encontrei {len(candidatos)}."
        )
    return candidatos[0]


def _boot_app0(pasta: Path, explicito: Path | None) -> Path | None:
    """Localiza o ``boot_app0.bin`` do core arduino-esp32, se disponível.

    Ele zera a partição ``otadata`` para que o bootloader escolha ``ota_0``.
    Sem esse arquivo a gravação normalmente funciona (uma otadata em branco
    leva ao mesmo lugar), mas incluí-lo torna o resultado determinístico —
    inclusive por cima de um chip que já tinha uma imagem OTA.
    """
    if explicito is not None:
        if not explicito.is_file():
            raise SystemExit(f"boot_app0 não encontrado: {explicito}")
        return explicito
    local = pasta / "boot_app0.bin"
    if local.is_file():
        return local
    base = Path.home() / "AppData" / "Local" / "Arduino15" / "packages" / "esp32"
    achados = sorted(base.glob("hardware/esp32/*/tools/partitions/boot_app0.bin"))
    return achados[-1] if achados else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pasta",
        nargs="?",
        type=Path,
        help="pasta com a exportação da Arduino IDE (padrão: procura em firmware/)",
    )
    parser.add_argument("--boot-app0", type=Path, default=None)
    parser.add_argument("--saida", type=Path, default=None)
    args = parser.parse_args()

    pasta = args.pasta or _descobrir_pasta()
    if not pasta.is_dir():
        raise SystemExit(f"pasta inexistente: {pasta}")

    app = _app_bin(pasta)
    bootloader = _localizar(pasta, ".bootloader.bin")
    partitions = _localizar(pasta, ".partitions.bin")
    boot_app0 = _boot_app0(pasta, args.boot_app0)

    versao = firmware_version()
    saida = args.saida or (RAIZ / "dist" / f"firmware-{versao}.bin")
    saida.parent.mkdir(parents=True, exist_ok=True)

    partes: list[str] = [
        hex(BOOTLOADER_ADDR),
        str(bootloader),
        hex(PARTITIONS_ADDR),
        str(partitions),
    ]
    if boot_app0 is not None:
        partes += [hex(BOOT_APP0_ADDR), str(boot_app0)]
    else:
        print("aviso: boot_app0.bin não encontrado — seguindo sem ele.")
    partes += [hex(APP_ADDR), str(app)]

    argv = [
        sys.executable,
        "-m",
        "esptool",
        "--chip",
        CHIP,
        "merge-bin",
        "--output",
        str(saida),
        "--flash-mode",
        FLASH_MODE,
        "--flash-freq",
        FLASH_FREQ,
        "--flash-size",
        FLASH_SIZE,
        *partes,
    ]
    print(">>> fundindo a imagem com o esptool")
    resultado = subprocess.run(argv, cwd=RAIZ)
    if resultado.returncode != 0:
        raise SystemExit(f"o esptool falhou (código {resultado.returncode})")

    tamanho = saida.stat().st_size / 1024
    print(f"\nPronto: {saida} ({tamanho:.0f} KB)")
    print("Anexe este arquivo ao release do GitHub para o aplicativo baixá-lo.")
    return 0


def _descobrir_pasta() -> Path:
    """Procura a exportação nos lugares onde a Arduino IDE costuma deixá-la."""
    base = RAIZ / "firmware"
    for candidata in sorted(base.rglob("*.ino.bootloader.bin")):
        return candidata.parent
    raise SystemExit(
        "não encontrei a exportação da Arduino IDE dentro de firmware/.\n"
        "Passe a pasta como argumento:\n"
        "    python tools\\merge_firmware.py caminho\\da\\pasta"
    )


if __name__ == "__main__":
    raise SystemExit(main())
