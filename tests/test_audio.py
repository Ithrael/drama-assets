import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave

import imageio_ffmpeg

from extract_audio import extract_assets


class AudioAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / 'silent-video.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error',
                        '-f', 'lavfi', '-i', 'color=size=32x32:rate=1',
                        '-t', '1', '-an', str(self.video)], check=True)
        self.character = self.root / 'package' / 'character-01'
        self.character.mkdir(parents=True)
        (self.character / 'character.json').write_text(json.dumps(
            {'character_id': '01', 'description': '原有描述必须保留'}))
        self.clips = [{'character_id': '01', 'start': 0, 'end': 0.8}]

    def test_no_audio_creates_status_but_no_fake_wavs(self):
        records = extract_assets(self.video, self.clips, self.character.parent)
        self.assertEqual(records[0]['status'], 'source_has_no_audio')
        self.assertIsNone(records[0]['voice'])
        self.assertEqual(list(self.character.rglob('*.wav')), [])
        saved = json.loads((self.character / 'character.json').read_text())
        self.assertEqual(saved['description'], '原有描述必须保留')
        self.assertEqual(saved['audio_assets'], records[0])

    def test_existing_audio_is_never_overwritten(self):
        audio = self.character / 'audio'
        audio.mkdir()
        original = audio / 'voice.wav'
        original.write_bytes(b'existing-user-audio')
        with self.assertRaisesRegex(ValueError, '已有人物音频'):
            extract_assets(self.video, self.clips, self.character.parent)
        self.assertEqual(original.read_bytes(), b'existing-user-audio')

    def test_invalid_times_and_role_paths_leave_package_unchanged(self):
        for cid, start, end in [('01', -1, 1), ('01', 1, 1),
                                ('01', 0, float('nan')), ('../outside', 0, 1)]:
            with self.subTest(cid=cid, start=start, end=end):
                with self.assertRaises(ValueError):
                    extract_assets(self.video, [dict(character_id=cid, start=start, end=end)],
                                   self.character.parent)
        self.assertFalse((self.character / 'audio').exists())

    def test_silence_and_out_of_bounds_never_become_voice_assets(self):
        source = self.root / 'silence.wav'
        with wave.open(str(source), 'wb') as wav:
            wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0' * 16000)
        for start, end in [(0, 0.8), (2, 3)]:
            with self.subTest(start=start, end=end):
                with self.assertRaises(ValueError):
                    extract_assets(source, [dict(character_id='01', start=start, end=end)],
                                   self.character.parent)
                self.assertFalse((self.character / 'audio').exists())


if __name__ == '__main__':
    unittest.main()
