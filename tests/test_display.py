"""Testes da composição das telas do display e da fonte do firmware."""

import unittest
from datetime import datetime

from polpad.actions import keys
from polpad.core import display, oled_font, oled_render
from polpad.core.models import (
    GRID_COLS,
    GRID_ROWS,
    KEY_COUNT,
    KEY_LAYOUT,
    SCREEN_H,
    SCREEN_W,
    Action,
    DisplayConfig,
    Profile,
    key_at,
    short_label,
)


class LayoutTest(unittest.TestCase):
    def test_layout_tem_18_posicoes_distintas_dentro_da_grade(self):
        self.assertEqual(KEY_COUNT, 18)
        self.assertEqual(len(set(KEY_LAYOUT)), 18)
        for row, col in KEY_LAYOUT:
            self.assertTrue(0 <= row < GRID_ROWS and 0 <= col < GRID_COLS)

    def test_linha_de_cima_tem_tres_teclas_a_direita(self):
        # As duas primeiras posições são o módulo e o display.
        self.assertIsNone(key_at(0, 0))
        self.assertIsNone(key_at(0, 1))
        self.assertEqual([key_at(0, c) for c in (2, 3, 4)], [0, 1, 2])
        self.assertEqual(key_at(3, 4), 17)

    def test_indices_seguem_a_ordem_de_leitura(self):
        ordem = sorted(range(KEY_COUNT), key=lambda k: KEY_LAYOUT[k])
        self.assertEqual(ordem, list(range(KEY_COUNT)))


class ShortLabelTest(unittest.TestCase):
    def test_abreviacoes(self):
        casos = {
            "Copiar": "COP",
            "Ctrl+Shift+P": "CSP",
            "npm run dev": "NRD",
            "Edição": "EDI",
            "x": "X",
            "": "?",
        }
        for texto, esperado in casos.items():
            self.assertEqual(short_label(texto), esperado, texto)

    def test_abreviacao_explicita_prevalece_e_nao_e_reabreviada(self):
        action = Action(type="media", label="Aumentar volume", short="VL+")
        self.assertEqual(action.display_short, "VL+")
        sem_abreviacao = Action(type="media", label="Aumentar volume")
        self.assertEqual(sem_abreviacao.display_short, "AV")

    def test_abreviacao_e_persistida_e_limitada(self):
        action = Action(type="hotkey", short="ABCD")
        restaurada = Action.from_dict(action.to_dict())
        self.assertEqual(restaurada.short, "ABC")
        self.assertNotIn("short", Action(type="hotkey").to_dict())


