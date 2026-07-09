# Contributing

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

`engine_sim/` has zero runtime dependencies and zero Godot imports — you can
develop and test the entire simulation core without Godot installed.
Working on the Godot UI itself additionally requires Godot 4.7+ and py4godot;
see the [Godot section of the README](README.md#using-it-from-godot).

## Before opening a PR

- `python -m pytest -q` must pass (currently 125 tests, 99% coverage — run
  with `--cov=engine_sim --cov=dyno_cli --cov-report=term-missing` to check
  what you added is covered).
- If you touch anything in `engine_sim/core/`, prefer adding or updating a
  test in `tests/` over relying on manual verification — the existing suite
  includes regression tests for several real bugs (idle stability, coast-down
  physics, PID handoff) that are easy to silently reintroduce.
- If you add a new engine or turbo preset, see "Adding your own engine or
  turbo" in the [README](README.md#using-engine_sim-in-your-own-project). Only add
  it to `ENGINE_CHOICES`/`TURBO_CHOICES_BY_ENGINE` if you can validate it
  against a published dyno figure (see `tests/test_*_validation.py` for the
  pattern) — undocumented/unvalidated presets should stay out of the
  selectable list, same as `EA888_GEN3B_IS38` today.
- Keep `engine_sim/` free of Godot imports. `godot/scripts/dyno_controller.py`
  is the only file allowed to touch both sides.

## Reporting bugs / proposing features

Open a GitHub issue. For bugs, a minimal reproduction using `dyno_cli.py`
(no Godot needed) is the fastest way to get it fixed.
