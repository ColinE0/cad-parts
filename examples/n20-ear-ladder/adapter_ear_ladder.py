r"""
Corner-relief ("Mickey ears") D-bore ladder for the N20 wheel adapter.

STATUS: printed and fitted, FROZEN. Colin, 2026-09-26: "the ears were perfect. they helped
tremendously"; best rung B 3.10 / 2.50 (his belief). Ears are now standard in every N20
adapter build (see ..\README.md).

WHAT IS DIFFERENT FROM wheel_adapter_v2.py, AND NOTHING ELSE IS:
two Ø1.0 relief circles cut at the two corners where the bore's flat meets its
arc, over the shaft's flat-engagement length only (z = -1.0 .. +8.0). Every
other dimension, the whole proven wheel_adapter_final silhouette, is copied
byte-for-byte, including RELIEF_EXTRA 0.02, the entry chamfer, the base fillet
and the engraved label. The base solid is built by the SAME code path as the
shipped part; the ears are a separate cut applied afterwards, so this file
cannot drift the proven geometry even by accident.

WHY, and what it predicts.

The 2026-08-07 ladder found a very sharp cliff: 3.10 "did not go on", 3.15
"glove tight". 0.05mm should not flip a fit that hard if the shaft were being
held by its round and flat SURFACES. A cliff that sharp is the signature of a
LOCAL interference, and the only local feature in a D-bore is the two corners.

The shaft's corners are machined sharp. The printed bore's corners are not: the
extruder cannot reproduce a 128.3 degree internal corner in a hole, so material
bulges inward exactly there. The shaft's sharp corner lands on that bulge and
stops, while the round and flat still have clearance to spare. On that reading,
the 0.15mm of diametral clearance in the shipped demo part is not the clearance
the fit needs; it is the clearance needed to clear the CORNERS, and the round
and flat are being opened up as collateral damage. That is the backlash.

Cut the corners away and the surfaces should be free to run much tighter.

FALSIFIABLE PREDICTION, which is the point of this ladder: rung B is 3.10/2.50,
the exact geometry that would NOT go on without ears. If B now slides on, the
corner-interference explanation is correct and the bore can be tightened. If B
still will not go on, the explanation is wrong, the clearance really is
distributed over the surfaces, ears are a dead end, and the shipped 3.15 stays
as it is. Either answer is worth one 4-part print.

  A  3.15 / 2.55   + ears   same bore as the SHIPPED demo part. Isolates the
                            ears as the only variable. Should now feel loose.
  B  3.10 / 2.50   + ears   the decisive rung. No-ear verdict: "did not go on".
  C  3.05 / 2.45   + ears   no-ear verdict: "has to be forced to even start".
  D  3.00 / 2.40   + ears   nominal, zero nominal clearance on both surfaces.

Labels are LETTERS, not bore digits, so these cannot be confused on the bench
with the existing parts engraved "15" and "20".

TRADEOFF, stated so it is not discovered on hardware: the ears sit at the bore
corners and push the local wall out toward the hex flat. Worst-case wall drops
from ~1.58mm to ~1.03mm at two small spots. Those spots carry no torque (the
flat does), but this is the reason not to grow the ears past Ø1.0. The script
asserts the wall stays above 0.8mm.

The ears also merge with the M3 grub pilot near z=-0.2, because the pilot
already breaks through the flat there by 0.1mm. That merge is inside the Ø10.9
boss where the wall is thick, and is expected, not a bug.

PRINT: boss-down (bore mouth on the bed), no supports, the SAME K2 profile the
2026-08-07 ladder was printed on. A different orientation or profile makes
every number in this file meaningless. Fit each rung to a real motor shaft and
rank them the way the last ladder was ranked.

Run via run_watchdogged.ps1, pointed at this file.
"""
import math
from pathlib import Path

import cadquery as cq
import cq_helpers as h

# ---- proven wheel_adapter_final geometry, copied verbatim from wheel_adapter_v2.py
PLUG_AF, PLUG_LEN = 6.2, 8.0
FLANGE_D, FLANGE_T = 11.0, 1.5
BOSS_D, BOSS_LEN = 10.9, 2.0
CAP_T, RELIEF_LEN = 1.5, 1.0
RELIEF_EXTRA = 0.02      # breaks the relief/D-bore tangency; see the ladder
FILLET_R, ENTRY_CHAMFER = 1.0, 0.4
GRUB_HOLE, GRUB_Z = 2.5, -0.2
MARK_H, MARK_CUT = 2.4, 0.3

