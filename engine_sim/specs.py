"""Data-driven engine/turbo/camshaft parameters.

An EngineSpec fully describes a physical engine build (displacement, cylinder
count, compression ratio, camshaft profile, friction characteristics). The
Engine model computes torque output from these parameters plus live
throttle/RPM/manifold-pressure inputs -- it never hardcodes a canned curve.
"""

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class CamSpec:
    """Camshaft profile. Longer duration / higher lift shifts the engine's
    breathing (volumetric efficiency) sweet spot to a higher RPM band, at the
    cost of low-RPM torque -- the classic cam trade-off."""

    intake_duration_deg: float = 220.0
    intake_lift_mm: float = 9.5
    overlap_deg: float = 20.0


@dataclass(frozen=True)
class EngineSpec:
    name: str
    displacement_l: float
    cylinders: int
    compression_ratio: float
    cam: CamSpec = field(default_factory=CamSpec)

    # The actual firing order (1-indexed cylinder numbers), e.g. (1, 3, 4, 2)
    # for most transverse inline-4s or (1, 5, 3, 6, 2, 4) for a BMW inline-6.
    # Doesn't change pulse *spacing* for an even-firing inline engine (that's
    # cylinders*rpm/120 regardless of order) -- it's the sequence each
    # cylinder's fixed exhaust signature repeats in every revolution, which is
    # what audio synthesis (or anything else caring about per-cylinder
    # character) should actually consume, rather than guessing from cylinder
    # count alone. Defaults to a plain 1..N sequence for anything that hasn't
    # set a real one.
    firing_order: Tuple[int, ...] = ()

    bore_mm: float = 82.5
    stroke_mm: float = 92.8

    idle_rpm: float = 900.0
    redline_rpm: float = 6700.0

    # Volumetric efficiency shape: flat "plateau" up to ve_falloff_rpm, then
    # tapering off as breathing/flow limits bite at high RPM. The falloff
    # point shifts with cam duration (longer duration breathes further up
    # the rev range).
    ve_peak: float = 0.92
    ve_floor_fraction: float = 0.55
    # Optional rising phase from idle_rpm up to ve_rise_rpm, before the flat
    # plateau. Turbocharged engines get their low-end torque rise from boost
    # building (MAP), not from VE, so this defaults to 0 (meaning "no rise
    # phase" -- VE is ve_peak from idle already, the original behavior,
    # unchanged for every existing preset). A naturally-aspirated engine has
    # no boost to do that job, so its VE curve itself has to rise from idle
    # to wherever it breathes best (e.g. the LS2 peaks torque at 4400rpm on
    # VE alone) -- set this for that case.
    ve_rise_rpm: float = 0.0

    # Miller/Otto-cycle engines (e.g. EA888 Gen3B "evo") vary *effective*
    # compression in real time via intake valve closing timing: early closure
    # (Miller) at low load for efficiency, later closure (near-Otto) under
    # load for power. Non-Miller engines just use compression_ratio as-is.
    miller_cycle: bool = False
    miller_compression_ratio: float = 0.0  # effective ratio at low load, if miller_cycle

    # FMEP-style friction model (Pa): fmep = a + b*rpm + c*rpm^2
    friction_a_pa: float = 35_000.0
    friction_b_pa_per_rpm: float = 10.0
    friction_c_pa_per_rpm2: float = 0.001

    combustion_efficiency: float = 0.98
    # Fraction of ideal Otto-cycle thermal efficiency actually realized once
    # heat loss, incomplete expansion etc. are accounted for.
    realism_factor: float = 0.80

    crank_inertia_kgm2: float = 0.18

    # Minimum pump-octane (AKI/(R+M)/2, US-style rating) the factory tune
    # assumes it can run without retarding timing under load -- approximate,
    # not an exact published spec, since manufacturers rarely publish a bare
    # knock-onset number. Running below this on a live octane override costs
    # thermal efficiency under load (ECU pulling timing to protect against
    # knock); running at or above it costs nothing, same as today.
    knock_octane_requirement: float = 91.0

    @property
    def displacement_m3(self) -> float:
        return self.displacement_l / 1000.0

    @property
    def firing_order_resolved(self) -> Tuple[int, ...]:
        """firing_order if set, else a plain 1..N sequence."""
        return self.firing_order or tuple(range(1, self.cylinders + 1))

    def ve_falloff_rpm(self) -> float:
        # Longer duration cams keep breathing well further up the rev range.
        return 4200.0 + (self.cam.intake_duration_deg - 200.0) * 25.0


