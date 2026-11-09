"""Suporte a Linux (X11): códigos de tecla, inicialização automática e
abertura de programas seguem regras diferentes das do Windows."""

import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from polpad.actions import builtin, keys
from polpad.actions.base import ActionError
from polpad.core import autostart
from polpad.device import flasher
from polpad.integrations import foreground

LINUX = sys.platform.startswith("linux")


class CapturaDeAtalhoNoLinuxTest(unittest.TestCase):
    """No X11 o ``nativeVirtualKey`` é o keysym. Lido como código do
    Windows, o "a" minúsculo (0x61) caía na faixa do teclado numérico e
    era gravado como "1" — e "b".."i" como "2".."9".
    """

    CTRL, SHIFT, ALT = 0x04000000, 0x02000000, 0x08000000
    KEYPAD = 0x20000000

    @staticmethod
    def _xkb(key, mods, keysym, scan):
        return keys.names_from_event(key, mods, keysym, scan, xkb=True)

    def test_letra_minuscula_nao_vira_numero(self):
        self.assertEqual(self._xkb(0x41, 0, 0x61, 38), ["a"])
        self.assertEqual(self._xkb(0x49, 0, 0x69, 31), ["i"])

    def test_ctrl_c(self):
        self.assertEqual(self._xkb(0x43, self.CTRL, 0x63, 54), ["ctrl", "c"])

    def test_shift_1_usa_a_tecla_fisica_e_nao_o_simbolo(self):
        # Com Shift o keysym já é "exclam" (0x21); o código X 10 é o do "1".
        self.assertEqual(self._xkb(0x21, self.SHIFT, 0x21, 10), ["shift", "1"])

    def test_teclado_numerico(self):
        self.assertEqual(self._xkb(0x35, self.KEYPAD, 0xFFB5, 84), ["5"])

    def test_teclas_especiais(self):
        self.assertEqual(self._xkb(0x01000033, self.ALT, 0xFFC1, 70), ["alt", "f4"])
        self.assertEqual(self._xkb(0x20, 0, 0x20, 65), ["space"])
        self.assertEqual(self._xkb(0x2D, 0, 0x2D, 20), ["-"])


class TeclasDeMidiaTest(unittest.TestCase):
    """Os códigos VK de mídia do Windows não significam nada no X11: lá
    0xB3 é o keysym de "³". Cada plataforma usa os seus."""

    def test_linux_usa_keysyms_xf86(self):
        with mock.patch.object(keys.sys, "platform", "linux"):
            self.assertEqual(keys.media_key("play_pause").vk, 0x1008FF14)
            self.assertEqual(keys.media_key("volume_up").vk, 0x1008FF13)

    def test_windows_continua_com_os_vk(self):
        with mock.patch.object(keys.sys, "platform", "win32"):
            self.assertEqual(keys.media_key("play_pause").vk, 0xB3)

    def test_controle_desconhecido(self):
        self.assertIsNone(keys.media_key("ejetar"))

    def test_todos_os_controles_existem_nas_duas_plataformas(self):
        self.assertEqual(set(keys.MEDIA_KEYSYM), set(keys.MEDIA_VK))
        self.assertEqual(set(keys.MEDIA_TITLES), set(keys.MEDIA_VK))


