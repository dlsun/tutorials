# Reproducing the analysis from the raw data

This document is the audit trail for the STATS 117 (Spring 2026) tutorial
experiment. It describes where each raw data file comes from, how to confirm
the files are the ones analyzed, and each step that turns them into the
paper's two tables. Every step is a script in this directory, and one command
runs them all:

```sh
cd Code
./run_pipeline.sh 07ee7f0cf184718ec44422bd60c42dcc3d71d6fc98c49b047458e3b928acb913
```

The argument is the expected combined SHA-256 of the raw data (Step 0). The
run stops if the raw files do not match it. Everything the run produces is
written to `Data/canonical/` (derived data) and `Results/` (logs and tables).
Nothing else in the repository is modified.

**In the public repository**, the four raw files in `Data/` are synthetic
stand-ins with the same layout (see `Data/README.md`). The digests in this
document are those of the real files, so they do not match the synthetic ones,
which have their own:

```sh
cd Code
./run_pipeline.sh f599569c7853c10c5a013d8bf385e9b44f4ba8cf2999a79e427e317aaf8f5e3a
```

The counts quoted below (students, consent matches, exam takers) hold for both
the real and the synthetic files.

Requirements: Python 3 with numpy and scipy. The versions used are recorded in
`Results/environment.txt` (the reference run used Python 3.13.2, numpy 2.5.2
and scipy 1.18.0).

## The raw data

Four CSV files, saved to `Data/` exactly as downloaded. **Do not open and
re-save them in Excel, Numbers, or any other spreadsheet program**: that can
rewrite numbers (it drops the leading zero of SIDs, for instance), dates and
line endings, which changes the SHA-256 digest. These files were all downloaded
on September 24, between 12:00 and 16:00 Pacific Time.

| File | Contents | Source |
|---|---|---|
| (a) `raw-sp26-gradescope-grades.csv` | Every grade for the quarter, for every enrolled student | The course's Gradescope gradebook → *Assignments* → *Download Grades* (CSV) |
| (b) `raw-tutorial-assignments.csv` | The students assigned to a tutorial (the treatment group), keyed by Stanford email, with slot and instructor | The tutorial-assignment Google spreadsheet: *File → Download → Comma-separated values* |
| (c) `raw-consent.csv` | Consent-form responses: timestamp, email, printed name, e-signature, date | *Completed* tab of the consent form's Google spreadsheet (the Google Form's responses): *File → Download → Comma-separated values* with that tab selected |
| (d) `raw-pretest-scores.csv` | Pretest inventory scores (0–12), keyed by Stanford email | *Sheet1* of the pretest's Google spreadsheet: *File → Download → Comma-separated values* with that tab selected |

Each of the three Google spreadsheets keeps a full edit history
(*File → Version history → See version history*). The history shows that
none of the responses or assignments were edited after they were collected.
The Gradescope course and the spreadsheets hold student records and are not
public; an auditor who is given access can confirm this and re-download the
files.

A caveat for the Gradescope export: it reflects the course's grades on the
day it is downloaded. A re-download matches byte for byte only while no grade,
regrade, extension or roster change has been made since. The spreadsheets
match as long as their contents are unchanged.

## Step 0: Fingerprint the raw data (`hash_raw_data.py`)

```sh
python3 hash_raw_data.py            # prints per-file digests + combined digest
python3 hash_raw_data.py --check <combined digest>
```

This prints the SHA-256 of each raw file in `shasum -a 256` format, followed
by a *combined* digest: the SHA-256 of those four lines, with the files in the
order (a), (b), (c), (d). The combined digest therefore fixes the contents
of all four files at once, and it can be recomputed with standard tools:

```sh
cd Data
shasum -a 256 raw-sp26-gradescope-grades.csv raw-tutorial-assignments.csv \
    raw-consent.csv raw-pretest-scores.csv | shasum -a 256
```

(`sha256sum` in place of `shasum -a 256` on Linux.) The reference digests are:

```
ac077d0483a4b4ef36be07fc6073e65224df938c658ae7bf2a3226da09d1e727  raw-sp26-gradescope-grades.csv
1c7d7e0cadca32c7c90763e19c0bcdb48324747ac8760828a6ecb0dd0d83f7d5  raw-tutorial-assignments.csv
1d89697dcd90b76c3244997991e135c0b31a9856d09f67df450003931f76693c  raw-consent.csv
a051dea5c5aec15b36c204285a2b3a8b71219e74e7cc85c1f4e697eb9c40686b  raw-pretest-scores.csv
combined SHA-256: 07ee7f0cf184718ec44422bd60c42dcc3d71d6fc98c49b047458e3b928acb913
```

## Step 1: Canonicalize the data (`canonicalize_data.py`)

```sh
python3 canonicalize_data.py --data-dir ../Data --outdir ../Data/canonical
```

This reads the four raw files and writes three derived files. It is
deterministic, with no randomness and no manual edits. Emails are compared
after trimming whitespace and lower-casing. The script stops without writing
anything if a required column is missing, or if an email is blank or repeated
within any one file.

**`grades-with-pretest.csv`** has one row per student in the Gradescope export,
in the export's order, with columns

```
Last Name,First Name,SID,Email,Midterm,Midterm - Max Points,Final,Final - Max Points,Pretest score,Randomize
```

* The first eight columns are copied verbatim from (a).
* `Pretest score` is the `Score` column of (d), joined on email. A student
  with no pretest row gets `-1`, the code the analysis reads as "did not take
  the pretest". Pretest rows whose email is not in Gradescope are listed in
  the log and otherwise ignored.
* `Randomize` is `1` if the student's email appears in (b), meaning they were
  assigned a tutorial (treatment), and `0` otherwise (control).

