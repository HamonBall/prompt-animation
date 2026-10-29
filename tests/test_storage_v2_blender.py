"""Copy-based real Blender retirement/migration transactions (explicit opt-in)."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.storage_v2 import retire_history,migrate_case,OUT
from tools.artifact_store import digest,atomic_json
from artifact_test_fixture import copy_scene,migration_record


@unittest.skipUnless('--blender-integration' in sys.argv,'explicit Blender integration opt-in required')
class StorageV2BlenderTests(unittest.TestCase):
    def setUp(self):
        parent=OUT/'.scratch';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.base=Path(self.temp.name).resolve()
        assert self.base.is_relative_to(parent.resolve());self.addCleanup(self.temp.cleanup)
        self.case=self.base/'artifacts/stages/05.1b/demo/example';self.case.mkdir(parents=True)
        source=ROOT/'artifacts/stages/05.1b/demo/torso.wave.default'
        for name in ('result.json','entry.json','instance.json','fragment.json','executable.json'):
            shutil.copy2(source/name,self.case/name)
        copy_scene(source,self.case/'preview.blend');migration_record(self.case)
        shutil.copy2(source.parent/'profile.json',self.case/'profile.json')
        self.original=digest(self.case/'preview.blend');self.result=digest(self.case/'result.json')
        for name in ('preview.blend1','visual-preview.blend1'):shutil.copy2(self.case/'preview.blend',self.case/name)

    def test_verified_obsolete_history_and_repeat(self):
        value=retire_history(self.case,apply=True)
        self.assertEqual(value['files'],2);self.assertEqual(digest(self.case/'preview.blend'),self.original)
        self.assertEqual(digest(self.case/'result.json'),self.result)
        self.assertEqual(retire_history(self.case,apply=True)['status'],'no_backups')

    def test_changed_canonical_and_backup_only_retained(self):
        (self.case/'preview.blend').write_bytes(b'changed canonical')
        with self.assertRaisesRegex(RuntimeError,'canonical hash'):retire_history(self.case,apply=True)
        self.assertTrue((self.case/'preview.blend1').exists())
        (self.case/'preview.blend').unlink()
        self.assertEqual(retire_history(self.case,apply=True)['status'],'retained_backup_only')

    def test_interrupted_retirement_resumes(self):
        from tools import storage_v2
        original=storage_v2.append_event;count=[0]
        def interrupt(event,*args,**kwargs):
            original(event,*args,**kwargs)
            if event['operation']=='obsolete_history_retired':
                count[0]+=1
                if count[0]==1:raise RuntimeError('injected interruption')
        with patch.object(storage_v2,'append_event',side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError,'interruption'):retire_history(self.case,apply=True)
        self.assertEqual(len(list(self.case.glob('*.blend1'))),1)
        self.assertEqual(retire_history(self.case,apply=True)['files'],1)

    def test_pending_bundle_validation_and_repeat(self):
        retire_history(self.case,apply=True)
        value=migrate_case(self.case,apply=True)
        self.assertEqual(value['status'],'migrated');self.assertFalse((self.case/'preview.blend').exists())
        m=json.loads((self.case/'preview-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(m['schema_version'],2);self.assertLess((self.case/'motion.blend').stat().st_size,8*1024**2)
        self.assertEqual(migrate_case(self.case,apply=True)['status'],'already_v2')

    def test_failure_before_manifest_preserves_source(self):
        retire_history(self.case,apply=True)
        with patch('tools.artifact_bundle.commit_bundle',side_effect=RuntimeError('before commit')):
            with self.assertRaisesRegex(RuntimeError,'before commit'):migrate_case(self.case,apply=True)
        self.assertEqual(digest(self.case/'preview.blend'),self.original)
        self.assertEqual(migrate_case(self.case,apply=True)['status'],'migrated')

    def test_failure_after_manifest_resumes_retirement(self):
        from tools import storage_v2
        original=storage_v2.append_event
        def interrupt(event,*args,**kwargs):
            original(event,*args,**kwargs)
            if event['operation']=='bundle_committed':raise RuntimeError('after commit')
        with patch.object(storage_v2,'append_event',side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError,'after commit'):migrate_case(self.case,apply=True)
        self.assertTrue((self.case/'preview.blend').exists())
        self.assertEqual(migrate_case(self.case,apply=True)['status'],'already_v2')
        self.assertFalse(list(self.case.glob('*.blend1')))
        self.assertFalse((self.case/'preview.blend').exists())


if __name__=='__main__':
    if '--blender-integration' in sys.argv:sys.argv.remove('--blender-integration')
    unittest.main()
