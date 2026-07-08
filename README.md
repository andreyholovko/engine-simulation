# Drag Racing Dyno Simulator

A real-time, parametric engine/turbo/ECU simulation, driven from Godot via an
embedded Python runtime (py4godot). This repo is an **engine dyno** —
crank-only, no transmission, no wheels, no tire-road friction. There's no
drag-strip/transmission phase currently planned; work right now is focused on
optimizing and deepening the realism of the dyno itself (more validated
engines, tighter physical modeling, better procedural audio), not on adding
new phases or features.

## Layout

```
engine_sim/                    Pure Python simulation core (zero Godot imports)
  specs.py                     EngineSpec / TurboSpec / CamSpec -- data-driven params,
                                shared by core/ and presets/, kept at top level since
                                both depend on it
  session.py                   DynoSession -- the one interface every frontend drives
                                (construction, live-override controls, and a flattened
                                DynoSnapshot for display), so the CLI, Godot, and any
                                future consumer can never silently diverge
  core/                        The simulation itself
    engine.py                  Engine (abstract) + ParametricEngine (mean-value engine model)
    turbo.py                   Turbo: spool lag + wastegate-controlled boost target
    ecu.py                     ECU: fuel control (AFR), wastegate duty, rev limiter, MAP
    dyno.py                    DynoBrake (load model) + SimulationLoop (tick loop)
  presets/                     Real-world engine/turbo data, one file each
    engines/
      ea888_gen3_is20.py       EA888_GEN3_IS20 -- the validation target, actually wired in
      ea888_gen3b_is38.py      EA888_GEN3B_IS38 -- Miller-cycle example, decorative only
    turbos/
      is20.py                 TURBO_IS20 -- actually wired in; edit max_boost_bar here
      is38.py                 TURBO_IS38 -- decorative only
tests/                         pytest suite, incl. validation against published EA888 figures
godot/                         Godot 4.7+ project
  addons/py4godot/             Embedded-Python GDExtension (gitignored -- see setup below)
  scripts/
    dyno_controller.py         py4godot Node: owns a DynoSession, ticks it every frame
    dyno_ui.gd                 Wires sliders/buttons/labels to the controller
    dyno_graph.gd              Live torque/power-vs-rpm plot, auto-scaling axes per engine
    dyno_audio.gd              Procedural engine + turbo sound, synthesized live from DynoController
  scenes/Dyno.tscn             The dyno interface (DynoController + DynoAudio + UI)
```

Everything under `engine_sim/` is still reached the same way from outside the
package (`from engine_sim import ECU, ...`, `from engine_sim.presets import
EA888_GEN3_IS20, TURBO_IS20`) -- `core/` and `presets/` are an internal
reorganization, not a public API change. Adding a new engine or turbo is just
a new file under `presets/engines/` or `presets/turbos/`, plus one line in
that folder's `__init__.py`.

## Why it's built this way

The simulation core (`engine_sim/`) is plain Python with no Godot imports at
all -- it's a mean-value engine model (MVEM), the same technique used in
real hardware-in-the-loop ECU test rigs: given throttle/RPM/manifold pressure
it computes air mass flow, fuel flow, and net crank torque from actual engine
parameters (displacement, cylinders, compression ratio, cam profile), not a
canned curve. `dyno_controller.py` is the *only* file where Godot and
engine_sim touch, wrapping a `DynoSession` as a py4godot Node. If the
py4godot binding ever becomes a dead end, only that adapter needs replacing.

**`DynoSession` (`engine_sim/session.py`) is the one interface every
consumer drives** -- `dyno_cli.py` and `dyno_controller.py` each used to
hand-build their own `Engine`/`Turbo`/`ECU`/`SimulationLoop` and hand-flatten
readings for display; both copies happened to agree, but nothing enforced
that. Now both just do `DynoSession()`, call `set_afr_override()` /
`set_boost_target_percent()` / `start_power_pull()` / `tick()`, and read a
`DynoSnapshot` back. `tests/test_session.py` locks this in with a test that
builds two independent sessions and asserts they produce bit-identical
curves -- any future consumer should do the same `DynoSession()` construction
rather than reaching into `engine_sim.core` directly.

## Running the Python simulation (fully verified, no Godot needed)

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

42 tests pass, including validation against three independently-published
figures:

