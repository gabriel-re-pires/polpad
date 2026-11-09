"""Ponto de entrada: ``python -m polpad``."""

from __future__ import annotations

import logging
import sys


def _menu_command(argv: list[str]) -> int | None:
    """``--instalar-no-menu`` / ``--remover-do-menu`` (Linux), sem abrir janela."""
    if "--instalar-no-menu" not in argv and "--remover-do-menu" not in argv:
        return None
    if not sys.platform.startswith("linux"):
        print("Disponível só no Linux.", file=sys.stderr)
        return 2
    from pathlib import Path

    from .update import linux_install

    if "--remover-do-menu" in argv:
        linux_install.uninstall()
        return 0
    linux_install.install(Path(sys.executable))
    print(f"Instalado em {linux_install.binary_path()}")
    return 0


def main() -> int:
    menu = _menu_command(sys.argv)
    if menu is not None:
        return menu

    from .update import setup_lock

    if setup_lock.setup_running():
        # O instalador está trocando os arquivos e reabre o Polpad no fim;
        # ficar aberto aqui prenderia o Polpad.exe que ele precisa substituir.
        return 0

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME, ORG_NAME, __version__
    from .app import MacropadApp
    from .core import logs
    from .core.store import default_data_dir
    from .single_instance import SingleInstance
    from .ui import notification_center
    from .ui.main_window import MainWindow
    from .ui.style import build_stylesheet
    from .ui.update_controller import UpdateController, safe_startup
    from .update import installer_options

    log_path = logs.setup()
    logging.getLogger(__name__).info(
        "%s %s iniciando (log: %s)", APP_NAME, __version__, log_path or "somente console"
    )

    start_minimized = "--minimized" in sys.argv
    # Reaberto após troca de versão: a instância antiga pode demorar a sair.
    after_update = "--apos-atualizacao" in sys.argv
    frozen = bool(getattr(sys, "frozen", False))

    # Liga a janela ao polpad.desktop (ícone no Wayland); tem de vir antes do
    # QApplication, que se registra no portal com esse nome.
    QApplication.setDesktopFileName("polpad")
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName(APP_NAME)
    qt_app.setOrganizationName(ORG_NAME)
    qt_app.setStyleSheet(build_stylesheet())
    # Fechar a janela minimiza para a bandeja; sair de verdade é pelo menu.
    qt_app.setQuitOnLastWindowClosed(False)

    # A segunda instância só pede à primeira que apareça e encerra.
    instance = SingleInstance()
    if not instance.try_acquire(wait_s=5.0 if after_update else 0.0):
        logging.getLogger(__name__).info(
            "já existe uma instância em execução; encerrando esta"
        )
        return 0

    # Antes da janela: confere a troca anterior e instala a pendente.
    result = safe_startup(
        default_data_dir(), __version__, frozen, release_instance=instance.release
    )
    if result.action == "exit":
        return 0

    core = MacropadApp()
    # Escolhas do instalador: antes da janela, que grava a inicialização
    # automática.
    if installer_options.apply(core.store.data_dir, core.store.settings):
        core.store.save()
    window = MainWindow(core)
    updates = UpdateController(
        core.store,
        window,
        release_instance=instance.release,
        quit_app=window.quit_for_switch,
        center=notification_center,
    )
    window.set_update_controller(updates)
    instance.activated.connect(window.present)
    if not start_minimized:
        window.show()
    updates.show_startup_result(result)
    if frozen:
        # Pelo código-fonte o atualizador fica desligado.
        updates.start()
        QTimer.singleShot(0, updates.maybe_offer_linux_install)
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
