"""Explicit temporary standalone fixtures for legacy scene transaction tests."""
from pathlib import Path
import subprocess
from tools.artifact_store import atomic_json,digest

ROOT=Path(__file__).resolve().parents[1]
BLENDER=Path('C:/Program Files/Blender Foundation/Blender 5.1/blender.exe')


def copy_scene(source,target):
    import shutil
    if (source/'preview.blend').exists():shutil.copy2(source/'preview.blend',target)
    else:
        subprocess.run([str(BLENDER),'--background','--factory-startup','--python-exit-code','1','--python',str(ROOT/'tools/load_artifact.py'),
                        '--','--case',str(source),'--export',str(target),'--temporary'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
        target.with_suffix('.export.json').unlink()


def migration_record(case):
    atomic_json(case/'artifact-migration.json',{'canonical_sha256':digest(case/'preview.blend'),'retained':[]})
