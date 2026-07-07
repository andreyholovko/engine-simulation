# Drag Racing Dyno Simulator

A real-time, parametric engine/turbo/ECU simulation, driven from Godot via an
embedded Python runtime (py4godot). Phase 1 (this repo, so far): an **engine
dyno** — crank-only, no transmission, no wheels, no tire-road friction. Those
arrive in the drag-strip phase.

## Layout

```
engine_sim/          Pure Python simulation core (zero Godot imports)
  specs.py           EngineSpec / TurboSpec / CamSpec -- data-driven engine params
  engine.py          Engine (abstract) + ParametricEngine (mean-value engine model)
  turbo.py           Turbo: spool lag + wastegate-controlled boost target
  ecu.py             ECU: fuel control (AFR), wastegate duty, rev limiter, MAP
  dyno.py            DynoBrake (load model) + SimulationLoop (tick loop)
  presets.py         EA888 Gen3 (IS20) and Gen3B (IS38) real-world presets
tests/               pytest suite, incl. validation against published EA888 figures
godot/                Godot 4.7+ project
  addons/py4godot/    Embedded-Python GDExtension (macOS arm64 build only, ~124MB)
  scripts/
    dyno_controller.py  py4godot Node: owns a SimulationLoop, ticks it every frame
    dyno_ui.gd          Wires sliders/buttons/labels to the controller
    dyno_graph.gd        Live torque/power-vs-rpm plot
  scenes/Dyno.tscn      The dyno interface
```

## Why it's built this way

The simulation core (`engine_sim/`) is plain Python with no Godot imports at
all -- it's a mean-value engine model (MVEM), the same technique used in
real hardware-in-the-loop ECU test rigs: given throttle/RPM/manifold pressure
it computes air mass flow, fuel flow, and net crank torque from actual engine
parameters (displacement, cylinders, compression ratio, cam profile), not a
canned curve. `dyno_controller.py` is the *only* file where Godot and
engine_sim touch, wrapping a `SimulationLoop` as a py4godot Node. If the
py4godot binding ever becomes a dead end, only that adapter needs replacing.

## Running the Python simulation (fully verified, no Godot needed)

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

14 tests pass, including validation against VW's own published EA888 Gen3
figures (147kW/200PS, 320Nm torque plateau 1500-4400rpm, IS20 full boost by
~3200rpm). The simulated curve lands at 323.8Nm peak torque @ 2636rpm and
156.1kW peak power @ 4928rpm -- within the tolerances documented in
`tests/test_ea888_validation.py`, which also explains *why* each tolerance is
sized the way it is (this is a simplified physical model, not a CFD replica).
There's also a regression test guarding a real bug that turned up during
manual testing: a power pull run right after free-play use used to carry over
residual turbo boost instead of starting cold from idle.

**Which presets are actually live:** `dyno_controller.py` and `dyno_cli.py`
both hardcode `EA888_GEN3_IS20` / `TURBO_IS20` from `engine_sim/presets.py`.
`EA888_GEN3B_IS38` / `TURBO_IS38` exist for variety but nothing wires them up
-- editing `TURBO_IS38.max_boost_bar` (easy to do by mistake, both presets
live in the same file) has no effect on anything you can see. If you want to
change the turbo's max boost, edit `TURBO_IS20.max_boost_bar`.

## Fastest way to actually drive it: `dyno_cli.py`

No Godot required. An interactive terminal dyno against the exact same
`engine_sim` core:

```bash
.venv/bin/python dyno_cli.py
```

```
dyno> throttle 100
dyno> step 3            # advance 3s at current throttle, free-play mode
dyno> afr 11.5           # override target AFR (or "afr auto" to release it)
dyno> sweep              # paced WOT power pull, prints the torque/power curve
dyno> quit
```

## Running the Godot dyno UI

Confirmed working in a real Godot 4.7 editor. `godot/addons/` is gitignored
(the py4godot GDExtension is a ~124MB bundled CPython runtime -- not
something to put in git), so **it will not be there after a fresh clone**.
Set it up once per machine:

1. Install **Godot 4.7** (the bundled py4godot build pins
   `compatibility_minimum = 4.7.0`).
2. Download the py4godot release for your platform:
   https://github.com/niklas2902/py4godot/releases/latest (`py4godot.zip`).
   It's a multi-platform bundle (~247MB); on macOS you only need the
   `cpython-3.14.4-darwin64` folder (arm64). Extract and place under
   `godot/addons/py4godot/` so that `godot/addons/py4godot/python.gdextension`
   exists alongside it, e.g.:
   ```
   godot/addons/py4godot/
     python.gdextension
     cpython-3.14.4-darwin64/
     LICENSE, Python.svg, dependencies.txt, get_pip.py,
     install_dependencies.py, signal_script.py
   ```
   (On Linux/Windows use the matching `cpython-3.14.4-<platform>` folder
   instead -- the `.gdextension` file already lists all of them.)
3. Open `godot/project.godot`. Godot should auto-detect the extension; enable
   it if asked.
4. Run the scene (`scenes/Dyno.tscn` is the main scene).

### Gotchas found by actually running it

- Editing the wrong preset is an easy mistake to make: see "Which presets are
  actually live" above -- `TURBO_IS38`/`EA888_GEN3B_IS38` are decorative only.
- There is no throttle control in the UI -- free-play throttle was removed
  because, with the dyno's minimal parasitic load, almost any throttle input
  just rockets RPM to the rev limiter and holds it there, making a slider feel
  broken across most of its range. The **Start Power Pull** button (a paced
  ECU-governed sweep) is the interactive path instead. Real throttle-driven
  free-play would need an actual load model (road-load curve or a PID-held
  RPM) before it's worth re-adding.
- py4godot itself is still labelled "early phase, more a demo than for bigger
  projects" by its own maintainer -- if something behaves oddly, that binding
  is the more likely suspect than `engine_sim`, which is fully pytest-covered.

### What each control does

- **Target Boost slider (0-100%)** -- caps the ECU's wastegate authority as a
  fraction of the turbo's `max_boost_bar` (`TURBO_IS20`, currently 1.3 bar).
  50% target measurably drops peak torque from ~324Nm to ~230Nm -- verified
  directly against the sim, not just wired up and assumed.
- **Override target AFR** -- checkbox + slider to force a fixed AFR instead
  of the ECU's own load-based control law (stoich cruise -> ~12.5 at WOT).
- **Start Power Pull** -- runs a paced WOT sweep (default 400rpm/s, adjustable)
  from idle to the rev limiter, plotting the torque/power curve live. Between
  pulls the engine just sits idle/off (throttle is fixed at 0).

## Not built yet

Transmission, drag strip mode (wheelspin, rolling resistance/tire friction --
deliberately *not* modeled in dyno mode), and multi-engine presets beyond
EA888 Gen3/Gen3B.
