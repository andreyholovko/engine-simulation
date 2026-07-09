"""Clutch: couples two independently-spinning inertias (engine/flywheel and
gearbox input shaft) up to a friction torque limit -- exactly a real clutch's
job, and the same "try locked, fall back to friction-limited slip" shape
DynoBrake.load_torque's ramp_rpm mode already uses for a single mass, just
generalized to two.

Given each side's own inertia and the torque already driving it, there's
exactly one clutch torque that would bring them to a *common* angular
acceleration (perfectly locked, moving as one rigid body). If that torque is
within the clutch's capacity, it locks -- both sides accelerate together, no
relative slip. If it isn't (a cold launch from a stop, a shift landing on a
mismatched engine speed, a dumped clutch at redline), the clutch can only
supply its capacity, applied in the direction that pulls the slower side up
and drags the faster side down -- classic kinetic friction, and the two sides
keep slipping relative to each other until they converge or the capacity
changes.
"""

from typing import Optional, Tuple

from engine_sim.specs import ClutchSpec

_LOCK_EPSILON_RAD_S = 1.0  # ~a few rpm -- "close enough to call it synced"


def couple_two_inertias(
    omega_1: float,
    torque_1_nm: float,
    inertia_1_kgm2: float,
    omega_2: float,
    torque_2_nm: float,
    inertia_2_kgm2: float,
    capacity_nm: float,
    dt: Optional[float] = None,
) -> Tuple[float, bool]:
    """Returns (transmitted_torque_nm, locked) for a friction coupling
    between two inertias, each already subject to its own external torque
    (torque_1 driving inertia_1 before any coupling torque; torque_2 already
    signed as a *load* on inertia_2, i.e. subtracted from it below).

    Locking is a two-part condition, not just "is there enough torque
    capacity" -- a coupling can't be *locked* while the two sides are still
    at genuinely different speeds, no matter how much capacity it has (that
    would mean an infinitely fast, infinitely hard snap to sync, which no
    real friction surface does). So:

      * Still meaningfully apart in speed (|omega_1 - omega_2| >
        _LOCK_EPSILON_RAD_S): always slipping, kinetic friction at exactly
        capacity_nm, signed toward whichever side is slower -- this is what
        makes a launch from a stop, or a shift landing on a mismatched
        engine speed, slip in a controlled way instead of never locking or
        instantly locking.
      * Already synced (within epsilon): *then* check whether static
        friction can hold them there against whatever torque imbalance
        remains -- the locked-condition torque, derived by setting
        alpha_1 == alpha_2:
            (torque_1 - Tc) / J1 == (Tc - torque_2) / J2
            => Tc = (J2*torque_1 + J1*torque_2) / (J1 + J2)
        If |Tc| exceeds capacity_nm even here, it breaks loose again
        (transmits capacity_nm, signed like Tc would have been).

    If `dt` is given, this also guards against a real instability found
    during development: a large capacity applied to a small reflected
    inertia (e.g. a low gear's wheel side, or a clutch dump at high rpm) can
    make the slipping torque overshoot *past* the sync point within a single
    step -- omega_diff crosses zero and comes out the other side, so next
    step's sign flips too, and it never converges, chattering between
    +capacity and -capacity forever instead of settling. Predicting whether
    a full step of slip torque would flip omega_diff's sign, and treating
    that step as a lock attempt instead, catches it exactly at the crossing
    -- the same physical moment a real clutch's kinetic friction actually
    would hand off to static friction. Backward compatible: omitting `dt`
    keeps the exact old behavior (every existing caller that doesn't pass it
    is unaffected)."""
    if inertia_1_kgm2 <= 0.0 or inertia_2_kgm2 <= 0.0:
        raise ValueError("inertias must be positive")

    omega_diff = omega_1 - omega_2
    if abs(omega_diff) > _LOCK_EPSILON_RAD_S:
        sign = 1.0 if omega_diff > 0.0 else -1.0
        slip_torque = sign * capacity_nm
        overshoots_sync = False
        if dt is not None:
            alpha_1 = (torque_1_nm - slip_torque) / inertia_1_kgm2
            alpha_2 = (slip_torque - torque_2_nm) / inertia_2_kgm2
            predicted_diff = omega_diff + (alpha_1 - alpha_2) * dt
            overshoots_sync = (predicted_diff > 0.0) != (omega_diff > 0.0)
        if not overshoots_sync:
            return slip_torque, False

    required = (inertia_2_kgm2 * torque_1_nm + inertia_1_kgm2 * torque_2_nm) / (inertia_1_kgm2 + inertia_2_kgm2)
    if abs(required) <= capacity_nm:
        return required, True

    sign = 1.0 if required >= 0.0 else -1.0
    return sign * capacity_nm, False


class Clutch:
    def __init__(self, spec: ClutchSpec):
        self.spec = spec
        # Actuator position: 0 = fully open (no torque capacity), 1 = fully
        # closed. Driven by Drivetrain's shift sequencing -- there's no
        # driver-operated pedal in this model (see core/drivetrain.py).
        self.engagement = 1.0

    def capacity_nm(self) -> float:
        return self.spec.max_static_torque_nm * max(0.0, min(1.0, self.engagement))
