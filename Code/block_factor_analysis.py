#!/usr/bin/env python3
"""Fixed-effects analysis of the randomized block design (117 tutorials).

This is the first of the paper's two analyses (the section "Fixed-effects
analysis of a randomized block design"). The companion script
randomization_test.py is the second, and data_utils.py holds the loading and
conventions the two share.

For student i, let W_i in {0, 1} be the treatment assignment, X_i in
{-1, 0, ..., 12} the pretest score (-1: did not take the pretest), and Y_i the
score on the exam being analyzed, as a percentage. Assignment was randomized
within pretest score, so each score is a block, and the paper fits the
standard linear model of a randomized block design,

    Y_i = tau * 1{W_i = 1} + sum_k beta_k * 1{X_i = k} + eps_i,

by ordinary least squares, with eps_i i.i.d. N(0, sigma^2). This is the
additive two-way ANOVA model outcome ~ Treatment + factor(Block), and tau is
the treatment effect. The estimate and its classical standard error are

    tau_hat     = sum_k w_k (mean_1k - mean_0k),
                  w_k proportional to n_1k n_0k / n_k,
    SE^2        = sigma_hat^2 / sum_i (W_i - Wbar_(X_i))^2,
    sigma_hat^2 = RSS / (n - B - 1),

where n_1k and n_0k count the treated and control students in block k with a
score on that exam, n_k = n_1k + n_0k, Wbar_k is the treated fraction of block
k, and B is the number of blocks holding a score. The test refers
t = tau_hat / SE to a t distribution on n - B - 1 degrees of freedom, against
H0: tau <= 0, and the one-sided lower confidence bound is
tau_hat - t_(n-B-1, 1-alpha) * SE. The t-test is the ANOVA F-test for
Treatment adjusted for blocks, made one-sided: F = t^2 on 1 and n - B - 1
degrees of freedom.

A block with only treated or only control students is kept in the fit -- it
helps estimate sigma^2 -- but gets zero weight in tau_hat. The classical SE
assumes a common error variance in both arms and every block.

The analysis is deterministic.

Usage:
    python3 block_factor_analysis.py [--input FILE] [--include FILE]
                                     [--alpha A] [--latex FILE]

--latex FILE writes the paper's table as a LaTeX tabular, one row per exam,
with columns

  Outcome                  the exam
  $n$                      consenting students with a score on that exam
  $\\what{\\tau}$ (pp)       tau_hat, in percentage points
  std.\\ error (pp)         its classical standard error
  t-score                  tau_hat / SE
  $p$-value                one-sided p-value from t_(n-B-1)
  95\\% lower $\\tau$ (pp)   the one-sided lower confidence bound at --alpha
"""

import argparse

import numpy as np
from scipy import stats

import data_utils as du
from data_utils import OUTCOMES


def factor_analysis(data, alpha=0.05):
    """OLS fit of outcome ~ Treatment + factor(Block), Block = pretest score.

    Classical (homoskedastic) standard error for the Treatment coefficient
    tau, with a one-sided t-test against H0: tau <= 0 on n - B - 1 degrees of
    freedom, B the number of blocks present among non-missing scores.
    """
    pretest, treat = data["pretest"], data["randomize"] == 1
    out = {}
    for name in OUTCOMES:
        y = data[name]
        finite = np.isfinite(y)
        yf, tf, bf = y[finite], treat[finite].astype(float), pretest[finite]
        blocks = np.unique(bf)
        n, n_blocks = len(yf), len(blocks)
        df = n - n_blocks - 1
        result = {"n_used": n, "n_blocks": n_blocks,
                  "n_informative": 0, "tau": np.nan, "se": np.nan,
                  "t": np.nan, "df": float(df), "p_one_sided": np.nan,
                  "lower_bound": np.nan, "sigma": np.nan}
        # Treatment column first, then one indicator per block (no intercept).
        X = np.column_stack([tf, (bf[:, None] == blocks[None, :])
                             .astype(float)])
        # Within-block variation in treatment; zero in single-arm blocks.
        t_within = tf - (X[:, 1:] @ (X[:, 1:].T @ tf / X[:, 1:].sum(axis=0)))
        sxx = float(t_within @ t_within)
        result["n_informative"] = int(sum(
            0 < tf[bf == b].sum() < np.sum(bf == b) for b in blocks))
        if df < 1 or sxx <= 1e-12:
            out[name] = result
            continue
        coef = np.linalg.lstsq(X, yf, rcond=None)[0]
        resid = yf - X @ coef
        sigma2 = float(resid @ resid) / df
        tau = float(coef[0])
        se = float(np.sqrt(sigma2 / sxx))
        t = tau / se if se > 0 else np.nan
        result.update({
            "tau": tau,
            "se": se,
            "t": float(t),
            "p_one_sided": float(stats.t.sf(t, df)),
            "lower_bound": float(tau - stats.t.ppf(1 - alpha, df) * se),
            "sigma": float(np.sqrt(sigma2)),
        })
        out[name] = result
    return out


