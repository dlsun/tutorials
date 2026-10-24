"""Loading of the 117 tutorial experiment data, shared by the two analyses.

This module owns everything that happens before a test statistic is computed:
reading the grade file, keeping the consenting students, rescaling scores to
percentages, and cutting students into pretest blocks. It is shared by

  block_factor_analysis.py  the fixed-effects analysis of the block design,
  randomization_test.py     the randomization test,

so both scripts see exactly the same students, in the same order, under the
same conventions. Neither script re-reads the CSV itself.

Data conventions
----------------
A "data" object is a dict of parallel arrays over the analyzed students:

    data["pretest"]     int   pretest inventory score, 0-12, or -1 if the
                              student never took the pretest
    data["randomize"]   int   1 = treatment, 0 = control
    data["email"]       str   lower-cased email address, the row's identity
    data["Midterm"]     float score as a percentage, NaN if missing
    data["Final"]       float score as a percentage, NaN if missing

plus bookkeeping entries ("n_total_rows", "max_points") that describe the file
the arrays came from. Students without both a pretest score and a Randomize
assignment never enter the arrays.

A missing score is left out of that exam's analysis only: a student with a
Final but no Midterm still counts toward the Final. The two exams are
therefore analyzed on different samples (66 and 64 consenting students).

Consenting students (--include)
-------------------------------
--include takes a CSV naming the students to keep; everyone else in the grade
file is dropped. The file must have

  * one column of email addresses, headed 'Email Address' or 'Email', and
  * one column holding the full name as a single field, headed 'Name'.

Headers are matched case-insensitively, and a header that merely contains the
word ('Student Email', 'Preferred Name') is accepted too; extra columns are
ignored. completed.csv, written by canonicalize_data.py, is the intended
input:

    Email Address,Name
    dsorense@example.edu,Desmond Sorensen
    aoyelow23@example.edu,Arlo Sage Oyelowo

Rows are tied to the grade file by match_rosters.py: first on email address,
then on last name, then on first name, where the first word of 'Name' is the
first name and the remainder is the last name. Only unambiguous matches are
accepted, and any row of the include file that matches nobody is listed in the
report header rather than passed over silently.

Percentages
-----------
Each outcome is rescaled to a percentage before anything else happens,
dividing by the row's own 'Midterm - Max Points' / 'Final - Max Points' entry.
A row whose maximum is blank, unparseable, or zero falls back to the largest
maximum seen elsewhere in the file; if no row carries a usable maximum for an
outcome the run stops rather than guessing. Percentages put the two exams on
one scale -- raw, the final is out of 154 and the midterm out of 101 -- so
effects are reported in percentage points.

Blocks
------
There is one block per realized pretest score: assignment was randomized
within score, so these are the blocks of the design.
"""

import csv
import sys

import numpy as np

import match_rosters

DEFAULT_INPUT = "../Data/canonical/grades-with-pretest.csv"
DEFAULT_INCLUDE = "../Data/canonical/completed.csv"
OUTCOMES = ("Midterm", "Final")

NO_PRETEST = -1  # 'Pretest score' code for a student who never took it


# ---------------------------------------------------------------- parsing ---

def parse_float(value):
    """Return float(value), or NaN for blank / unparseable entries."""
    value = (value or "").strip()
    if not value:
        return np.nan
    try:
        return float(value)
    except ValueError:
        return np.nan


