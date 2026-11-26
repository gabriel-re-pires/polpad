"""Regressões da revisão geral de 26/11/2026; cada classe diz o defeito."""

import json
import logging
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import serial
from PIL import Image

from polpad.actions import builtin
from polpad.actions.base import ActionContext, ActionError
from polpad.core import icons, profile_io
from polpad.core.controller import Controller
from polpad.core.models import Action, Profile, Settings
from polpad.core.store import Store
from polpad.device import flasher, protocol
from polpad.device.link import SerialLink, _access_denied
from polpad.integrations import home_assistant

from .apoio import CofreFalso


class _ComPasta(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)
        self._tmp.cleanup()

    def _store(self) -> Store:
        store = Store(data_dir=self.dir / "dados", vault=CofreFalso())
        store.load()
        return store

    def _png(self, nome: str) -> Path:
        caminho = self.dir / nome
        Image.new("RGB", (32, 32), (255, 255, 255)).save(caminho)
        return caminho


class IconPathImportadoTest(_ComPasta):
    """O ``icon_path`` vinha do arquivo importado: podia apontar para um
    compartilhamento de rede (vazando credenciais ao abrir) ou para um
    documento do usuário, que a troca de ícone depois apagava.
    """

    def test_icon_path_do_arquivo_e_descartado(self):
        texto = json.dumps(
            {
                "format": profile_io.FORMAT,
                "version": profile_io.VERSION,
                "profile": {"name": "X", "icon_path": r"\\host\share\a.png"},
            }
        )
        importado = profile_io.from_json(texto)
        self.assertIsNone(importado.profile.icon_path)

    def test_trocar_icone_nao_apaga_arquivo_fora_da_pasta_de_icones(self):
        store = self._store()
        documento = self.dir / "tese.docx"
        documento.write_bytes(b"importante")
        perfil = store.profiles[0]
        perfil.icon_path = str(documento)

        store.import_icon(str(self._png("novo.png")), perfil)

        self.assertTrue(documento.exists())

    def test_trocar_icone_ainda_remove_o_antigo_da_pasta_de_icones(self):
        store = self._store()
        perfil = store.profiles[0]
        jpg = self.dir / "b.jpg"
        Image.new("RGB", (32, 32), (255, 255, 255)).save(jpg)
        antigo = store.import_icon(str(self._png("a.png")), perfil)

        store.import_icon(str(jpg), perfil)

        self.assertFalse(Path(antigo).exists())

    def test_icone_embutido_invalido_e_descartado(self):
        store = self._store()
        importado = profile_io.ImportedProfile(
            profile=Profile(name="X"), icon_bytes=b"nao e imagem", icon_suffix=".png"
        )
        novo = store.add_imported_profile(importado)
        self.assertIsNone(novo.icon_path)
        self.assertEqual(list(store.icons_dir.glob("*")), [])


class ImagemGiganteTest(_ComPasta):
    """Um PNG de 1 bit com 12000x12000 tem poucos KB, mas a conversão para
    RGBA alocava centenas de MB na thread da interface."""

    def test_recusa_imagem_com_lado_enorme(self):
        caminho = self.dir / "bomba.png"
        Image.new("1", (5000, 10), 0).save(caminho)
        with self.assertRaises(ValueError):
            icons.validar_imagem(caminho)


class AcoesSensiveisTest(unittest.TestCase):
    """A confirmação da importação só olhava comando, abrir e webhook: uma
    macro Win+R + texto, ou uma ação do Home Assistant, passava calada."""

    def _alvos(self, action: Action) -> list:
        return profile_io.sensitive_actions(Profile(name="X", bindings={0: action}))

    def test_macro_atalho_mais_texto(self):
        macro = Action(
            "macro",
            {
                "steps": [
                    {"type": "hotkey", "params": {"keys": ["win", "r"]}},
                    {"type": "text", "params": {"text": "powershell"}},
                ]
            },
        )
        self.assertTrue(self._alvos(macro))

    def test_home_assistant(self):
        acao = Action(
            "home_assistant",
            {"domain": "lock", "service": "unlock", "entity_id": "lock.porta"},
        )
        (alvo,) = [a for _, a in self._alvos(acao)]
        self.assertIn("lock.unlock", alvo)

    def test_obs_requisicao_livre(self):
        self.assertTrue(self._alvos(Action("obs", {"operation": "raw", "request": "X"})))

    def test_texto_com_enter(self):
        self.assertTrue(self._alvos(Action("text", {"text": "rm -rf", "enter": True})))

    def test_atalho_e_texto_simples_continuam_sem_aviso(self):
        self.assertEqual(self._alvos(Action("hotkey", {"keys": ["ctrl", "c"]})), [])
        self.assertEqual(self._alvos(Action("text", {"text": "oi"})), [])
        self.assertEqual(self._alvos(Action("obs", {"operation": "scene"})), [])


