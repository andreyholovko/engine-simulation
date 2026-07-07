#!/usr/bin/env python3
"""Interactive terminal dyno -- drives the same engine_sim core the Godot UI
uses, no Godot required. Run it yourself (needs a real TTY for input()):

    .venv/bin/python dyno_cli.py

Commands:
    throttle <0-100>   set throttle percent (free-play mode)
    step <seconds>     advance the sim that long at the current throttle,
                       printing a snapshot every ~0.5s
    afr <value|auto>   override target AFR, or "auto" for the ECU's own
                       load-based control law
    sweep              run a paced WOT power pull (idle -> rev limiter),
                       print the torque/power curve
    status             print the current reading
    quit               exit
"""

from engine_sim import ECU, DynoBrake, ParametricEngine, SimulationLoop, Turbo
from engine_sim.presets import EA888_GEN3_IS20, TURBO_IS20


def build_loop() -> SimulationLoop:
    engine = ParametricEngine(EA888_GEN3_IS20)
    turbo = Turbo(TURBO_IS20)
    ecu = ECU(engine, turbo)
    brake = DynoBrake()
    return SimulationLoop(ecu, brake)


def status_line(loop: SimulationLoop, r) -> str:
    return (
        f"rpm={r.rpm:6.0f}  torque={r.engine.net_torque_nm:6.1f}Nm  "
        f"power={r.power_kw:6.1f}kW  boost={r.boost_bar:4.2f}bar  "
        f"afr={r.engine.afr_actual:5.2f}  ve={r.engine.ve:4.2f}  "
        f"air={r.engine.air_mass_flow_kg_s * 1000:5.2f}g/s  "
        f"fuel={r.engine.fuel_mass_flow_kg_s * 1000:5.2f}g/s  "
        f"cr={r.engine.effective_compression_ratio:4.2f}"
        + ("  [REV LIMIT]" if loop.ecu.rev_limiter_active(r.rpm) else "")
    )


def run_sweep(loop: SimulationLoop) -> None:
    readings = loop.run_power_pull()
    peak_t = max(readings, key=lambda r: r.engine.net_torque_nm)
    peak_p = max(readings, key=lambda r: r.power_w)
    print(f"\n{'rpm':>6} {'torque(Nm)':>11} {'power(kW)':>10} {'boost(bar)':>11}")
    last_bucket = -1
    for r in readings:
        bucket = int(r.rpm // 300)
        if bucket != last_bucket:
            last_bucket = bucket
            print(f"{r.rpm:6.0f} {r.engine.net_torque_nm:11.1f} {r.power_kw:10.1f} {r.boost_bar:11.2f}")
    print(f"\npeak torque: {peak_t.engine.net_torque_nm:.1f} Nm @ {peak_t.rpm:.0f} rpm")
    print(f"peak power:  {peak_p.power_kw:.1f} kW @ {peak_p.rpm:.0f} rpm\n")


def main() -> None:
    loop = build_loop()
    throttle_pct = 0.0
    print(__doc__)
    print("Ready. Engine: " + EA888_GEN3_IS20.name)

    while True:
        try:
            line = input("dyno> ").strip()
        except EOFError:
            break
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ("quit", "exit"):
            break

        elif cmd == "throttle" and len(parts) == 2:
            throttle_pct = max(0.0, min(100.0, float(parts[1])))
            print(f"throttle set to {throttle_pct:.0f}%")

        elif cmd == "afr" and len(parts) == 2:
            if parts[1].lower() == "auto":
                loop.ecu.set_target_afr(None)
                print("AFR: auto (ECU control law)")
            else:
                loop.ecu.set_target_afr(float(parts[1]))
                print(f"AFR override: {float(parts[1]):.2f}")

        elif cmd == "step" and len(parts) == 2:
            duration = float(parts[1])
            dt = 0.02
            elapsed = 0.0
            last_print = 0.0
            r = None
            while elapsed < duration:
                r = loop.tick(dt, throttle=throttle_pct / 100.0, mode="free_accel")
                elapsed += dt
                if elapsed - last_print >= 0.5 or elapsed >= duration:
                    print(status_line(loop, r))
                    last_print = elapsed

        elif cmd == "sweep":
            run_sweep(loop)

        elif cmd == "status":
            r = loop.tick(0.0, throttle=throttle_pct / 100.0, mode="free_accel")
            print(status_line(loop, r))

        else:
            print("unknown command -- see the module docstring (run: python -c \"import dyno_cli; print(dyno_cli.__doc__)\")")


if __name__ == "__main__":
    main()
