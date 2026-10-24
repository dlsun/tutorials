#!/usr/bin/env python3
"""Build the analysis inputs of the 117 tutorial experiment from the raw CSVs.

This is step 1 of the audit pipeline (see PIPELINE.md). It reads the four raw
exports, unchanged from how they were downloaded,

  raw-sp26-gradescope-grades.csv   every Gradescope grade for the quarter
  raw-tutorial-assignments.csv     students assigned to a tutorial, by email
  raw-consent.csv                  the consent form's responses
  raw-pretest-scores.csv           the pretest inventory scores, by email

and writes the two files that block_factor_analysis.py and
randomization_test.py read, plus an audit trail:

grades-with-pretest.csv
    One row per student in the Gradescope export, in the export's order, with
    columns

        Last Name, First Name, SID, Email, Midterm, Midterm - Max Points,
        Final, Final - Max Points, Pretest score, Randomize

    The first eight are copied verbatim (as strings) from the Gradescope
    export. 'Pretest score' is the 'Score' column of the pretest file, joined
    on email address; a student with no pretest row gets -1, the code
    data_utils.py reads as "never took the pretest". 'Randomize' is 1 if the
    student's email appears in the tutorial assignments (treatment) and 0
    otherwise (control). Emails are compared after stripping whitespace and
    lower-casing.

completed.csv
    One row per consent-form response that can be tied to a Gradescope
    student, in the order of the form. Every response on the form counts as
    consent. That includes responses whose 'Signature' field is blank: those
    students typed their name into 'Print Name' (and their email and the date)
    on the consent form, and the typed name is taken as their signature.
    The file has columns 'Email Address' (the student's
    @stanford.edu address from Gradescope) and 'Name' (Gradescope first
    name, then last name). Responses are tied to Gradescope with the
    matching data_utils.py applies to an --include file (match_rosters.py):
    email, then last name, then first name, each accepted only when unique.
    Responses still unmatched after those passes go through one more pass,
    on the full name with case, spaces, hyphens and other non-letters removed
    ("Ana Sofia Reyes" and "Ana-Sofia" + "Reyes" agree), again accepted only
    when exactly one unmatched student carries that name. Anything left over
    is reported, not guessed at.

consent-matches.csv
    The audit trail for completed.csv: for each consent response, its row
    number, timestamp, the email and name as typed on the form, the Gradescope
    student it was matched to (if any), the pass that matched it, and whether
    the consent was signed in the 'Signature' field or, that field being
    blank, by the printed name.

Nothing is written unless every check passes: each input must carry the
columns it is read for, and no email may appear twice in any one file.

Usage:
    python3 canonicalize_data.py [--data-dir DIR] [--outdir DIR]
"""

import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict

import match_rosters

RAW_GRADES = "raw-sp26-gradescope-grades.csv"
RAW_TUTORIALS = "raw-tutorial-assignments.csv"
RAW_CONSENT = "raw-consent.csv"
RAW_PRETEST = "raw-pretest-scores.csv"

GRADE_COLUMNS = ("Last Name", "First Name", "SID", "Email", "Midterm",
                 "Midterm - Max Points", "Final", "Final - Max Points")
OUTPUT_COLUMNS = GRADE_COLUMNS + ("Pretest score", "Randomize")
NO_PRETEST = "-1"

# How a consent response was signed, for consent-matches.csv. A blank
# 'Signature' is accepted: the printed name stands in for the signature.
SIGNED = "signature"
SIGNED_BY_NAME = "printed name (signature blank)"

FULL_NAME_PASS = "full name"


def norm_email(value):
    return (value or "").strip().lower()


def compact_name(value):
    """Lower-cased letters only: 'Ana-Sofia Reyes' and 'ana sofia reyes' agree."""
    return re.sub(r"[^a-z]", "", (value or "").lower())


def read_csv(path, required):
    """Rows and header of a raw CSV, stopping if a required column is absent."""
    rows, fieldnames = match_rosters.read_rows(path)
    missing = [c for c in required if c not in (fieldnames or [])]
    if missing:
        sys.exit(f"{path}: missing column(s) {missing}; found {fieldnames}")
    return rows, fieldnames


def email_index(rows, column, path):
    """{email: row}, stopping on a blank or repeated address."""
    index = {}
    for i, row in enumerate(rows, start=2):   # line 1 is the header
        email = norm_email(row.get(column))
        if not email:
            sys.exit(f"{path}, line {i}: blank '{column}'")
        if email in index:
            sys.exit(f"{path}, line {i}: '{email}' appears more than once")
        index[email] = row
    return index


# ------------------------------------------------------------ the grade file --

def build_grades(grades, pretest, tutorials):
    """Rows of grades-with-pretest.csv, in Gradescope order."""
    out = []
    for row in grades:
        email = norm_email(row["Email"])
        record = {col: row[col] for col in GRADE_COLUMNS}
        if email in pretest:
            score = pretest[email]["Score"].strip()
            if not re.fullmatch(r"-?\d+", score):
                sys.exit(f"{RAW_PRETEST}: score '{score}' for {email} is not "
                         f"an integer")
            record["Pretest score"] = score
        else:
            record["Pretest score"] = NO_PRETEST
        record["Randomize"] = "1" if email in tutorials else "0"
        out.append(record)
    return out


# --------------------------------------------------------- the consent file --

