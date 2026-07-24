"""Webster signal-timing DECISION (traffic-realism Phase 4, increment 1).

Webster, F.V. (1958), "Traffic signal settings", Road Research Technical Paper
39. The classic result for the cycle length and green split that (approximately)
minimizes total intersection delay at a FIXED-time, two-phase signal, given each
phase's critical (heaviest) approach flow relative to its saturation flow. This
is the standard research fallback when the real signal's timing plan is not
public: Portland runs SCATS, an adaptive controller that responds to real-time
detector counts, and PBOT does not publish SCATS timing plans (per-signal timing
CARDS are public-records-requestable, but that is a future ground-truth project,
not this one). Webster instead computes what a reasonable FIXED plan would be
from the same volumes the simulation already generates.

THE MODEL
---------
For a two-phase intersection (this matches the existing signal model in
config.py: one phase serves the east-west approaches, the other north-south),
each phase i has a flow ratio

    y_i = q_i / (n_lanes_i * sat_flow)

where q_i is the CRITICAL approach flow of that phase in veh/h -- the heaviest
of the (possibly several) approaches the phase serves, since the phase's green
must be long enough for its worst-loaded approach; lighter approaches sharing
the same green are already served by it. sat_flow is the saturation flow per
lane (veh/h on continuous green), so n_lanes_i * sat_flow is the phase's total
discharge capacity.

    Y = y_ew + y_ns                  (total intersection flow ratio)
    L = 2 * lost_time_s              (total lost time, one lost-time interval
                                       per phase: startup + clearance)

Webster's optimal cycle length:

    C0 = (1.5 * L + 5) / (1 - Y)

This is minimized-delay, not maximum-throughput; it is only valid for Y < 1
(undersaturated). We clamp C0 to [cycle_min_s, cycle_max_s] -- real signals do
not run a 3-second or a 400-second cycle regardless of what the formula says.

The available green (cycle minus lost time) is then split between the phases
in proportion to their flow ratios -- the phase with the heavier relative
demand gets the larger share of the green:

    g_tot = C0 - L
    g_i   = g_tot * y_i / Y

with a floor of min_green_s enforced on each phase's effective green (a
pedestrian-crossing / driver-expectation minimum, not a capacity number; see
`cycle_and_split`'s docstring for the exact reallocation rule).

DEGENERATE CASES (Y is a ratio; the formula above only makes sense on (0, 1)):
  Y == 0   no demand at all on either phase. There is nothing to optimize; sit
           at the shortest allowed cycle with an even split (arbitrary, but
           harmless -- nobody is waiting either way).
  Y >= 1   oversaturated: the formula's (1 - Y) denominator is zero or negative,
           so C0 is undefined or would blow up/go negative. There is no fixed
           cycle that clears this much demand. The standard practical fallback
           is the maximum allowed cycle (it maximizes green time delivered per
           hour, which is the best a fixed-time plan can do); the green split
           is still allocated proportionally to the (still meaningful) y's.

RETURN VALUE
------------
`cycle_and_split` returns (cycle_s, green_split_ew), where green_split_ew is
defined as the FRACTION OF THE CYCLE the east-west phase holds -- its own
effective green plus its own phase's lost time, i.e.
(g_ew + lost_time_s) / cycle_s. Defining it this way (rather than as the bare
green fraction) means the EW and NS fractions sum to exactly 1.0 by
construction, and the returned number is directly comparable to
config.SIGNAL_GREEN_SPLIT, which is likewise a fraction of the full cycle.

WHY THIS MODULE IS PURE
------------------------
No imports from generate.py or any simulation state, and no side effects: this
is one function of plain arithmetic on the flows it is given, mirroring
src/mobil.py's discipline (a small, hand-checkable decision module, verified in
isolation by src/webster_scenarios.py before any later increment wires it into
step_vehicles).

NOT MODELED HERE (explicitly out of scope for increment 1)
------------------------------------------------------------
- Actuated or adaptive control (what Portland's SCATS controllers actually run).
  Webster is a fixed-time MODEL of what a reasonable plan would look like, not
  a claim about the real controller's behavior.
- Yellow and all-red clearance intervals -- increment 2.
- Green-wave (progression) offsets along a corridor -- increment 2.
- Multi-phase (protected left-turn, etc.) intersections -- this is a two-phase
  model only, matching the existing uniform-signal model it replaces.
"""


