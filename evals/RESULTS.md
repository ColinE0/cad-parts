# Eval results, 2026-11-14

Two batches on the same day, each in the same three arms, one run per cell:

- **Fable 5.1, medium effort, with the skill**
- **Fable 5.2, high effort, with the skill**
- **Fable 5.2, high effort, no skill**: same venv and pinned packages, but no `cq_helpers` and no runner

Batch 1 ran the six original prompts (evals 1 to 6). Batch 2 ran two harder prompts rebuilt from
failures the skill was written after (evals 8 and 9). A third hard prompt, eval 7, is built but
was not run; see [Eval 7: built, not run](#eval-7-built-not-run).

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

## Isolation

`--safe-mode` disables CLAUDE.md files, skills, installed plugins, hooks and MCP servers. In all
24 runs the session's skill list held only Claude Code's built-in skills, no hook produced an
event, and no MCP server was connected. The session's init event still lists the plugins
installed on the machine, but none of their skills appeared in any run. Safe mode does not
sandbox the filesystem. One no-skill run (batch 1, eval 2) listed and searched folders above its
own while looking for the missing helper library. Nothing was there to find (the skill copy the
other arms used was created after that run finished), and `grade.py` now flags any path a run
touches outside its folder; no batch 2 run touched one. A stricter harness would run each eval
as a separate low-privilege user or in a container, and pass `--include-hook-events` to prove
the hooks stayed off.

Raw transcripts are not published: they contain local paths and folder listings from the machine
the evals ran on.