def match_consent(consent, grades, grade_fields):
    """Tie each consent response to a Gradescope row.

    Returns {consent index: (grade index, pass name)}. The first three passes
    are exactly match_rosters.match_rows, the matching data_utils.py applies to
    --include files; the last is the compact full-name pass described in the
    module docstring.
    """
    rows_a = [{"Email Address": r["Email Address"], "Name": r["Print Name"]}
              for r in consent]
    result = match_rosters.match_rows(rows_a, grades,
                                      ["Email Address", "Name"], grade_fields)
    matched = {m.index_a: (m.index_b, m.how) for m in result.matches}

    taken = {j for j, _ in matched.values()}
    by_name = defaultdict(list)
    for j, row in enumerate(grades):
        if j not in taken:
            key = compact_name(f"{row['First Name']} {row['Last Name']}")
            if key:
                by_name[key].append(j)
    for i in result.unmatched_a:
        candidates = [j for j in by_name.get(compact_name(consent[i]["Print Name"]), [])
                      if j not in taken]
        if len(candidates) == 1:
            matched[i] = (candidates[0], FULL_NAME_PASS)
            taken.add(candidates[0])
    return matched


def full_name(row):
    return " ".join(p for p in (row["First Name"].strip(),
                                row["Last Name"].strip()) if p)


# ------------------------------------------------------------------ output ---

def write_csv(path, columns, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default="../Data",
                        help="directory holding the raw CSVs "
                             "(default: %(default)s)")
    parser.add_argument("--outdir", default="../Data/canonical",
                        help="directory to write the derived CSVs to "
                             "(default: %(default)s)")
    args = parser.parse_args(argv)

    def raw(name):
        return os.path.join(args.data_dir, name)

    grades, grade_fields = read_csv(raw(RAW_GRADES), GRADE_COLUMNS)
    tutorial_rows, _ = read_csv(raw(RAW_TUTORIALS), ("Email",))
    consent, _ = read_csv(raw(RAW_CONSENT),
                          ("Timestamp", "Email Address", "Print Name",
                           "Signature"))
    pretest_rows, _ = read_csv(raw(RAW_PRETEST), ("Email Address", "Score"))

    grade_index = email_index(grades, "Email", RAW_GRADES)
    tutorials = email_index(tutorial_rows, "Email", RAW_TUTORIALS)
    pretest = email_index(pretest_rows, "Email Address", RAW_PRETEST)
    email_index(consent, "Email Address", RAW_CONSENT)

    print("=" * 78)
    print("Step 1: canonicalize the raw data")
    print("=" * 78)
    print(f"Gradescope students:               {len(grades)}  ({RAW_GRADES})")
    print(f"Tutorial assignments:              {len(tutorials)}  "
          f"({RAW_TUTORIALS})")
    print(f"Pretest scores:                    {len(pretest)}  ({RAW_PRETEST})")
    print(f"Consent responses:                 {len(consent)}  ({RAW_CONSENT})")

    # A tutorial or pretest email that is not in Gradescope cannot enter the
    # grade file; list them so the omission is visible.
    for label, index in (("tutorial", tutorials), ("pretest", pretest)):
        stray = sorted(e for e in index if e not in grade_index)
        print(f"{label.capitalize()} emails not in Gradescope: "
              f"{' ' * (14 - len(label))}{len(stray)}")
        for email in stray:
            print(f"    {email}")

    rows = build_grades(grades, pretest, tutorials)
    counts = Counter(r["Randomize"] for r in rows)
    n_no_pretest = sum(r["Pretest score"] == NO_PRETEST for r in rows)
    print(f"\ngrades-with-pretest.csv:           {len(rows)} rows  "
          f"(Randomize=1: {counts['1']}, Randomize=0: {counts['0']}, "
          f"no pretest: {n_no_pretest})")

    matched = match_consent(consent, grades, grade_fields)
    blank_signature = [i for i, r in enumerate(consent)
                       if not r["Signature"].strip()]
    passes = Counter(how for _, how in matched.values())
    print(f"completed.csv:                     {len(matched)} of "
          f"{len(consent)} consent responses matched  ("
          + ", ".join(f"{how}: {n}" for how, n in passes.items()) + ")")
    for i, (j, how) in sorted(matched.items()):
        if how != "email":
            print(f"    [{how:>10}]  form: {consent[i]['Print Name'].strip()} "
                  f"<{consent[i]['Email Address'].strip()}>  ->  "
                  f"{full_name(grades[j])} <{grades[j]['Email'].strip()}>")
    unmatched = [i for i in range(len(consent)) if i not in matched]
    print(f"Consent responses left unmatched:  {len(unmatched)}")
    for i in unmatched:
        print(f"    line {i + 2}: {consent[i]['Print Name'].strip()} "
              f"<{consent[i]['Email Address'].strip()}>")
    if blank_signature:
        print(f"Consent responses signed by printed name only (blank "
              f"'Signature', accepted as consent): {len(blank_signature)}  "
              f"({', '.join(f'line {i + 2}' for i in blank_signature)})")

    completed = [{"Email Address": grades[j]["Email"].strip(),
                  "Name": full_name(grades[j])}
                 for i, (j, _) in sorted(matched.items())]
    audit = []
    for i, row in enumerate(consent):
        j, how = matched.get(i, (None, "unmatched"))
        audit.append({
            "Form line": i + 2,
            "Timestamp": row["Timestamp"],
            "Form email": row["Email Address"].strip(),
            "Form name": row["Print Name"].strip(),
            "Matched email": grades[j]["Email"].strip() if j is not None else "",
            "Matched name": full_name(grades[j]) if j is not None else "",
            "Matched by": how,
            "Signed by": SIGNED if row["Signature"].strip() else SIGNED_BY_NAME,
        })

    os.makedirs(args.outdir, exist_ok=True)
    outputs = (
        ("grades-with-pretest.csv", OUTPUT_COLUMNS, rows),
        ("completed.csv", ("Email Address", "Name"), completed),
        ("consent-matches.csv", tuple(audit[0]) if audit else (), audit),
    )
    print()
    for name, columns, data in outputs:
        path = os.path.join(args.outdir, name)
        write_csv(path, columns, data)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
