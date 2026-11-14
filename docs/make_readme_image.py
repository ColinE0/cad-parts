r"""Draws docs/island-check.png, the picture at the top of the README: eval 8's sled bridge with
the tunnel cut straight through it. The cut passes the fit check (the sled clears), and
cq_helpers.islands() still finds the centre post it leaves hanging from the deck, printed upright.
The third panel is the grounded fix two of the three eval runs built: two posts flanking the tunnel.
Every number in the captions comes from the helpers, not from this file.

Run it through the runner with a venv that has the pinned packages (cq_helpers comes from this repo):
    & ..\cad-parts\scripts\run_watchdogged.ps1 -Script make_readme_image.py -Python <venv>\Scripts\python.exe
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cad-parts" / "venv-modules"))

import cadquery as cq  # noqa: E402
import cq_helpers as h  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

OUT = HERE / "island-check.png"

# eval 8's bridge, same constants as evals/eval-assets/sled_bridge.py
L, W, H, BASE_T, WALL_T, DECK_T, POST = 80.0, 40.0, 32.0, 3.0, 5.0, 4.0, 6.0
TUN_W, TUN_H = 14.0, 10.0        # the tunnel the eval prompt asks for, from the bed up
SLED_W, SLED_H = 12.0, 8.0       # the sled that has to drive through, on the table
FIX_X = 10.0                     # the fix: posts at x = +-10, inner faces on the tunnel walls

GREY, RED, GREEN, BED = "#9aa3ad", "#d62728", "#2ca02c", "#e4e6ea"
VIEW = (640, 380)
FRAME = (-50, 50, -35, 35, -1, 33)


def box(dx, dy, dz, x=0.0, y=0.0, z=0.0):
    return cq.Workplane("XY").box(dx, dy, dz, centered=(True, True, False)).translate((x, y, z))


def bridge(post_xs):
    wall = box(WALL_T, W, H)
    part = (box(L, W, BASE_T)
            .union(wall.translate((-(L - WALL_T) / 2, 0, 0))).union(wall.translate(((L - WALL_T) / 2, 0, 0)))
            .union(box(L, W, DECK_T, z=H - DECK_T)))
    for x in post_xs:
        part = part.union(box(POST, POST, H - DECK_T - BASE_T, x=x, z=BASE_T))
    return part.cut(box(TUN_W, W + 2, TUN_H))


cut = bridge([0.0])
fix = bridge([-FIX_X, FIX_X])
sled = box(SLED_W, W + 20, SLED_H)
bed = box(L + 20, W + 30, 0.8, z=-0.8)
for s in (cut, fix):
    assert s.val().isValid()

fit = h.interference(cut.val(), sled.val())
assert not fit["intersects"], fit
isl = h.islands(cut, up="+z")
assert len(isl) == 1 and isl[0]["risk"] == "HIGH", isl
i = isl[0]
x, y, _ = i["at_xyz"]
w = i["min_width_mm"]
region = box(2 * w, 2 * w, i["z1"] - i["z0"], x=x, y=y, z=i["z0"])   # the bed is at z 0
hang, rest = cut.intersect(region), cut.cut(region)
assert abs(hang.val().Volume() - POST * POST * (i["z1"] - i["z0"])) < 1e-6, "region is not just the post"
assert not h.islands(fix, up="+z"), "the fix still has an island"
assert not h.interference(fix.val(), sled.val())["intersects"]


def panel(items, elev, azim):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "v.png"
        h.render_views(items, str(p), [("", elev, azim)], size=VIEW, frame=FRAME)
        return Image.open(p).convert("RGB")


iso, front = (22, -58), (0, -90)
imgs = [panel([(rest, GREY), (hang, RED), (sled, GREEN), (bed, BED)], *iso),
        panel([(rest, GREY), (hang, RED), (sled, GREEN), (bed, BED)], *front),
        panel([(fix, GREY), (sled, GREEN), (bed, BED)], *iso)]
heads = ["Tunnel cut: the sled clears, every fit check passes",
         f"Printed upright, the post starts {i['z0']:g} mm above the bed",
         "The fix: two posts on the base, islands() reads clean"]


def font(name, size):
    try:
        return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
    except OSError:
        return ImageFont.load_default()


title_f, head_f, mono_f = font("segoeuib.ttf", 30), font("segoeui.ttf", 21), font("consola.ttf", 19)
pad, top, headh, foot = 24, 70, 40, 92
Wc, Hc = 3 * VIEW[0] + 4 * pad, top + headh + VIEW[1] + foot
canvas = Image.new("RGB", (Wc, Hc), "white")
dr = ImageDraw.Draw(canvas)
dr.text((Wc / 2, top / 2 + 4), 'Fit checks ask "does it fit". islands() asks "can it be built bottom-up".',
        fill="#1f2328", font=title_f, anchor="mm")
for k, (img, head) in enumerate(zip(imgs, heads)):
    x0 = pad + k * (VIEW[0] + pad)
    dr.text((x0 + VIEW[0] / 2, top + headh / 2), head, fill="#1f2328", font=head_f, anchor="mm")
    canvas.paste(img, (x0, top + headh))
y0 = top + headh + VIEW[1] + 18
lines = [f"interference(cut, sled): {fit['volume_mm3']:.3f} mm3 overlap",
         f"islands(cut, up=\"+z\"): {i['risk']}, {i['height']:g} mm tall from bed+{i['z0']:g} to the deck at "
         f"bed+{i['z1']:g}, {i['min_width_mm']:g} mm thin    islands(fix): none"]
for n, line in enumerate(lines):
    dr.text((pad, y0 + n * 30), line, fill="#1f2328" if n else "#57606a", font=mono_f)
sw, step = 16, 120
lx = Wc - pad - 3 * step + 30
for n, (col, lab) in enumerate([(GREY, "part"), (RED, "island"), (GREEN, "sled")]):
    dr.rectangle([lx + n * step, y0 + 3, lx + n * step + sw, y0 + 3 + sw], fill=col)
    dr.text((lx + n * step + sw + 8, y0 - 1), lab, fill="#1f2328", font=head_f)
canvas.save(OUT, optimize=True)
print(f"{OUT} {canvas.size[0]} x {canvas.size[1]}", flush=True)
print("DONE", flush=True)
