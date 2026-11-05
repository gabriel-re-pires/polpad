"""Testes do protocolo serial e do empacotamento de imagens."""

import base64
import unittest

from PIL import Image

from polpad.core import icons
from polpad.core.models import SCREEN_H, SCREEN_W
from polpad.device import protocol


class ProtocolTest(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        message = {"t": "key", "k": 7, "e": "down"}
        self.assertEqual(protocol.decode(protocol.encode(message)), message)

    def test_decode_tolerates_boot_logs(self):
        self.assertIsNone(protocol.decode(b"ets Jul 29 2019 12:21:46\r"))
        self.assertIsNone(protocol.decode(b""))
        self.assertIsNone(protocol.decode(b"{json quebrado"))
        self.assertIsNone(protocol.decode(b'{"sem_tipo": 1}'))

    def test_text_message_limits_lines(self):
        message = protocol.msg_text(["a", "b", "c", "d"])
        self.assertEqual(len(message["lines"]), 3)


class IconPackingTest(unittest.TestCase):
    def test_pack_unpack_roundtrip(self):
        img = Image.new("1", (SCREEN_W, SCREEN_H), 0)
        pixels = img.load()
        for x in range(0, SCREEN_W, 3):
            pixels[x, x % SCREEN_H] = 255
        packed = icons.pack_bits(img)
        self.assertEqual(len(packed), SCREEN_W * SCREEN_H // 8)
        restored = icons.unpack_bits(packed)
        self.assertEqual(list(img.getdata()), list(restored.getdata()))

    def test_payload_is_base64_of_1024_bytes(self):
        img = Image.new("1", (SCREEN_W, SCREEN_H), 255)
        payload = base64.b64encode(icons.pack_bits(img)).decode()
        self.assertEqual(len(base64.b64decode(payload)), 1024)

    def test_load_for_oled_resizes_any_image(self, tmp_name="_tmp_icon.png"):
        import os
        import tempfile

        src = Image.new("RGB", (500, 300), (255, 128, 0))
        path = os.path.join(tempfile.gettempdir(), tmp_name)
        src.save(path)
        try:
            mono = icons.load_for_oled(path)
            self.assertEqual(mono.size, (SCREEN_W, SCREEN_H))
            self.assertEqual(mono.mode, "1")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
