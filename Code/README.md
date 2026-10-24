# Explanation of code

`run_pipeline.sh` runs the whole analysis, from the raw Gradescope and Google
Sheets exports to the paper's two tables. `PIPELINE.md` documents each step
and the provenance of every raw file.

| Script | Step | What it does |
|---|---|---|
| `hash_raw_data.py` | 0 | SHA-256 of each raw file, and a combined digest to check them against |
| `canonicalize_data.py` | 1 | joins the four raw exports into `grades-with-pretest.csv` (exam scores, pretest score and assignment for every student) and `completed.csv` (the consenting students) |
| `block_factor_analysis.py` | 2a | the fixed-effects analysis of the randomized block design |
| `randomization_test.py` | 2b | the randomization test and its lower confidence bound |
| `data_utils.py` | | loading shared by the two analyses: the consenting students, scores as percentages, the pretest blocks, the LaTeX tables |
| `match_rosters.py` | | ties a roster of names and emails to the Gradescope students; used by steps 1 and 2 |

Both analyses use the 66 consenting students. Scores are percentages of each
exam's maximum, and a student missing an exam is left out of that exam's
analysis only, so the Midterm is analyzed on 66 students and the Final on 64.
Each script writes the paper's table with `--latex FILE`, and each runs with
no arguments from this directory, reading the files in `../Data/canonical/`.
The module docstrings (`python3 <script> --help`) have the details.

## Fixed-effects analysis

For student $i$, let $W_i$ be the treatment assignment, $X_i \in \{-1, 0,
\ldots, 12\}$ the pretest score ($-1$: did not take the pretest), and $Y_i$
the exam score. Assignment was randomized within pretest score, so each score
is a block, and `block_factor_analysis.py` fits

```math
Y_i = \tau \, 1\{W_i = 1\} + \sum_{k=-1}^{12} \beta_k \, 1\{X_i = k\} + \varepsilon_i
```

by ordinary least squares. It reports $\hat\tau$, its classical standard
error, the one-sided t-test of $\tau \le 0$ on $n - B - 1$ degrees of freedom
($B$ the number of blocks present), and the 95% lower confidence bound
$\hat\tau - t_{0.95}\,\mathrm{SE}$. This is the additive two-way ANOVA model,
and the t-test is the ANOVA F-test for treatment adjusted for blocks
($F = t^2$), made one-sided.

## Randomization test

`randomization_test.py` re-randomizes the treatment 1,000,000 times within
each pretest score, holding the number treated in each block fixed, and
compares the observed difference in means with its distribution over the
re-randomizations. That gives a one-sided p-value for the null that the
tutorials helped no one, $Y_i(1) \le Y_i(0)$ for every $i$. It then inverts
the test over shifts $\tau$ and reports the smallest $\tau$ at which

```math
H_\tau: Y_i(1) \le Y_i(0) + \tau \text{ for every } i
```

survives at level 0.05, a 95% lower confidence bound on the effect. The
re-randomizations are drawn once, with seed 0, and reused for every $\tau$.
