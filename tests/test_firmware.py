"""Testes da gravação de firmware: escolha de endereço, validação e release.

O esptool em si não é exercitado (exigiria um ESP32 na porta); o que se
verifica aqui é tudo o que decide *o que* será gravado — a parte em que um
engano custa uma regravação manual do dispositivo.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import requests

from polpad.device import firmware_release, flasher

from .apoio import ClienteFalso, RespostaFalsa

ESP_HEADER = bytes([0xE9, 0x00, 0x02, 0x03])


def _release_payload(tag: str = "v1.2.0", asset: str = "firmware-1.2.0.bin") -> dict:
    return {
        "tag_name": tag,
        "body": "notas",
        "assets": [
            {"name": "Polpad.exe", "size": 1, "browser_download_url": "x"},
            {
                "name": asset,
                "size": len(ESP_HEADER),
                "browser_download_url": f"https://exemplo/{asset}",
            },
        ],
    }


class EnderecoTest(unittest.TestCase):
    def test_exportacao_da_arduino_vai_para_a_aplicacao(self):
        self.assertEqual(
            flasher.guess_offset(Path("macropad_firmware.ino.bin")),
            flasher.APP_OFFSET,
        )

    def test_imagem_completa_vai_para_zero(self):
        for nome in ("firmware-1.0.0.bin", "merged.bin", "FIRMWARE.BIN"):
            with self.subTest(nome=nome):
                self.assertEqual(flasher.guess_offset(Path(nome)), flasher.MERGED_OFFSET)

    def test_from_path_marca_aplicacao_isolada(self):
        imagem = flasher.FirmwareImage.from_path("sketch.ino.bin")
        self.assertTrue(imagem.app_only)
        self.assertFalse(flasher.FirmwareImage.from_path("firmware.bin").app_only)


class ValidacaoTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.pasta = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def _imagem(self, nome: str, conteudo: bytes) -> flasher.FirmwareImage:
        caminho = self.pasta / nome
        caminho.write_bytes(conteudo)
        return flasher.FirmwareImage.from_path(caminho)

    def test_aceita_imagem_com_o_cabecalho_da_espressif(self):
        flasher.validate(self._imagem("firmware.bin", ESP_HEADER))

    def test_recusa_arquivo_que_nao_e_firmware(self):
        with self.assertRaises(flasher.FlashError) as caso:
            flasher.validate(self._imagem("firmware.bin", b"PK\x03\x04zip"))
        self.assertIn("não parece um firmware", str(caso.exception))

    def test_recusa_arquivo_vazio(self):
        with self.assertRaises(flasher.FlashError):
            flasher.validate(self._imagem("firmware.bin", b""))

    def test_recusa_arquivo_inexistente(self):
        imagem = flasher.FirmwareImage.from_path(self.pasta / "sumiu.bin")
        with self.assertRaises(flasher.FlashError):
            flasher.validate(imagem)


class MensagensDeErroTest(unittest.TestCase):
    """As falhas mais comuns precisam virar instrução, não traceback."""

    def test_porta_ocupada_sugere_fechar_o_monitor_serial(self):
        texto = flasher._describe(OSError("Access is denied on COM7"))
        self.assertIn("Monitor Serial", texto)

    def test_mensagem_ambigua_do_esptool_cobre_os_dois_casos(self):
        """O esptool não separa "ocupada" de "sumiu"; a dica trata ambos."""
        texto = flasher._describe(
            OSError("Could not open COM7, the port is busy or doesn't exist.")
        )
        self.assertIn("em uso por outro", texto)
        self.assertIn("desconectado", texto)

    def test_porta_inexistente_pede_para_reconectar(self):
        texto = flasher._describe(OSError("Could not open COM9"))
        self.assertIn("não existe mais", texto)

    def test_sem_resposta_sugere_o_modo_de_gravacao(self):
        texto = flasher._describe(RuntimeError("Failed to connect to ESP32-C3"))
        self.assertIn("BOOT", texto)

    def test_erro_desconhecido_e_repassado(self):
        texto = flasher._describe(RuntimeError("pane genérica"))
        self.assertEqual(texto, "pane genérica")


class ReleaseTest(unittest.TestCase):
    def test_escolhe_o_binario_do_firmware_entre_os_anexos(self):
        cliente = ClienteFalso(RespostaFalsa(payload=[_release_payload()]))
        release = firmware_release.latest_release(session=cliente)
        self.assertEqual(release.asset_name, "firmware-1.2.0.bin")
        self.assertEqual(release.version, "1.2.0")
        self.assertEqual(release.tag, "v1.2.0")

    def test_release_sem_firmware_anexado_explica_o_problema(self):
        payload = [{"tag_name": "v1.0.0", "assets": [{"name": "app.exe", "size": 1}]}]
        cliente = ClienteFalso(RespostaFalsa(payload=payload))
        with self.assertRaises(firmware_release.ReleaseError) as caso:
            firmware_release.latest_release(session=cliente)
        self.assertIn("firmware*.bin", str(caso.exception))

    def test_firmware_do_release_mais_recente_que_tem_um(self):
        """Publicar uma versão só do aplicativo não pode quebrar a gravação."""
        sem_firmware = {
            "tag_name": "v0.5.0",
            "assets": [
                {"name": "Polpad-Setup.exe", "size": 1, "browser_download_url": "x"}
            ],
        }
        payload = [sem_firmware, _release_payload("v0.4.1", "firmware-2.0.2.bin")]
        cliente = ClienteFalso(RespostaFalsa(payload=payload))
        release = firmware_release.latest_release(session=cliente)
        self.assertEqual(release.tag, "v0.4.1")
        self.assertEqual(release.version, "2.0.2")

    def test_falha_de_rede_vira_mensagem_amigavel(self):
        cliente = ClienteFalso(requests.ConnectionError("sem rota"))
        with self.assertRaises(firmware_release.ReleaseError) as caso:
            firmware_release.latest_release(session=cliente)
        self.assertIn("internet", str(caso.exception))

    def test_resposta_invalida_nao_estoura_traceback(self):
        cliente = ClienteFalso(RespostaFalsa(payload={"inesperado": 1}))
        with self.assertRaises(firmware_release.ReleaseError):
            firmware_release.latest_release(session=cliente)


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.pasta = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)
        # O cache real fica no perfil do usuário; os testes nunca o tocam.
        original = firmware_release.cache_dir
        firmware_release.cache_dir = lambda: self.pasta  # type: ignore[assignment]
        self.addCleanup(setattr, firmware_release, "cache_dir", original)

    def _release(self, tamanho: int) -> firmware_release.FirmwareRelease:
        return firmware_release.FirmwareRelease(
            tag="v1.2.0",
            version="1.2.0",
            asset_name="firmware-1.2.0.bin",
            url="https://exemplo/firmware-1.2.0.bin",
            size=tamanho,
        )

    def test_baixa_e_grava_no_cache(self):
        cliente = ClienteFalso(RespostaFalsa(conteudo=ESP_HEADER))
        caminho = firmware_release.download(
            self._release(len(ESP_HEADER)), session=cliente
        )
        self.assertTrue(caminho.is_file())
        self.assertEqual(caminho.read_bytes(), ESP_HEADER)

    def test_download_incompleto_nao_vira_arquivo_valido(self):
        """Um .bin truncado no cache seria gravado no macropad depois."""
        cliente = ClienteFalso(RespostaFalsa(conteudo=b"\xe9"))
        with self.assertRaises(firmware_release.ReleaseError):
            firmware_release.download(self._release(999), session=cliente)
        self.assertEqual(list(self.pasta.glob("*.bin")), [])
        self.assertEqual(list(self.pasta.glob("*.part")), [])

    def test_reaproveita_o_cache_sem_baixar_de_novo(self):
        release = self._release(len(ESP_HEADER))
        cliente = ClienteFalso(RespostaFalsa(conteudo=ESP_HEADER))
        firmware_release.download(release, session=cliente)
        firmware_release.download(release, session=cliente)
        self.assertEqual(len(cliente.chamadas), 1)


class VersaoTest(unittest.TestCase):
    def test_normaliza_formatos_de_tag(self):
        self.assertEqual(firmware_release.normalize_version("v1.2.0"), "1.2.0")
        self.assertEqual(firmware_release.normalize_version("fw-2.0"), "2.0")
        self.assertEqual(firmware_release.normalize_version("1.0.1"), "1.0.1")

    def test_compara_versoes(self):
        self.assertTrue(firmware_release.is_newer("1.1.0", "1.0.9"))
        self.assertTrue(firmware_release.is_newer("1.1", "1.0.9"))
        self.assertFalse(firmware_release.is_newer("1.0.0", "1.0.0"))
        self.assertFalse(firmware_release.is_newer("0.9", "1.0"))

    def test_versao_ilegivel_nao_sugere_atualizacao(self):
        self.assertFalse(firmware_release.is_newer("dev", "1.0.0"))
        self.assertFalse(firmware_release.is_newer("1.0.0", ""))


if __name__ == "__main__":
    unittest.main()


class VersaoDoAnexoTest(unittest.TestCase):
    """A versão do firmware precisa vir do NOME DO ANEXO, não da tag.

    As tags do repositório versionam o *aplicativo* (v0.2.0); o firmware
    tem numeração própria (2.0.0). Lendo a tag, o diálogo comparava
    "0.2.0" com o "2.0.0" que o dispositivo informa no ``hello`` e
    concluía que o release era mais antigo — o aviso de atualização dizia
    o contrário do certo e a mensagem de sucesso mostrava a versão errada.
    """

    def _release(self, tag, asset):
        cliente = ClienteFalso(RespostaFalsa(payload=[_release_payload(tag, asset)]))
        return firmware_release.latest_release(session=cliente)

    def test_versao_vem_do_anexo_e_nao_da_tag(self):
        release = self._release("v0.2.0", "firmware-2.0.0.bin")
        self.assertEqual(release.version, "2.0.0")
        self.assertEqual(release.tag, "v0.2.0")  # a tag segue sendo a do release

    def test_aviso_de_atualizacao_fica_correto(self):
        release = self._release("v0.2.0", "firmware-2.1.0.bin")
        # Dispositivo com 2.0.0 deve ser avisado de que há firmware novo.
        self.assertTrue(firmware_release.is_newer(release.version, "2.0.0"))
        igual = self._release("v0.2.0", "firmware-2.0.0.bin")
        self.assertFalse(firmware_release.is_newer(igual.version, "2.0.0"))
        self.assertEqual(igual.version, "2.0.0")

    def test_anexo_sem_numero_cai_para_a_tag(self):
        release = self._release("v0.2.0", "firmware.bin")
        self.assertEqual(release.version, "0.2.0")

    def test_numero_do_chip_no_nome_nao_vira_versao(self):
        release = self._release("v0.2.0", "firmware-esp32c3-2.0.0.bin")
        self.assertEqual(release.version, "2.0.0")

    def test_extrai_versao_de_nomes_variados(self):
        casos = {
            "firmware-2.0.0.bin": "2.0.0",
            "firmware-v2.0.0.bin": "2.0.0",
            "firmware_1.10.2.bin": "1.10.2",
            "firmware-2.0.bin": "2.0",
            "firmware.bin": "",          # sem número: quem decide é a tag
            "firmware-esp32c3.bin": "",  # "32" não é versão
        }
        for nome, esperado in casos.items():
            self.assertEqual(firmware_release.version_from_asset(nome), esperado, nome)
