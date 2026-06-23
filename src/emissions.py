"""Per-vehicle NOx emissions from the SUMO HBEFA3 model.

The agent simulation gives every vehicle an instantaneous speed and acceleration
at each step (the IDM produces both). SUMO's HBEFA3-based emission model turns
that (v, a) pair into a NOx emission rate with a single polynomial, so it plugs
straight onto our per-step values with no extra state. This is "approach B" in
DATASETS.md, the lowest-friction path to a real emission surface.

Formula and coefficients are taken verbatim from Eclipse SUMO,
src/utils/emissions/HelpersHBEFA3.{h,cpp} (the compute() method). On flat ground:

    E_mg_s = max( (f0 + f1*a*v + f2*a^2*v + f3*v + f4*v^2 + f5*v^3) / 3.6 , 0 )

with v in m/s and a in m/s^2, output in mg/s. We divide by 1000 to return g/s.
The /3.6 scale is HBEFA3-specific (the raw polynomial is fitted in g/h); do not
pair these coefficients with the different HBEFA4 scale.
Docs: https://sumo.dlr.de/docs/Models/Emissions/HBEFA3-based.html

We keep SUMO's max(...,0) floor (it stops the negative f3*v term from producing
nonphysical negative emissions at low speed). We omit SUMO's separate
engine-coasting cutoff, which zeros emission under hard deceleration: that is a
documented simplification and only affects some braking steps.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# HBEFA3 NOx polynomial coefficients (f0..f5) by vehicle class, in SUMO's order.
# Rows copied from HelpersHBEFA3.cpp. Diesel Euro 4 is the NOx-relevant passenger
# car (diesels are the NOx problem); gasoline Euro 4 is kept as a cross-check
# alternative. Both avoid the DATASETS.md blacklist (LDV+NOx, PC_G_EU0+NOx).
HBEFA3_NOX_COEFFS = {
    "PC_D_EU4": (47.45, 4.011, 0.0, -4.061, 0.1619, 0.0),    # passenger car, diesel, Euro 4
    "PC_G_EU4": (4.336, 0.4428, 0.0, -0.3204, 0.01371, 0.0),  # passenger car, gasoline, Euro 4
}

HBEFA3_SCALE = 3.6            # SUMO HBEFA3 scale: divides g/h to mg/s. HBEFA3-specific.
_MG_PER_S_TO_G_PER_S = 1.0e-3


def active_coeffs():
    """The NOx coefficient row for the class chosen in config.EMISSION_CLASS.
    Look this up once before a hot loop and pass it to nox_g_per_s, rather than
    re-reading config every call."""
    return HBEFA3_NOX_COEFFS[config.EMISSION_CLASS]


def nox_g_per_s(v_mps, a_mps2, coeffs):
    """NOx emission rate in grams per second for one vehicle.

    Arguments:
        v_mps   instantaneous speed (m/s)
        a_mps2  instantaneous acceleration (m/s^2); sign matters, braking is
                negative, and the max(...,0) floor handles the low-speed case
        coeffs  an (f0..f5) tuple from HBEFA3_NOX_COEFFS (use active_coeffs())

    Implements SUMO's HBEFA3 polynomial on flat ground (slope 0), then converts
    the model's native mg/s to g/s.
    """
    f = coeffs
    v, a = v_mps, a_mps2          # slope 0, so SUMO's slope-adjusted a2 reduces to a
    poly = (f[0] + f[1] * a * v + f[2] * a * a * v
            + f[3] * v + f[4] * v * v + f[5] * v * v * v)
    mg_per_s = max(poly / HBEFA3_SCALE, 0.0)    # SUMO's MAX2(..., 0.)
    return mg_per_s * _MG_PER_S_TO_G_PER_S
