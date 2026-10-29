"""Pure storage-v2 budget, path, retention and reference checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import storage_policy as policy
from tools.artifact_store import atomic_json,digest
from tools.artifact_bundle import validate_manifest,recover_bundle


class StorageV2Tests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'artifacts/maintenance/storage-v2/.scratch';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.base=Path(self.temp.name).resolve()
        assert self.base.is_relative_to(parent.resolve())
        self.addCleanup(self.temp.cleanup)
        self.root=self.base/'artifacts';self.root.mkdir();self.case=self.root/'stages/06/demo/example';self.case.mkdir(parents=True)

    def bundle(self):
        asset=self.root/'assets'/('a'*64)/'avatar.blend';asset.parent.mkdir(parents=True);asset.write_bytes(b'asset')
        motion=self.case/'motion.blend';motion.write_bytes(b'action')
        atomic_json(asset.with_name('asset.json'),{'schema_version':2,'sha256':digest(asset)})
        m={'schema_version':2,'bundle_root':'../../../..','asset':{'path':'../../../../assets/'+asset.parent.name+'/avatar.blend','content_hash':asset.parent.name,'sha256':digest(asset)},
           'motion':{'path':'motion.blend','sha256':digest(motion)}}
        atomic_json(self.case/'preview-manifest.json',m)
        return asset,motion,m

    def test_relative_references_and_changed_asset(self):
        asset,motion,m=self.bundle();validate_manifest(self.case,root=self.root)
        asset.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'hash mismatch'):validate_manifest(self.case,root=self.root)

    def test_missing_asset_and_escape(self):
        asset,motion,m=self.bundle();asset.unlink()
        with self.assertRaises(FileNotFoundError):validate_manifest(self.case,root=self.root)
        m['asset']['path']='../../../../../source.blend';atomic_json(self.case/'preview-manifest.json',m)
        with self.assertRaises(ValueError):validate_manifest(self.case,root=self.root)

    def test_budget_estimate_and_hard_stop(self):
        policy.enforce(self.case,growth=100,temporary=100,case_bytes=100,root=self.root)
        with self.assertRaisesRegex(RuntimeError,'case'):policy.enforce(self.case,case_bytes=9*policy.MiB,root=self.root)
        with self.assertRaisesRegex(RuntimeError,'global'):policy.preflight_batch(self.case,representative_case_bytes=5*policy.GiB,cases=1,views=2,frames=10,root=self.root)
        with self.assertRaisesRegex(RuntimeError,'temporary'):policy.enforce(self.case,temporary=513*policy.MiB,root=self.root,migration=True)

    def test_current_and_cross_stage_totals(self):
        (self.case/'result.json').write_text('{}',encoding='utf-8')
        data=policy.inventory(self.root)
        assert data['bytes']==sum(v['bytes'] for v in data['files'].values())
        assert data['bytes']==sum(v['bytes'] for v in data['by_extension'].values())
        assert data['bytes']==sum(v['bytes'] for v in data['by_class'].values())
        assert data['bytes']==sum(v['bytes'] for v in data['by_stage'].values())

    def test_failure_pin_requires_reason_and_review(self):
        with self.assertRaises(ValueError):policy.pin_failure(self.case,signature='failure.1',owner='',reason='test',review_trigger='resolution',root=self.root)
        policy.pin_failure(self.case,signature='failure.1',owner='test',reason='unresolved reproduction',review_trigger='issue resolved',root=self.root)
        self.assertEqual(json.loads((self.case/'failure-pin.json').read_text())['signature'],'failure.1')

    def test_live_writer_and_path_escape(self):
        child=subprocess.Popen([sys.executable,'-c','import sys;sys.stdin.read()'],stdin=subprocess.PIPE)
        try:
            atomic_json(self.case/'.artifact-writer.lock',{'pid':child.pid})
            self.assertIsNotNone(policy.active_writer(self.case,self.root))
        finally:
            child.stdin.close();child.wait(timeout=10)
        with self.assertRaises(ValueError):policy.confined(self.root.parent/'outside',self.root)

    def test_process_death_before_and_after_manifest_commit(self):
        asset,motion,old=self.bundle()
        previous=self.case/'motion.previous.blend';motion.rename(previous)
        motion.write_bytes(b'new action');new_sha=digest(motion)
        transaction={'owner':'artifact-bundle-v2','old_manifest':old,'new_sha256':new_sha,'previous_sha256':digest(previous)}
        atomic_json(self.case/'bundle-transaction.json',transaction)
        recover_bundle(self.case,root=self.root)
        self.assertEqual(digest(motion),old['motion']['sha256']);validate_manifest(self.case,root=self.root)
        motion.rename(previous);motion.write_bytes(b'new action')
        new={**old,'motion':{'path':'motion.blend','sha256':new_sha}}
        atomic_json(self.case/'preview-manifest.json',new);atomic_json(self.case/'bundle-transaction.json',transaction)
        validate_manifest(self.case,root=self.root)
        self.assertFalse(previous.exists());self.assertFalse((self.case/'bundle-transaction.json').exists())

    def test_render_resume_rejects_missing_changed_and_stale_inputs(self):
        from tools import artifact_store as store
        asset,motion,m=self.bundle()
        (self.case/'front').mkdir()
        for name in ('front/0001.png','front/0002.png','front-sheet.png'):
            (self.case/name).write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        m.update({'complete':True,'views':{'front':{}},'expected_frames':[1,2],
                  'inputs':{'producer_sha256':'old'},'verification':{'passed':True},'visual_evidence':{'complete':True}})
        atomic_json(self.case/'preview-manifest.json',m)
        with patch.object(store,'input_identity',return_value={'producer_sha256':'old'}):
            self.assertTrue(store.render_complete(self.case,('front',)))
        with patch.object(store,'input_identity',return_value={'producer_sha256':'changed'}):
            self.assertFalse(store.render_complete(self.case,('front',)))
            self.assertTrue(store.render_complete(self.case,('front',),allow_legacy=True))
        (self.case/'front/0002.png').unlink()
        self.assertFalse(store.render_complete(self.case,('front',),allow_legacy=True))
        asset.write_bytes(b'changed')
        self.assertFalse(store.render_complete(self.case,('front',),allow_legacy=True))

    def test_low_free_space_and_reparse_are_rejected(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        with patch.object(policy.shutil,'disk_usage',return_value=SimpleNamespace(free=1)):
            with self.assertRaisesRegex(RuntimeError,'free_space'):policy.enforce(self.case,temporary=1024,root=self.root)
        entry=SimpleNamespace(name='escape',path=str(self.root/'escape'),is_symlink=lambda:False,
                              stat=lambda **kw:SimpleNamespace(st_file_attributes=0x400))
        entries=MagicMock();entries.__enter__.return_value=iter([entry])
        with patch.object(policy.os,'scandir',return_value=entries):
            with self.assertRaisesRegex(ValueError,'Link/junction'):policy.inventory(self.root)


if __name__=='__main__':unittest.main()
