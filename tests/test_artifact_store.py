"""Failure safety and completion semantics, independent of Blender."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import artifact_store as store
from tools.compact_stage_artifacts import safe_path, compact_case


class StorageTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'artifacts/test-tmp'
        parent.mkdir(parents=True,exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        assert Path(self.temp.name).resolve().is_relative_to(parent.resolve())
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)

    def test_compact_numeric_output_preserves_every_value(self):
        value={'samples':[{'frame':1,'target':[.125,-.25,1.5],'measured':{'angle':20.0},'phase':None}]*20,
               'review':{'passed':True,'issues':[]}}
        pretty=self.out/'pretty.json';compact=self.out/'compact.json'
        store.atomic_json(pretty,value);store.atomic_json(compact,value,compact=True)
        self.assertEqual(json.loads(compact.read_text()),json.loads(pretty.read_text()))
        self.assertLess(compact.stat().st_size,pretty.stat().st_size)

    def fake_bpy(self, fail=False):
        preferences = SimpleNamespace(save_version=3)
        def save(**kwargs):
            self.assertTrue(kwargs['compress'])
            self.assertTrue(kwargs['copy'])
            self.assertEqual(preferences.save_version, 0)
            Path(kwargs['filepath']).write_bytes(b'compressed scene' * 8)
            if fail: raise RuntimeError('injected failure')
            return {'FINISHED'}
        @contextmanager
        def load(path):
            yield SimpleNamespace(scenes=['scene'], objects=['rig']), SimpleNamespace()
        class Libraries:
            def __len__(self): return 0
        libraries=Libraries()
        libraries.load=load
        return SimpleNamespace(context=SimpleNamespace(preferences=SimpleNamespace(filepaths=preferences)),
            ops=SimpleNamespace(file=SimpleNamespace(pack_all=lambda:None),wm=SimpleNamespace(save_as_mainfile=save)),
            data=SimpleNamespace(libraries=libraries))

    def test_atomic_save_repeat_and_failure_restore_preferences(self):
        destination=self.out/'preview.blend'
        destination.write_bytes(b'original')
        bad=self.fake_bpy(fail=True)
        with self.assertRaisesRegex(RuntimeError,'injected'):
            store.save_scene(destination,bpy_module=bad)
        self.assertEqual(destination.read_bytes(),b'original')
        self.assertEqual(bad.context.preferences.filepaths.save_version,3)
        good=self.fake_bpy()
        for _ in range(2): store.save_scene(destination,bpy_module=good)
        self.assertEqual(good.context.preferences.filepaths.save_version,3)
        self.assertEqual([p.name for p in self.out.iterdir()],['preview.blend'])

    def complete_case(self):
        (self.out/'preview.blend').write_bytes(b'blend')
        (self.out/'result.json').write_text('{"frames":2}',encoding='utf-8')
        for view in ('front','side'):
            (self.out/view).mkdir()
            for name in [f'{view}-sheet.png',f'{view}/0001.png',f'{view}/0002.png']:
                (self.out/name).write_bytes(b'\x89PNG\r\n\x1a\n'+b'x'*20)
        scene=SimpleNamespace(frame_start=1,frame_end=2,frame_current=1,render=SimpleNamespace(fps=30,fps_base=1))
        store.write_manifest(self.out,scene,views={'front':{},'side':{}},complete=True)
        return scene

    def test_missing_frame_and_changed_inputs_invalidate_resume(self):
        scene=self.complete_case()
        self.assertTrue(store.render_complete(self.out,('front','side')))
        (self.out/'front/0002.png').unlink()
        self.assertFalse(store.render_complete(self.out,('front','side')))
        with self.assertRaises(RuntimeError):store.write_manifest(self.out,scene,views={'front':{},'side':{}},complete=True)

    def test_stale_recipe_and_interrupted_manifest(self):
        scene=self.complete_case()
        (self.out/'entry.json').write_text('{}',encoding='utf-8')
        self.assertFalse(store.render_complete(self.out,('front','side')))
        store.write_manifest(self.out,scene,views={'front':{},'side':{}},complete=True)
        store.write_manifest(self.out,scene)
        self.assertFalse(store.render_complete(self.out,('front','side')))

    def test_live_writer_is_exclusive(self):
        with store.producer_lease(self.out):
            with self.assertRaisesRegex(RuntimeError,'Active artifact writer'):
                with store.producer_lease(self.out): pass
        self.assertFalse((self.out/'.artifact-writer.lock').exists())

    def test_path_escape_and_backup_only_retained(self):
        with self.assertRaises(ValueError):safe_path(self.out.parent,[self.out])
        with self.assertRaises(ValueError):safe_path(self.out/'..'/'outside',[self.out])
        (self.out/'preview.blend1').write_bytes(b'only recovery')
        self.assertEqual(compact_case(self.out,[self.out],self.out/'evidence',apply=True)['status'],'retained_backup_only')
        self.assertTrue((self.out/'preview.blend1').is_file())

    def test_entry_labels_are_not_parameter_labels(self):
        scene=SimpleNamespace(frame_start=1,frame_current=12)
        m=store.entry_metadata('entry-bent-turned.json',{},scene)
        self.assertEqual(m['entry_kind'],'authored_non_neutral')
        self.assertEqual(m['parameter_label'],'default parameters')

    def test_missing_packed_resource_keeps_previous_scene(self):
        destination=self.out/'preview.blend'
        destination.write_bytes(b'previous valid scene')
        fake=self.fake_bpy()
        fake.data.images=[SimpleNamespace(source='FILE',packed_file=None,name='Missing texture')]
        with self.assertRaisesRegex(RuntimeError,'not embedded'):
            store.save_scene(destination,bpy_module=fake)
        self.assertEqual(destination.read_bytes(),b'previous valid scene')
        self.assertEqual(fake.context.preferences.filepaths.save_version,3)

    def test_changed_scene_invalidates_completion(self):
        self.complete_case()
        (self.out/'preview.blend').write_bytes(b'different action')
        self.assertFalse(store.render_complete(self.out,('front','side')))

    @unittest.skipUnless(os.name=='nt','Windows junction regression')
    def test_junction_cannot_escape_allowed_root(self):
        import subprocess
        from tools.compact_stage_artifacts import inventory
        allowed=self.out/'allowed';allowed.mkdir()
        outside=self.out/'outside';outside.mkdir()
        link=allowed/'escape'
        result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
        if result.returncode:
            self.skipTest('Junction creation unavailable: '+result.stderr.decode(errors='replace').strip())
        try:
            with self.assertRaises(ValueError):safe_path(link,[allowed])
            with self.assertRaises(ValueError):inventory(allowed,[allowed])
        finally:
            assert link.is_junction() and link.parent.resolve()==allowed.resolve()
            assert outside.resolve().is_relative_to(self.out.resolve())
            os.rmdir(link)  # Remove only this test's junction, never its target.

    def test_reparse_metadata_is_rejected_before_traversal(self):
        from tools.compact_stage_artifacts import inventory
        from unittest.mock import MagicMock
        entry=SimpleNamespace(path=str(self.out/'escape'),is_symlink=lambda:False,
                              stat=lambda **kw:SimpleNamespace(st_file_attributes=0x400))
        entries=MagicMock()
        entries.__enter__.return_value=iter([entry])
        with patch('tools.compact_stage_artifacts.os.scandir',return_value=entries):
            with self.assertRaisesRegex(ValueError,'reparse'):
                inventory(self.out,[self.out])


if __name__=='__main__':unittest.main()