- **EA888 Gen3 (MK7 GTI, IS20)** -- VW/Audi's own published 147kW/200PS,
  320Nm torque plateau 1500-4400rpm, IS20 full boost by ~3200rpm. Simulated:
  323.8Nm peak torque @ 2636rpm, 156.1kW peak power @ 4928rpm.
- **BMW B58B30 (340i)** -- BMW's published 320hp (238.7kW) @ 5500-6500rpm,
  330lb-ft (447Nm) flat 1380-5000rpm, redline 7000rpm. Simulated: 446.1Nm
  peak torque @ 2052rpm, 235.8kW peak power @ 5352rpm. (Despite being
  colloquially called "twin-turbo," the B58 uses one turbocharger with a
  twin-scroll housing, not two turbos -- modeled as a single `TurboSpec`,
  same as every other preset here.)
- **GM LS2 (Corvette C6)** -- GM's published 400hp (298.3kW) @ 6000rpm,
  400lb-ft (542.4Nm) @ 4400rpm, redline 6500rpm. Simulated: 539.0Nm peak
  torque @ 4206rpm, 309.6kW peak power @ 5670rpm. The first naturally-
  aspirated preset (paired with `TURBO_NONE`, `max_boost_bar=0.0` -- no
  special-casing anywhere, boost just never builds) -- and the first one
  that needed `EngineSpec.ve_rise_rpm`: turbocharged engines get their
  low-end torque rise from boost building, but with no boost to lean on, the
  LS2's volumetric-efficiency curve itself has to rise from idle to its
  4400rpm peak. Defaults to a no-op (0.0) for every other preset, verified
  by `tests/test_components.py::test_ve_rise_phase_is_opt_in_only`.

Tolerances are documented in `tests/test_ea888_validation.py` /
`tests/test_b58_validation.py` / `tests/test_ls2_validation.py`, which also
explain *why* each is sized the way it is (this is a simplified physical
model, not a CFD replica). There's also a regression test guarding a real bug
that turned up during manual testing: a power pull run right after free-play
use used to carry over residual turbo boost instead of starting cold from
idle.

**Selecting an engine:** `ENGINE_CHOICES` in `engine_sim/presets/__init__.py`
is the registry both `DynoSession.select_engine(key)` and every UI read from
-- currently `"ea888_gen3_is20"` (the default), `"b58_340i"`, and `"ls2_na"`.
In the CLI: `engine ls2_na` (or `engines` to list choices). In Godot: the
**Engine** dropdown at the top of the UI. `EA888_GEN3B_IS38` / `TURBO_IS38`
also exist in `presets/` for variety but are deliberately left out of
`ENGINE_CHOICES` -- they're explicitly *not* validated against a published
dyno sheet (see that file's docstring), so they're not offered as an
equally-trustworthy selectable option. Editing `TURBO_IS38`'s `max_boost_bar` (easy to do by
mistake, presets live in neighboring files) has no effect on anything you can
see for the same reason -- if you want to change a turbo's max boost, make
sure you're editing the `TurboSpec` actually referenced by `ENGINE_CHOICES`.

## Fastest way to actually drive it: `dyno_cli.py`

No Godot required. An interactive terminal dyno against the exact same
`engine_sim` core:

```bash
.venv/bin/python dyno_cli.py
```

