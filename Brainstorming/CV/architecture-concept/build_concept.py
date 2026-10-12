"""Regenerate the current API + agentic architecture and the Blender scene proposal."""
from pathlib import Path
import runpy
base=Path(__file__).resolve().parent
for script in ['build_agentic_concept.py','build_visual.py','build_scene_plan.py','build_scene_visual.py']:
    runpy.run_path(str(base/script))
