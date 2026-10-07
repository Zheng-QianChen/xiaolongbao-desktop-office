import json
from pathlib import Path
import tempfile
import unittest
from native_scene import NativeScene


class SceneTests(unittest.TestCase):
    def test_mode_does_not_overwrite_free_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'scene.json'
            scene=NativeScene(path)
            scene.positions['worker']=[180,190]
            scene.mode='house';scene.save()
            scene=NativeScene(path)
            self.assertEqual(scene.position('worker',[330,125],680,540,(107,85)),[330,125])
            scene.mode='free'
            self.assertEqual(scene.position('worker',[330,125],680,540,(107,85)),[180,190])

    def test_corrupt_or_offscreen_positions_recover(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'scene.json'
            path.write_text(json.dumps({'positions':{'bad':[None,1],'worker':[-999,9999]}}))
            scene=NativeScene(path)
            self.assertNotIn('bad',scene.positions)
            self.assertEqual(scene.position('worker',[330,125],680,540,(107,85)),[12,443])
            path.write_text('not JSON')
            self.assertEqual(NativeScene(path).mode,'free')


if __name__=='__main__':unittest.main()