```
dyno> engines            # list selectable engines
dyno> engine b58_340i    # switch engine+turbo mid-session
dyno> throttle 100
dyno> step 3            # advance 3s at current throttle, free-play mode
dyno> afr 11.5           # override target AFR (or "afr auto" to release it)
dyno> boost 50           # cap wastegate authority at 50% of max boost (or "boost auto")
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

- **Engine dropdown** -- selects from `ENGINE_CHOICES`, rebuilding the
  session's Engine/Turbo/ECU for the chosen preset (`DynoSession.
  select_engine()`). Aborts any in-progress pull. The graph (below) rescales
  its axes automatically for whichever engine is selected.
  **Real bug found and fixed here:** the dropdown initially didn't work at
  all -- `engine_choices`/`engine_name` are `str`-typed py4godot properties,
  and py4godot's own examples only ever show `int`/`float`/`bool`/`Vector3`,
  never `str`. Selection now goes through `select_engine_by_index(int)` end
  to end (`dyno_ui.gd` hardcodes the picker's labels, matching
  `ENGINE_CHOICES`' order, instead of parsing `engine_choices`) -- `int` is a
  type already confirmed working (`rpm`, `engine_count`, etc. all display
  correctly). The `str` properties are left in place as a nice-to-have/debug
  aid, but nothing load-bearing depends on them anymore.
- **Target Boost slider (0-100%)** -- caps the ECU's wastegate authority as a
  fraction of the turbo's `max_boost_bar` (`TURBO_IS20`, currently 1.3 bar).
  50% target measurably drops peak torque from ~324Nm to ~230Nm -- verified
  directly against the sim, not just wired up and assumed.
- **Override target AFR** -- checkbox + slider to force a fixed AFR instead
  of the ECU's own load-based control law (stoich cruise -> ~12.5 at WOT).
- **Start Power Pull** -- runs a paced WOT sweep (default 400rpm/s, adjustable)
  from idle to the rev limiter, plotting the torque/power curve live. Between
  pulls the engine holds idle (800rpm, see below), not WOT.

### Sound

`dyno_audio.gd` (a `DynoAudio` node alongside `DynoController` in
`Dyno.tscn`) procedurally synthesizes engine and turbo sound live from the
controller's state -- no audio assets. Two oscillators, each a pure function
of a single continuously-advancing phase (never hard-reset, never driven by a
separate envelope that can jump):

- **Engine**: phase is counted in cylinders, not radians, so each firing
  event lands a cubed half-sine pulse timed to real `cylinders * rpm / 120`
  firing frequency. Per-cylinder amplitude (manufacturing-tolerance/runner-
  length character) comes from `EngineSpec.firing_order_resolved`, is fixed
  per engine (deterministic RNG seeded from `engine_generation`, not redrawn
  every firing event), and always changes on a waveform zero-crossing, so
  swapping engines mid-session can never click. A one-pole lowpass darkens
  the tone with displacement (EA888 2.0L brightest, LS2 6.0L deepest) --
  bigger engine sounds deeper, independent of firing rate.
- **Turbo**: a whine that rises in pitch and gain with `boost_bar /
  max_boost_bar` (spool fraction).

`EngineSpec.firing_order` is the same data both audio and the physics model
consume -- audio is a consumer of engine facts, not a separate system that
guesses from cylinder count alone.

### Idle: holds 800rpm, doesn't stall or run away (fixed, worth knowing why)

Two related bugs showed up back to back and are both fixed in
`engine_sim/core/ecu.py` and `engine_sim/session.py`:

1. **RPM settling around 6500 at "idle" instead of near zero.** Root cause:
   `ECU.intake_manifold_pressure()` only ever *added* boost scaled by
   throttle -- it never modeled the throttle plate restricting airflow at
   closed throttle, so 0% threshold still breathed at full atmospheric
   pressure and produced real torque (verified: ~118Nm) against only ~3Nm of
   dyno parasitic drag. Nothing stopped it climbing to the rev limiter.
   `intake_manifold_pressure()` now blends from a closed-throttle vacuum
   floor (`IDLE_MAP_PA`, ~30kPa) up to atmospheric as throttle opens --
   unchanged at WOT (throttle=1), so the validated power-pull curve is
   bit-for-bit identical.
2. That alone wasn't enough on its own (a fixed idle-air opening still needs
   *something* to hold it at a target RPM -- too much authority and it
   climbs, too little and it stalls, and there's no way to land exactly on
   zero net torque by tuning constants alone). The real fix: the ECU always
   applies a small, fixed idle-air-control opening at zero throttle
   (`idle_throttle_equivalent`, modest torque, never cut) and
   `DynoSession.tick()` uses the dyno brake's existing `hold_rpm` PID
   (`SimulationLoop`/`DynoBrake`, already built for exactly this) to hold
   RPM at `idle_rpm_target` (800rpm, `EA888_GEN3_IS20.idle_rpm`) against it --
   the same way a real idle is also held against accessory/AC-compressor
   load, not by tuning the engine to balance itself unaided. Recovers
   smoothly back to ~800rpm after a power pull too, not just on startup.

Covered by `tests/test_components.py::test_zero_throttle_uses_bounded_idle_air_not_full_atmospheric_map`
and `tests/test_session.py::test_session_starts_at_idle_and_holds_it` /
`::test_idle_recovers_after_a_power_pull`.

## Not built, and not currently planned

Transmission and drag-strip mode (wheelspin, rolling resistance/tire friction
-- deliberately *not* modeled in dyno mode). There's no roadmap toward these
right now -- current work is optimization and realism on the dyno model
itself (new validated engine/turbo presets, tighter physical modeling,
audio), not new phases or scope.