class AcaoMalFormadaTest(unittest.TestCase):
    """Um ``type`` que não é texto era aceito e quebrava a busca no registro
    de ações; com o perfil ativo, o app deixava de abrir."""

    def test_tipo_que_nao_e_texto(self):
        with self.assertRaises(ValueError):
            Action.from_dict({"type": ["hotkey"]})

    def test_params_que_nao_sao_objeto(self):
        with self.assertRaises(ValueError):
            Action.from_dict({"type": "text", "params": "abc"})

    def test_tecla_invalida_e_descartada_sem_perder_o_perfil(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        perfil = Profile.from_dict(
            {
                "name": "X",
                "bindings": {
                    "0": {"type": ["hotkey"]},
                    "1": {"type": "text", "params": {"text": "a"}},
                },
            }
        )
        self.assertEqual(list(perfil.bindings), [1])

    def test_icon_path_que_nao_e_texto(self):
        self.assertIsNone(Profile.from_dict({"name": "X", "icon_path": [1]}).icon_path)


class ConfiguracaoIlegivelTest(_ComPasta):
    """Falha de leitura (permissão) era tratada como arquivo corrompido: o
    app gravava o padrão por cima e todos os perfis sumiam."""

    def _config(self) -> Path:
        pasta = self.dir / "dados"
        pasta.mkdir()
        config = pasta / "config.json"
        dados = {"profiles": [Profile(name="Meu perfil").to_dict()]}
        config.write_text(json.dumps(dados), encoding="utf-8")
        return config

    def test_erro_de_leitura_nao_sobrescreve(self):
        config = self._config()
        original = config.read_bytes()
        erros: list[str] = []
        store = Store(data_dir=config.parent, vault=CofreFalso())
        store.on_error = erros.append
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("negado")):
            store.load()

        self.assertFalse(store.save())
        self.assertEqual(config.read_bytes(), original)
        self.assertTrue(erros)

    def test_sem_copia_de_seguranca_nao_sobrescreve(self):
        config = self._config()
        config.write_text("{ isto não é json", encoding="utf-8")
        original = config.read_bytes()
        store = Store(data_dir=config.parent, vault=CofreFalso())
        with mock.patch.object(shutil, "copy", side_effect=OSError("disco cheio")):
            store.load()

        self.assertFalse(store.save())
        self.assertEqual(config.read_bytes(), original)

    def test_json_invalido_com_copia_segue_gravando(self):
        config = self._config()
        config.write_text("{ isto não é json", encoding="utf-8")
        store = Store(data_dir=config.parent, vault=CofreFalso())
        store.load()

        self.assertTrue(store.save())
        self.assertTrue(config.with_suffix(".json.bak").exists())

    def test_recarregar_libera_a_gravacao(self):
        config = self._config()
        store = Store(data_dir=config.parent, vault=CofreFalso())
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("negado")):
            store.load()
        store.load()
        self.assertTrue(store.save())
        self.assertEqual([p.name for p in store.profiles], ["Meu perfil"])


class AtalhoSemTeclaPresaTest(unittest.TestCase):
    """Os modificadores eram pressionados fora do ``try``: se o segundo
    falhasse, o primeiro ficava preso."""

    def test_falha_no_segundo_modificador_solta_o_primeiro(self):
        teclado = mock.Mock()
        teclado.press.side_effect = [None, RuntimeError("sem mapeamento")]
        ctx = ActionContext(settings=Settings())
        with (
            mock.patch.object(builtin, "_keyboard", teclado),
            self.assertRaises(RuntimeError),
        ):
            builtin.run_hotkey({"keys": ["ctrl", "shift", "p"]}, ctx)

        self.assertEqual(teclado.release.call_count, 1)
        self.assertEqual(teclado.release.call_args, teclado.press.call_args_list[0])


class IntervaloDaMacroTest(unittest.TestCase):
    """Sem teto, uma macro importada com intervalo enorme prendia a fila de
    ações e as teclas seguintes eram descartadas."""

    def test_intervalo_e_limitado(self):
        ctx = ActionContext(settings=Settings())
        passos = [
            {"type": "media", "params": {"control": "x"}},
            {"type": "media", "params": {"control": "x"}},
        ]
        with (
            mock.patch.object(builtin.time, "sleep") as dormir,
            mock.patch("polpad.actions.base.get") as get,
        ):
            get.return_value = mock.Mock()
            builtin.run_macro({"steps": passos, "delay_ms": 10**9}, ctx)

        dormir.assert_called_once_with(builtin.MACRO_MAX_DELAY_MS / 1000)


