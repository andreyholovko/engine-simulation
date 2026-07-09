"""Torque converter: fluid coupling between the engine and the gearbox
input shaft (turbine), the way a torque-converter automatic launches and
idles without a driver-operated clutch pedal at all -- the converter itself
slips continuously and multiplies torque at low speed ratios, exactly the
"creeps forward at idle in Drive" behavior every automatic has.

Simplified fluid-coupling model, same "real shape, not a lab bench-test
replica" spirit as Turbo's logistic spool curve: the impeller (pump, bolted
to the engine) absorbs torque proportional to its own speed squared --
pump_torque = K * omega_pump^2 -- which is what actually produces a stall
speed (the rpm the engine settles at against a stalled turbine at WOT: below
that rpm engine torque exceeds absorption and it keeps revving; above it,
absorption wins and it stops climbing -- no separate "stall speed" formula
needed, it falls out of this one balance). The turbine receives that same
pump torque multiplied by a ratio that's largest at stall (speed_ratio 0)
and falls to 1.0 by coupling_speed_ratio, matching how a real converter's
torque multiplication only exists during the stall/launch phase, not once
it's mechanically coupled.

A lockup clutch (TCC) -- a plain Clutch, the same primitive the manual
gearbox's shift ramp uses -- can transmit torque directly pump-to-turbine
*in parallel* with the fluid path (not instead of it), bypassing the
converter's slip losses once conditions allow (see AutomaticDrivetrain).
Modeling it as an additive parallel path rather than blending/replacing the
fluid torque avoids a hard handoff discontinuity: at zero lockup capacity it
contributes nothing, and by the time real conditions let it ramp in (higher
gear, light-moderate throttle) the fluid path has usually already pulled
speed_ratio close to 1.0 on its own, so there's little left for the lockup
clutch to resolve.
"""

from dataclasses import dataclass
from math import exp
from typing import Tuple

from engine_sim.core.clutch import Clutch, couple_two_inertias
from engine_sim.specs import ClutchSpec, TorqueConverterSpec


@dataclass
class TorqueConverterReading:
    speed_ratio: float  # turbine/pump, 0 at stall, ~1 once coupled
    torque_ratio: float  # multiplication actually delivered this tick (fluid path only)
    pump_torque_nm: float  # fluid-path torque drawn from the pump/engine
    turbine_torque_nm: float  # fluid-path torque delivered to the turbine
    lockup_engagement: float
    lockup_locked: bool
    lockup_torque_nm: float