@unittest.skipUnless(LINUX, "inicialização automática XDG")
class InicializacaoAutomaticaXdgTest(unittest.TestCase):
    """No Linux a inicialização automática é um .desktop em
    ``~/.config/autostart``; antes ela simplesmente não existia."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_ligar_e_desligar(self):
        self.assertFalse(autostart.is_enabled())
        autostart.apply(True)
        arquivo = Path(self._tmp.name) / "autostart" / "polpad.desktop"
        self.assertTrue(arquivo.exists())
        self.assertTrue(autostart.is_enabled())
        conteudo = arquivo.read_text(encoding="utf-8")
        self.assertIn("-m polpad --minimized", conteudo)
        autostart.apply(False)
        self.assertFalse(arquivo.exists())
        # Desligar o que já está desligado não é erro.
        autostart.apply(False)

    def test_executavel_empacotado(self):
        with (
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch.object(sys, "executable", "/home/eu/.local/bin/polpad"),
        ):
            self.assertIn(
                "Exec=/home/eu/.local/bin/polpad --minimized\n",
                autostart.desktop_entry(),
            )


class CampoExecTest(unittest.TestCase):
    """O campo Exec tem regras próprias de aspas (Desktop Entry Spec)."""

    def test_caminho_simples_fica_sem_aspas(self):
        self.assertEqual(
            autostart.exec_line(["/usr/bin/polpad", "-x"]), "/usr/bin/polpad -x"
        )

    def test_espaco_pede_aspas(self):
        self.assertEqual(
            autostart.exec_line(["/home/a b/python", "-m"]), '"/home/a b/python" -m'
        )

    def test_caracteres_especiais(self):
        self.assertEqual(autostart.exec_line(["100%"]), "100%%")
        self.assertEqual(autostart.exec_line(["$HOME"]), '"\\\\$HOME"')


class TerminalVisivelTest(unittest.TestCase):
    """ "Abrir em um terminal visível" usava o ``cmd /k`` do Windows; no
    Linux o comando rodava escondido."""

    def test_usa_o_primeiro_terminal_disponivel(self):
        def which(nome):
            return f"/usr/bin/{nome}" if nome == "xfce4-terminal" else None

        with (
            mock.patch.object(builtin.shutil, "which", which),
            mock.patch.dict(os.environ, {"SHELL": "/bin/bash"}),
        ):
            argv = builtin._terminal_argv("git pull", "/home/eu/projeto dois")
        self.assertEqual(argv[:4], ["/usr/bin/xfce4-terminal", "-x", "/bin/bash", "-c"])
        script = argv[4]
        self.assertIn("cd '/home/eu/projeto dois'", script)
        self.assertIn("git pull", script)
        # Como o /k: o terminal continua aberto depois do comando.
        self.assertTrue(script.endswith("exec /bin/bash"))

    def test_sem_terminal(self):
        with mock.patch.object(builtin.shutil, "which", return_value=None):
            self.assertIsNone(builtin._terminal_argv("ls"))


@unittest.skipUnless(LINUX, "abrir alvos fora do Windows (no Windows é o os.startfile)")
class AbrirAlvoNoLinuxTest(unittest.TestCase):
    """No Windows o ``os.startfile`` abre um .exe; no Linux só se aceitava
    um caminho existente, entregue ao ``xdg-open`` — que abre um binário
    num editor de texto em vez de executá-lo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _arquivo(self, nome, conteudo, executavel):
        caminho = self.dir / nome
        caminho.write_bytes(conteudo)
        if executavel:
            caminho.chmod(caminho.stat().st_mode | stat.S_IXUSR)
        return caminho

    def test_pasta_e_documento_abrem_no_app_padrao(self):
        self.assertEqual(builtin._launch_argv(str(self.dir)), ["xdg-open", str(self.dir)])
        pdf = self._arquivo("doc.pdf", b"%PDF-1.7", executavel=False)
        self.assertEqual(builtin._launch_argv(str(pdf)), ["xdg-open", str(pdf)])

    def test_programa_e_executado(self):
        script = self._arquivo("app.sh", b"#!/bin/sh\necho oi\n", executavel=True)
        self.assertEqual(builtin._launch_argv(str(script)), [str(script)])

    def test_arquivo_com_x_que_nao_e_programa_abre_no_app_padrao(self):
        # Partições NTFS montadas marcam tudo como executável.
        pdf = self._arquivo("ntfs.pdf", b"%PDF-1.7", executavel=True)
        self.assertEqual(builtin._launch_argv(str(pdf)), ["xdg-open", str(pdf)])

    def test_programa_do_path_com_argumentos(self):
        with mock.patch.object(builtin.shutil, "which", return_value="/usr/bin/code"):
            argv = builtin._launch_argv("code ~/projeto")
        self.assertEqual(argv, ["code", str(Path.home() / "projeto")])

    def test_alvo_inexistente(self):
        with (
            mock.patch.object(builtin.shutil, "which", return_value=None),
            self.assertRaises(ActionError),
        ):
            builtin._launch_argv("programa-que-nao-existe")


class AppEmFocoNoLinuxTest(unittest.TestCase):
    """No Linux o app em foco é identificado pela classe da janela."""

    def test_usa_a_classe_e_nao_o_papel_da_janela(self):
        self.assertEqual(foreground.wm_class_name(("Navigator", "firefox")), "firefox")
        self.assertEqual(foreground.wm_class_name(("code", "Code")), "code")

    def test_sem_classe(self):
        self.assertIsNone(foreground.wm_class_name(None))
        self.assertEqual(foreground.wm_class_name(("xterm", "")), "xterm")


