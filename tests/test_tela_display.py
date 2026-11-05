"""Cartão "Tela do display": ícone e itens da tela montada se excluem."""

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from polpad.core.store import Store
from polpad.ui.inspector import DisplayCard

from .apoio import CofreFalso

_app = QApplication.instance() or QApplication([])


class TelaDoDisplayTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        self.store.load()
        self.perfil = self.store.profiles[0]
        self.card = DisplayCard(self.store)
        self.card.show_profile(self.perfil)

    def tearDown(self):
        self._tmp.cleanup()

    def _marcados(self):
        nomes = [box.text() for box in self.card._boxes.values() if box.isChecked()]
        if self.card._icon.isChecked():
            nomes.insert(0, "Ícone")
        return nomes

    def test_comeca_no_icone_com_o_resto_desligado(self):
        self.assertEqual(self._marcados(), ["Ícone"])
        self.assertFalse(self.card._text.isEnabled())

    def test_marcar_um_item_desmarca_o_icone_e_liga_so_ele(self):
        self.card._boxes["show_time"].setChecked(True)
        self.assertEqual(self._marcados(), ["Hora"])
        self.assertEqual(self.perfil.display.mode, "personalizado")
        self.assertTrue(self.card._text.isEnabled())

    def test_marcar_o_icone_desmarca_os_itens(self):
        self.card._boxes["show_time"].setChecked(True)
        self.card._boxes["show_date"].setChecked(True)
        self.card._icon.setChecked(True)
        self.assertEqual(self._marcados(), ["Ícone"])
        cfg = self.perfil.display
        self.assertEqual(cfg.mode, "icone")
        self.assertFalse(cfg.show_time or cfg.show_date or cfg.show_profile)

    def test_desmarcar_o_icone_traz_hora_data_e_nome(self):
        self.card._icon.setChecked(False)
        self.assertEqual(self._marcados(), ["Hora", "Data", "Nome do perfil"])

    def test_desmarcar_o_ultimo_item_volta_ao_icone(self):
        self.card._boxes["show_time"].setChecked(True)
        self.card._boxes["show_time"].setChecked(False)
        self.assertEqual(self._marcados(), ["Ícone"])
        self.assertEqual(self.perfil.display.mode, "icone")

    def test_com_texto_livre_a_tela_montada_continua(self):
        self.card._boxes["show_time"].setChecked(True)
        self.card._text.textEdited.emit("Ola")
        self.card._boxes["show_time"].setChecked(False)
        self.assertEqual(self.perfil.display.mode, "personalizado")
        self.assertEqual(self.perfil.display.text, "Ola")

    def test_cada_perfil_guarda_a_sua(self):
        outro = self.store.add_profile("Outro")
        self.card._boxes["show_date"].setChecked(True)
        self.card.show_profile(outro)
        self.assertEqual(self._marcados(), ["Ícone"])
        self.card.show_profile(self.perfil)
        self.assertEqual(self._marcados(), ["Data"])


if __name__ == "__main__":
    unittest.main()
