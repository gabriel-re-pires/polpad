"""Tela de espera do firmware: o polvo com os tentáculos girando."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from PIL import Image, ImageChops

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "animacao_espera", RAIZ / "tools" / "animacao_espera.py"
)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError("tools/animacao_espera.py não encontrado")
anim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(anim)


class AnimacaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quadros = anim.quadros()

    def test_cabecalho_do_firmware_esta_em_dia(self):
        # Quem muda o logo ou o gerador precisa regravar o espera_anim.h.
        gravado = anim.SAIDA.read_text(encoding="utf-8")
        self.assertEqual(gravado, anim.cabecalho(self.quadros))

    def test_quadros_do_tamanho_certo(self):
        self.assertEqual(len(self.quadros), anim.QUADROS)
        for quadro in self.quadros:
            self.assertEqual(quadro.size, (anim.LADO, anim.LADO))
            self.assertEqual(len(anim.bytes_xbm(quadro)), anim.LADO * anim.LADO // 8)

    def test_corpo_parado_e_tentaculos_girando(self):
        primeiro, meio = self.quadros[0], self.quadros[anim.QUADROS // 2]
        centro = (anim.LADO - 1) / 2
        raio = anim.RAIO_CORPO * anim.LADO / 256 - 1.5
        diferentes = ImageChops.difference(primeiro, meio).load()
        no_corpo = [
            (x, y)
            for y in range(anim.LADO)
            for x in range(anim.LADO)
            if (x - centro) ** 2 + (y - centro) ** 2 <= raio**2 and diferentes[x, y]
        ]
        self.assertEqual(no_corpo, [])
        self.assertIsNotNone(ImageChops.difference(primeiro, meio).getbbox())

    def test_volta_fecha_sem_pulo(self):
        # Girar 45° volta à primeira imagem: o quadro seguinte ao último
        # tem de ser quase igual ao primeiro.
        seguinte = anim.quadros_em([45.0])[0]
        diferentes = ImageChops.difference(seguinte, self.quadros[0])
        acesos = sum(diferentes.histogram()[1:])
        self.assertLess(acesos, anim.LADO * anim.LADO // 50)

    def test_texto_cabe_no_display_com_os_pontos(self):
        tela = anim.tela(self.quadros[0], 3)
        self.assertEqual(tela.size, (128, 64))
        vazia = Image.new("1", (1, 64), 0).tobytes()
        for x in (0, 127):
            self.assertEqual(tela.crop((x, 0, x + 1, 64)).tobytes(), vazia)


if __name__ == "__main__":
    unittest.main()
