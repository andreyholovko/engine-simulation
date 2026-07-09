#!/usr/bin/env python3
"""Interactive terminal dyno -- drives DynoSession, the exact same interface
the Godot UI drives, no Godot required. Run it yourself (needs a real TTY for
input()):

    .venv/bin/python dyno_cli.py

Commands:
    engines            list selectable engines (key + display name)
    engine <key>        switch to a different engine (and its stock turbo)
    turbos              list turbo choices for the CURRENT engine
    turbo <key>         swap turbos on the SAME engine -- different curve,
                       same validated engine spec
    throttle <0-100>   set throttle percent (free-play mode)
    boost <0-100|auto>  override wastegate target as % of max boost, or
                       "auto" to restore full authority
    step <seconds>     advance the sim that long at the current throttle,
                       printing a snapshot every ~0.5s
    afr <value|auto>   override target AFR, or "auto" for the ECU's own
                       load-based control law
    octane <value|auto>  set pump octane (knock/timing-retard model), or
                       "auto" to restore the engine's own knock_octane_requirement
    sweep              run a paced WOT power pull (idle -> rev limiter),
                       print the torque/power curve
    status             print the current reading
    quit               exit
"""

from engine_sim import DynoSession, DynoSnapshot


def status_line(s: DynoSnapshot) -> str:
    return (
        f"rpm={s.rpm:6.0f}  torque={s.torque_nm:6.1f}Nm  "
        f"power={s.power_kw:6.1f}kW  boost={s.boost_bar:4.2f}bar  "
        f"afr={s.afr_actual:5.2f}  ve={s.volumetric_efficiency:4.2f}  "
        f"air={s.air_mass_flow_g_s:5.2f}g/s  "
        f"fuel={s.fuel_mass_flow_g_s:5.2f}g/s  "
        f"cr={s.effective_compression_ratio:4.2f}  "
        f"iat={s.intake_air_temp_k - 273.15:4.1f}C"
        + ("  [REV LIMIT]" if s.rev_limiter_active else "")
    )


def run_sweep(session: DynoSession) -> None:
    snapshots = session.run_power_pull()
    peak_t = max(snapshots, key=lambda s: s.torque_nm)
    peak_p = max(snapshots, key=lambda s: s.power_kw)
    print(f"\n{'rpm':>6} {'torque(Nm)':>11} {'power(kW)':>10} {'boost(bar)':>11}")
    last_bucket = -1
    for s in snapshots:
        bucket = int(s.rpm // 300)
        if bucket != last_bucket:
            last_bucket = bucket
            print(f"{s.rpm:6.0f} {s.torque_nm:11.1f} {s.power_kw:10.1f} {s.boost_bar:11.2f}")
    print(f"\npeak torque: {peak_t.torque_nm:.1f} Nm @ {peak_t.rpm:.0f} rpm")
    print(f"peak power:  {peak_p.power_kw:.1f} kW @ {peak_p.rpm:.0f} rpm\n")


def main() -> None:
    session = DynoSession()
    throttle_pct = 0.0
    print(__doc__)
    print("Ready. Engine: " + session.ecu.engine.spec.name)

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

        elif cmd == "engines":
            for key, name in DynoSession.list_engine_choices():
                marker = "*" if key == session.engine_key else " "
                print(f" {marker} {key:16s} {name}")

        elif cmd == "engine" and len(parts) == 2:
            try:
                session.select_engine(parts[1])
                print(f"engine: {session.ecu.engine.spec.name}")
            except ValueError as exc:
                print(exc)

        elif cmd == "turbos":
            for key, name in session.list_turbo_choices():
                marker = "*" if key == session.turbo_key else " "
                print(f" {marker} {key:20s} {name}")

        elif cmd == "turbo" and len(parts) == 2:
            try:
                session.select_turbo(parts[1])
                print(f"turbo: {session.ecu.turbo.spec.name}")
            except ValueError as exc:
                print(exc)

        elif cmd == "throttle" and len(parts) == 2:
            throttle_pct = max(0.0, min(100.0, float(parts[1])))
            print(f"throttle set to {throttle_pct:.0f}%")

        elif cmd == "boost" and len(parts) == 2:
            if parts[1].lower() == "auto":
                session.set_boost_target_percent(None)
                print("boost target: auto (full wastegate authority)")
            else:
                session.set_boost_target_percent(float(parts[1]))
                print(f"boost target: {float(parts[1]):.0f}%")

        elif cmd == "afr" and len(parts) == 2:
            if parts[1].lower() == "auto":
                session.set_afr_override(None)
                print("AFR: auto (ECU control law)")
            else:
                session.set_afr_override(float(parts[1]))
                print(f"AFR override: {float(parts[1]):.2f}")

        elif cmd == "octane" and len(parts) == 2:
            if parts[1].lower() == "auto":
                session.set_octane_override(None)
                print("octane: auto (engine's own knock_octane_requirement)")
            else:
                session.set_octane_override(float(parts[1]))
                print(f"octane set to {float(parts[1]):.0f}")

        elif cmd == "step" and len(parts) == 2:
            duration = float(parts[1])
            dt = 0.02
            elapsed = 0.0
            last_print = 0.0
            snapshot = None
            while elapsed < duration:
                snapshot = session.tick(dt, throttle_percent=throttle_pct)
                elapsed += dt
                if elapsed - last_print >= 0.5 or elapsed >= duration:
                    print(status_line(snapshot))
                    last_print = elapsed

        elif cmd == "sweep":
            run_sweep(session)

        elif cmd == "status":
            print(status_line(session.tick(0.0, throttle_percent=throttle_pct)))

        else:
            print("unknown command -- see the module docstring (run: python -c \"import dyno_cli; print(dyno_cli.__doc__)\")")


if __name__ == "__main__":
    main()