class TorqueConverter:
    def __init__(self, spec: TorqueConverterSpec):
        self.spec = spec
        self.lockup_clutch = Clutch(ClutchSpec(name=f"{spec.name} lockup", max_static_torque_nm=spec.lockup_capacity_nm))
        # Clutch.__init__ defaults engagement to 1.0 -- right for the manual
        # gearbox's dry clutch (starts engaged, no pedal pressed), wrong
        # here: a real TCC starts disengaged and only locks once commanded
        # (see AutomaticDrivetrain._lockup_commanded()). Left at the Clutch
        # default, a fresh session would start with the lockup clutch at
        # full capacity even in 1st gear (where it should never engage),
        # dragging the engine down hard for the ~0.15s it takes the release
        # ramp to unwind it.
        self.lockup_clutch.engagement = 0.0

    def torque_ratio(self, speed_ratio: float) -> float:
        spec = self.spec
        sr = max(0.0, min(1.0, speed_ratio))
        if sr >= spec.coupling_speed_ratio:
            return 1.0
        x = sr / spec.coupling_speed_ratio
        return spec.stall_torque_ratio + (1.0 - spec.stall_torque_ratio) * x

    def tick(
        self,
        dt: float,
        omega_pump: float,
        torque_pump_available_nm: float,
        pump_inertia_kgm2: float,
        omega_turbine: float,
        turbine_load_nm: float,
        turbine_inertia_kgm2: float,
        lockup_commanded: bool,
    ) -> Tuple[float, float, TorqueConverterReading]:
        """Returns (pump_reaction_nm, turbine_drive_nm) -- pump_reaction_nm
        is what the caller subtracts from the engine side's own torque
        before integrating it, turbine_drive_nm is what it adds to the
        turbine side, mirroring exactly how Drivetrain's clutch-pack torque
        already flows into its alpha_engine/alpha_wheel integration.

        Two regimes, split at coupling_speed_ratio:

          * Below it (stall/launch): the K*omega_pump^2 * torque_ratio(SR)
            formula from the module docstring -- real torque multiplication,
            turbine genuinely receives more torque than the pump gives up.
            The lockup clutch is applied as a genuinely separate, additive
            path here -- in practice it's never actually commanded this
            early (see AutomaticDrivetrain._lockup_commanded()'s gear/
            throttle gating), so there's no real risk of it fighting the
            multiplication formula the way the next bullet describes.
          * At/above it (coupling phase): a real converter's multiplication
            has already ended by here, so this is handled as a
            capacity-limited coupling (the same couple_two_inertias math the
            lockup clutch and the manual gearbox's clutch both use) instead
            of a flat torque_ratio=1 -- found necessary during development:
            with a flat ratio, nothing ever opposed the turbine actually
            *outrunning* the pump once SR reached the clamp, so the wheel
            could keep accelerating forever with engine rpm pinned at a
            stall-equivalent plateau. Critically, this is *exactly* the
            regime the lockup clutch also operates in (cruise, higher gear,
            light-moderate throttle) -- treating the fluid coupling's own
            capacity and the lockup clutch's capacity as two independent
            couple_two_inertias calls here was a second real bug: each
            call's lock/slip decision (and its overshoot guard) reasons as
            if it were the *only* torque acting between pump and turbine,
            blind to the other's simultaneous contribution, so the two
            fought each other -- verified directly: at a steady 40% throttle
            cruise, wheel_torque and the reported lock state oscillated
            wildly every tick, never settling. Summing both capacities into
            one couple_two_inertias call gives a single coherent decision
            instead, exactly like a real overlapping fluid+mechanical
            coupling actually behaves (both surfaces share the same relative
            slip; their capacities simply add).
        Continuous at the coupling_speed_ratio boundary: fluid capacity
        there is K*omega_pump^2 either way, matching what the
        multiplication-zone formula already evaluates to as SR ->
        coupling_speed_ratio (torque_ratio -> 1.0)."""
        spec = self.spec
        speed_ratio = 0.0 if omega_pump <= 1e-3 else max(0.0, min(1.0, omega_turbine / omega_pump))
        fluid_capacity_nm = spec.capacity_nm_per_rads2 * omega_pump * omega_pump

        target = 1.0 if lockup_commanded else 0.0
        tau = spec.lockup_apply_time_s if lockup_commanded else spec.lockup_release_time_s
        alpha = 1.0 - exp(-dt / max(tau, 1e-3))
        self.lockup_clutch.engagement += (target - self.lockup_clutch.engagement) * alpha
        lockup_capacity_nm = self.lockup_clutch.capacity_nm()

        if speed_ratio < spec.coupling_speed_ratio:
            ratio = self.torque_ratio(speed_ratio)
            fluid_pump_nm = fluid_capacity_nm
            fluid_turbine_nm = fluid_capacity_nm * ratio
            lockup_torque, locked = couple_two_inertias(
                omega_pump, torque_pump_available_nm, pump_inertia_kgm2,
                omega_turbine, turbine_load_nm, turbine_inertia_kgm2,
                lockup_capacity_nm, dt=dt,
            )
            pump_reaction_nm = fluid_pump_nm + lockup_torque
            turbine_drive_nm = fluid_turbine_nm + lockup_torque
        else:
            # Multiplication has already ended by here -- torque_ratio's own
            # real value asymptotically continues to be ~1.0. Fluid and
            # lockup capacities are combined into one decision (see the
            # docstring above) rather than two independent ones.
            ratio = 1.0
            combined_capacity_nm = fluid_capacity_nm + lockup_capacity_nm
            combined_torque, locked = couple_two_inertias(
                omega_pump, torque_pump_available_nm, pump_inertia_kgm2,
                omega_turbine, turbine_load_nm, turbine_inertia_kgm2,
                combined_capacity_nm, dt=dt,
            )
            fluid_pump_nm = combined_torque
            fluid_turbine_nm = combined_torque
            lockup_torque = combined_torque  # can't cleanly attribute the combined result to one path
            pump_reaction_nm = combined_torque
            turbine_drive_nm = combined_torque

        reading = TorqueConverterReading(
            speed_ratio=speed_ratio,
            torque_ratio=ratio,
            pump_torque_nm=fluid_pump_nm,
            turbine_torque_nm=fluid_turbine_nm,
            lockup_engagement=self.lockup_clutch.engagement,
            lockup_locked=locked,
            lockup_torque_nm=lockup_torque,
        )
        return pump_reaction_nm, turbine_drive_nm, reading
