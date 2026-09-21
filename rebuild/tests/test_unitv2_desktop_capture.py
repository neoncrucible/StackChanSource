import asyncio
import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from kcore.appliance import KadenceAppliance
from kcore.vision import DeskVision


def jpeg(size=(640, 480)):
    output = io.BytesIO()
    Image.new('RGB', size, 'red').save(output, format='JPEG')
    return output.getvalue()


class UnitV2DesktopCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_source_and_dimensions(self):
        events = []
        vision = DeskVision(lambda name, data: events.append(data))
        await vision.accept_jpeg(jpeg(), vision.generation)
        self.assertEqual((vision.width, vision.height), (640, 480))
        self.assertEqual(events[-1]['source_device'], 'unitv2-camera')
        self.assertFalse(events[-1]['retained'])
        with Image.open(io.BytesIO(vision.png)) as image:
            self.assertEqual(image.size, (640, 480))

    async def test_clear_invalidates_inflight_capture(self):
        vision = DeskVision()
        generation = vision.generation
        vision.clear()
        with self.assertRaisesRegex(RuntimeError, 'cleared or replaced'):
            await vision.accept_jpeg(jpeg(), generation)
        self.assertIsNone(vision.png)

    async def test_robot_capture_resets_source(self):
        vision = DeskVision()
        await vision.accept_jpeg(jpeg(), vision.generation)
        with patch('kcore.vision.decode_image', return_value=(b'png', [])):
            await vision.accept(b'raw')
        self.assertEqual(vision.source_device, 'robot-camera')
        self.assertEqual((vision.width, vision.height), (320, 240))

    async def test_save_uses_actual_source_and_dimensions(self):
        vision = DeskVision()
        await vision.accept_jpeg(jpeg(), vision.generation)
        class Store:
            async def call(self, name): return [{'id': 1}]
            def _call(self, name, args):
                self.saved = args
                return {'id': 1, 'media_id': 2}
        store = Store()
        with tempfile.TemporaryDirectory() as directory:
            await vision.save(Path(directory), store, 1)
        self.assertEqual(store.saved['width'], 640)
        self.assertEqual(store.saved['height'], 480)
        self.assertEqual(store.saved['source_device'], 'unitv2-camera')

    async def test_cancelled_capture_never_publishes(self):
        app = KadenceAppliance.__new__(KadenceAppliance)
        app.vision = DeskVision()
        app._unitv2_capture_lock = asyncio.Lock()
        started = asyncio.Event()
        loop = asyncio.get_running_loop()
        def capture(*args, **kwargs):
            loop.call_soon_threadsafe(started.set)
            time.sleep(.05)
            return jpeg()
        with patch('kcore.unitv2_network.start_camera_stream'), patch('kcore.unitv2_network.capture_jpeg', side_effect=capture):
            task = asyncio.create_task(app.capture_unitv2_snapshot('192.168.40.175'))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertIsNone(app.vision.png)
        self.assertFalse(app._unitv2_capture_lock.locked())
