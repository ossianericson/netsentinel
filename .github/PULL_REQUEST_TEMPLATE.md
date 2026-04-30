## Summary

<!-- What does this PR do? One paragraph. -->

## Changes

<!-- Bullet list of specific changes made. -->

## Test plan

<!-- How did you verify this works? Which tests cover it? -->

- [ ] `python -m pytest tests/ -v --tb=short` passes
- [ ] `python -m pytest tests/test_version_consistency.py` passes (if version bumped)
- [ ] `python app.py --smoke` passes
- [ ] Tested manually in the app (describe what you clicked/checked)

## Checklist

- [ ] No raw hex colour strings outside `ui/styles.py` / `modules/colours.py`
- [ ] No Qt imports in `modules/` files
- [ ] New module has a corresponding `tests/test_<name>.py`
- [ ] No raw exceptions shown in the UI — all errors translated to user-friendly messages
- [ ] If new page added: registered in `dashboard._build_tabs()` and reachable via a nav mode