# shaft, measured by Colin 2026-08-07
SHAFT_LEN, SHAFT_FLAT_LEN, SHAFT_DIA = 10.0, 7.0, 3.00
SHAFT_ROUND_BASE = SHAFT_LEN - SHAFT_FLAT_LEN

# ---- the one new feature
EAR_D = 1.0              # Ø1.0 = 2.5 extrusion widths on a 0.4 nozzle: prints
                         # as a real hole, still small enough to keep the wall
EAR_R = EAR_D / 2
MIN_WALL = 0.8           # floor for the local wall at the ear, see docstring

TOP = FLANGE_T + PLUG_LEN
TOTAL = BOSS_LEN + TOP
BORE_DEPTH = TOTAL - CAP_T
GRUB_FROM_MOUTH = GRUB_Z + BOSS_LEN
STANDOFF = max(0.0, SHAFT_ROUND_BASE - RELIEF_LEN)
INSERTION = SHAFT_LEN - STANDOFF
FLAT_MARGIN = (STANDOFF + GRUB_FROM_MOUTH) - SHAFT_ROUND_BASE

# the ears span exactly the length over which the shaft's FLAT is inside the
# bore: from the top of the round mouth relief to the bore floor. Starting them
# any lower would put a new edge inside the entry-chamfer selector box at
# z = -2.1..-1.9 and OCCT has already broken a chamfer on this part once.
EAR_Z0 = -BOSS_LEN + RELIEF_LEN
EAR_Z1 = TOP - CAP_T
EAR_LEN = EAR_Z1 - EAR_Z0

assert MARK_CUT < CAP_T, "engraving would break the push-out cap"
assert INSERTION <= BORE_DEPTH, "shaft would bottom out"
assert FLAT_MARGIN > 0, "grub would land on the shaft's round base, not the flat"
assert EAR_Z0 > -BOSS_LEN + 0.5, "ear would fall inside the entry-chamfer selector box"

print(f"seating: mouth stops {STANDOFF:.1f}mm off the motor face, "
      f"{INSERTION:.1f}mm of shaft engaged, grub {FLAT_MARGIN:+.1f}mm onto "
      f"the flat", flush=True)
print(f"ears: Ø{EAR_D} x {EAR_LEN:.1f} long, z {EAR_Z0:+.1f} to {EAR_Z1:+.1f}\n",
      flush=True)

# folder-name, file-name, bore, flat, label, no-ear verdict from the 2026-08-07 ladder
VARIANTS = [
    ("A bore 3.15 + ears", "adapter_ear_A_b315", 3.15, 2.55, "A",
     "shipped demo fit, was glove tight without ears"),
    ("B bore 3.10 + ears", "adapter_ear_B_b310", 3.10, 2.50, "B",
     "DECISIVE: did not go on without ears"),
    ("C bore 3.05 + ears", "adapter_ear_C_b305", 3.05, 2.45, "C",
     "had to be forced to even start without ears"),
    ("D bore 3.00 + ears", "adapter_ear_D_b300", 3.00, 2.40, "D",
     "nominal, never tested without ears"),
]

CONTROL_VOL = 508.8      # wheel_adapter_demo_b315, the rung Colin physically fitted


def corners(bore_dia, bore_flat):
    """The two points where the bore's flat meets its arc. Ear centres."""
    r = bore_dia / 2
    c = bore_flat - r
    hc = math.sqrt(r * r - c * c)
    return r, c, hc