class HomeAssistantSemJsonTest(unittest.TestCase):
    """Um 200 com HTML (proxy, página de login) escapava como
    ``JSONDecodeError`` e o botão Testar não dava retorno."""

    def test_resposta_html_vira_action_error(self):
        resposta = mock.Mock(status_code=200, ok=True)
        resposta.json.side_effect = ValueError("não é json")
        with (
            mock.patch.object(home_assistant.requests, "get", return_value=resposta),
            self.assertRaises(ActionError),
        ):
            home_assistant.check_connection("http://ha.local:8123", "t")


class PortaEmUsoNoWindowsTest(unittest.TestCase):
    """No Windows o pyserial embrulha o PermissionError sem errno: "porta em
    uso" nunca era avisada e o app tentava a cada 2 s em silêncio."""

    def test_mensagem_do_pyserial_no_windows(self):
        exc = serial.SerialException(
            "could not open port 'COM5': PermissionError(13, 'Acesso negado.', None, 5)"
        )
        self.assertTrue(_access_denied(exc))

    def test_porta_que_nao_existe_nao_e_acesso_negado(self):
        exc = serial.SerialException(
            "could not open port 'COM9': FileNotFoundError(2, 'O sistema não pode "
            "encontrar o arquivo especificado.', None, 2)"
        )
        self.assertFalse(_access_denied(exc))


class EnlaceResistenteTest(unittest.TestCase):
    """Uma exceção fora de SerialException/OSError matava a thread do enlace
    e o macropad não reconectava mais; e ``send`` fechava a porta no meio
    de uma leitura da outra thread."""

    def _link(self, negadas=None):
        return SerialLink(
            on_message=lambda m: None,
            on_state=lambda c, p: None,
            on_denied=(negadas.append if negadas is not None else None),
        )

    def test_erro_inesperado_nao_escapa_da_tentativa(self):
        link = self._link()
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        with mock.patch.object(
            link, "_connect_and_read", side_effect=AttributeError("hEvent")
        ):
            link._attempt("COM5")  # não levanta

    def test_porta_em_uso_avisa(self):
        negadas: list[str] = []
        link = self._link(negadas)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        erro = serial.SerialException("could not open port 'COM5': PermissionError(13)")
        with mock.patch.object(link, "_connect_and_read", side_effect=erro):
            link._attempt("COM5")
        self.assertEqual(negadas, ["COM5"])

    def test_falha_de_escrita_nao_fecha_a_porta_desta_thread(self):
        link = self._link()
        porta = mock.Mock(is_open=True)
        porta.write.side_effect = serial.SerialException("cabo removido")
        link._serial = porta

        link.send(protocol.msg_ping())

        porta.close.assert_not_called()
        self.assertTrue(link._write_failed)

    def test_handshake_pede_o_hello(self):
        self.assertEqual(protocol.msg_ping(hello=True), {"t": "ping", "hello": True})
        self.assertEqual(protocol.msg_ping(), {"t": "ping"})


class TelaAoReconectarTest(_ComPasta):
    """Quadros gerados com o enlace fora eram "enviados" para o nada e,
    ao reconectar, suprimidos como repetidos: o display ficava velho."""

    def test_reconectar_reenvia_o_quadro(self):
        enviados: list[dict] = []
        store = self._store()
        controlador = Controller(
            store=store, runner=mock.Mock(), send=enviados.append
        )
        controlador.push_display()
        self.assertEqual(len(enviados), 1)

        controlador.link_state(False)
        controlador.push_display()  # perdido: sem enlace
        controlador.link_state(True)

        self.assertEqual(len(enviados), 3)
        self.assertEqual(enviados[-1]["t"], "img")


class CancelarGravacaoTest(unittest.TestCase):
    """O cancelamento levantava de novo no teardown do esptool, que então
    não resetava o chip nem fechava a porta."""

    def test_cancelamento_levanta_uma_vez_so(self):
        classe = flasher._callback_logger_class()
        cancelar = threading.Event()
        classe.bind(None, None, cancelar)
        self.addCleanup(classe.bind, None, None, None)
        logger = classe()
        cancelar.set()

        with self.assertRaises(flasher.FlashCancelledError):
            logger.print("bloco")
        logger.print("teardown")  # não levanta


if __name__ == "__main__":
    unittest.main()
