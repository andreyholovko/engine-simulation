# Drag Racing Dyno Simulator

[![CI](https://github.com/andreyholovko/engine-simulation/actions/workflows/ci.yml/badge.svg)](https://github.com/andreyholovko/engine-simulation/actions/workflows/ci.yml)

A real-time, parametric engine/turbo/ECU simulation, written in plain Python
with zero dependencies. It's a **mean-value engine model (MVEM)** — the same
technique used in real hardware-in-the-loop ECU test rigs — so torque and
power come from actual engine parameters (displacement, compression ratio,
cam profile, turbo spool/wastegate behavior) rather than a canned curve.
Validated against published dyno figures for three real engines (EA888,
B58, LS2) — see [Validation](#validation).

The simulation core (`engine_sim/`) has **no Godot dependency at all** and
can be dropped into any Python 3.11+ project — a CLI, a web backend, a
different game engine, a teaching tool. This repo also ships a Godot 4.7 UI
that drives it as one example consumer; see
[Using it from Godot](#using-it-from-godot) if that's what you're after.

Licensed under MIT — see [`LICENSE`](LICENSE).

## Layout

```
engine_sim/            Simulation core, zero dependencies, zero Godot imports
  specs.py              EngineSpec / TurboSpec / CamSpec -- plain data, no behavior
  session.py             DynoSession -- the single interface to drive the sim
  core/                  engine.py, turbo.py, ecu.py, dyno.py -- the simulation itself
  presets/               Real-world engine/turbo data, one file each
dyno_cli.py             Interactive terminal dyno -- no Godot needed
tests/                  pytest suite, incl. validation against published dyno figures
godot/                  Godot 4.7+ project (an example DynoSession consumer)
  scripts/dyno_controller.py   The only file where Godot and engine_sim touch
```

## Using `engine_sim` in your own project

Not yet published to a package index — vendor the `engine_sim/` directory
(or the whole repo) into your project; it has no dependencies of its own.

```python
from engine_sim import DynoSession
from engine_sim.presets import ENGINE_CHOICES

print(list(ENGINE_CHOICES))         # available engine keys

session = DynoSession()
session.select_engine("b58_340i")   # or any key from ENGINE_CHOICES
session.set_afr_override(None)      # let the ECU control AFR ("auto")
session.start_power_pull()

for _ in range(600):                # advance ~10s at 60 ticks/s
    snapshot = session.tick(dt=1 / 60, throttle_percent=100)

print(snapshot.rpm, snapshot.torque_nm, snapshot.power_kw)
```

`DynoSession` (`engine_sim/session.py`) is the one interface every consumer
should drive — construction, live-override controls
(`set_afr_override()`, `set_boost_target_percent()`, `set_octane_override()`),
and a flattened `DynoSnapshot` for display. `tests/test_session.py` asserts
two independently-built sessions produce bit-identical curves, so anything
built the same way stays in sync with the CLI and Godot UI. Reach into
`engine_sim.core` directly only if you need to compose the pieces
(`Engine`, `Turbo`, `ECU`, `DynoBrake`, `SimulationLoop`) yourself.

Want to model your own engine? See [Adding a new engine](#adding-a-new-engine) below.

## Running the tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

125 tests, 99% coverage (`--cov=engine_sim --cov=dyno_cli --cov-report=term-missing`
for the breakdown).

## Validation

Simulated output checked against independently-published manufacturer dyno
figures, with documented tolerances (this is a simplified physical model,
not a CFD replica — see `tests/test_*_validation.py` for why each tolerance
is sized the way it is):

| Engine | Published | Simulated |
|---|---|---|
| **EA888 Gen3** (MK7 GTI, IS20) | 147kW/200PS, 320Nm plateau 1500-4400rpm | 323.8Nm @ 2636rpm, 156.1kW @ 4928rpm |
| **BMW B58B30** (340i) | 320hp/238.7kW @ 5500-6500rpm, 447Nm flat 1380-5000rpm | 446.1Nm @ 2052rpm, 235.8kW @ 5352rpm |
| **GM LS2** (Corvette C6, naturally aspirated) | 400hp/298.3kW @ 6000rpm, 542.4Nm @ 4400rpm | 539.0Nm @ 4206rpm, 309.6kW @ 5670rpm |

**Selecting an engine/turbo:** `ENGINE_CHOICES` lists `"ea888_gen3_is20"`
(default), `"b58_340i"`, `"ls2_na"` — each paired with its own stock turbo
via `DynoSession.select_engine(key)`. `TURBO_CHOICES_BY_ENGINE` lists
upgrade paths per engine (e.g. EA888's stock IS20 → IS38 → aftermarket
big-frame hybrid), swappable independently via `DynoSession.select_turbo(key)`
without changing the engine. `presets/__init__.py`'s own docstrings say which
numbers are real/documented versus representative of a category.

## Adding a new engine

New engines are pure data — no simulation code changes required.

1. **Create `engine_sim/presets/engines/<your_engine>.py`** defining an
   `EngineSpec`. Only `name`, `displacement_l`, `cylinders`, and
   `compression_ratio` are required — everything else has a sensible
   default (see `engine_sim/specs.py` for the full field list and what each
   one controls):

   ```python
   from engine_sim import CamSpec, EngineSpec

   MY_ENGINE = EngineSpec(
       name="My Engine",
       displacement_l=2.0,
       cylinders=4,
       compression_ratio=10.5,
       cam=CamSpec(intake_duration_deg=230.0, intake_lift_mm=10.0, overlap_deg=18.0),
       firing_order=(1, 3, 4, 2),
       idle_rpm=800.0,
       redline_rpm=7000.0,
       knock_octane_requirement=91.0,
   )
   ```

   Naturally-aspirated engines should also set `ve_rise_rpm` (the RPM where
   volumetric efficiency alone finishes rising to peak, since there's no
   boost to do that job) — see `LS2_NA` in
   `engine_sim/presets/engines/ls2_na.py` for a worked example.

2. **Register it** in `engine_sim/presets/engines/__init__.py` — one import
   line plus one entry in `__all__`.

3. **Pick or add a matching turbo.** Reuse an existing `TurboSpec` from
   `engine_sim/presets/turbos/`, add a new one the same way (`name`,
   `max_boost_bar`, and `spool_midpoint_rpm` are the required fields), or use
   `TURBO_NONE` if the engine is naturally aspirated.

4. **Make it selectable** by adding one entry to `ENGINE_CHOICES` in
   `engine_sim/presets/__init__.py`:

   ```python
   "my_engine": (MY_ENGINE, MY_TURBO, "Display Name"),
   ```

   and, if you want turbo swaps available for it, an entry in
   `TURBO_CHOICES_BY_ENGINE["my_engine"]` (index 0 should match whatever
   turbo `ENGINE_CHOICES` paired it with).

5. **Validate it before trusting it.** Don't add an engine to
   `ENGINE_CHOICES` until its simulated peak torque/power/RPM have been
   checked against a real published dyno figure, the way
   `tests/test_ea888_validation.py` / `test_b58_validation.py` /
   `test_ls2_validation.py` do, with a documented, justified tolerance.
   `EA888_GEN3B_IS38` (`presets/engines/ea888_gen3b_is38.py`) is a real
   example of a preset left *out* of `ENGINE_CHOICES` for exactly this
   reason — it exists for variety but was never validated.

6. **Godot UI only:** add the matching label to `godot/scripts/dyno_ui.gd`'s
   hardcoded `ENGINE_LABELS` list, in the same order as `ENGINE_CHOICES`. It's
   intentionally not read from the live `engine_choices` string property —
   py4godot string-typed properties aren't reliable across the Python/GDScript
   boundary (see `dyno_controller.py`).

## Driving it from the terminal: `dyno_cli.py`

No Godot required — an interactive terminal dyno against the exact same
`engine_sim` core:

```bash
.venv/bin/python dyno_cli.py
```

```
dyno> engines            # list selectable engines
dyno> engine b58_340i    # switch engine (and its stock turbo) mid-session
dyno> turbos             # list turbo choices for the CURRENT engine
dyno> turbo b58tu        # swap turbos on the SAME engine -- different curve
dyno> throttle 100
dyno> step 3             # advance 3s at current throttle, free-play mode
dyno> afr 11.5           # override target AFR (or "afr auto" to release it)
dyno> boost 50           # cap wastegate authority at 50% of max boost (or "boost auto")
dyno> octane 85          # set pump octane -- knock/timing-retard model (or "octane auto")
dyno> sweep              # paced WOT power pull, prints the torque/power curve
dyno> quit
```

## Simulated behavior

Beyond the raw torque/power curve, the model includes:

- **Turbo spool & heat soak** — spool lag and wastegate-controlled boost
  build over time; intake air temp chases ambient + heat from sustained
  boost with its own slow (~10s) thermal lag that doesn't reset between
  back-to-back pulls, like a real intercooler.
- **Load-based wastegate duty & AFR** — both indexed on RPM and load
  (manifold pressure), not throttle position alone, matching how real
  speed-density ECUs index their base tables.
- **Rev limiter with hysteresis** — fuel cut resumes only once RPM drops a
  set margin below the cut point, so holding WOT into the limiter bounces
  RPM rather than flatlining.
- **Knock/octane model** — running below an engine's octane requirement
  costs efficiency under real load only; each preset has its own
  sensitivity.
- **Firing-order-derived turbo response** — a twin-scroll housing (e.g. the
  B58) genuinely spools differently from a single-scroll one of the same
  size, derived from the engine's actual firing order rather than a second
  hand-tuned constant.
- **Real engine braking off-throttle** — lifting mid-pull decelerates under
  actual engine braking (DFCO fuel cut above idle+20%, no floor on net
  torque), not just light parasitic drag — a real coast-down, not a fade.
- **Idle hold** — a closed-throttle vacuum floor plus a PID brake hold the
  engine at its target idle RPM, including recovery right after a pull.
- **Procedural audio** (Godot only, `dyno_audio.gd`) — engine and turbo
  sound are synthesized live from simulation state, no audio assets; tone
  and turbo whine both scale with the actual engine/turbo fitted.

## Using it from Godot

Confirmed working in a real Godot 4.7 editor via
[py4godot](https://github.com/niklas2902/py4godot), an embedded-Python
GDExtension. `godot/addons/py4godot/` is gitignored (it's a large bundled
CPython runtime) and must be set up per machine:

1. Install **Godot 4.7** (the bundled py4godot build pins
   `compatibility_minimum = 4.7.0`).
2. Download the py4godot release for your platform from its
   [releases page](https://github.com/niklas2902/py4godot/releases/latest)
   (`py4godot.zip`). Extract just the `cpython-3.14.4-<platform>` folder for
   your OS (e.g. `cpython-3.14.4-darwin64` on Apple Silicon macOS) into
   `godot/addons/py4godot/`, so that
   `godot/addons/py4godot/python.gdextension` exists alongside it.
3. Open `godot/project.godot`; Godot should auto-detect the extension.
4. Run `scenes/Dyno.tscn`, the main scene.

`godot/scripts/dyno_controller.py` is the *only* file where Godot and
`engine_sim` touch — it owns a `DynoSession` and ticks it every frame. If
you're integrating `engine_sim` into a different engine, this file is the
one worth reading as a reference adapter.

Note: py4godot itself is labelled "early phase" by its own maintainer — if
something behaves oddly in the Godot UI, suspect the binding before
suspecting `engine_sim`, which is fully pytest-covered independently of it.

## Contributing

Bug reports, new validated presets, and PRs are welcome — see
[`CONTRIBUTING.md`](CONTRIBUTING.md) for how to get set up and what's
expected before opening a PR.
