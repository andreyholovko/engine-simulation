#!/usr/bin/env python3
"""Interactive terminal dyno -- drives DynoSession, the exact same interface
the Godot UI drives, no Godot required. Run it yourself (needs a real TTY for
input()):

    .venv/bin/python dyno_cli.py

Commands:
    cars                list selectable cars (key + display name)
    car <key>           switch to a different car (its engine + stock turbo)
    turbos              list turbo choices for the CURRENT car
    turbo <key>         swap turbos on the SAME car -- different curve,
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
                       print the torque/power curve -- crank mode only
    status             print the current reading
    mode <crank|chassis>  switch dyno type -- chassis adds a clutch, manual
                       gearbox and a tire slipping against the roller
    tires              list tire choices (chassis mode)
    tire <key>          swap tire size/compound (chassis mode)
    transmissions      list transmission choices (chassis mode)
    transmission <key>  swap manual <-> automatic (chassis mode)
    shift up|down      shift gear (chassis mode, manual transmission only --
                       the automatic shifts itself off throttle position)
    quit               exit
"""

from engine_sim import DynoSession, DynoSnapshot


def status_line(s: DynoSnapshot) -> str:
    line = (
        f"rpm={s.rpm:6.0f}  torque={s.torque_nm:6.1f}Nm  "
        f"power={s.power_kw:6.1f}kW  boost={s.boost_bar:4.2f}bar  "
        f"afr={s.afr_actual:5.2f}  ve={s.volumetric_efficiency:4.2f}  "
        f"air={s.air_mass_flow_g_s:5.2f}g/s  "
        f"fuel={s.fuel_mass_flow_g_s:5.2f}g/s  "
        f"cr={s.effective_compression_ratio:4.2f}  "
        f"iat={s.intake_air_temp_k - 273.15:4.1f}C"
        + ("  [REV LIMIT]" if s.rev_limiter_active else "")
    )
    if s.dyno_mode == "chassis":
        gear_label = "N" if s.gear == 0 else str(s.gear)
        clutch_label = "locked" if s.clutch_locked else "SLIP"
        line += (
            f"\n         gear={gear_label:>2}  {'(shifting) ' if s.shifting else '           '}"
            f"clutch={s.clutch_engagement:4.2f}({clutch_label})  "
            f"wheel={s.wheel_rpm:6.0f}rpm  speed={s.vehicle_speed_kmh:6.1f}km/h  "
            f"slip={s.slip_ratio:+6.3f}  "
            # What a real chassis dyno actually measures (roller-derived) --
            # compare against the engine torque/power above to see slip loss
            # directly: they only diverge when the clutch or tire is slipping.
            f"at_wheel={s.wheel_torque_nm:6.1f}Nm/{s.wheel_power_kw:5.1f}kW"
        )
    return line


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
    car_name = next(name for key, name in DynoSession.list_car_choices() if key == session.car_key)
    print("Ready. Car: " + car_name)

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

        elif cmd == "cars":
            for key, name in DynoSession.list_car_choices():
                marker = "*" if key == session.car_key else " "
                print(f" {marker} {key:16s} {name}")

        elif cmd == "car" and len(parts) == 2:
            try:
                session.select_car(parts[1])
                print(f"car: {session.ecu.engine.spec.name}")
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
            try:
                run_sweep(session)
            except ValueError as exc:
                print(exc)

        elif cmd == "status":
            print(status_line(session.tick(0.0, throttle_percent=throttle_pct)))

        elif cmd == "mode" and len(parts) == 2:
            try:
                session.select_dyno_mode(parts[1])
                print(f"dyno mode: {session.dyno_mode}")
            except ValueError as exc:
                print(exc)

        elif cmd == "tires":
            for key, name in DynoSession.list_tire_choices():
                marker = "*" if key == session.tire_key else " "
                print(f" {marker} {key:8s} {name}")

        elif cmd == "tire" and len(parts) == 2:
            try:
                session.select_tire(parts[1])
                print(f"tire: {parts[1]}")
            except ValueError as exc:
                print(exc)

        elif cmd == "transmissions":
            for key, name in DynoSession.list_transmission_choices():
                marker = "*" if key == session.transmission_key else " "
                print(f" {marker} {key:14s} {name}")

        elif cmd == "transmission" and len(parts) == 2:
            try:
                session.select_transmission(parts[1])
                print(f"transmission: {parts[1]}")
            except ValueError as exc:
                print(exc)

        elif cmd == "shift" and len(parts) == 2 and parts[1].lower() in ("up", "down"):
            if parts[1].lower() == "up":
                session.shift_up()
            else:
                session.shift_down()
            print(f"gear: {'N' if session.current_gear == 0 else session.current_gear}")

        else:
            print("unknown command -- see the module docstring (run: python -c \"import dyno_cli; print(dyno_cli.__doc__)\")")


if __name__ == "__main__":
    main()
