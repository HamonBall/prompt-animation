"""A failed native process is not a successful cache without explicit recovery."""
import json
from pathlib import Path
from tools.artifact_store import digest
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import confined
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/stages/05.3b'


def verified_native_cache(directory):
    directory=Path(directory);log=directory/'render.log'
    if not log.exists() or 'EXCEPTION_ACCESS_VIOLATION' not in log.read_text():return True
    try:
        recovery=json.loads((OUT/'native-shutdown-recovery.json').read_text())['cases'][directory.name]
        if not recovery['passed'] or recovery['native_exit_code']!=0 or recovery['motion_or_media_regenerated']:return False
        if recovery['original_failure_log_sha256']!=digest(log) or recovery['renderer_sha256']!=digest(ROOT/'tools/render_fingers.py'):return False
        if recovery['checker_sha256']!=digest(ROOT/'tests/blender_fingers_cached_playback.py'):return False
        if recovery['recovery_driver_sha256']!=digest(ROOT/'tools/recover_fingers_native.py'):return False
        if recovery['recovery_log_sha256']!=digest(OUT/('cached-playback-'+directory.name+'.log')):return False
        if recovery['runtime_lock_sha256']!=digest(OUT/'runtime-lock.json'):return False
        manifest,asset,motion=validate_manifest(directory)
        if recovery['frames']!=len(manifest['expected_frames']):return False
        expected={str(p.relative_to(ROOT)) for p in [asset,motion,*(directory/v['media']['path'] for v in manifest['views'].values())]}
        if set(recovery['payloads'])!=expected:return False
        for relative,record in recovery['payloads'].items():
            path=confined(ROOT/relative);stat=path.stat()
            if digest(path)!=record['sha256'] or stat.st_mtime_ns!=record['mtime_ns'] or stat.st_size!=record['bytes']:return False
        return True
    except (OSError,ValueError,KeyError,TypeError):return False
