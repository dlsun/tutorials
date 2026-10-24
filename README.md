# Small-group tutorials: analysis code

Code for the analysis in *What's Old Is New: Improved Learning from Small-Group
Tutorials*, a randomized experiment run in STATS 117 at Stanford in Spring 2026.
It takes the raw course exports through to the paper's two tables.

**The data in this repository are synthetic.** The real data are student
records (grades, consent forms and survey answers) and are not public. `Data/`
holds invented stand-ins with the same file names, columns and formatting as
the real exports, so that the code can be run and checked; see
[`Data/README.md`](Data/README.md). Everything in `Data/canonical/` and
`Results/` was computed from them and says nothing about the real experiment.

## Quick start

Python 3 with the packages in `requirements.txt`:

```sh
pip install -r requirements.txt
cd Code
./run_pipeline.sh f599569c7853c10c5a013d8bf385e9b44f4ba8cf2999a79e427e317aaf8f5e3a
```

The argument is the combined SHA-256 of the four raw files in `Data/`, and the
run stops if they do not match it. A run takes a minute or two, most of it
spent on the 1,000,000 draws of the randomization test. It rewrites
`Data/canonical/` and `Results/` and touches nothing else.

## The analyses

The paper reports two analyses of the consenting students, each done by one
script that writes the paper's table, with the paper's columns:

| Script | Analysis | Table |
|---|---|---|
| `Code/block_factor_analysis.py` | fixed-effects analysis of the randomized block design: least squares of the exam score on treatment and one indicator per pretest score | `Results/factor-table.tex` |
| `Code/randomization_test.py` | randomization test within pretest-score blocks, inverted to give a lower confidence bound on the effect | `Results/randomization-table.tex` |

[`Code/README.md`](Code/README.md) describes the scripts, and
[`Code/PIPELINE.md`](Code/PIPELINE.md) every step from the raw files to the
tables.

## Checking a run

With the package versions in `requirements.txt`, a run reproduces the
committed outputs byte for byte, so after it

```sh
git status --short -- ../Data ../Results
```

prints nothing. `Results/output-sha256.txt` lists the digest of each output.
Other versions of numpy can change the Monte Carlo results of the
randomization test.

The synthetic data also have a known answer: tutorials raise every treated
student's score by 10 percentage points on each exam. With 66 students the
estimates are noisy, and this draw is an unlucky one. The estimates come out at
3.6 to 5.1 points, and every 95% lower confidence bound falls just below 0,
well below the true effect of 10.

## Running on the real data

An auditor who has been given the real exports places them in `Data/`,
replacing the synthetic files, and runs the pipeline with the real data's
digest, which is also printed in the paper's supplementary material:

```sh
cd Code
./run_pipeline.sh 07ee7f0cf184718ec44422bd60c42dcc3d71d6fc98c49b047458e3b928acb913
```

`Code/PIPELINE.md` is the audit trail. It describes where each raw file comes
from, gives the digest of each, and explains each step from the raw files to
the tables.

## Layout

| Path | Contents |
|---|---|
| `Code/` | the scripts; [`Code/README.md`](Code/README.md) describes each one |
| `Code/run_pipeline.sh` | the full pipeline, from raw files to tables |
| `Code/PIPELINE.md` | the audit trail |
| `Data/` | the synthetic raw files, and `canonical/`, what the pipeline derives from them |
| `Results/` | the pipeline's outputs on the synthetic data |
