"""Testes dos backups dos perfis feitos antes de trocar de versão."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from polpad.update import backup


class BackupTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dados = Path(self._tmp.name)
        (self.dados / "config.json").write_text("B", encoding="utf-8")
        (self.dados / "icons").mkdir()
        (self.dados / "icons" / "a.png").write_bytes(b"png")
        for sub, nome in (("logs", "x.log"), ("firmware", "f.bin"), ("updates", "u.exe")):
            (self.dados / sub).mkdir()
            (self.dados / sub / nome).write_bytes(b"x")
        self.agora = datetime(2026, 11, 6, 12, 0, 0)

    def _arquivos(self, pasta: Path) -> list[str]:
        return sorted(
            p.relative_to(pasta).as_posix() for p in pasta.rglob("*") if p.is_file()
        )

    def test_copia_so_perfis_e_icones(self):
        copia = backup.create(self.dados, "0.5.0", "0.5.1", now=self.agora)
        self.assertEqual(
            self._arquivos(copia.path), ["backup.json", "config.json", "icons/a.png"]
        )
        self.assertEqual(copia.from_version, "0.5.0")
        self.assertEqual(copia.to_version, "0.5.1")

    def test_mantem_cinco(self):
        for i in range(7):
            backup.create(
                self.dados, f"0.5.{i}", "0.6.0", now=self.agora + timedelta(minutes=i)
            )
        lista = backup.list_backups(self.dados)
        self.assertEqual(len(lista), 5)
        self.assertEqual(lista[0].from_version, "0.5.6")
        self.assertEqual(lista[-1].from_version, "0.5.2")

    def test_restaurar_guarda_o_atual_antes(self):
        antiga = backup.create(self.dados, "0.6.0", "0.5.0", now=self.agora)
        (antiga.path / "config.json").write_text("A", encoding="utf-8")
        seguranca = backup.restore(
            self.dados, antiga, "0.5.0", now=self.agora + timedelta(minutes=1)
        )
        self.assertEqual((self.dados / "config.json").read_text(encoding="utf-8"), "A")
        self.assertEqual(
            (seguranca.path / "config.json").read_text(encoding="utf-8"), "B"
        )
        self.assertEqual(seguranca.to_version, "restauração")
        self.assertTrue((self.dados / "icons" / "a.png").is_file())

    def test_restaurar_a_mais_antiga_com_cinco_guardadas(self):
        for i in range(5):
            backup.create(
                self.dados, f"0.5.{i}", "0.6.0", now=self.agora + timedelta(minutes=i)
            )
        mais_antiga = backup.list_backups(self.dados)[-1]
        (mais_antiga.path / "config.json").write_text("A", encoding="utf-8")
        backup.restore(
            self.dados, mais_antiga, "0.6.0", now=self.agora + timedelta(minutes=9)
        )
        self.assertEqual((self.dados / "config.json").read_text(encoding="utf-8"), "A")
        self.assertEqual(len(backup.list_backups(self.dados)), 5)

    def test_backup_json_corrompido_e_ignorado(self):
        backup.create(self.dados, "0.5.0", "0.5.1", now=self.agora)
        estragada = self.dados / "backups" / "estragada"
        estragada.mkdir()
        (estragada / "backup.json").write_text("{", encoding="utf-8")
        self.assertEqual(len(backup.list_backups(self.dados)), 1)

    def test_sem_pasta_de_backups(self):
        self.assertEqual(backup.list_backups(self.dados), [])

    def test_rotulo(self):
        copia = backup.Backup(Path("x"), self.agora, "0.6.0", "0.5.0")
        self.assertEqual(copia.label, "0.6.0 → 0.5.0")


if __name__ == "__main__":
    unittest.main()