# ------------------------------------------------------------- reporting ---

def report(data, dropped, args, unmatched_inclusions, factor):
    print("=" * 78)
    print("Fixed-effects analysis of the randomized block design")
    print("=" * 78)
    du.print_data_header(data, dropped, args, unmatched_inclusions)
    print(f"Confidence level:                  {1 - args.alpha:.0%} "
          f"(alpha = {args.alpha}, one-sided)")
    print("Hypothesis:  H0: tau <= 0   H1: the tutorials raised scores")
    du.print_blocks(data["pretest"], data["randomize"])

    alpha = args.alpha
    print("\nOLS: outcome ~ Treatment + factor(pretest score), classical SE")
    print(f"  {'outcome':<8}{'blocks':>7}{'mixed':>7}{'n':>5}{'tau_hat':>10}"
          f"{'SE':>9}{'t':>8}{'df':>6}{'p (1-sided)':>13}{'sigma_hat':>11}"
          f"{f'{1 - alpha:.0%} lower':>12}")
    print(f"  {'-' * 88}")
    for name in OUTCOMES:
        r = factor[name]
        print(f"  {name:<8}{r['n_blocks']:>7}{r['n_informative']:>7}"
              f"{r['n_used']:>5}{r['tau']:>10.4f}{r['se']:>9.4f}"
              f"{r['t']:>8.3f}{r['df']:>6.0f}{r['p_one_sided']:>13.4f}"
              f"{r['sigma']:>11.4f}{r['lower_bound']:>12.4f}")
    print("  blocks = pretest scores present; mixed = blocks holding both "
          "arms, the only\n  ones that inform tau_hat.")


LATEX_HEADER = ("Outcome", "$n$", r"$\what{\tau}$ (pp)", r"std.\ error (pp)",
                "t-score", "$p$-value", r"95\% lower $\tau$ (pp)")


def latex_rows(factor):
    """Cells of the paper's table, one row per exam."""
    rows = []
    for name in OUTCOMES:
        r = factor[name]
        rows.append([
            name,
            r["n_used"],
            du.format_sig(r["tau"]),
            du.format_sig(r["se"]),
            du.format_sig(r["t"]),
            du.format_p(r["p_one_sided"]),
            du.format_sig(r["lower_bound"]),
        ])
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    du.add_data_arguments(parser)
    parser.add_argument("--alpha", type=float, default=0.05,
                        help="one-sided level for the confidence bound "
                             "(default: %(default)s)")
    args = parser.parse_args(argv)

    data, dropped, unmatched_inclusions = du.load_from_args(args)
    factor = factor_analysis(data, args.alpha)
    report(data, dropped, args, unmatched_inclusions, factor)
    if args.latex:
        du.write_latex_table(args.latex, LATEX_HEADER, latex_rows(factor))


if __name__ == "__main__":
    main()
