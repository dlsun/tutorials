# Synthetic data

**None of the students in these files exist.** The real data behind the
experiment are student records (grades, consent forms and survey answers) and
are not public. The four raw files here are invented stand-ins for them:

| File | Stands in for |
|---|---|
| `raw-sp26-gradescope-grades.csv` | the Gradescope gradebook export: 105 students, every assignment |
| `raw-tutorial-assignments.csv` | the tutorial-assignment sheet: the 44 treated students |
| `raw-consent.csv` | the consent form's 66 responses |
| `raw-pretest-scores.csv` | the 69 pretest scores, 2 of them for students not in Gradescope |

They are built to match the real exports in structure: file names, columns,
quoting, line endings, value formats, and every count the documentation quotes.
The pipeline therefore runs on them exactly as it does on the real files, and
each irregularity the code handles appears in them. Examples include consent
responses typed with a personal email or a differently spelled name, blank
signatures, students who never took the pretest, and students who missed one
exam or both.

Everything else is invented: names, emails (at the reserved domains
`example.edu` and `example.com`), SIDs, scores, timestamps, survey answers,
tutorial instructors and rooms. No name, email address or SID of a real
student appears in them. The scores were drawn from a simple model in which
tutorials raise every treated student's score by 10 percentage points on each
exam. Results computed from these files say nothing about the real
experiment.

`canonical/` holds what Step 1 of the pipeline derives from the raw files.

As with the real exports, do not open and re-save the CSVs in a spreadsheet
program: that rewrites them and changes their digests.
