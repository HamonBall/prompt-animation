"""Crash boundaries for owned videos before and after manifest publication."""
import json
from pathlib import Path
import tempfile
import unittest
from tools.artifact_store import atomic_json,digest
from tools.media_transaction import OWNER,prepare_publication,resume_build,cached_media,source_identity,published_frame_plans

ROOT=Path(__file__).resolve().parents[1]


class MediaTransactionTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'artifacts/maintenance/storage-v2/.scratch';parent.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.temp.cleanup)
        self.case=Path(self.temp.name).resolve();assert self.case.is_relative_to(parent.resolve())
        (self.case/'front').mkdir();frame=self.case/'front/0001.png';frame.write_bytes(b'owned frame')
        self.source=[{'path':'front/0001.png','bytes':frame.stat().st_size,'sha256':digest(frame)}]

    def candidate(self,payload=b'verified movie'):
        path=self.case/'.front.pending.mkv';path.write_bytes(payload);sha=digest(path)
        media={'owner':OWNER,'verified':True,'path':'front-'+sha+'.mkv','sha256':sha,'frames':[1],'fps':30,'fps_base':1.0}
        return path,media

    def test_interruption_before_rename_and_verified_reuse(self):
        candidate,media=self.candidate();prepare_publication(self.case,'front',self.source,media,candidate)
        self.assertTrue(candidate.exists());resume_build(self.case)
        self.assertFalse(candidate.exists());self.assertTrue((self.case/media['path']).exists())
        self.assertEqual(cached_media(self.case,'front',source_identity(self.source,30,1.0)),media)
        resume_build(self.case);self.assertEqual(len(list(self.case.glob('*.mkv'))),1)

    def test_interruption_after_rename_and_post_manifest_png_plan(self):
        candidate,media=self.candidate();prepare_publication(self.case,'front',self.source,media,candidate)
        candidate.replace(self.case/media['path']);resume_build(self.case)
        atomic_json(self.case/'preview-manifest.json',{'complete':True,'views':{'front':{'media':media}}})
        self.assertEqual(published_frame_plans(self.case),[self.source])
        (self.case/'front/0001.png').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'changed'):published_frame_plans(self.case)

    def test_changed_source_retires_only_unreferenced_owned_movie(self):
        candidate,old=self.candidate();prepare_publication(self.case,'front',self.source,old,candidate);resume_build(self.case)
        atomic_json(self.case/'preview-manifest.json',{'complete':True,'views':{'front':{'media':old}}})
        candidate,new=self.candidate(b'new verified movie');prepare_publication(self.case,'front',self.source,new,candidate);resume_build(self.case)
        self.assertTrue((self.case/old['path']).exists())
        atomic_json(self.case/'preview-manifest.json',{'complete':True,'views':{'front':{'media':new}}})
        resume_build(self.case);self.assertFalse((self.case/old['path']).exists());self.assertTrue((self.case/new['path']).exists())

    def test_corrupt_candidate_and_escaping_view_fail_closed(self):
        candidate,media=self.candidate();prepare_publication(self.case,'front',self.source,media,candidate)
        candidate.write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError,'missing or changed'):resume_build(self.case)
        self.assertTrue(candidate.exists())
        with self.assertRaises(ValueError):cached_media(self.case,'../escape','x')


if __name__=='__main__':unittest.main()