def parse_int(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def nanmean(values):
    """Mean over non-missing entries; NaN if the group is entirely missing."""
    if not np.any(np.isfinite(values)):
        return np.nan
    return float(np.nanmean(values))


# --------------------------------------------------------------- rosters ---

def load_inclusions(path, roster_path):
    """Match an include file against the grade file; see the module docstring.

    The include CSV needs a column of email addresses and a column holding the
    full name in one field. Returns (emails, unmatched), where emails is the
    set of grade-file addresses whose students were matched -- the students to
    keep -- and unmatched describes the include-file rows that matched nobody.
    """
    result = match_rosters.match_files(path, roster_path)
    if result.columns_a.get("email") is None or result.columns_a.get("name") is None:
        sys.exit(f"{path}: --include needs a column of email addresses and a "
                 f"column named 'Name'; found {list(result.rows_a[0])}"
                 if result.rows_a else f"{path}: no rows")
    unmatched = [result.describe_a(i) for i in result.unmatched_a]
    return result.matched_b_emails(), unmatched


# ------------------------------------------------------------------ load ---

def to_percent(scores, maxima, name):
    """Rescale raw scores to percentages of each student's maximum.

    Each row carries its own "<outcome> - Max Points" value; a row missing one
    falls back to the largest maximum seen elsewhere in the file, since a blank
    denominator is a gap in the bookkeeping rather than a different exam. A
    maximum of zero is treated as missing too -- it would divide by zero.
    """
    usable = np.isfinite(maxima) & (maxima > 0)
    if not np.any(usable):
        sys.exit(f"Scores need a usable '{name} - Max Points' column; "
                 f"none of the analyzed rows have a positive value.")
    maxima = np.where(usable, maxima, np.max(maxima[usable]))
    return 100.0 * scores / maxima, np.unique(maxima[usable])


def load_data(path, include):
    """Load the grade file, keeping only the students whose email is in include.

    Returns (data, dropped) where data is a dict of parallel arrays over the
    included students who have both a pretest score and a Randomize
    assignment, and dropped is a dict of counts describing what was left out
    and why. Each outcome is rescaled to a percentage of the maximum in its
    "<outcome> - Max Points" column, and data["max_points"] records the
    denominators used.
    """
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    scores = {name: [] for name in OUTCOMES}
    maxima = {name: [] for name in OUTCOMES}
    pretest, randomize, kept_emails = [], [], []
    dropped = {"not_included": 0, "no_pretest": 0, "no_randomize": 0}

    for row in rows:
        email = (row.get("Email") or "").strip().lower()
        if email not in include:
            dropped["not_included"] += 1
            continue
        score = parse_int(row.get("Pretest score"))
        assignment = parse_int(row.get("Randomize"))
        if score is None:
            dropped["no_pretest"] += 1
            continue
        if assignment is None:
            dropped["no_randomize"] += 1
            continue
        pretest.append(score)
        randomize.append(assignment)
        kept_emails.append(email)
        for name in OUTCOMES:
            scores[name].append(parse_float(row.get(name)))
            maxima[name].append(parse_float(row.get(f"{name} - Max Points")))

    data = {
        "pretest": np.array(pretest, dtype=int),
        "randomize": np.array(randomize, dtype=int),
        "email": np.array(kept_emails, dtype=object),
        "n_total_rows": len(rows),
        "max_points": {},
    }
    for name in OUTCOMES:
        y, used = to_percent(np.array(scores[name], dtype=float),
                             np.array(maxima[name], dtype=float), name)
        data["max_points"][name] = used
        data[name] = y
    return data, dropped


# ---------------------------------------------------------------- blocks ---

def build_blocks(pretest, randomize):
    """One entry per pretest score, ascending: (score, indices, # treated)."""
    blocks = []
    for score in np.unique(pretest):
        idx = np.flatnonzero(pretest == score)
        blocks.append((int(score), idx, int(np.sum(randomize[idx] == 1))))
    return blocks


def print_blocks(pretest, randomize):
    """Print the block table: size, arm counts, and treatment probability."""
    print("\nBlocks (one per pretest score; n, treated, control, P(treated)):")
    for score, idx, n_treated in build_blocks(pretest, randomize):
        print(f"  {score:>8}: n = {len(idx):3d}, treated = {n_treated:3d}, "
              f"control = {len(idx) - n_treated:3d}, "
              f"p = {n_treated / len(idx):.3f}")


# ------------------------------------------------------------------- CLI ---

def add_data_arguments(parser):
    """Add the input options shared by both scripts."""
    parser.add_argument("--input", default=DEFAULT_INPUT, metavar="FILE",
                        help="grade file written by canonicalize_data.py "
                             "(default: %(default)s)")
    parser.add_argument("--include", default=DEFAULT_INCLUDE, metavar="FILE",
                        help="CSV of the consenting students, with an email "
                             "column and a 'Name' column (default: "
                             "%(default)s); matched to the grade file on "
                             "email, then last name, then first name -- see "
                             "data_utils.py")
    parser.add_argument("--latex", metavar="FILE",
                        help="also write the paper's table as a LaTeX tabular "
                             "to FILE")
    return parser


def load_from_args(args):
    """Load the grade file named by args, keeping the included students.

    Returns (data, dropped, unmatched_inclusions). Exits if no student
    survives the filtering.
    """
    include, unmatched_inclusions = load_inclusions(args.include, args.input)
    data, dropped = load_data(args.input, include)
    if len(data["pretest"]) == 0:
        sys.exit("No students with both a pretest score and a Randomize value.")
    return data, dropped, unmatched_inclusions


def print_data_header(data, dropped, args, unmatched_inclusions=()):
    """Print the provenance block: rows read, rows dropped, students kept."""
    n = len(data["pretest"])
    treat = data["randomize"] == 1

    print(f"Rows in file:                      {data['n_total_rows']}"
          f"  ({args.input})")
    print(f"Dropped, not on include list:      {dropped['not_included']}"
          f"  ({args.include})")
    if unmatched_inclusions:
        print(f"  listed but matched no student:    "
              f"{len(unmatched_inclusions)}")
        for entry in unmatched_inclusions:
            print(f"    {entry}")
    print(f"Dropped, no pretest score:         {dropped['no_pretest']}")
    print(f"Dropped, no Randomize assignment:  {dropped['no_randomize']}")
    print(f"Students analyzed:                 {n}")
    print(f"  observed treatment (Randomize=1): {int(np.sum(treat))}")
    print(f"  observed control   (Randomize=0): {int(np.sum(~treat))}")
    n_no_pretest = int(np.sum(data["pretest"] == NO_PRETEST))
    if n_no_pretest:
        print(f"  never took the pretest (score {NO_PRETEST}): {n_no_pretest}")
    for name in OUTCOMES:
        n_scored = int(np.sum(np.isfinite(data[name])))
        print(f"  with a {name} score:{' ' * (19 - len(name))}{n_scored}")
    denominators = ", ".join(
        f"{name} / {'; '.join(f'{m:g}' for m in data['max_points'][name])}"
        for name in OUTCOMES
    )
    print(f"Scores as percentages of:          {denominators}")


# ------------------------------------------------------------ LaTeX tables ---
#
# Each analysis script can write the table the paper prints (--latex FILE):
# one row per exam, floats to 3 significant digits and p-values rounded to the
# nearest 0.001, in the paper's layout.

def format_sig(x, digits=3):
    """x to `digits` significant digits, in fixed-point notation."""
    if x is None or not np.isfinite(x):
        return "--"
    if x == 0:
        return "0"
    rounded = float(f"{x:.{digits}g}")
    decimals = max(0, digits - 1 - int(np.floor(np.log10(abs(rounded)))))
    return latex_minus(f"{rounded:.{decimals}f}")


def format_p(p):
    """A p-value rounded to the nearest 0.001."""
    if p is None or not np.isfinite(p):
        return "--"
    return f"{p:.3f}"


def latex_minus(text):
    return "$-$" + text[1:] if text.startswith("-") else text


def write_latex_table(path, header, rows):
    """Write a tabular in the paper's layout: centered columns between rules.

    The table is also printed, so it lands in the run's log.
    """
    lines = [r"\begin{tabular}{|" + "c|" * len(header) + "}",
             r"\hline",
             " & ".join(header) + r" \\",
             r"\hline\hline"]
    for row in rows:
        lines += [" & ".join(str(cell) for cell in row) + r" \\", r"\hline"]
    lines += [r"\end{tabular}"]
    text = "\n".join(lines) + "\n"
    with open(path, "w") as f:
        f.write(text)
    print(f"\nLaTeX table written to {path}:\n")
    print(text, end="")
