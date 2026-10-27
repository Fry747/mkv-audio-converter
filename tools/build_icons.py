"""Render the unchanged Breeze SVG into PNG and a multi-resolution Windows ICO."""
from pathlib import Path
import struct
from PySide6.QtCore import QBuffer, QIODevice, QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]


def build():
    app = QGuiApplication.instance() or QGuiApplication([])
    folder = ROOT / 'mkv_audio_converter/assets'
    renderer = QSvgRenderer(str(folder / 'icon.svg'))
    if not renderer.isValid():
        raise RuntimeError('Invalid source icon')
    frames = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        bitmap = QImage(size, size, QImage.Format.Format_ARGB32)
        bitmap.fill(0)
        painter = QPainter(bitmap)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        data = QBuffer()
        data.open(QIODevice.OpenModeFlag.WriteOnly)
        if not bitmap.save(data, 'PNG'):
            raise RuntimeError('PNG encoding failed')
        frames.append((size, bytes(data.data())))
        if size == 256:
            (folder / 'icon.png').write_bytes(bytes(data.data()))
    offset = 6 + 16 * len(frames)
    directory, images = bytearray(), bytearray()
    for size, data in frames:
        directory += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        images += data
        offset += len(data)
    (folder / 'icon.ico').write_bytes(struct.pack('<HHH', 0, 1, len(frames)) + directory + images)


if __name__ == '__main__':
    build()
