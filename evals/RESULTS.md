# Eval results, 2026-11-14

Six prompts (`evals.json`, inputs in `eval-assets/`), three arms, one run per cell:

- **Fable 5.1, medium effort, with the skill**
- **Fable 5.2, high effort, with the skill**
- **Fable 5.2, high effort, no skill**: same venv and pinned packages, but no `cq_helpers` and no runner

Every run was headless Claude Code 2.1.325 (`claude -p --safe-mode`, no session persistence, web
tools off) in its own fresh folder, inside a job object with a 12 GB cap. The user prompt was the
eval prompt verbatim. Parts were measured by `harness/grade.py`; process items come from each
run's transcript. Before these runs, the eval 6 input (`runaway.py`) had its docstring cut back:
it used to state the expected answer, which would have leaked the rubric to the no-skill arm.

## Scorecard

| | 5.1 medium + skill | 5.2 high + skill | 5.2 high, no skill |
|---|---|---|---|
| Part geometry right, measured (evals 1 to 5) | 5/5 | 5/5 | 5/5 |
| Input files byte-identical afterwards | 6/6 | 6/6 | 6/6 |
| CadQuery processes run with no memory cap | 0 | 0 | 13 |
| CadQuery runs through the capped runner | 15 | 11 | n/a |
| STL checked watertight before hand-off (evals 1 to 5) | 5/5 | 5/5 | 2/5 |
| Render made and opened (evals 1 to 5) | 5/5 | 5/5 | 1/5 |
| Eval 5: feature decomposition written before the script | yes | yes | no |
| Eval 6: cap kill diagnosed without raising the cap | yes | yes | no |
| Questions and assumptions written down | 5/6 | 6/6 | 3/6 |
| Searched outside its own folder | 0/6 | 0/6 | 1/6 |
| Tokens, all six (cache reads included) | 2.15 M | 2.23 M | 1.08 M |
| Cost at API list prices, all six | $6.18 | $7.28 | $3.46 |
| Wall time, all six | 11.8 min | 12.7 min | 8.2 min |

## Per eval

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

## What this shows, and what it does not

On six small parts, Fable 5.2 at high effort gets the geometry right with no help at all. The
skill does not make the model smarter at these. It makes the process safe and checkable: no CAD
process ever ran without a memory cap, every part went through the watertight gate and a render
that was actually opened, a part from a drawing started with a written plan, and a memory kill got
the right reflex. That costs about twice the tokens and about half again the wall time.

These evals are too easy to show the failures the skill was built from. The next set should be
those failures: a non-uniform scale of an imported STEP (the machine-killer), a part with a
floating island that passes every fit check, and a dependent part whose parent STEP moved on.

An earlier run on 2026-10-05 (skill only, one model) also passed all six.

## Isolation

`--safe-mode` kept personal CLAUDE.md files, skills, plugins and hooks out of every run (checked:
no hook events, no personal skills in the session's skill list). It does not sandbox the
filesystem. One no-skill run (eval 2) listed and searched folders above its own while looking for
the missing helper library. Nothing was there to find (the skill copy the other arms used was
created after that run finished), and `grade.py` now flags any path a run touches outside its
folder. A stricter harness would run each eval as a separate low-privilege user or in a container.

Raw transcripts are not published: they contain local paths and folder listings from the machine
the evals ran on.
