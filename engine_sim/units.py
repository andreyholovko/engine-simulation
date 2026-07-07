"""Physical constants shared across the simulation core."""

R_AIR = 287.05  # J/(kg*K), specific gas constant for dry air
P_ATM = 101_325.0  # Pa
IDLE_MAP_PA = 30_000.0  # Pa, closed-throttle manifold vacuum floor (~0.3 bar absolute)
T_INTAKE_DEFAULT = 313.0  # K, ~40C post-intercooler charge temp
LHV_GASOLINE = 44.0e6  # J/kg, lower heating value of gasoline
STOICH_AFR = 14.7  # stoichiometric air-fuel ratio, gasoline

BAR_TO_PA = 1.0e5
KW_PER_WATT = 1.0e-3
NM_PER_RADS_TO_KW = 1.0 / 1000.0


def rpm_to_rad_s(rpm: float) -> float:
    from math import pi
    return rpm * 2.0 * pi / 60.0


def rad_s_to_rpm(omega: float) -> float:
    from math import pi
    return omega * 60.0 / (2.0 * pi)


def power_watts(torque_nm: float, omega_rad_s: float) -> float:
    return torque_nm * omega_rad_s
