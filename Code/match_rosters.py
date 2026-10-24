"""Match a name/email roster (CSV_A) against the merged grade file (CSV_B).

CSV_A has one column of email addresses and one column holding a full name;
CSV_B splits the name across 'Last Name' and 'First Name' and has its own
'Email' column. Column names are found case-insensitively, so 'Email Address'
or 'Email', and 'Name' or 'Student Name', are all recognized.

Matching proceeds in three passes, each restricted to rows still unmatched:

  1. email address
  2. last name  (CSV_A's name splits as: first word = first name, rest = last)
  3. first name

Within a pass a candidate is accepted only if exactly one still-unmatched row
in CSV_B carries that key, so a shared last name never forces an arbitrary
pairing; such rows fall through to the next pass or stay unmatched.

canonicalize_data.py uses it to tie consent responses to Gradescope students,
and data_utils.py to apply an --include file:

    from match_rosters import match_files, match_rows

    result = match_files("completed.csv", "grades-with-pretest.csv")
    result.matched_b_emails()     # emails in CSV_B that were matched
    result.unmatched_a            # indices of the CSV_A rows that matched nothing
    result.matches                # list of Match(index_a, index_b, how)
"""

import csv
from collections import defaultdict
from dataclasses import dataclass, field

# Header names looked for in each file, best candidate first. Matching is
# case-insensitive: an exact match wins, otherwise the first header containing
# the candidate as a substring is used.
A_EMAIL_HEADERS = ("email address", "email", "e-mail")
A_NAME_HEADERS = ("name", "full name", "student name")
B_EMAIL_HEADERS = ("email", "email address", "e-mail")
B_LAST_HEADERS = ("last name", "last", "surname")
B_FIRST_HEADERS = ("first name", "first", "given name")

# The passes, in order: (record key, human-readable label).
PASSES = (("email", "email"), ("last", "last name"), ("first", "first name"))


def norm(value):
    return (value or "").strip().lower()


def split_name(full_name):
    """First word is the first name; everything after it is the last name."""
    parts = (full_name or "").split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def find_column(fieldnames, candidates, forbid=()):
    """Return the header best matching candidates, or None.

    Exact (case-insensitive) matches take priority over substring matches, and
    candidates are tried in the order given. Headers containing any string in
    forbid are never returned -- that is what keeps a bare 'name' lookup from
    latching onto 'Last Name'.
    """
    headers = [h for h in (fieldnames or []) if h is not None]
    allowed = [h for h in headers
               if not any(bad in norm(h) for bad in forbid)]
    for candidate in candidates:
        for header in allowed:
            if norm(header) == candidate:
                return header
    for candidate in candidates:
        for header in allowed:
            if candidate in norm(header):
                return header
    return None


def read_rows(path):
    """Read a CSV into a list of dicts, tolerating a UTF-8 byte-order mark."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


@dataclass
class Match:
    """One accepted pairing, and which pass accepted it."""
    index_a: int
    index_b: int
    how: str


@dataclass
class MatchResult:
    rows_a: list
    rows_b: list
    matches: list
    unmatched_a: list  # indices into rows_a
    columns_a: dict = field(default_factory=dict)
    columns_b: dict = field(default_factory=dict)

    def matched_b_emails(self):
        """Lower-cased emails of the CSV_B rows that were matched."""
        col = self.columns_b.get("email")
        if col is None:
            return set()
        return {norm(self.rows_b[m.index_b].get(col)) for m in self.matches
                if norm(self.rows_b[m.index_b].get(col))}

    def describe_a(self, i):
        row = self.rows_a[i]
        name = (row.get(self.columns_a.get("name"), "") or "").strip()
        email = (row.get(self.columns_a.get("email"), "") or "").strip()
        return f"{name} <{email}>" if email else name


def match_rows(rows_a, rows_b, fieldnames_a=None, fieldnames_b=None):
    """Match rows_a against rows_b; see the module docstring for the scheme.

    rows_a and rows_b are lists of dicts (as from csv.DictReader). The column
    names are inferred from fieldnames_* when given, otherwise from the keys of
    the first row. Returns a MatchResult.
    """
    fieldnames_a = fieldnames_a or (list(rows_a[0]) if rows_a else [])
    fieldnames_b = fieldnames_b or (list(rows_b[0]) if rows_b else [])

    columns_a = {
        "email": find_column(fieldnames_a, A_EMAIL_HEADERS),
        # Forbid 'first'/'last' so a file carrying both styles of name column
        # still resolves 'Name' correctly.
        "name": find_column(fieldnames_a, A_NAME_HEADERS,
                            forbid=("first", "last")),
    }
    columns_b = {
        "email": find_column(fieldnames_b, B_EMAIL_HEADERS),
        "last": find_column(fieldnames_b, B_LAST_HEADERS, forbid=("first",)),
        "first": find_column(fieldnames_b, B_FIRST_HEADERS, forbid=("last",)),
    }

    a_records = []
    for i, row in enumerate(rows_a):
        first, last = split_name(row.get(columns_a["name"], ""))
        a_records.append({
            "i": i,
            "email": norm(row.get(columns_a["email"], "")),
            "first": norm(first),
            "last": norm(last),
        })

    b_records = [{
        "j": j,
        "email": norm(row.get(columns_b["email"], "")),
        "first": norm(row.get(columns_b["first"], "")),
        "last": norm(row.get(columns_b["last"], "")),
    } for j, row in enumerate(rows_b)]

    matches = []
    matched_a, matched_b = set(), set()

    for key, label in PASSES:
        # Index the still-unmatched CSV_B rows by this pass's key.
        index = defaultdict(list)
        for b in b_records:
            if b["j"] not in matched_b and b[key]:
                index[b[key]].append(b["j"])

        for a in a_records:
            if a["i"] in matched_a or not a[key]:
                continue
            candidates = [j for j in index.get(a[key], []) if j not in matched_b]
            if len(candidates) == 1:  # ambiguity is left to a later pass
                matches.append(Match(a["i"], candidates[0], label))
                matched_a.add(a["i"])
                matched_b.add(candidates[0])

    return MatchResult(
        rows_a=rows_a,
        rows_b=rows_b,
        matches=matches,
        unmatched_a=[a["i"] for a in a_records if a["i"] not in matched_a],
        columns_a=columns_a,
        columns_b=columns_b,
    )


def match_files(path_a, path_b):
    """Read both CSVs and match them; returns a MatchResult."""
    rows_a, fields_a = read_rows(path_a)
    rows_b, fields_b = read_rows(path_b)
    return match_rows(rows_a, rows_b, fields_a, fields_b)
