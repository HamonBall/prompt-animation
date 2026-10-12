"""Explicit local clip catalog; assets and provenance are never guessed by AI."""
from dataclasses import dataclass
from pathlib import Path
import json
import math
from .models import PlanError


@dataclass(frozen=True)
class ClipRecord:
    id: str
    path: str
    tags: tuple[str, ...]
    starting_state: str
    ending_state: str
    source_rig: str
    provenance: str
    start_frame: float | None = None
    end_frame: float | None = None
    planted_feet: tuple[str, ...] = ()


def load_catalog(path):
    """Paths are resolved relative to an explicitly selected local catalog."""
    catalog = Path(path).resolve()
    try:
        rows = json.loads(catalog.read_text(encoding='utf-8'))
        if not isinstance(rows, list):
            raise ValueError('Expected list')
        records, ids = [], set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('tags'), list):
                raise ValueError('Invalid catalog entry')
            record = ClipRecord(**{**row, 'tags': tuple(row['tags']),
                                   'planted_feet': tuple(row.get('planted_feet', ()))})
            if not isinstance(record.id, str) or not 1 <= len(record.id) <= 48 or record.id in ids or not record.tags:
                raise ValueError('Invalid ID/tags')
            if any(not isinstance(tag, str) or not tag.strip() for tag in record.tags):
                raise ValueError('Invalid action tags')
            ids.add(record.id)
            for field in ('starting_state', 'ending_state', 'source_rig', 'provenance'):
                if not isinstance(getattr(record, field), str) or not getattr(record, field).strip():
                    raise ValueError('Missing catalog metadata')
            if record.source_rig != 'Mixamo':
                raise PlanError('Clip retargeting currently supports Mixamo source rigs.')
            asset = (catalog.parent / record.path).resolve()
            if not asset.is_file() or asset.suffix.lower() != '.fbx':
                raise ValueError('Missing FBX clip')
            if any(s not in ('left', 'right') for s in record.planted_feet):
                raise ValueError('Invalid planted-foot metadata')
            if (record.start_frame is None) != (record.end_frame is None):
                raise ValueError('Trimming needs both frame endpoints')
            if record.start_frame is not None and (any(type(v) not in (int, float) or not math.isfinite(v)
                    for v in (record.start_frame, record.end_frame)) or record.end_frame <= record.start_frame):
                raise ValueError('Invalid trimming interval')
            records.append(ClipRecord(**{**record.__dict__, 'path': str(asset)}))
        return tuple(records)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, PlanError):
            raise
        raise PlanError('Invalid local clip catalog.') from exc


def select_clip(records, action, starting_state):
    candidates = [c for c in records if action in c.tags and c.starting_state == starting_state]
    if not candidates:
        raise PlanError('No catalog clip matches this action and starting posture.')
    return candidates[0]
