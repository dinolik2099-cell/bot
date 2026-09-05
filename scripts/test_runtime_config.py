from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.execution import RuntimeConfig,validate_runtime_config
def main():
 validate_runtime_config(RuntimeConfig())
 for x in (RuntimeConfig(mode="live"),RuntimeConfig(one_shot=False),RuntimeConfig(persist_state=True)):
  try: validate_runtime_config(x)
  except PermissionError: pass
  else: raise AssertionError("unsafe runtime config accepted")
 print("RUNTIME_CONFIG_SYNTHETIC_TEST_OK")
if __name__=="__main__":main()
