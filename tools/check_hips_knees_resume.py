"""Verify twice that every accepted Stage 05.4 bundle can be reused as-is."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from hips_knees_cases import cases
from tools.artifact_bundle import validate_manifest
from tools.artifact_store import atomic_json,digest
from tools.hips_knees_views import render_valid
from tools.legs_evidence import OUT
from tools.storage_policy import ARTIFACTS,inventory


def snapshot():
    payloads={}
    def capture(path):
        key=path.relative_to(ARTIFACTS).as_posix()
        if key not in payloads:
            stat=path.stat()
            payloads[key]={'sha256':digest(path),'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}
    for asset in (ARTIFACTS/'assets').glob('*/avatar.blend'):
        capture(asset)
    for rig in ('demo','mixamo'):
        for name,_,_,_ in cases():
            directory=OUT/rig/name
            assert render_valid(directory),directory
            manifest,asset,motion=validate_manifest(directory)
            paths=(asset,motion,*(directory/v['media']['path'] for v in manifest['views'].values()))
            for path in paths:
                capture(path)
    return payloads


def main():
    before=inventory()
    assert not before['leases']
    first=snapshot()
    second=snapshot()
    after=inventory()
    assert first==second and before['files']==after['files'] and not after['leases']
    assert len(first)==2*len(cases())*3+3
    atomic_json(OUT/'resume-no-growth.json',{'passed':True,'read_only_passes':2,
        'artifact_bytes_before_report':before['bytes'],'artifact_files_before_report':before['file_count'],
        'payload_count':len(first),'payloads':first})
    print('LEGS_RESUME_WITHOUT_GROWTH_PASSED',len(first),flush=True)


if __name__=='__main__':main()
