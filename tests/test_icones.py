"""Conversão de ícones para o OLED e ícone na troca de perfil.

Os casos abaixo são exatamente os que deixavam o display em branco (ou
cheio de ruído) com a conversão anterior.
"""

import base64
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from polpad.core import display, icons
from polpad.core.controller import Controller
from polpad.core.models import SCREEN_H, SCREEN_W, Profile
from polpad.core.store import Store

from .apoio import CofreFalso


def _lit(mono: Image.Image) -> int:
    return sum(mono.convert("L").histogram()[1:])


class ConversaoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _salvar(self, img: Image.Image, nome: str) -> str:
        caminho = self.dir / nome
        img.save(caminho)
        return str(caminho)

    def test_pictograma_preto_em_fundo_transparente_acende(self):
        """O formato mais comum de ícone ficava 100% apagado."""
        img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((24, 24, 104, 104), fill=(0, 0, 0, 255))
        mono = icons.icon_bitmap(self._salvar(img, "preto.png"), 48)

        self.assertGreater(_lit(mono), 0.5 * 48 * 48)
        # O fundo transparente continua apagado (cantos do quadro).
        self.assertEqual(mono.getpixel((0, 0)), 0)

    def test_logo_em_fundo_branco_apaga_o_fundo(self):
        """Um JPG com fundo branco acendia o display inteiro."""
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        ImageDraw.Draw(img).rectangle((60, 60, 140, 140), fill=(20, 20, 20))
        mono = icons.icon_bitmap(self._salvar(img, "logo.jpg"), 48)

        # O desenho (escuro) acende; a borda branca, recortada, não sobra.
        self.assertGreater(_lit(mono), 0.8 * 48 * 48)
        img2 = Image.new("RGB", (200, 200), (255, 255, 255))
        ImageDraw.Draw(img2).ellipse((40, 40, 160, 160), fill=(20, 20, 20))
        mono2 = icons.icon_bitmap(self._salvar(img2, "circulo.jpg"), 48)
        self.assertEqual(mono2.getpixel((0, 0)), 0)
        self.assertEqual(mono2.getpixel((24, 24)), 255)

    def test_logo_colorido_preserva_detalhe_interno(self):
        """Círculo verde com um furo escuro: o furo continua apagado."""
        img = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((0, 0, 95, 95), fill=(30, 215, 96, 255))
        draw.rectangle((40, 40, 56, 56), fill=(0, 0, 0, 255))
        mono = icons.icon_bitmap(self._salvar(img, "cor.png"), 48)

        self.assertEqual(mono.getpixel((24, 24)), 0)   # furo
        self.assertEqual(mono.getpixel((24, 8)), 255)  # anel

    def test_margens_sao_recortadas(self):
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle((120, 120, 135, 135), fill=(255, 255, 255, 255))
        mono = icons.icon_bitmap(self._salvar(img, "pequeno.png"), 48)
        # 16 px no meio de 256 viraria 3 px; recortado, ocupa a área toda.
        self.assertEqual(_lit(mono), 48 * 48)

    def test_tela_do_icone_e_so_o_desenho_na_altura_do_display(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle((0, 0, 63, 63), fill=(255, 255, 255, 255))
        perfil = Profile(name="OBS", icon_path=self._salvar(img, "obs.png"))
        frame = display.icon_frame(perfil)

        self.assertEqual(frame.size, (SCREEN_W, SCREEN_H))
        alto = SCREEN_H - 2 * display.ICON_MARGIN
        # Quadrado de 60x60 centralizado; nenhum texto embaixo.
        self.assertEqual(_lit(frame), alto * alto)
        self.assertEqual(frame.getpixel((SCREEN_W // 2, display.ICON_MARGIN)), 255)
        self.assertEqual(frame.getpixel((SCREEN_W // 2, SCREEN_H - 1)), 0)

    def test_icone_ilegivel_cai_para_o_nome(self):
        falso = self.dir / "falso.png"
        falso.write_text("não é imagem", encoding="utf-8")
        perfil = Profile(name="Sem", icon_path=str(falso))
        self.assertEqual(
            display.icon_frame(perfil).tobytes(),
            display.title_frame("Sem").tobytes(),
        )


class TrocaComIconeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        dir_ = Path(self._tmp.name)
        self.store = Store(data_dir=dir_, vault=CofreFalso())
        self.store.load()
        self.store.settings.mode_key = 17
        self.store.profiles[0].name = "A"
        self.b = self.store.add_profile("B")
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((0, 0, 31, 31), fill=(0, 0, 0, 255))
        caminho = dir_ / "b.png"
        img.save(caminho)
        self.b.icon_path = str(caminho)
        for perfil in self.store.profiles:
            perfil.display.mode = "personalizado"

        self.sent = []
        self.scheduled = []
        self.controller = Controller(
            store=self.store,
            runner=type("R", (), {"submit": lambda self, a: None})(),
            send=self.sent.append,
            schedule=lambda s, fn: self.scheduled.append((s, fn)),
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _ultimo(self):
        return icons.unpack_bits(base64.b64decode(self.sent[-1]["d"])).tobytes()

    def _tela(self, perfil):
        return display.profile_frame(perfil).tobytes()

    def test_troca_mostra_o_icone_e_depois_a_tela_montada(self):
        self.controller.activate_profile(self.b.id)
        self.assertEqual(self._ultimo(), display.icon_frame(self.b).tobytes())
        self.assertTrue(self.controller.splashing)

        segundos, fim = self.scheduled[-1]
        self.assertEqual(segundos, Controller.SPLASH_S)
        fim()
        self.assertEqual(self._ultimo(), self._tela(self.b))
        self.assertFalse(self.controller.splashing)

    def test_perfil_sem_icone_mostra_o_nome_na_troca(self):
        a = self.store.profiles[0]
        self.controller.activate_profile(a.id)
        self.assertEqual(self._ultimo(), display.title_frame("A").tobytes())
        self.assertTrue(self.controller.splashing)

    def test_modo_icone_nao_precisa_de_icone_temporario(self):
        self.b.display.mode = "icone"
        self.controller.activate_profile(self.b.id)
        self.assertEqual(self._ultimo(), display.icon_frame(self.b).tobytes())
        self.assertEqual(self.scheduled, [])

    def test_retorno_de_troca_anterior_nao_atropela_a_atual(self):
        self.controller.activate_profile(self.b.id)
        _, fim_antigo = self.scheduled[-1]
        self.controller.activate_profile(self.store.profiles[0].id)  # sem ícone
        self.controller.activate_profile(self.b.id)
        enviados = len(self.sent)
        fim_antigo()  # retorno da primeira troca chega atrasado
        self.assertEqual(len(self.sent), enviados)
        self.assertTrue(self.controller.splashing)

    def test_desligado_nas_configuracoes(self):
        self.b.display.icon_splash = False
        self.controller.activate_profile(self.b.id)
        self.assertEqual(self._ultimo(), self._tela(self.b))

    def test_relogio_nao_interrompe_o_icone(self):
        self.controller.activate_profile(self.b.id)
        enviados = len(self.sent)
        self.controller.tick()
        self.assertEqual(len(self.sent), enviados)
        self.assertTrue(self.controller.splashing)


if __name__ == "__main__":
    unittest.main()