class FontTest(unittest.TestCase):
    def test_tabela_completa_e_glifo_conhecido(self):
        self.assertEqual(len(oled_font.FONT), 256 * 5)
        # 'A' na fonte clássica da GFX.
        self.assertEqual(list(oled_font.glyph(ord("A"))), [0x7C, 0x12, 0x11, 0x12, 0x7C])

    def test_largura_de_texto_como_getTextBounds(self):  # noqa: N802 — nome da GFX
        self.assertEqual(oled_render.text_width("abc", 1), 18)
        self.assertEqual(oled_render.text_width("abc", 2), 36)

    def test_desenho_do_caractere_respeita_celula_6x8(self):
        frame = oled_render.new_frame()
        oled_render.draw_text(frame, 10, 20, "A", 1)
        pixels = frame.load()
        # Coluna 0 de 'A' = 0x7C: bits 2..6 acesos -> linhas 22..26.
        acesos = [y for y in range(SCREEN_H) if pixels[10, y]]
        self.assertEqual(acesos, [22, 23, 24, 25, 26])
        # A 6ª coluna da célula é o espaçamento: sempre apagada.
        self.assertFalse(any(pixels[15, y] for y in range(SCREEN_H)))

    def test_texto_em_tamanho_2_dobra_os_pixels(self):
        f1 = oled_render.new_frame()
        f2 = oled_render.new_frame()
        oled_render.draw_text(f1, 0, 0, "A", 1)
        oled_render.draw_text(f2, 0, 0, "A", 2)
        p1, p2 = f1.load(), f2.load()
        for x in range(12):
            for y in range(16):
                self.assertEqual(bool(p2[x, y]), bool(p1[x // 2, y // 2]))

    def test_tela_de_texto_segue_a_geometria_do_firmware(self):
        # Uma linha: tamanho 2, altura 20, y = (64 - 20 + 4) // 2 = 24.
        frame = oled_render.render_text_lines(["A"])
        pixels = frame.load()
        linhas = sorted(
            {y for y in range(SCREEN_H) for x in range(SCREEN_W) if pixels[x, y]}
        )
        self.assertEqual(linhas[0], 24)  # a 3ª coluna de 'A' (0x11) acende o bit 0
        # Três linhas: tamanho 1, altura 12, y inicial = (64 - 36 + 4) // 2 = 16.
        frame = oled_render.render_text_lines(["A", "A", "A"])
        pixels = frame.load()
        linhas = sorted(
            {y for y in range(SCREEN_H) for x in range(SCREEN_W) if pixels[x, y]}
        )
        self.assertEqual(linhas[0], 16)
        self.assertEqual(linhas[-1], 16 + 2 * 12 + 6)  # bit 6 = última linha de 'A'


class TelasDoPerfilTest(unittest.TestCase):
    def _perfil(self, name="OBS", **kw):
        perfil = Profile(name=name)
        perfil.display.mode = "personalizado"
        for k, v in kw.items():
            setattr(perfil.display, k, v)
        return perfil

    def test_modo_icone_sem_icone_usa_o_nome_no_maior_tamanho_que_couber(self):
        curto = display.profile_frame(Profile(name="VS Code"))
        longo = display.profile_frame(Profile(name="Edição de vídeo longa"))
        self.assertEqual(
            curto.tobytes(), oled_render.render_text_lines(["VS Code"]).tobytes()
        )
        # 21 letras: não cabe em tamanho 2, então sai numa linha em tamanho 1.
        esperado = oled_render.new_frame()
        oled_render.draw_text_centered(esperado, 28, "Edicao de video longa", 1)
        self.assertEqual(longo.tobytes(), esperado.tobytes())

    def test_nome_longo_nao_sai_cortado(self):
        for nome in (
            "Photoshop 2",
            "Edição de vídeo",
            "Edição de vídeo longa",
            "Supercalifragilisticexpialidocious",
        ):
            with self.subTest(nome=nome):
                bbox = display.title_frame(nome).getbbox()
                self.assertIsNotNone(bbox)
                self.assertGreater(bbox[0], 0)
                self.assertLess(bbox[2], SCREEN_W)

    def test_palavra_maior_que_a_linha_quebra_em_pedacos(self):
        palavra = "Supercalifragilisticexpialidocious"
        self.assertEqual(
            display.title_frame(palavra).tobytes(),
            oled_render.render_text_lines([palavra[:21], palavra[21:]]).tobytes(),
        )

    def test_personalizado_tem_faixa_com_o_perfil(self):
        frame = display.profile_frame(self._perfil(), datetime(2026, 11, 3, 9, 7))
        pixels = frame.load()
        self.assertEqual(frame.size, (SCREEN_W, SCREEN_H))
        self.assertTrue(pixels[0, 0] and pixels[SCREEN_W - 1, 0])
        self.assertTrue(any(not pixels[x, 4] for x in range(50, 78)))

    def test_hora_muda_o_quadro(self):
        perfil = self._perfil()
        a = display.custom_frame(perfil, datetime(2026, 1, 1, 9, 7))
        b = display.custom_frame(perfil, datetime(2026, 1, 1, 9, 8))
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_data_em_portugues_sem_acento(self):
        self.assertEqual(display.date_text(datetime(2026, 11, 7)), "sab, 07 nov 2026")

    def test_todos_os_elementos_cabem_no_display(self):
        perfil = self._perfil("W" * 40, text="W" * 40)
        frame = display.custom_frame(perfil, datetime(2026, 12, 31, 23, 59))
        pixels = frame.load()
        self.assertFalse(any(pixels[x, SCREEN_H - 1] for x in range(SCREEN_W)))

    def test_sem_elementos_mostra_o_nome(self):
        perfil = self._perfil(
            "X", show_time=False, show_date=False, show_profile=False
        )
        frame = display.custom_frame(perfil, datetime.now())
        self.assertEqual(frame.tobytes(), display.title_frame("X").tobytes())

    def test_cada_perfil_tem_a_sua_tela(self):
        relogio = self._perfil("A")
        icone = Profile(name="B")
        agora = datetime(2026, 11, 3, 9, 7)
        self.assertEqual(
            display.profile_frame(icone, agora).tobytes(),
            display.title_frame("B").tobytes(),
        )
        self.assertNotEqual(
            display.profile_frame(relogio, agora).tobytes(),
            display.title_frame("A").tobytes(),
        )

    def test_configuracao_antiga_vira_a_de_cada_perfil(self):
        legado = DisplayConfig.from_legacy_settings(
            {"display_mode": "personalizado", "custom_date": False, "custom_text": "oi"}
        )
        perfil = Profile.from_dict({"name": "Velho"}, legado)
        self.assertEqual(perfil.display.mode, "personalizado")
        self.assertFalse(perfil.display.show_date)
        self.assertEqual(perfil.display.text, "oi")
        # "mapa", que não existe mais, vira "icone".
        mapa = DisplayConfig.from_legacy_settings({"display_mode": "mapa"})
        self.assertEqual(mapa.mode, "icone")

    def test_configuracao_do_perfil_sobrevive_ao_salvar(self):
        perfil = self._perfil("Rel", show_date=False, text="ola")
        volta = Profile.from_dict(perfil.to_dict())
        self.assertEqual(volta.display, perfil.display)

    def test_payload_e_mensagem_sao_reversiveis(self):
        frame = display.profile_frame(self._perfil("A"))
        message = {"t": "img", "fmt": "xbm1", "d": display.frame_payload(frame)}
        restaurado = display.frame_from_message(message)
        self.assertEqual(restaurado.tobytes(), frame.tobytes())
        self.assertIsNone(display.frame_from_message({"t": "img", "d": "!!!"}))
        self.assertIsNone(display.frame_from_message({"t": "ping"}))


class GravacaoDeAtalhoTest(unittest.TestCase):
    """A UI grava combinações com QKeySequenceEdit; a tradução para os
    nomes do pynput é pura e fica fora do Qt."""

    def test_combinacoes(self):
        from PySide6.QtGui import QKeySequence

        casos = {
            "Ctrl+Shift+P": ["ctrl", "shift", "p"],
            "Alt+F4": ["alt", "f4"],
            "Ctrl+Alt+Del": ["ctrl", "alt", "delete"],
            "Meta+E": ["win", "e"],
            "Return": ["enter"],
            "Ctrl+Shift": [],  # só modificadores: inválido
        }
        for texto, esperado in casos.items():
            nomes = keys.names_from_qt(QKeySequence(texto))
            self.assertEqual(nomes, esperado, texto)
            for nome in nomes:
                self.assertTrue(keys.is_valid(nome), nome)


class CapturaDeAtalhoTest(unittest.TestCase):
    """Tecla do QKeyEvent com códigos do Windows (``xkb=False``); os do
    Linux estão em ``test_linux``."""

    CTRL, SHIFT, ALT = 0x04000000, 0x02000000, 0x08000000

    @staticmethod
    def _windows(key, mods, vk):
        return keys.names_from_event(key, mods, vk, xkb=False)

    def test_ctrl_c(self):
        self.assertEqual(self._windows(0x43, self.CTRL, 0x43), ["ctrl", "c"])

    def test_shift_1_usa_a_tecla_fisica_e_nao_o_simbolo(self):
        # Com Shift, o Qt informa "!" (0x21); o código virtual é o do "1".
        self.assertEqual(self._windows(0x21, self.SHIFT, 0x31), ["shift", "1"])

    def test_teclas_especiais_e_modificador_sozinho(self):
        self.assertEqual(self._windows(0x01000033, self.ALT, 0), ["alt", "f4"])
        self.assertEqual(self._windows(0x01000021, self.CTRL, 0x11), [])

    def test_texto_exibido(self):
        self.assertEqual(keys.pretty(["ctrl", "shift", "p"]), "Ctrl + Shift + P")
        self.assertEqual(keys.pretty(["win", "f13"]), "Win + F13")
        self.assertEqual(keys.pretty(["ctrl", "pageup"]), "Ctrl + PgUp")


if __name__ == "__main__":
    unittest.main()