**`completed.csv`** lists the students who consented, with columns
`Email Address` (their `@stanford.edu` address from Gradescope) and `Name`
(Gradescope first name, then last name). Each row of (c) is one consent.

**A blank `Signature` counts as signed.** Every response on the form counts
as consent, including those whose `Signature` field is empty. Those students
typed their name into *Print Name* on the consent form, along with their
email and the date, and the typed name is taken as their signature.
Because many students typed a personal email or a shortened name on the
form, each response is tied to a Gradescope student in passes. Each pass
accepts a pairing only when exactly one not-yet-matched student carries that
key, so an ambiguous key never forces a match:

1. email address;
2. last name (the first word of the printed name is taken as the first
   name, and the rest as the last name);
3. first name;
4. the full name with case, spaces, hyphens and other non-letters removed
   (so "Ana Sofia Reyes" on the form matches "Ana-Sofia" + "Reyes" in
   Gradescope).

Passes 1–3 are exactly the matching `data_utils.py` applies to an
`--include` file (implemented in `match_rosters.py`). Pass 4 applies only to
responses still unmatched after them. A response that no pass matches is
listed in the log and left out.

**`consent-matches.csv`** is the audit trail for `completed.csv`. It has one
row per consent response: its line in (c), timestamp, the email and name as
typed, the Gradescope student it was matched to, which pass matched it, and
`Signed by`: either `signature`, or `printed name (signature blank)` when the
typed name stands in for the signature.
The log `Results/canonicalize.log` also lists every match not made by
email, so the name-based matches can be checked by eye.

In the reference run, all 66 consent responses match (55 by email, 9 by last
name, 1 by first name, 1 by full name). Six responses have a blank
`Signature` field. As described above, they are counted as consents signed by
printed name, and the log lists them by line.

## Step 2: Analysis

The paper reports two analyses, one script each. Both read
`Data/canonical/grades-with-pretest.csv` and keep only the students matched in
`Data/canonical/completed.csv`, the 66 consenting students. Scores are
percentages of each exam's maximum, so effects are in percentage points. A
student missing an exam is left out of that exam's analysis only, so the
Midterm is analyzed on 66 students and the Final on 64.

Each script writes the corresponding table of the paper, with the paper's
columns and layout: one row per exam, floats to three significant digits and
p-values rounded to the nearest 0.001.

### 2a. Fixed-effects analysis of the block design (`block_factor_analysis.py`)

```sh
python3 block_factor_analysis.py --input ../Data/canonical/grades-with-pretest.csv \
    --include ../Data/canonical/completed.csv \
    --latex ../Results/factor-table.tex
```

This fits the paper's linear model of a randomized block design by ordinary
least squares, with one indicator for treatment and one for each pretest score
in $\{-1, 0, \ldots, 12\}$. Each score is a block, since assignment was
randomized within score. This is the additive two-way ANOVA model
`outcome ~ Treatment + factor(Block)`, and the t-test on the treatment
coefficient is the ANOVA F-test for treatment adjusted for blocks
($F = t^2$), made one-sided. The module docstring has the details. Table
columns:

| Column | Meaning |
|---|---|
| `$n$` | consenting students with a score on that exam |
| `$\what{\tau}$ (pp)` | OLS coefficient on treatment |
| `std.\ error (pp)` | classical (homoskedastic) OLS standard error |
| t-score | $\hat\tau / \mathrm{SE}$ |
| `$p$-value` | one-sided p-value from $t_{n-B-1}$, $B$ the number of blocks present |
| `95\% lower $\tau$ (pp)` | $\hat\tau - t_{n-B-1,\,0.95}\,\mathrm{SE}$ |

This step is deterministic.

### 2b. Randomization test (`randomization_test.py`)

```sh
python3 randomization_test.py --input ../Data/canonical/grades-with-pretest.csv \
    --include ../Data/canonical/completed.csv -N 1000000 \
    --latex ../Results/randomization-table.tex
```

Students are re-randomized 1,000,000 times within their pretest-score blocks,
holding each block's number of treated students fixed (seed 0), and the
observed difference in means is compared with its distribution over the
re-randomizations. The test is then inverted to give the lower confidence
bound: the smallest $\tau$ for which
$H_\tau\colon Y_i(1) \le Y_i(0) + \tau$ for every $i$ survives at level 0.05.
The module docstring has the details. Table columns:

| Column | Meaning |
|---|---|
| `$n$` | consenting students with a score on that exam |
| Tutorial mean | observed mean score of the treated students |
| Control mean | observed mean score of the control students |
| `$\what{\tau}$ (pp)` | their difference |
| `$p$-value` | one-sided p-value of the test of no effect, $(k + 1) / (N + 1)$, where $k$ of the $N$ re-randomized differences are at least the observed one |
| `95\% lower $\tau$ (pp)` | the smallest $\tau$ at which $H_\tau$ is not rejected |

The p-value and the bound are Monte Carlo quantities. With the seed fixed,
they are exactly reproducible on the same inputs and the same numpy version.
They also depend on the row order of the input file, which Step 1 fixes to the
Gradescope export's order.

## Outputs of a run

| File | Contents |
|---|---|
| `Results/environment.txt` | Python / numpy / scipy versions |
| `Results/raw-sha256.txt` | Step 0 digests (and the check result) |
| `Results/canonicalize.log` | Step 1 counts, non-email matches, warnings |
| `Results/factor.log`, `Results/factor-table.tex` | Step 2a full report and table |
| `Results/randomization.log`, `Results/randomization-table.tex` | Step 2b full report and table |
| `Results/output-sha256.txt` | digests of the three derived CSVs and the two tables |

Two runs on the same raw data and software versions produce identical files.
`Results/output-sha256.txt` confirms this quickly.
