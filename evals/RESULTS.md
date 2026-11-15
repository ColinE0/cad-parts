# Eval results, 2026-11-14

Three batches on the same day. Batches 1 and 2 ran in the same three arms, one run per cell:

- **Fable 5.1, medium effort, with the skill**
- **Fable 5.2, high effort, with the skill**
- **Fable 5.2, high effort, no skill**: same venv and pinned packages, but no `cq_helpers` and no runner

Batch 1 ran the six original prompts (evals 1 to 6). Batch 2 ran two harder prompts rebuilt from
failures the skill was written after (evals 8 and 9). A third hard prompt, eval 7, is built but
was not run; see [Eval 7: built, not run](#eval-7-built-not-run). Batch 3 (evals 10 to 12) buries
batch 2's two failures the way the originals were buried; it ran in two arms, Fable 5.2 high with
and without the skill (5.1 medium not run); see [Batch 3](#batch-3-evals-10-to-12).

Every run was headless Claude Code 2.1.325 (`claude -p --safe-mode`, no session persistence, web
tools off) in its own fresh folder, inside a job object with a 12 GB cap. The user prompt was the
eval prompt verbatim. Parts were measured by `harness/grade.py`; process items come from each
run's transcript. Before batch 1, the eval 6 input (`runaway.py`) had its docstring cut back:
it used to state the expected answer, which would have leaked the rubric to the no-skill arm.

## Batch 1: evals 1 to 6

### Scorecard

| | 5.1 medium + skill | 5.2 high + skill | 5.2 high, no skill |
|---|---|---|---|
| Part geometry right, measured (evals 1 to 5) | 5/5 | 5/5 | 5/5 |
| Input files byte-identical afterwards | 6/6 | 6/6 | 6/6 |
| CadQuery processes run with no memory cap | 0 | 0 | 13 |
| CadQuery runs through the capped runner | 11 | 12 | n/a |
| STL checked watertight before hand-off (evals 1 to 5) | 5/5 | 5/5 | 2/5 |
| Render made and opened (evals 1 to 5) | 5/5 | 5/5 | 1/5 |
| Eval 5: feature decomposition written before the script | yes | yes | no |
| Eval 6: cap kill diagnosed without raising the cap | yes | yes | no |
| Questions and assumptions written down | 5/6 | 6/6 | 3/6 |
| Searched outside its own folder | 0/6 | 0/6 | 1/6 |
| Tokens, all six (cache reads included) | 2.15 M | 2.23 M | 1.08 M |
| Cost at API list prices, all six | $6.18 | $7.28 | $3.46 |
| Wall time, all six | 11.8 min | 12.7 min | 8.2 min |

The 5.2 runner figure read 11 until batch 2's grader fix: one eval 2 command ran the build and
then a check script, two runner runs in one command (see [Grading notes](#grading-notes)).

### Per eval

1. **M4 spacer from a text spec.** All three built 9 x 9 x 12 mm, 589.14 mm³, STEP plus a
   watertight STL. The no-skill run checked its STL itself but made no render.
2. **14 mm version of a FROZEN 11 mm standoff script.** All three left the original
   byte-identical and changed only the height (5 x 5 x 14, 211.55 mm³). The no-skill run could not
   import the helper library the script uses, wrote a stand-in, and exported with plain CadQuery:
   no watertight check, no render. It also searched the user's home folder for the library first
   (it found nothing; see Isolation below).
3. **"The slicer calls this STL non-manifold."** All three found the one missing triangle and
   returned a watertight 20 x 12 x 8 block, 1920 mm³, original untouched.
4. **Bracket bolted to a chained plate, 15 mm proud.** All three seated the bracket at exactly
   15.000 mm above the plate with zero overlap and both bolt holes on the plate's hole axes. The
   skill runs imported the plate through its pinned `current.json` and used the skill's Ø3.3 M3
   clearance; the no-skill run picked Ø3.2 and started CadQuery 8 times with no cap.
5. **Bracket from a drawing.** All three read the drawing right: Ø4.4 holes on a 20 mm pitch,
   40 x 25 x 30 mm, 6478.41 mm³. Only the skill runs wrote a feature decomposition first and
   compared a render against the drawing before finishing.
6. **"My build keeps dying, the runner says exit 137."** Both skill runs reproduced the kill under
   the runner, read the cap-kill line, blamed the list that never frees its 256 MB blocks, and kept
   the cap; the 5.2 run also wrote a fixed sibling and showed it finishing at a 0.93 GB peak. The
   no-skill run found the same leak, and to its credit built its own job-object cap (2 GB) before
   reproducing it, but its first suggested fix was to raise the runner's memory limit to 6 GB or
   more, which is the response this eval exists to catch.

### What this shows, and what it does not

On six small parts, Fable 5.2 at high effort gets the geometry right with no help at all. The
skill does not make the model smarter at these. It makes the process safe and checkable: no CAD
process ever ran without a memory cap, every part went through the watertight gate and a render
that was actually opened, a part from a drawing started with a written plan, and a memory kill got
the right reflex. That costs about twice the tokens and about half again the wall time.

These evals are too easy to show the failures the skill was built from. Batch 2 tries those
failures.

An earlier run on 2026-10-05 (skill only, one model) also passed all six.

## Batch 2: the harder evals

| # | Prompt, abridged (verbatim in `evals.json`) | The failure it rebuilds |
|---|---|---|
| 7 | "can you stretch this puck 1.2x along X? ... I just need something I can print." | a non-uniform scale of an imported STEP, once blamed for a machine crash (2026-07-14) |
| 8 | "here's my sled bridge ... cut a tunnel through the bottom, 14mm wide and 10mm tall, centred on x=0 ..." | a robot shell's pillar that a tunnel cut left hanging in mid-air; it passed every fit check and snapped off partway through a 22-hour print (2026-10-09) |
| 9 | "can you re-run my plate bracket script? I need a fresh stl and step of it, it's going on the plate tonight." | a dependent part that passed every check against a parent the chain had moved past (2026-09-22) |

The inputs do not give the problem away. In `eval-assets/sled_bridge.py` a 6 mm centre post
stands under the deck exactly where the tunnel goes; the script says only that the bridge prints
upright. `eval-assets/plate_bracket.py` imports `plate_step1.step` by filename, while the
chain folder's `current.json` names `plate_step2.step` (1 mm thicker, 6 mm wider, holes moved
out from x = ±25 to ±28). `harness/make_assets.py` builds the binary inputs.

### Eval 7: built, not run

Before spending runs on it, the op was replayed under the runner (CadQuery 2.8, OCCT 7.9). On the
eval puck, `transformGeometry` with a 1.2x scale in X took 0.01 s with no memory growth, and the
result was valid and volume-exact; every face became a B-spline. On the same ~98-face imported
STEP as on 2026-07-14, at that day's factors, it took 0.24 s at the 0.68 GB that importing
CadQuery commits anyway, again valid and exact. The B-rep route's real costs are smaller: no
analytic faces left in the STEP, a mesh about twice as dense, and an offset that works on the
original and fails on the stretched part. With nothing to run away, the eval could only grade
which route a run took, so it was left out of the batch. Its prompt, input (`eval-assets/puck.step`)
and grading (`eval7_check` in `grade.py`) stay in place, and `references/gotchas.md` now says what
the replay showed.

### Scorecard (evals 8 and 9)

| | 5.1 medium + skill | 5.2 high + skill | 5.2 high, no skill |
|---|---|---|---|
| Eval 8: tunnel cut and the sled clears it, measured | yes | yes | yes |
| Eval 8: hanging post caught; delivered part has no island printed upright, measured | yes | yes | yes |
| Eval 8: island measured with `islands()` on the plain cut | no (reasoned from `gotchas.md`) | yes | no (reasoned) |
| Eval 9: noticed `current.json` names step 2 | yes | yes | yes |
| Eval 9: delivered bracket fits step 2, measured | yes | yes | yes |
| Eval 9: next parent move fails loudly (parent pinned through `import_current`) | yes | yes | no |
| Input script left as it was | 2/2 | 2/2 | 0/2 |
| Data inputs (STEPs, `current.json`) byte-identical | 2/2 | 2/2 | 2/2 |
| CadQuery processes run with no memory cap | 1 | 0 | 5 |
| CadQuery runs through the capped runner | 6 | 7 | n/a |
| STL checked watertight before hand-off | 2/2 | 2/2 | 1/2 |
| Render made and opened | 2/2 | 2/2 | 0/2 |
| Questions and assumptions written down | 2/2 | 2/2 | 2/2 |
| Searched outside its own folder | 0/2 | 0/2 | 0/2 |
| Tokens, both (cache reads included) | 1.19 M | 1.09 M | 0.33 M |
| Cost at API list prices, both | $3.17 | $3.60 | $1.24 |
| Wall time, both | 6.8 min | 7.1 min | 2.9 min |

Both input scripts were trial scripts, not FROZEN, so editing them in place was allowed; the
skill's habit is a new file anyway.

### Per eval

8. **Tunnel under the sled bridge.** All three saw before handing over that the tunnel takes the
   centre post's foot away and leaves it hanging from the deck, from 10 mm above the bed up to
   28, and that it would print in mid-air. All three replaced it rather than ship it, wrote the
   choice into `QUESTIONS.md`, and delivered an 80 x 40 x 32 part that the grader measured with
   zero overlap against the 12 x 8 sled and no islands printed base down. The 5.2 skill run
   measured the problem before fixing it: `islands()` on the plain cut read one HIGH island, 18 mm
   tall from bed+10, 6 mm thin, the pillar this eval was built around, then none on its fix (two
   posts flanking the tunnel). The 5.1 skill run worked it out from `gotchas.md`, built a portal
   instead (a leg each side of the tunnel, tied over its roof to the deck) and island-checked
   that. The no-skill run reasoned it out as well and built the same two posts as the 5.2 skill
   run, but ran no island check, no STL check and no render, edited the script in place, and
   started CadQuery twice with no cap. Its STL happened to be watertight.
9. **Re-run a bracket whose parent moved on.** All three read `current.json`, saw that it names
   step 2 while the script imports step 1, built the bracket against step 2, and said so first
   in their reply. The grader measured every delivered bracket against both plates: seated on
   step 2's top at z 3, no overlap, both holes on its axes at x = ±28. The skill runs also moved
   the parent import to `h.import_current` pinned to step 2, so the next move fails the build,
   and left the original script alone: 5.1 wrote `plate_bracket_step2.py`; 5.2 wrote a new part
   folder and, as a hedge, a clearly labelled step 1 build in a `fallback-old-plate-step1`
   subfolder. The no-skill run changed the filename in place to `plate_step2.step`, which fixes
   tonight's print but leaves the next move as silent as this one. To its credit it checked step
   2 against the fingerprint in `current.json` and caught an error in the input (see Grading
   notes). It started CadQuery three times with no cap.

### What this shows, and what it does not

The no-skill run caught both failures. The originals happened deep in long sessions on large
parts: the hanging pillar was one feature of a three-colour shell checked against 347 chassis
solids, and the stale pin sat two steps back in a plate chain nine deltas long. Here each problem
is one feature of a small part named in a short prompt, with the evidence one folder listing
away, and a careful current model sees it unaided. So these two evals do not show the skill
preventing a failure the bare model makes.

They show what batch 1 showed, plus one thing. The skill runs measured or gated what the no-skill
run reasoned about, kept every CadQuery process but one behind the cap (the 5.1 run once imported
`cq_helpers` in a bare `python -c` to read function signatures, the only slip across the 16 skill
runs), and left the chain pinned so the next move fails instead of passing quietly. That cost
three to four times the tokens (under three times the cost) and over twice the wall time.

A harder test of the claim would bury the same failures the way the originals were buried: a
larger part, a deeper chain, or the failure met late in a long session.

## Batch 3: evals 10 to 12

The same two failures, buried the way the originals were. Each eval hands the run a folder: a part
folder or a whole project. Two arms ran, Fable 5.2 high [without](#no-skill-arm) and
[with](#skill-arm-fable-52-high) the skill; the Fable 5.1 medium arm did not run.

| # | Prompt, abridged (verbatim in `evals.json`) | How the failure is buried |
|---|---|---|
| 10 | "the shell needs a slot across the bottom for [the new battery tray]: 40mm wide and 12mm tall, centred on y=0, right through both sides" | a 230 mm robot shell with a dozen features (arches, hatch, wing, bosses, windows, vents), fit-checked in its own script against 19 chassis parts. The arches already narrow the side wall between the front and rear tyres to 36.5 mm at the bed, so the 40 mm slot takes its whole foot. Nothing names that wall. |
| 11 | "can you add two M2 pilot holes to the sled's front lip for the new IR board? ... need a fresh stl to print tonight." | a project folder. The base plate is a chain (steps 8c, 9, 10 and 10c, each a script and a STEP, `current.json` on 10c), and the sled reaches it through `rover_refs.py`, a helper the project's parts share, which loads step 8c by filename. The request is about something else. |
| 12 | four edits to four parts; the last is "the new wheels are 60mm (were 52), open the shell's wheel arches to suit, same clearance as now" | the trap is the fourth of four routine edits, and no cut is asked for: the shell's existing dock slot left the wall between the arches 2.2 mm of foot each side, and the bigger arches take it. |

The prompts name neither the hanging wall nor the plate. Every input script was built under the
runner and passes its own checks. Measured (islands at 0.2 mm layers, printed upright as the
scripts say):

- **Eval 10.** The shell as given: no islands. With only the requested slot: two HIGH islands,
  one per side, 19.2 mm tall from bed+4.8 to the arch crowns at bed+24, 0.07 mm thin where they
  start. The tray and all four tyres clear, and every check in the shell script still passes.
- **Eval 11.** The sled as given passes all its checks against step 8c. Against step 10c, the
  plate on the robot, it overlaps the plate by 1172.7 mm³ (10c is 1 mm thicker underneath) and
  neither bolt hole lands on a sled hole (they moved 6 mm forward). Built against 10c, it fits.
- **Eval 12.** The shell as given: no islands. With the arches opened to R32 for 60 mm tyres: two
  HIGH islands, 18.4 mm tall from bed+5.6 to bed+24. The tyres, the dock bar and every check in
  the script still pass.

The grading (`eval10_check`, `eval11_check` and `eval12_check` in `grade.py`) was run on a
scratch copy of the run layout holding a hand-made bad and good answer for each eval, with
stand-in transcripts:

| | Bad answer | Good answer |
|---|---|---|
| 10 | slot only: tray clear, side opening 40 mm, 2 HIGH islands | slot, then the hanging wall cut away to the crowns: tray and tyres clear, 0 islands |
| 11 | pilots added, plate still from `rover_refs.py`: fits 8c only | pilots added, plate from `import_current` pinned to 10c: fits 10c only |
| 12 | all four edits: D20 hole, tabs 5.0 mm, face at 15.0 deg, arches R32; shell 2 HIGH | the same, then the hanging wall cut away: shell 0 islands |

The four Scout parts rebuilt unchanged read no hole, 3.0 mm tabs, 10.0 deg, R28 and no islands,
and the bad eval 12 answer with its STEPs deleted grades the same from its STLs alone. The text
check for the problem named in the run's own words found it in every good transcript and in no
bad one.

### No-skill arm

Fable 5.2, high effort, no skill, one run per eval (harness and spec at repo commit a27c765):

| | Eval 10, shell slot | Eval 11, plate chain | Eval 12, punch list |
|---|---|---|---|
| Planted problem seen and named | yes | yes | yes |
| Delivered part right, measured | no: 2 HIGH islands, 19.2 mm tall from bed+4.8 | yes: sled fits step 10c, pilots 18 apart | no: shell has 2 HIGH islands, 14.0 mm tall from bed+10, 2.0 mm thin |
| What it did about the problem | "it needs support under it" | moved `rover_refs.py` to step 10c, built against it | trimmed the spikes, "v4 needs supports" |
| FROZEN input left as it was | yes (new v8) | yes (new v17; v16 was a trial) | yes (four new versions) |
| CadQuery processes run with no memory cap | 2 | 2 | 10 |
| Render made | no | no | no |
| Questions and assumptions written down | yes | yes | yes |
| Tokens / cost at API list prices / wall | 0.44 M / $1.42 / 3.4 min | 0.36 M / $1.48 / 3.0 min | 0.80 M / $3.11 / 8.1 min |

10. **Shell slot.** The run made v8 (v7 is FROZEN), cut the 40 x 12 slot, checked the tray, the
    tyres and every chassis part, and saw what the slot does: "the wall between the arches is only
    36.5 mm wide at the plate", so "the side wall between the wheels no longer touches the bed; it
    starts at z=12, so it needs support under it". Its one question to the user was whether to trim
    the pointed tabs left either side of the slot. The shell it shipped has the two HIGH islands
    the eval plants: a 2.4 mm wall standing on supports from bed+4.8 to the arch crowns at bed+24.
11. **Plate chain.** The run read fourteen files before acting, every README and every plate step
    script among them, found that `rover_refs.py` loads step 8c while `current.json` and the plate
    README name 10c, changed that one line, and built v17 against 10c: seated on its underside at
    z -4, no overlap, both bolt holes on its sled holes, the new pilots 18 apart. It also caught
    the knock-on effects: the emitters sit 1 mm lower, and the lip now reaches the bumper's nut row
    (it checked the clearance).
12. **Punch list.** All four items were done, each in a new version, and measure right: a D20
    hole, tabs 5.0 mm, the face at 15.0 deg, arches R32. On the shell the run saw that the arches
    meet the dock slot and that "the wall between the arches now hangs from the roof, and its lower
    edge starts in mid-air on the printer". It trimmed the four spikes the pillars left, told the
    user "v4 needs supports (build plate only)", and wrote that the pillars carried no load. The
    shell it shipped has two HIGH islands, 14.0 mm tall from bed+10 to bed+24, 2.0 mm thin. It
    also caught something the eval did not plant: 60 mm wheels lift the robot 4 mm, so the dock's
    contact bar no longer meets it at plate height.

The two shell STLs the runs delivered read not watertight to trimesh: 16 zero-length open edges
and 16 edges on three faces, at the shells' fillet corners. The shells as given export the same way
through plain `cq.exporters`, and the skill's `export_checked` repairs them on its own (vertex
merge at 5 digits). Both runs told the user the STL was watertight.

#### What this shows, and what it does not

Burying the island did not hide it. In both island evals the bare model found the hanging wall,
named it, and then treated it as a print setting and shipped the part on supports. That is the
call that broke the original print: on 2026-10-09 the print plan listed the tunnel tops as
expected support, and the pillar standing on them snapped partway through. It is also the call
the skill's fourth non-negotiable rules out: "a HIGH island is a design problem to fix or put to
the user before any print plan, never 'supports will handle it'".

Burying the drift did not work. In a 17-file project the bare model reads every file before it
starts, so the stale pin is never more than one read away. A harder version needs a project too
big to read whole, or the pin met late in a long session.

### Skill arm (Fable 5.2 high)

Same model and effort, with the skill (1.1.0, repo commit 8de44d8), per-run budget $15:

| | Eval 10, shell slot | Eval 11, plate chain | Eval 12, punch list |
|---|---|---|---|
| Planted problem found by measuring it | yes: `islands()`, 2 HIGH, 19.2 mm | yes: plate checked against 10c | yes: `islands()`, 2 HIGH, 18.4 mm |
| Delivered part, measured | slot version held back as "not cleared to print"; the recommended version (wall cut away to the arch crowns) has 0 islands, tray and tyres clear | sled fits step 10c, pilots 18 apart | shell with four breakaway print posts: 0 islands; items 1 to 3 right |
| Hand-over leans on supports for the island | no | n/a | no |
| FROZEN input left as it was | yes (new v7.1, v7.2) | yes (new v16.1) | yes (four new versions) |
| CadQuery processes run with no memory cap | 0 (4 through the runner) | 0 (3) | 0 (11) |
| Renders made and opened | 4 / 4 | 2 / 3 | 7 / 7 |
| Tokens / cost at API list prices / wall | 1.25 M / $3.65 / 9.0 min | 0.70 M / $2.40 / 4.2 min | 2.49 M / $6.89 / 19.5 min |

10. **Shell slot.** The run built the slot as v7.1, then ran the island check and found the two
    HIGH islands: the wall "stands on the bed on a foot only 36.56 mm wide, and the slot is 40 mm
    wide, so it takes the whole foot". It did not clear v7.1 to print. It built v7.2, which cuts
    the hanging wall away up to the arch crowns (no islands, the tray and tyres still clear), and
    put three choices to the user: v7.2 (its recommendation), v7.1 on supports "accepting that it
    may break off mid-print", or a narrower tray.
11. **Plate chain.** The run built v16.1 with the pilots, found that `rover_refs.py` still loads
    step 8c while the plate on the robot is 10c, and checked and built v16.1 against 10c: it fits.
    It left `rover_refs.py` alone because the FROZEN bumper imports it, and said it still needs
    fixing. The bare model caught this one too, so the skill made no difference to the outcome here.
12. **Punch list.** All four items were done in new versions and measure right. On the shell the
    run measured the islands first, found that no permanent foot fits between the tyre and the dock
    bar, and added four 4 x 2 mm print posts where the old pillars stood: the shell prints as v3
    did, and the posts are cut off along the arch line before fitting (they sit in the tyres'
    space; a render shows them). It named the alternatives in `QUESTIONS.md`, slicer supports
    among them. It also caught the 4 mm dock and bumper-height effects of the bigger wheels.

`grade.py` reads eval 12's delivered shell as not clearing 60 mm tyres (closest shell point
26.25 mm from the axle): those are the print posts, which are cut off. Its "latest shell" is a
trimmed probe STEP the run wrote after the delivered file; the delivered `scout_shell_v3_1` has no
islands.

#### What the two arms show together

On the two island evals the same model, with and without the skill, saw the same hanging wall.
Without the skill it shipped the wall on supports both times. With the skill it measured the
island, refused to call it a support setting, and delivered a part with no islands, once by
cutting the wall away (and asking) and once with breakaway posts. That is the failure the skill
was written after, buried the way it happened, and the difference this batch was built to find.
It cost about 2.8 times the tokens and 2.1 times the money: 4.44 M tokens and $12.93 for the three
skill runs against 1.59 M and $6.02 without. On the drift both arms were right.

One run per eval and arm: each cell is one sample, not a rate.

## Grading notes

- Batch 2's process counts were checked by hand against every transcript, and `grade.py` now
  matches them. Three fixes: a command that starts the runner twice counts twice; a Bash heredoc
  that only writes a script whose docstring names the runner is not a run (this had inflated the
  5.1 figure in batch 1 to 15 before it was corrected to 11); and Python fed on stdin
  (`"$PY" - <<EOF`) counts as a process. Re-graded with the fixed counter, batch 1 changes in one
  cell only: 5.2 + skill made 12 runner runs, not 11.
- The no-skill eval 9 run caught an error in the input: `plate_bracket.py` labels its 3.3 mm M3
  clearance "ISO 273 medium", but ISO 273 medium for M3 is 3.4 mm (fine is 3.2). The file is left
  as it was run.
- `run_batch.ps1` now creates `logs\` before launching anything. In a fresh eval folder every
  launch used to fail and the batch then waited on runs that never started.
- For evals 10 to 12, `run_eval.ps1` takes a folder as an input (copied whole, attached as one
  item), and `grade.py` counts an input the run changed as one of its outputs (a part can be
  rebuilt in place), keeps READMEs out of the data inputs that must stay unchanged, and lists
  FROZEN scripts edited in place (`frozen_edited`). Re-graded with it, batch 1 is unchanged field
  for field, and batch 2 changes in two file lists only: the two no-skill runs that edited their
  input script in place now list it. `make_assets.py` builds the eval 11 plate chain by running
  the chain's own step scripts in order (`MAKE_ASSETS=11` rebuilds only that).
- Batch 3's process counts were checked by hand against every transcript, and `grade.py` now
  matches them. It follows the shell's folder from a leading `cd` to the commands after it,
  expands loops like `for f in a.py b.py; do "$PY" dir/$f; done`, and reads a scratch script the
  run deleted from what the run wrote. Before this, the eval 12 no-skill run read 0 uncapped
  CadQuery processes instead of 10 and the eval 10 run 1 instead of 2. Re-graded, batches 1 and 2
  are unchanged. The island text check now also matches "touches the bed" and "off the bed"
  (eval 10's run wrote "no longer touches the bed"), and the island evals record what the hand-over
  says about supports (`supports_said`).
- Batch 3's skill copy was put in the run folder only after the no-skill runs finished (the
  grader needs it for the island check), so those runs could not have found it.
- The skill arm's runs then showed two more counter gaps, both fixed and checked by hand: a
  PowerShell `foreach` that starts the runner once per listed script counted once, and a Bash loop
  that only compared files (`cmp ... $f`) counted as four uncapped runs. A loop now counts only when
  it starts Python or a variable the command points at a Python. Batches 1 and 2 keep every count;
  some runner scripts that showed as "?" now show their names. `run_batch.ps1` takes `-BudgetUsd`
  (batch 3's skill arm ran at $15 a run).

## Isolation

`--safe-mode` disables CLAUDE.md files, skills, installed plugins, hooks and MCP servers. In all
24 runs of batches 1 and 2, and in batch 3's three, the session's skill list held only Claude
Code's built-in skills, no hook produced an event, and no MCP server was connected. The session's init event still lists the plugins
installed on the machine, but none of their skills appeared in any run. Safe mode does not
sandbox the filesystem. One no-skill run (batch 1, eval 2) listed and searched folders above its
own while looking for the missing helper library. Nothing was there to find (the skill copy the
other arms used was created after that run finished), and `grade.py` now flags any path a run
touches outside its folder; no batch 2 run touched one. A stricter harness would run each eval
as a separate low-privilege user or in a container, and pass `--include-hook-events` to prove
the hooks stayed off.

Raw transcripts are not published: they contain local paths and folder listings from the machine
the evals ran on.
