from __future__ import annotations
import json,tempfile
from pathlib import Path
from quantbot.research.artifact_store import seal,write_named_new_json,read_verified_json,ArtifactError
def blocked(fn):
 try: fn()
 except ArtifactError: return
 raise AssertionError("artifact bypass accepted")
def main():
 with tempfile.TemporaryDirectory() as d:
  payload=seal({"schema_version":"synthetic","run_id":"r"*64}); path=write_named_new_json(d,"artifact.json",payload); assert read_verified_json(path)["run_id"]=="r"*64
  blocked(lambda:write_named_new_json(d,"artifact.json",payload)); blocked(lambda:write_named_new_json(d,"../escape.json",payload))
  path.write_text("{",encoding="utf-8");blocked(lambda:read_verified_json(path))
 print("ARTIFACT_STORE_ADVERSARIAL_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
