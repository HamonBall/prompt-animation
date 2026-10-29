"""Manifest guards for lossless full-motion evidence, without Blender."""
import json
from pathlib import Path
import tempfile
import unittest
from tools.artifact_store import atomic_json,digest,files_complete
from tools.lossless_evidence import OWNER,media_complete,retire_pngs,resume_retirement

ROOT=Path(__file__).resolve().parents[1]


class LosslessEvidenceTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'artifacts/maintenance/storage-v2/.scratch';parent.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.temp.cleanup)
        self.case=Path(self.temp.name).resolve();assert self.case.is_relative_to(parent.resolve())
        (self.case/'motion.blend').write_bytes(b'motion')
        (self.case/'front-sheet.png').write_bytes(b'\x89PNG\r\n\x1a\nproof')
        video=self.case/'front.mkv';video.write_bytes(b'verified-test-video')
        self.media={'owner':OWNER,'representation':'ffv1_mkv','verified':True,'codec':'FFV1','path':'front.mkv',
                    'sha256':digest(video),'frames':[1,2],'fps':30,'fps_base':1.0,'decoded_pixel_sha256':['a'*64,'b'*64]}
        self.manifest={'motion':{'path':'motion.blend'},'views':{'front':{'media':self.media}},'expected_frames':[1,2],
                       'fps':30,'fps_base':1.0,'complete':True}
        atomic_json(self.case/'preview-manifest.json',self.manifest)

    def test_frame_order_timing_hash_and_missing_media(self):
        self.assertTrue(files_complete(self.case,self.manifest))
        for change in ({'frames':[2,1]},{'fps':24},{'verified':False},{'decoded_pixel_sha256':[]}):
            self.assertFalse(media_complete(self.case,{**self.media,**change},[1,2],fps=30,fps_base=1.0))
        (self.case/'front.mkv').write_bytes(b'changed')
        self.assertFalse(files_complete(self.case,self.manifest))
        (self.case/'front.mkv').unlink();self.assertFalse(files_complete(self.case,self.manifest))

    def test_retirement_refuses_numeric_files_and_changed_frames(self):
        result=self.case/'result.json';result.write_bytes(b'accepted numeric evidence')
        with self.assertRaisesRegex(ValueError,'owned'):
            retire_pngs(self.case,[[{'path':'result.json','sha256':digest(result),'bytes':result.stat().st_size}]])
        self.assertTrue(result.exists())
        folder=self.case/'front';folder.mkdir();frame=folder/'0001.png';frame.write_bytes(b'old frame')
        plan=[{'path':'front/0001.png','sha256':digest(frame),'bytes':frame.stat().st_size}]
        frame.write_bytes(b'changed frame')
        with self.assertRaisesRegex(RuntimeError,'changed'):retire_pngs(self.case,[plan])
        self.assertTrue(frame.exists())

    def test_retirement_resumes_only_against_committed_media(self):
        folder=self.case/'front';folder.mkdir();frame=folder/'0001.png';frame.write_bytes(b'owned frame')
        files=[{'path':'front/0001.png','sha256':digest(frame),'bytes':frame.stat().st_size}]
        atomic_json(self.case/'media-retirement.json',{'owner':OWNER,'state':'prepared','current_media':{'front.mkv':'wrong'},'files':files})
        with self.assertRaisesRegex(RuntimeError,'manifest changed'):resume_retirement(self.case)
        self.assertTrue(frame.exists())
        atomic_json(self.case/'media-retirement.json',{'owner':OWNER,'state':'prepared','current_media':{'front.mkv':self.media['sha256']},'files':files})
        resume_retirement(self.case);self.assertFalse(frame.exists())
        resume_retirement(self.case)


if __name__=='__main__':unittest.main()
