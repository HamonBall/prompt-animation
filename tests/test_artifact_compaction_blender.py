"""Opt-in integration checks on copies. Run directly with Blender's Python."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.compact_stage_artifacts import compact_case,BLENDER
from tools.artifact_store import digest
from artifact_test_fixture import copy_scene


@unittest.skipUnless('--blender-integration' in sys.argv, 'explicit real-Blender integration flag required')
class CompactionIntegration(unittest.TestCase):
    def setUp(self):
        scratch=ROOT/'artifacts/maintenance/storage-v2/.scratch';scratch.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch,prefix='migration-test-')
        self.root=Path(temp.name).resolve()
        assert self.root.is_relative_to(scratch)
        self.addCleanup(temp.cleanup)
        self.case=self.root/'artifacts/stages/05.1b/demo/case'
        self.case.mkdir(parents=True)
        source=ROOT/'artifacts/stages/05.1b/demo/torso.lean.default'
        for name in ('entry.json','instance.json','fragment.json','executable.json','result.json'):
            shutil.copy2(source/name,self.case/name)
        copy_scene(source,self.case/'preview.blend')
        shutil.copy2(source.parent/'profile.json',self.case.parent/'profile.json')
        self.allowed=[self.root/'artifacts/stages/05.1b']

    def compact(self):
        return compact_case(self.case,self.allowed,self.root/'evidence',apply=True)

    def test_identical_scene_retired_and_reapply_is_idempotent(self):
        shutil.copy2(self.case/'preview.blend',self.case/'visual-preview.blend')
        result=self.compact()
        self.assertEqual(result['retired_files'],1)
        canonical=digest(self.case/'preview.blend')
        self.assertEqual(self.compact()['status'],'already_compacted')
        self.assertEqual(digest(self.case/'preview.blend'),canonical)

    def test_distinct_camera_is_embedded_before_retirement(self):
        target=self.case/'visual-preview.blend'
        code="import bpy; bpy.context.scene.camera.location.x+=.25; bpy.ops.wm.save_as_mainfile(filepath="+repr(str(target))+",compress=True,copy=True)"
        subprocess.run([str(BLENDER),'--background',str(self.case/'preview.blend'),'--python-expr',code],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
        result=self.compact()
        self.assertEqual(result['retired_files'],1)
        record=json.loads((self.case/'artifact-migration.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(record['preserved_cameras']),2)

    def test_differing_action_is_retained(self):
        copy_scene(ROOT/'artifacts/stages/05.1b/demo/torso.twist.default',self.case/'visual-preview.blend')
        old=digest(self.case/'visual-preview.blend')
        result=self.compact()
        self.assertTrue(result['retained'])
        self.assertEqual(digest(self.case/'visual-preview.blend'),old)

    def test_corrupt_second_scene_is_retained(self):
        (self.case/'visual-preview.blend').write_bytes(b'corrupt historical scene')
        result=self.compact()
        self.assertTrue(result['retained'])
        self.assertEqual((self.case/'visual-preview.blend').read_bytes(),b'corrupt historical scene')

    def test_backup_only_playable_copy_is_retained(self):
        backup=self.case/'preview.blend1'
        (self.case/'preview.blend').rename(backup)
        original=digest(backup)
        result=self.compact()
        self.assertEqual(result['status'],'retained_backup_only')
        self.assertEqual(digest(backup),original)
        self.assertFalse((self.case/'preview.blend').exists())


if __name__=='__main__':
    if '--blender-integration' in sys.argv:sys.argv.remove('--blender-integration')
    # The decorator was evaluated before removing the custom flag.
    unittest.main()