def _critical_flow(flows):
    """The flow ratio for a phase uses its CRITICAL (heaviest) approach: a
    protected phase's green must be long enough for its worst-loaded approach,
    and any lighter approach sharing that same green is already served by it.
    Accepts either a single flow in veh/h, or an iterable of per-approach flows
    for that phase, in which case the maximum governs."""
    if isinstance(flows, (int, float)):
        return float(flows)
    return float(max(flows))


def cycle_and_split(flows_ew, flows_ns, n_lanes_ew=1, n_lanes_ns=1,
                     sat_flow=1900.0, lost_time_s=4.0,
                     cycle_min_s=30.0, cycle_max_s=120.0, min_green_s=7.0):
    """Webster cycle length and EW green-split fraction for one two-phase
    intersection. flows_ew / flows_ns: critical approach flow(s) for each
    phase, veh/h (scalar or iterable; see `_critical_flow`). n_lanes_ew /
    n_lanes_ns: lane count serving that phase's critical approach (default 1,
    matching the base single-lane model). The remaining keyword defaults mirror
    config.WEBSTER_* so this function can be called standalone (no config
    import here, matching src/mobil.py's pattern of taking resolved values, not
    reading config directly); a caller wires config.WEBSTER_* into these
    keywords explicitly.

    Returns (cycle_s, green_split_ew) -- see the module docstring for what
    green_split_ew means (a fraction of the full cycle, EW + NS sums to 1.0).
    """
    q_ew = _critical_flow(flows_ew)
    q_ns = _critical_flow(flows_ns)
    y_ew = q_ew / (n_lanes_ew * sat_flow)
    y_ns = q_ns / (n_lanes_ns * sat_flow)
    Y = y_ew + y_ns
    L = 2.0 * lost_time_s   # one lost-time interval per phase, two phases

    if Y <= 0.0:
        # No demand on either approach: nothing to optimize for. Shortest legal
        # cycle, even split -- no one is waiting on either phase regardless.
        return cycle_min_s, 0.5

    if Y >= 1.0:
        # Oversaturated: Webster's (1 - Y) denominator is zero or negative, so
        # the "optimal cycle" formula has no valid answer. Fall back to the
        # longest allowed cycle (delivers the most green per hour a fixed-time
        # plan can offer); the split below still allocates it proportionally.
        cycle_s = cycle_max_s
    else:
        cycle_s = (1.5 * L + 5.0) / (1.0 - Y)
        cycle_s = min(max(cycle_s, cycle_min_s), cycle_max_s)   # clamp to range

    g_tot = cycle_s - L   # effective green available to split between phases

    if g_tot < 2.0 * min_green_s:
        # Not enough green in this cycle to give BOTH phases even their minimum
        # green, let alone a proportional split. Rather than violate the floor,
        # lengthen the cycle to EXACTLY the length that fits two minimum greens
        # plus lost time -- the smallest cycle in which both phases are
        # drivable at all. No surplus remains to allocate proportionally.
        cycle_s = 2.0 * min_green_s + L
        g_ew = min_green_s
        g_ns = min_green_s
    else:
        g_ew = g_tot * (y_ew / Y)
        g_ns = g_tot * (y_ns / Y)
        # Floor each phase's green at min_green_s. g_tot >= 2*min_green_s (the
        # branch above) guarantees at most ONE phase can be under the floor --
        # if it takes the deficit from the other, the other still clears the
        # floor by construction, so raise the deficient phase and shrink its
        # partner by exactly the same amount (the total, and so the cycle
        # length, is unchanged).
        if g_ew < min_green_s:
            deficit = min_green_s - g_ew
            g_ew = min_green_s
            g_ns -= deficit
        elif g_ns < min_green_s:
            deficit = min_green_s - g_ns
            g_ns = min_green_s
            g_ew -= deficit

    green_split_ew = (g_ew + lost_time_s) / cycle_s
    return cycle_s, green_split_ew
