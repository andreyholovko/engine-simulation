"""Tire model: longitudinal slip ratio -> friction force.

Slip ratio is the standard vehicle-dynamics definition -- the fractional
mismatch between the tire's own contact-patch surface speed (wheel angular
speed * rolling radius) and the surface it's actually rolling on (here, the
chassis dyno roller):

    slip_ratio = (wheel_surface_speed - road_surface_speed) / max(|both|)

Zero at a perfect, non-slipping roll; positive under drive torque (wheel
trying to outrun the road -- acceleration, wheelspin at the extreme);
negative under braking. The force a tire can deliver isn't proportional to
slip ratio -- it rises steeply from zero, peaks at a fairly small slip ratio
(real street tires: ~10-15%), and *falls off* beyond that as the contact
patch fully breaks away into sliding friction -- the same rise-then-fall
shape every real tire's longitudinal force curve has (the "magic formula"
family of models). This simplifies that shape to the handful of tunable
points TireCompound already carries, instead of a full Pacejka coefficient
set.
"""

from dataclasses import dataclass

from engine_sim.specs import TireSpec

G = 9.81  # m/s^2


@dataclass
class TireReading:
    slip_ratio: float
    mu: float  # friction coefficient actually delivered this tick
    longitudinal_force_n: float  # positive = accelerating the road/roller forward
    wheel_surface_speed_mps: float
    road_surface_speed_mps: float


class Tire:
    def __init__(self, spec: TireSpec):
        self.spec = spec

    @property
    def peak_mu(self) -> float:
        """Compound's peak_mu, scaled for this tire's actual width against
        the compound's reference width -- see TireSpec.width_grip_sensitivity."""
        spec = self.spec
        width_ratio = spec.width_mm / spec.reference_width_mm
        return spec.compound.peak_mu * (1.0 + spec.width_grip_sensitivity * (width_ratio - 1.0))

    def slip_ratio(self, wheel_surface_speed_mps: float, road_surface_speed_mps: float) -> float:
        denom = max(abs(wheel_surface_speed_mps), abs(road_surface_speed_mps), 1e-3)
        return (wheel_surface_speed_mps - road_surface_speed_mps) / denom

    def friction_coefficient(self, slip_ratio: float) -> float:
        """Piecewise: linear rise from 0 at zero slip to peak_mu at
        slip_ratio_at_peak, then an easing falloff toward sliding_mu as slip
        continues to 100% -- real tires ease off past the peak, they don't
        cliff-edge to zero."""
        compound = self.spec.compound
        s = abs(slip_ratio)
        peak = self.peak_mu
        s_peak = max(compound.slip_ratio_at_peak, 1e-3)

        if s <= s_peak:
            return peak * (s / s_peak)

        beyond = min((s - s_peak) / max(1.0 - s_peak, 1e-3), 1.0)
        return peak + (compound.sliding_mu - peak) * beyond

    def tick(
        self,
        wheel_omega_rad_s: float,
        road_omega_rad_s: float,
        road_radius_m: float,
        normal_force_n: float,
    ) -> TireReading:
        wheel_surface_speed = wheel_omega_rad_s * self.spec.radius_m
        road_surface_speed = road_omega_rad_s * road_radius_m

        slip = self.slip_ratio(wheel_surface_speed, road_surface_speed)
        mu = self.friction_coefficient(slip)
        # Force direction follows the sign of the slip (wheel outrunning the
        # road drives it forward; wheel lagging the road -- braking -- drags
        # it back), magnitude capped by mu * normal load (Coulomb friction).
        force = mu * normal_force_n * (1.0 if slip >= 0.0 else -1.0)

        return TireReading(
            slip_ratio=slip,
            mu=mu,
            longitudinal_force_n=force,
            wheel_surface_speed_mps=wheel_surface_speed,
            road_surface_speed_mps=road_surface_speed,
        )
