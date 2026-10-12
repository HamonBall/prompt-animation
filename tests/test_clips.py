import json
from pathlib import Path
import tempfile
import unittest
from avatar_app.clips import load_catalog, select_clip
from avatar_app.models import PlanError


class ClipTests(unittest.TestCase):
    def test_explicit_metadata_selection_and_relative_asset_path(self):
        scratch = Path(__file__).resolve().parents[1] / 'artifacts' / 'test-tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            (root / 'sample.fbx').write_bytes(b'fixture')
            row = {'id': 'sit', 'path': 'sample.fbx', 'tags': ['sit'],
                   'starting_state': 'standing', 'ending_state': 'seated',
                   'source_rig': 'Mixamo', 'provenance': 'Owned test fixture',
                   'start_frame': 5, 'end_frame': 20, 'planted_feet': ['left', 'right']}
            catalog = root / 'clips.json'
            catalog.write_text(json.dumps([row]), encoding='utf-8')
            records = load_catalog(catalog)
            self.assertEqual(select_clip(records, 'sit', 'standing').path, str(root / 'sample.fbx'))
            with self.assertRaises(PlanError):
                select_clip(records, 'lie', 'standing')
            for changes in ({'provenance': ''}, {'path': 'missing.fbx'}, {'end_frame': 2},
                            {'source_rig': 'Unknown'}, {'planted_feet': ['head']}):
                catalog.write_text(json.dumps([{**row, **changes}]), encoding='utf-8')
                with self.subTest(changes=changes), self.assertRaises(PlanError):
                    load_catalog(catalog)
