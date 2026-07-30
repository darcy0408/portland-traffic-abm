"""MOBIL lane-changing decision (traffic-realism Phase 3).

Kesting, Treiber & Helbing (2007), "General lane-changing model MOBIL for
car-following models" (Transportation Research Record 1999). A vehicle changes to
an adjacent lane iff BOTH criteria hold:

  SAFETY    the prospective NEW follower (the car behind the gap being entered) is
            not forced to brake harder than b_safe once the mover cuts in:

                a_new_follower_after  >=  -b_safe

  INCENTIVE the mover's own acceleration gain outweighs the politeness-weighted
            disadvantage it imposes on the followers it affects, by more than a
            switching threshold:

                (a_self_after - a_self_before)
                    >  p * ( (a_new_before + a_old_before)
                            -(a_new_after  + a_old_after ) )  +  a_thr

            a_self   = the mover;   a_old = its OLD follower (staying in the lane
            the mover leaves);      a_new = the NEW follower (in the target lane).
            "before" is the frozen current state; "after" is the hypothetical once
            the mover sits in the target lane. p (politeness) weights how much the
            mover cares about the braking it inflicts on others; a_thr is a
            hysteresis threshold that stops cars flip-flopping between equal lanes.

WHY THIS MODULE IS PURE
-----------------------
Every acceleration above is an ordinary IDM acceleration
(generate.idm_acceleration) for the relevant follower/leader pairing. This module
does NOT recompute physics: the caller (step_vehicles, or the hand-checkable gate
in src/mobil_scenarios.py) evaluates the six IDM accelerations from real gaps and
speeds and passes them in. So the car-following kernel stays single-sourced and
verified, and MOBIL is only the small, testable DECISION layered on top. A follower
that does not exist (the mover is last in its lane, or the target lane is empty
behind the gap) is passed as None: it contributes zero to the incentive sum, and a
missing NEW follower makes the safety test trivially pass (nobody to brake).
"""
from collections import namedtuple

# Immutable parameter bundle, filled from config once (like emissions.active_coeffs
# / fleet.resolved: resolve config lookups before any hot loop).
MobilParams = namedtuple("MobilParams", ("politeness", "a_thr", "b_safe"))


def params_from_config(config):
    """Build a MobilParams from the config module. Kept as a function (not read at
    import) so a scenario can override the module values without editing config."""
    return MobilParams(politeness=config.MOBIL_POLITENESS,
                       a_thr=config.MOBIL_A_THRESHOLD,
                       b_safe=config.MOBIL_B_SAFE)


def is_safe(a_new_follower_after, b_safe):
    """MOBIL safety: the new follower may not be forced past b_safe of braking.
    a_new_follower_after is None when the target lane has no follower behind the
    gap, which is trivially safe (no one to brake)."""
    if a_new_follower_after is None:
        return True
    return a_new_follower_after >= -b_safe


def incentive_margin(self_before, self_after, old_pair, new_pair, politeness):
    """The left-minus-right of the incentive inequality:

        (a_self_after - a_self_before) - p * (others' total acceleration loss)

    A positive result means the change is attractive; MOBIL accepts it when this
    exceeds a_thr. `old_pair` / `new_pair` are each the (before, after) IDM
    acceleration of that follower, or None if that follower does not exist (it then
    contributes nothing to the loss). "Loss" is before - after: how much MORE the
    follower must brake because of the change, so a change that eases a follower
    (after > before) actually helps the incentive."""
    own_gain = self_after - self_before
    others_loss = 0.0
    for pair in (old_pair, new_pair):
        if pair is not None:
            before, after = pair
            others_loss += before - after
    return own_gain - politeness * others_loss


def wants_change(self_before, self_after, old_pair, new_pair, params):
    """Full MOBIL decision for one candidate target lane. Returns
    (change: bool, margin: float). `change` is True only when the move is both safe
    and the incentive margin clears the threshold; `margin` is returned regardless
    so the caller can pick the BEST of several candidate lanes (largest margin).

    self_before / self_after : the mover's IDM accel now / in the target lane.
    old_pair / new_pair       : (before, after) accel of the old / new follower,
                                or None when that follower is absent.
    """
    a_new_after = None if new_pair is None else new_pair[1]
    if not is_safe(a_new_after, params.b_safe):
        return False, float("-inf")            # unsafe: never change, rank last
    margin = incentive_margin(self_before, self_after, old_pair, new_pair,
                              params.politeness)
    return (margin > params.a_thr), margin
