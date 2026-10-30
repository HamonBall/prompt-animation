"""A hand bundle may retain additional reviewed cameras beyond required views."""
import json
from pathlib import Path
from tools.artifact_store import render_complete as exact_render_complete
from tools.artifact_store import input_identity,files_complete
from tools.artifact_bundle import validate_manifest
from tools.hands_source_compatibility import numeric_source_valid,OUT


def render_complete(directory,required_views):
    try:
        manifest=json.loads((Path(directory)/'preview-manifest.json').read_text())
        actual=tuple(manifest['views'])
        if not set(required_views)<=set(actual):return False
        if exact_render_complete(directory,actual):return True
        identity=input_identity(directory)
        if not numeric_source_valid(directory,identity):return False
        plan=json.loads((OUT/'endpoint-baseline-migration.json').read_text())
        key=Path(directory).resolve().relative_to(OUT.resolve()).as_posix()
        result=json.loads((Path(directory)/'result.json').read_text())
        if plan['cases'][key]['affected'] or result['producer_sha256']!=plan['previous_producer_sha256'] or manifest['inputs']['producer_sha256']!=plan['previous_producer_sha256']:return False
        validate_manifest(directory)
        return (manifest['complete'] and manifest['visual_evidence']['complete'] and
                {k:v for k,v in manifest['inputs'].items() if k!='producer_sha256'}==
                {k:v for k,v in identity.items() if k!='producer_sha256'} and files_complete(directory,manifest))
    except (OSError,ValueError,KeyError,TypeError):return False