@unittest.skipUnless(LINUX, "grupo dono da porta serial (não há módulo grp no Windows)")
class PermissaoDaPortaTest(unittest.TestCase):
    """Sem estar no grupo dono da porta (uucp/dialout), o esptool falha com
    "Permission denied" embrulhado em "the port is busy or doesn't exist" —
    e a dica falava em fechar o Monitor Serial."""

    def test_sugere_entrar_no_grupo(self):
        texto = flasher._describe(
            OSError(
                "Could not open /dev/ttyACM0, the port is busy or doesn't exist.\n"
                "([Errno 13] could not open port /dev/ttyACM0: [Errno 13] "
                "Permission denied: '/dev/ttyACM0')"
            )
        )
        self.assertIn("usermod -aG", texto)
        self.assertNotIn("Monitor Serial", texto)


class InstalacaoNoMenuTest(unittest.TestCase):
    """O executável baixado se instala no menu sem o código-fonte."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        casa = Path(self._tmp.name) / "casa"
        casa.mkdir()
        self.casa = casa
        ambiente = {
            "HOME": str(casa),
            "XDG_DATA_HOME": str(casa / ".local" / "share"),
            "XDG_CONFIG_HOME": str(casa / ".config"),
        }
        patcher = mock.patch.dict(os.environ, ambiente)
        patcher.start()
        self.addCleanup(patcher.stop)
        home = mock.patch.object(Path, "home", return_value=casa)
        home.start()
        self.addCleanup(home.stop)
        self.origem = Path(self._tmp.name) / "Polpad"
        self.origem.write_bytes(b"\x7fELF")

    def test_instala_e_remove(self):
        from polpad.update import linux_install

        linux_install.install(self.origem)
        binario = self.casa / ".local" / "bin" / "polpad"
        desktop = self.casa / ".local" / "share" / "applications" / "polpad.desktop"
        self.assertEqual(linux_install.binary_path(), binario)
        self.assertEqual(binario.read_bytes(), b"\x7fELF")
        exec_esperado = f"Exec={autostart.exec_line([str(binario)])}"
        self.assertIn(exec_esperado, desktop.read_text(encoding="utf-8"))
        icones = list(linux_install.icon_paths().values())
        self.assertEqual(len(icones), 7)
        self.assertTrue(all(p.is_file() for p in icones))
        self.assertTrue(linux_install.is_installed())

        autostart.desktop_file().parent.mkdir(parents=True)
        autostart.desktop_file().write_text("x", encoding="utf-8")
        linux_install.uninstall()
        self.assertFalse(binario.exists())
        self.assertFalse(desktop.exists())
        self.assertFalse(any(p.exists() for p in icones))
        self.assertFalse(autostart.desktop_file().exists())
        self.assertFalse(linux_install.is_installed())

    @unittest.skipUnless(LINUX, "permissão de execução POSIX")
    def test_binario_executavel(self):
        from polpad.update import linux_install

        linux_install.install(self.origem)
        modo = linux_install.binary_path().stat().st_mode
        self.assertTrue(modo & stat.S_IXUSR)

    def test_running_from_menu(self):
        from polpad.update import linux_install

        binario = str(self.casa / ".local" / "bin" / "polpad")
        with mock.patch.object(sys, "executable", binario):
            self.assertTrue(linux_install.running_from_menu())
        with mock.patch.object(sys, "executable", str(self.origem)):
            self.assertFalse(linux_install.running_from_menu())


class OpcoesDoMenuTest(unittest.TestCase):
    def test_sem_opcao_segue_para_a_janela(self):
        from polpad import __main__ as entrada

        self.assertIsNone(entrada._menu_command(["Polpad"]))

    def test_instalar_no_menu_usa_o_proprio_executavel(self):
        from polpad import __main__ as entrada

        with (
            mock.patch.object(sys, "platform", "linux"),
            mock.patch("polpad.update.linux_install.install") as instalar,
            mock.patch.object(sys, "executable", "/opt/polpad/Polpad"),
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                codigo = entrada._menu_command(["Polpad", "--instalar-no-menu"])
            self.assertEqual(codigo, 0)
        instalar.assert_called_once_with(Path("/opt/polpad/Polpad"))


if __name__ == "__main__":
    unittest.main()
