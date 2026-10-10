"""Запуск JS-проверок правил применения ответов (tests/web/*.mjs), если в системе есть node."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node не установлен")
def test_client_state_rules():
    r = subprocess.run(["node", "--test", str(ROOT / "tests" / "web" / "state.test.mjs")], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node не установлен")
def test_app_js_syntax():
    for f in ("src/state.js", "src/useSearch.js", "vite.config.js"):
        r = subprocess.run(["node", "--check", str(ROOT / "frontend" / f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