def build_base(bore_dia, bore_flat, label):
    """Byte-for-byte the shipped wheel_adapter_v2 build(). Do not touch."""
    ac = PLUG_AF / math.cos(math.radians(30))
    part = (cq.Workplane("XY").circle(BOSS_D / 2).extrude(-BOSS_LEN)
            .union(cq.Workplane("XY").circle(FLANGE_D / 2).extrude(FLANGE_T))
            .union(cq.Workplane("XY", origin=(0, 0, FLANGE_T))
                   .polygon(6, ac).extrude(PLUG_LEN)))

    r, c, hc = corners(bore_dia, bore_flat)
    part = part.cut(cq.Workplane("XY", origin=(0, 0, -BOSS_LEN))
                    .moveTo(-hc, c).lineTo(hc, c)
                    .threePointArc((0, -r), (-hc, c)).close().extrude(BORE_DEPTH))

    y0 = BOSS_D / 2 + 0.5
    part = part.cut(cq.Workplane("XZ", origin=(0, y0, GRUB_Z))
                    .circle(GRUB_HOLE / 2).extrude(y0 - (c - 0.1)))
    part = part.cut(cq.Workplane("XY", origin=(0, 0, -BOSS_LEN))
                    .circle(r + RELIEF_EXTRA).extrude(RELIEF_LEN))

    part = part.edges(cq.selectors.BoxSelector(
        (-3, -3, -BOSS_LEN - 0.1), (3, 3, -BOSS_LEN + 0.1), boundingbox=True
    )).chamfer(ENTRY_CHAMFER)
    part = part.edges(cq.selectors.BoxSelector(
        (-4, -4, FLANGE_T - 0.2), (4, 4, FLANGE_T + 0.2), boundingbox=True
    )).fillet(FILLET_R)
    part = part.cut(cq.Workplane("XY", origin=(0, 0, TOP - MARK_CUT))
                    .text(label, MARK_H, MARK_CUT + 0.1, combine=False))
    return part


def add_ears(part, bore_dia, bore_flat):
    """The only new feature: relief at the two flat/arc corners."""
    _, c, hc = corners(bore_dia, bore_flat)
    return part.cut(cq.Workplane("XY", origin=(0, 0, EAR_Z0))
                    .pushPoints([(-hc, c), (hc, c)])
                    .circle(EAR_R).extrude(EAR_LEN))


ROOT = Path(__file__).parent

# Guard rail first: rebuild the shipped part from THIS file's copy of the code
# and check it against the volume of the rung Colin actually held. If this
# fails, the geometry has drifted and every rung below is a different part than
# the one that was validated, so nothing printed from here would mean anything.
ctrl = build_base(3.15, 2.55, "15").val()
assert ctrl.isValid(), "control rung: invalid solid"
assert abs(ctrl.Volume() - CONTROL_VOL) < 0.15, (
    f"control rung is {ctrl.Volume():.1f} mm3 but the validated shipped part is "
    f"{CONTROL_VOL}; the proven geometry has drifted, STOP")
print(f"control: shipped 3.15 geometry reproduces at {ctrl.Volume():.1f} mm3 "
      f"(validated {CONTROL_VOL}) OK\n", flush=True)

for folder, name, bore, flat, label, prior in VARIANTS:
    OUT = ROOT / folder
    OUT.mkdir(exist_ok=True)

    r = bore / 2
    wall = PLUG_AF / 2 - (r + EAR_R)       # conservative: hex apothem, any clocking
    assert wall > MIN_WALL, (
        f"{name}: ear leaves only {wall:.2f}mm of wall to the hex flat")

    base = build_base(bore, flat, label)
    g0 = h.describe(base.val())
    part = add_ears(base, bore, flat)
    s = part.val()
    g1 = h.describe(s)

    # OCCT sometimes returns the input UNCHANGED instead of raising. If the ear
    # cut silently no-opped, this whole print would be four copies of the old
    # part and the experiment would quietly answer the wrong question.
    assert not h.is_noop(h.diff(g0, g1)), f"{name}: ear cut did nothing"
    assert s.isValid(), f"{name}: invalid solid"
    removed = g0["volume_mm3"] - g1["volume_mm3"]
    assert removed > 0, f"{name}: ears added volume instead of removing it"

    bb = s.BoundingBox()
    assert abs(bb.xlen - 11.0) < 0.01 and abs(bb.zlen - TOTAL) < 1e-6, \
        f"{name}: bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f}"

    print(f"{label}  bore {bore} / flat {flat}  vol {s.Volume():.1f} mm3 "
          f"(ears removed {removed:.1f})", flush=True)
    print(f"   surface clearance {bore - SHAFT_DIA:+.2f} round / "
          f"{flat - (SHAFT_DIA - 0.6):+.2f} flat, wall at ear {wall:.2f}mm",
          flush=True)
    print(f"   without ears this rung was: {prior}", flush=True)

    h.export_checked(s, str(OUT / name))
    h.render6(s, str(OUT / f"{name}.png"))

print("DONE", flush=True)
