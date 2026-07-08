---
description: "Test conventions: URL assertions, scaling guards, LOC budgets, coverage ratchet."
applyTo: "tests/**"
---

# Test Conventions

## URL assertions: use `urllib.parse`, never substring

Any assertion that a URL appears in or matches some output **must** parse the URL with
`urllib.parse.urlparse` and compare on a parsed component (`hostname`, `port`, `scheme`,
`path`). Substring assertions like `assert "host.example.com" in msg` are flagged by CodeQL
as `py/incomplete-url-substring-sanitization` (high severity — "the string may be at an
arbitrary position in the URL") and **will fail CI**.

### Wrong

```python
# Substring match — CodeQL py/incomplete-url-substring-sanitization
assert "192.168.1.1" in output
assert "https://api.example.com/v1" in url
```

### Right

```python
from urllib.parse import urlparse

urls = [tok for tok in output.split() if "://" in tok]
assert len(urls) == 1
assert urlparse(urls[0]).hostname == "192.168.1.1"

parsed = urlparse(url)
assert parsed.scheme == "https"
assert parsed.hostname == "api.example.com"
assert parsed.path.startswith("/v1")
```

---

## Scaling guards — catch O(n²) regressions without a benchmarking library

For any function that processes a list (MetricStore queries, scan result processing, device
list operations), add a scaling guard alongside the unit tests: measure median wall time at
two input sizes, assert the ratio stays below a threshold.

```python
import statistics, time

def _median_time(fn, repeats=5):
    times = [None] * repeats
    for i in range(repeats):
        t0 = time.perf_counter()
        fn()
        times[i] = time.perf_counter() - t0
    return statistics.median(times)

def test_my_function_scaling():
    small = build_input(50)
    large = build_input(500)
    t_small = _median_time(lambda: my_function(small))
    t_large = _median_time(lambda: my_function(large))
    if t_small < 1e-7:
        pytest.skip("below measurement threshold")
    ratio = t_large / t_small
    assert ratio < 15, (
        f"Scaling ratio {ratio:.1f}x for 10x input suggests O(n^2) regression "
        f"(t_small={t_small:.6f}s, t_large={t_large:.6f}s)"
    )
```

Threshold guide: O(n) → ratio ≈ 10×, use `< 15`. O(n log n) → ratio ≈ 13×, use `< 20`. Set
the threshold ~30% above the theoretical baseline to absorb CI noise. Skip (not fail) when the
small run is below 1e-7 s — too fast to measure.

---

## LOC budget tests — enforce RULE-AH1 structurally

Architecture invariants (file size limits, required package structure) belong in
`tests/test_module_loc.py`. Glob the target directory, compare line counts against a budget
dict, and emit an error message that says what split to make. Do NOT trim cosmetically to
pass the test — that defeats the purpose.

```python
KNOWN_LARGE_MODULES = {
    "big_module.py": 750,  # split: X -> x_helpers.py
}
DEFAULT_BUDGET = 600

def test_no_module_exceeds_loc_budget():
    offenders = []
    for path in sorted(MODULES_ROOT.glob("*.py")):
        budget = KNOWN_LARGE_MODULES.get(path.name, DEFAULT_BUDGET)
        n = sum(1 for _ in path.read_text().splitlines())
        if n > budget:
            offenders.append((path.name, n, budget))
    assert not offenders, f"Split these modules: {offenders}"
```

---

## Coverage ratchet — gates only move upward

NetSentinel is a GUI app; headless CI coverage is ~35%. Do **not** set `fail_under` in
`pyproject.toml`. Apply the ratchet rule whenever coverage is checked:

1. Measure actual coverage: `python -m pytest tests/ --cov=. --cov-report=term-missing -q`
2. If `actual >= gate + 5`, raise the gate to `actual - 3` and update `pyproject.toml`.
3. **Never lower the gate.** A regression means new code shipped without tests — add them.

```
actual = 42%   gate = 35%   ->  42 >= 35+5  ->  raise gate to 39%
actual = 41%   gate = 39%   ->  41 <  39+5  ->  leave gate at 39%
actual = 38%   gate = 39%   ->  FAIL — add tests for the new untested code
```

`pytest` markers declared in `pyproject.toml`:
- `live` — requires real network/device; skipped in CI by default
- `benchmark` — performance/scaling tests; skipped in CI by default
- `slow` — longer than a few seconds
- `integration` — multi-module end-to-end

Run them explicitly when needed:
```powershell
python -m pytest -m live          # only live tests
python -m pytest -m "not live"    # skip live (same as default)
python -m pytest -m benchmark     # only scaling/perf tests
```