@dataclass(frozen=True)
class TurboSpec:
    name: str
    max_boost_bar: float  # gauge pressure, bar
    # RPM at which the turbo reaches ~50% of max boost at WOT -- matches how
    # manufacturers quote "full boost by N rpm".
    spool_midpoint_rpm: float
    spool_width_rpm: float = 700.0
    spool_time_constant_s: float = 0.35

    # Charge-air heating: a real turbo (even intercooled) delivers boosted
    # air hotter than ambient, and that heat builds up over a sustained pull
    # -- a boosted engine's torque tapers slightly the longer it's held at
    # boost, unlike this sim's previous flat-ambient-forever intake temp.
    # Rise is *post-intercooler* (whatever cooling exists is already priced
    # into this one number, deliberately, rather than modeling compressor
    # discharge temp and intercooler effectiveness as two separate invented
    # constants -- see Turbo.tick()).
    charge_temp_rise_k_per_bar: float = 30.0
    # Thermal lag to reach steady charge temp -- much slower than the boost
    # pressure signal itself (spool_time_constant_s), which is why back-to-
    # back pulls run hotter than a single pull from cold even though boost
    # itself reads the same on the gauge each time.
    heat_soak_time_constant_s: float = 10.0

    # How many independent exhaust paths feed the turbine (1 = single-scroll
    # log manifold combining every cylinder's pulses into one feed; 2 =
    # twin-scroll, splitting the firing order into two alternating groups).
    # Combined with the engine's actual firing order (not just cylinder
    # count) in Turbo, this is what makes spool response engine-specific
    # instead of a purely hand-tuned constant -- see
    # Turbo._compute_pulse_quality().
    exhaust_scroll_groups: int = 1


@dataclass(frozen=True)
class CarSpec:
    """A specific, real car -- what DynoSession.select_car()/
    select_car_by_index() actually swap (see presets.CAR_CHOICES). Bundles
    the engine that powers it with the turbo it ships stock: picking "a
    car" picks both at once, the way rolling a specific car onto a dyno or
    up to a drag strip actually works -- nobody selects "an engine" in the
    abstract and only then discovers what it's bolted into. Swapping just
    the turbo afterward, same car, same engine, is the separate axis
    TURBO_CHOICES_BY_CAR covers (DynoSession.select_turbo())."""

    name: str
    engine_spec: EngineSpec
    turbo_spec: TurboSpec


@dataclass(frozen=True)
class TireCompound:
    """A tire's rubber, independent of its size. peak_mu/sliding_mu are
    longitudinal friction coefficients (force = mu * normal load), the same
    quantity real tire data sheets and racing-sim "grip level" numbers mean
    -- a compound alone doesn't fully determine grip (see TireSpec.width_mm),
    but it sets the coefficient a given contact patch delivers."""

    name: str
    peak_mu: float  # friction coefficient at the grip peak (slip_ratio_at_peak)
    slip_ratio_at_peak: float  # fraction (0-1); real street tires peak around 0.10-0.15
    sliding_mu: float  # coefficient once fully broken away (high slip, e.g. a burnout)


@dataclass(frozen=True)
class TireSpec:
    """A physical tire+wheel assembly: size, width and compound, exactly the
    three numbers a real tire sidecode (e.g. 225/45R17) plus a compound
    choice actually specifies. Drives Tire's slip-ratio -> force curve."""

    name: str
    radius_m: float  # rolling radius, wheel+tire combined
    width_mm: float
    compound: TireCompound
    # Rotational inertia of the wheel+tire assembly about its own axle --
    # what a launch or a shift has to spin up/down, separate from the
    # vehicle's own linear mass (see RollerSpec.vehicle_mass_kg).
    inertia_kgm2: float = 1.2
    # Width's effect on grip: modeled as a simple scaling off a reference
    # width rather than a second curve -- wider than reference -> more
    # contact patch -> more peak mu; narrower -> less. A real tire's width
    # vs. grip relationship isn't perfectly linear either, but this captures
    # the right *direction* and magnitude without inventing a second
    # unvalidated curve shape on top of the compound's own.
    reference_width_mm: float = 225.0
    width_grip_sensitivity: float = 0.15  # fractional peak_mu change per 100% width delta from reference


@dataclass(frozen=True)
class ClutchSpec:
    """Friction clutch between the engine/flywheel and the gearbox input
    shaft. max_static_torque_nm is its torque capacity fully clamped
    (locked) -- real clutches are sized with headroom over the engine's peak
    torque so they *can* lock solidly; sized too small (or worn/slipping)
    and it can't transmit everything the engine makes, which this model
    reproduces directly (see core/clutch.py's lock-vs-slip decision)."""

    name: str
    max_static_torque_nm: float


@dataclass(frozen=True)
class TransmissionSpec:
    """A manual gearbox: fixed ratios (index 0 = 1st) plus a final drive
    ratio applied after every gear. shift_time_s is how long the auto-clutch
    sequence (declutch -> swap ratio -> re-clutch) takes for a paddle/button
    shift -- the torque-interruption window a real shift also has, just
    without a driver-operated clutch pedal to control it (see
    core/drivetrain.py)."""

    name: str
    gear_ratios: Tuple[float, ...]
    final_drive_ratio: float
    shift_time_s: float = 0.25


