"""Encontrar o macropad entre as portas seriais, no Linux e no Windows."""

from __future__ import annotations

import errno
import os
import unittest
from unittest import mock

import serial

from polpad.device import protocol, serial_access
from polpad.device.link import SerialLink, available_ports


class PortaFalsa:
    def __init__(self, device, vid=None, hwid="n/a", description="n/a"):
        self.device = device
        self.vid = vid
        self.hwid = hwid
        self.description = description


class ListaDePortasTest(unittest.TestCase):
    """No Linux o pyserial lista dezenas de /dev/ttyS* que não têm hardware
    nenhum por trás (32 num notebook comum). O macropad sumia no meio delas
    e o usuário testava uma por uma."""

    def _listar(self, portas):
        with mock.patch(
            "polpad.device.link.list_ports.comports", return_value=portas
        ):
            return [porta for porta, _ in available_ports()]

    def test_portas_fantasmas_do_linux_ficam_de_fora(self):
        portas = [PortaFalsa(f"/dev/ttyS{i}") for i in range(32)]
        portas.append(
            PortaFalsa(
                "/dev/ttyACM0",
                vid=protocol.ESPRESSIF_VID,
                hwid="USB VID:PID=303A:1001 SER=88:56 LOCATION=1-1:1.0",
                description="USB JTAG/serial debug unit",
            )
        )
        self.assertEqual(self._listar(portas), ["/dev/ttyACM0"])

    def test_porta_com_de_verdade_no_windows_continua(self):
        # COM1 da placa-mãe não é USB, mas existe: o Windows só lista o que há.
        portas = [PortaFalsa("COM1", hwid="ACPI\\PNP0501\\1")]
        self.assertEqual(self._listar(portas), ["COM1"])

    def test_macropad_vem_primeiro(self):
        portas = [
            PortaFalsa("COM3", vid=0x1A86, hwid="USB VID:PID=1A86:7523"),
            PortaFalsa("COM7", vid=protocol.ESPRESSIF_VID, hwid="USB VID:PID=303A:1001"),
            PortaFalsa("COM1", hwid="ACPI\\PNP0501\\1"),
        ]
        self.assertEqual(self._listar(portas), ["COM7", "COM3", "COM1"])


class PortaSemPermissaoTest(unittest.TestCase):
    """A busca automática achava o macropad, mas sem permissão para abrir a
    porta o aviso ia só para o log: a interface seguia em "Procurando o
    macropad…" como se ele não estivesse ligado."""

    def _link(self):
        self.negadas = []
        return SerialLink(
            on_message=lambda m: None,
            on_state=lambda c, p: None,
            on_denied=self.negadas.append,
        )

    def _abrir_falha(self, err):
        return mock.patch(
            "polpad.device.link.serial.Serial",
            side_effect=serial.SerialException(err, "could not open port"),
        )

    def test_avisa_a_interface_uma_vez_por_porta(self):
        link = self._link()
        with self._abrir_falha(errno.EACCES), self.assertLogs(
            "polpad.device.link", "WARNING"
        ):
            link._attempt("/dev/ttyACM0")
            link._attempt("/dev/ttyACM0")  # o enlace tenta de novo a cada 2 s
        self.assertEqual(self.negadas, ["/dev/ttyACM0"])

    def test_outros_erros_nao_sao_falta_de_permissao(self):
        link = self._link()
        with self._abrir_falha(errno.ENOENT):
            link._attempt("/dev/ttyACM0")
        self.assertEqual(self.negadas, [])

    def test_porta_negada_continua_sendo_tentada(self):
        # Depois de liberado o acesso, a próxima tentativa tem de conectar
        # sozinha — sem o rodízio pular a porta.
        link = self._link()
        with mock.patch(
            "polpad.device.link.list_ports.comports",
            return_value=[PortaFalsa("/dev/ttyACM0", vid=protocol.ESPRESSIF_VID)],
        ), self._abrir_falha(errno.EACCES), self.assertLogs(
            "polpad.device.link", "WARNING"
        ):
            link._attempt(link._find_port())
            self.assertEqual(link._find_port(), "/dev/ttyACM0")


class LiberarAcessoTest(unittest.TestCase):
    """Entrar no grupo uucp/dialout só vale depois de sair da sessão. Uma
    regra udev com ``uaccess`` dá acesso ao usuário da sessão na hora."""

    def _rodar(self, returncode=0, stderr=""):
        chamadas = []

        def run(argv, **kwargs):
            # O arquivo temporário com a regra é apagado depois: lê agora.
            with open(argv[-2], encoding="utf-8") as regra:
                chamadas.append((argv, regra.read()))
            return mock.Mock(returncode=returncode, stderr=stderr, stdout="")

        return chamadas, run

    def test_regra_cobre_o_esp32_pela_sessao_ativa(self):
        self.assertIn('ATTRS{idVendor}=="303a"', serial_access.RULE)
        self.assertIn('TAG+="uaccess"', serial_access.RULE)
        self.assertEqual(f"{protocol.ESPRESSIF_VID:04x}", "303a")

    def test_instala_a_regra_e_reaplica_com_uma_senha_so(self):
        chamadas, run = self._rodar()
        serial_access.grant(run=run)
        self.assertEqual(len(chamadas), 1, "pediria a senha mais de uma vez")
        argv, regra = chamadas[0]
        self.assertEqual(argv[0], "pkexec")
        self.assertEqual(argv[-1], str(serial_access.RULE_PATH))
        self.assertEqual(regra, serial_access.RULE)
        script = argv[3]
        self.assertIn("udevadm control --reload", script)
        self.assertIn("udevadm trigger", script)
        self.assertFalse(os.path.exists(argv[-2]), "temporário ficou para trás")

    def test_janela_de_senha_fechada(self):
        _, run = self._rodar(returncode=126)
        with self.assertRaises(serial_access.GrantCancelledError):
            serial_access.grant(run=run)

    def test_falha_traz_o_motivo(self):
        _, run = self._rodar(returncode=127, stderr="No authentication agent found.")
        with self.assertRaises(serial_access.GrantError) as ctx:
            serial_access.grant(run=run)
        self.assertNotIsInstance(ctx.exception, serial_access.GrantCancelledError)
        self.assertIn("No authentication agent", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
