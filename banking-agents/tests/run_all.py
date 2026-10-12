"""Dependency-free test runner:  python -m tests.run_all   (pytest also works: `pytest -q`)."""
import importlib
import pkgutil
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    passed, failed = 0, []
    for m in sorted(pkgutil.iter_modules([str(Path(__file__).parent)]), key=lambda m: m.name):
        if not m.name.startswith("test_"):
            continue
        mod = importlib.import_module(f"tests.{m.name}")
        for name in [n for n in dir(mod) if n.startswith("test_")]:
            t0 = time.time()
            try:
                getattr(mod, name)()
                passed += 1
                print(f"  ok    {m.name}.{name}  ({time.time() - t0:.1f}s)")
            except Exception:
                failed.append(f"{m.name}.{name}")
                print(f"  FAIL  {m.name}.{name}")
                traceback.print_exc()
    print(f"\n{passed} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