@dataclass(frozen=True)
class TorqueConverterSpec:
    """A torque converter: the fluid coupling between the engine and the
    gearbox input shaft (turbine) a torque-converter automatic launches and
    idles through, with no driver-operated clutch pedal at all -- the
    converter itself slips continuously, which is what actually produces the
    "creeps forward at idle in Drive" behavior every automatic has (see
    core/torque_converter.py for the physics)."""

    name: str
    # Impeller/pump absorption constant K: pump_torque = K * omega_pump^2 --
    # the single number that sets both idle creep torque (small, at idle
    # rpm) and WOT stall speed (the rpm the engine settles at against a
    # stalled turbine -- realistic units land it around 2000-2500rpm).
    capacity_nm_per_rads2: float
    stall_torque_ratio: float  # multiplication at speed_ratio 0 (typ. 1.8-2.5)
    coupling_speed_ratio: float  # speed_ratio where multiplication reaches 1.0 (typ. 0.85-0.9)
    lockup_capacity_nm: float  # lockup clutch (TCC) torque capacity once fully applied
    lockup_apply_time_s: float = 0.5
    # Real TCCs release much faster than they apply -- releasing late (e.g.
    # into a sudden kickdown) would fight the converter's own cushioning
    # right when it's needed most.
    lockup_release_time_s: float = 0.15
    turbine_inertia_kgm2: float = 0.03  # turbine + gearbox input shaft -- small, like the manual's clutch disk


@dataclass(frozen=True)
class AutomaticTransmissionSpec:
    """A torque-converter automatic: same gear_ratios/final_drive_ratio
    shape as TransmissionSpec (Drivetrain reads them structurally -- it
    doesn't care which type it was given), plus the torque converter and a
    throttle-aware shift map that replaces the driver's own +/- shift
    buttons entirely. "User input" for this transmission is just the
    accelerator -- the same throttle_percent every mode already takes --
    exactly like a real automatic, where load and road speed decide the
    gear, not the driver's hand."""

    name: str
    gear_ratios: Tuple[float, ...]
    final_drive_ratio: float
    torque_converter: TorqueConverterSpec
    # Clutch-pack swap time -- automatics blend gears smoother/slower than a
    # paddle-shift manual's snappier ramp.
    shift_time_s: float = 0.5
    # Shift map: upshift/downshift rpm points at light throttle (economy)
    # and at WOT (kickdown ceiling/floor), interpolated by throttle in
    # between -- flooring it at cruise rpm should immediately want a lower
    # gear (real kickdown), exactly what interpolating downshift_rpm up
    # toward downshift_rpm_wot as throttle rises produces.
    #
    # downshift_rpm_wot needs real margin below whatever rpm an upshift at
    # upshift_rpm_wot actually lands on in the *tallest-gap* gear pair (the
    # ratio between adjacent gears isn't constant -- 1st->2nd is usually the
    # biggest drop), or a WOT upshift can land right back at/below its own
    # downshift floor and immediately reverse -- hunting, forever. Found
    # directly: a 3800 floor here, against a 6MT-style box where 1st->2nd
    # alone already lands a clean upshift at ~3855rpm, needed only the
    # shift's own rpm sag (real engine braking during the torque-managed
    # cut, not a bug) to dip under it.
    upshift_rpm_light: float = 2200.0
    upshift_rpm_wot: float = 6200.0
    downshift_rpm_light: float = 1200.0
    downshift_rpm_wot: float = 2800.0
    # Lockup only engages from this gear upward (1st/2nd stay
    # converter-coupled for launch smoothness/multiplication, same as real
    # Aisin-class units), and only releases again above this throttle
    # (kickdown wants the converter's own cushioning/multiplication back).
    lockup_min_gear: int = 3
    lockup_max_throttle: float = 0.6


@dataclass(frozen=True)
class RollerSpec:
    """The chassis dyno's roller/drum, standing in for the road: it has its
    own physical inertia (the drum itself) plus the vehicle's linear mass
    reflected into an equivalent rotational inertia at the roller surface
    (J = mass * radius^2 -- the standard trick for putting a car's mass on a
    spinning drum), so accelerating the roller costs the same effort a real
    car's mass would take to accelerate down a road."""

    name: str
    radius_m: float
    inertia_kgm2: float  # the physical drum's own inertia
    vehicle_mass_kg: float
    parasitic_torque_nm: float = 15.0  # roller bearing + driveline drag, always opposing motion
    # Deliberately not modeling weight transfer/aero downforce -- a fixed
    # static split of the vehicle's weight onto the driven axle/tire this
    # roller represents, not a full suspension/chassis dynamics model.
    driven_axle_weight_fraction: float = 0.5
    # Simple quadratic aero drag (F = 0.5*rho*Cd*A*v^2) -- without it, top
    # gear never actually tops out (nothing opposes speed except a flat
    # rolling drag), which reads as obviously wrong the first time anyone
    # holds WOT for a while. Typical compact/sport-car coefficients.
    drag_coefficient: float = 0.32
    frontal_area_m2: float = 2.2
