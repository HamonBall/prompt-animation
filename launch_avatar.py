"""Run with blender --python launch_avatar.py (opens a dedicated application scene)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from avatar_app.main import main

if __name__ == '__main__':
    main()
