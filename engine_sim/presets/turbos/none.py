"""Placeholder "turbo" for naturally-aspirated engines (e.g. the LS2).

max_boost_bar=0.0 means the turbo model never produces any boost, regardless
of rpm/throttle/wastegate duty -- MAP stays exactly the naturally-aspirated
curve (closed-throttle vacuum up to atmospheric at WOT, see
ECU.intake_manifold_pressure), and turbo whine audio reads spool_fraction as
0 throughout. Every consumer (ECU, Turbo, dyno_audio.gd) already guards
against max_boost_bar==0 (no special-casing needed anywhere) -- this is just
a TurboSpec with no boost authority, not a different code path."""

from engine_sim import TurboSpec

TURBO_NONE = TurboSpec(
    name="(naturally aspirated -- no turbo)",
    max_boost_bar=0.0,
    spool_midpoint_rpm=3000.0,
    spool_width_rpm=1000.0,
    spool_time_constant_s=0.3,
)
