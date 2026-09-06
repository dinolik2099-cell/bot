"""Write a versioned N3 manifest from metadata only; never loads research data."""
from pathlib import Path
import json, subprocess, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from quantbot.research.candidate_universe import CURRENT_PROTOCOL_SCOPE, build_candidate_universe
from quantbot.research.freeze_manifest import build_freeze_manifest
from quantbot.research.model_registry import register_existing_models, validate_registry
from quantbot.strategies.model_pool import register_model_pool

def main():
    lock = json.loads((ROOT / "data/reports/research_boundary_lock.json").read_text(encoding="utf-8"))
    register_existing_models(); register_model_pool(); validate_registry()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = build_freeze_manifest(build_candidate_universe(), CURRENT_PROTOCOL_SCOPE, lock, commit)
    output = ROOT / "docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json"
    if output.exists(): raise FileExistsError(f"immutable freeze exists: {output}")
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"FREEZE_MANIFEST_OK identity={manifest['research_freeze_identity']}")
if __name__ == "__main__": main()
