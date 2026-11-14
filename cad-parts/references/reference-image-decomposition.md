# Modeling from a reference image: decompose before you build

Adapted from the vision-decompose skill of the author's earlier, retired Onshape
plugin; the process survives the tool. When the user gives a reference image (drawing with callouts,
iso render, photo, hand sketch) and asks to model it, the first deliverable is
NOT a CadQuery script. It is a structured feature decomposition they can
sanity-check.

Why: vision-to-CAD is the hard step of this loop, not CAD-to-CAD. Skim the
image and jump to scripting and you will misread features (boss vs pocket,
complex pill outline vs rounded rectangle, missed callouts) and burn a long
iteration loop fixing errors 30 seconds of careful looking would have caught.

## Tooling (local replacements for the old MCP image tools)

- **View the image**: Read it directly (native multimodal input).
- **Zoom into small text / dense regions**: crop at native resolution with a
  3-line Pillow script in the scratchpad, then Read the crop:
  ```python
  from PIL import Image
  Image.open(SRC).crop((x1, y1, x2, y2)).save(DST)  # pixel coords
  ```
  Pillow is in C:\cadquery-venv (matplotlib dependency). Crop liberally; a
  crop is cheaper than a wrong dimension. Run crop and measuring scripts
  through the watchdog runner like any other venv script.
- There is no OCR tool anymore: dimensions are read by eye from crops. The
  classic misread still applies: **Ø often looks like 9** (Ø50 vs 950). Any
  9-prefixed value that would be geometrically absurd is almost certainly a
  diameter symbol; crop and re-read it.

## Output format (save as decomposition.md, don't just say it)

Write it next to the reference image (or in the part's folder) with the
image path recorded at the top. It is a handoff artifact: it must survive
context compaction, the user edits it directly, and the build script is written
against the file, not chat scroll-back.

```
## OVERVIEW
One sentence: what IS this part (bracket / plate / flange / housing / ...).

## ENVELOPE
Overall X × Y × Z. Check the title block for units FIRST; US drawings default
to inches: state the native value AND the mm conversion. UNKNOWN if unreadable.

## FEATURE TREE
F1: <short name>
  type: base-plate | boss | through-hole | blind-hole | pocket | slot | fillet |
        chamfer | counterbore | countersink | shell | rib | taper | thread | other
  role: primary | secondary | subtractive | cosmetic
  size: approximate mm
  position: fraction of envelope OR relative to another feature
  face / orientation: which face, which axis
  count: 1 or N (pattern)
  dim_source: drawing_callout | drawing_scaled | render_inferred
              (drawing_scaled = an undimensioned position measured off a
              dimensioned drawing; calibrate px/mm from a callout in THE SAME
              view, since views of one drawing can differ in scale)
  notes: tolerance / finish / anything unusual

## RELATIONSHIPS
Which features cut into which, which are patterned from which. Call out
DERIVED outlines explicitly ("pocket follows the pill silhouette offset 10 mm
inward"): derived outlines are the single biggest class of misread feature.

## UNCERTAINTIES
Everything you'd want the user to confirm before committing to a build.
```

After writing it, check with the user: "does this match what you intended?"
They have more context than the image; let them correct the read before any
script exists. Update the file with their corrections, then build.

## Process

1. **Overview scan.** One sentence: what is this part. No feature list yet.
2. **Count features.** If you count ≤ 3 on a part that fills the frame, you
   are missing some; real parts have 6-12+.
3. **Crop-and-describe each feature**: shape, size (callout if visible, else
   fraction of envelope), position, polarity (additive boss vs subtractive
   pocket, get this right).
4. **Drawings specifically**: title block first (units, and exclude its
   numbers: "Rev D", scale "1:1", years are not dimensions). Callout syntax:
   `Ø25` diameter, `R3` radius, `4X` applies to 4 instances, `M6x1.0` thread.
5. **Cross-check before finalizing**:
   - *Multi-view correlation*: a feature in one view must appear in the other
     views that would show it (silhouette or hidden lines). Visible in only
     one view = suspected misread, goes in UNCERTAINTIES.
   - *Dimensional consistency*: sub-dims sum to the envelope, hole centers
     inside the outline, pattern spacing consistent with count and span.
     Contradictions are LISTED, never silently resolved.
   - *Backside*: iso views hide features; dashed lines are real geometry.
6. **Coverage self-check**: does the tree cover every distinct silhouette
   region? Rescan the full image once before finalizing.

## Build-phase handoff

- Every dim in the FEATURE TREE becomes a named constant in the part script;
  ENVELOPE becomes the bbox assert.
- Mid-build and before declaring done, run
  `h.render_compare(solid, ref_image_path, out_png)` and READ the PNG:
  feature count, placement, and proportion against the reference, side by
  side. A part modeled from an image is not done until this comparison has
  actually been looked at.
