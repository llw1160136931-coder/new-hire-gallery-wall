import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.load_tests.generate_fixtures import MIB, main, make_jpeg, make_mp4, parse_sizes


class GenerateFixturesTests(unittest.TestCase):
    def test_parse_sizes_deduplicates_and_rejects_out_of_range_values(self):
        self.assertEqual(parse_sizes('1, 5,1'), [1, 5])
        with self.assertRaises(Exception):
            parse_sizes('0')
        with self.assertRaises(Exception):
            parse_sizes('501')

    def test_generated_jpeg_is_valid_and_has_exact_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.jpg'
            record = make_jpeg(path, 1, force=False)
            self.assertEqual(path.stat().st_size, MIB)
            self.assertEqual(record['content_type'], 'image/jpeg')
            with Image.open(path) as image:
                image.verify()

    def test_generated_mp4_has_expected_signature_and_exact_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.mp4'
            record = make_mp4(path, 1, source=None, force=False)
            self.assertEqual(path.stat().st_size, MIB)
            self.assertIn(b'ftyp', path.read_bytes()[:16])
            self.assertFalse(record['playable'])

    def test_main_writes_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            exit_code = main([
                '--output-dir', directory,
                '--image-mib', '1',
                '--video-mib', '1',
            ])
            self.assertEqual(exit_code, 0)
            manifest = json.loads((Path(directory) / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(len(manifest['fixtures']), 2)
            self.assertTrue(all(item['sha256'] for item in manifest['fixtures']))
            assets_csv = (Path(directory) / 'assets.csv').read_text(encoding='utf-8')
            self.assertIn('kind,path,content_type,sha256,playable', assets_csv)
            self.assertIn('image,', assets_csv)
            self.assertIn('video,', assets_csv)


if __name__ == '__main__':
    unittest.main()
