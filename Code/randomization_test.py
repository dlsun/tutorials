#!/usr/bin/env python3
"""Randomization test for the 117 tutorial experiment.

This is the second of the paper's two analyses (the section "Randomization
test", with details in the appendix "Analysis of the randomization tests").
The companion script block_factor_analysis.py is the first, and data_utils.py
holds the loading and conventions the two share.

The test is exact in the design: the reference distribution is the
distribution of the test statistic over the assignments the experiment could
have produced, holding the students and their observed scores fixed. Nothing
is assumed about the distribution of scores, and no large-sample approximation
is used.

The test statistic is the difference in means, T(S) = mean of the treated
minus mean of the controls under assignment S, over the students with a score
on the exam being analyzed. Re-randomized assignments S are drawn uniformly
from those the design allows: within each pretest-score block, the number of
treated students is held at its observed count m_k, and which m_k of the n_k
students are treated is chosen uniformly at random. The analysis uses
--num-randomizations draws (default 1,000,000) from a generator seeded with
--seed (default 0).

1. The test of no effect
------------------------

    H0: Y_i(1) <= Y_i(0) for every student i,

against the one-sided alternative that the tutorials raised scores. At the
boundary Y_i(1) = Y_i(0), every student's score is fixed no matter how the
coins fell, so the null distribution of T is obtained by re-randomizing and
recomputing it, and the p-value is its upper tail at the observed T_obs. The
add-one (Phipson-Smyth) convention, (#{T(S) >= T_obs} + 1) / (N + 1), keeps it
from ever being exactly zero.

2. The lower confidence bound (--alpha)
---------------------------------------

For a constant tau consider the one-sided null

    H_tau: Y_i(1) <= Y_i(0) + tau for every student i,

i.e. "no student was helped by more than tau points". Testing it inverts into
a one-sided confidence bound: the reported tau* is the smallest tau that
survives at level alpha, so every tau < tau* is rejected and

    tau* is a level-(1 - alpha) lower confidence bound on max_i (Y_i(1) - Y_i(0))

-- and, if effects are taken to be constant across students, a lower bound on
that common effect.

To test H_tau we impute the missing potential outcome under the boundary null
Y_i(1) = Y_i(0) + tau: a treated student's control score is Y_i - tau and a
control student's treated score is Y_i + tau. Writing W_i for the *observed*
assignment, the adjusted control-scale outcome is Y_i^0 = Y_i - tau W_i, and a
re-randomized assignment S gives

    T(S; tau) = mean_S(Y^0 + tau) - mean_{S^c}(Y^0) = A(S) + tau (1 - B(S)),
    A(S) = mean_S(Y) - mean_{S^c}(Y),   B(S) = mean_S(W) - mean_{S^c}(W).

The observed assignment has A = T_obs and B = 1, so T(S_obs; tau) = T_obs for
every tau, and the p-value for H_tau is the upper tail

    p(tau) = P( T(S; tau) >= T_obs ) = P( A(S) >= T_obs - tau (1 - B(S)) ).

Because the imputed outcomes move with tau, the null draws are not simply the
raw permutation statistics compared against T_obs - tau; the B(S) term is
exactly that dependence. A(S) and B(S) are both recorded once per draw, so
p(tau) is an O(N) scan of stored numbers and the search reuses the same N
draws at every step.

Since B(S) <= 1 always, tau |-> T_obs - tau (1 - B(S)) is non-increasing, so p
is non-decreasing in tau: small tau is rejected, large tau is not, and the
crossing point tau* = inf{tau : p(tau) > alpha} is found by bisection. Two
sanity checks fall out: p(0) is exactly the p-value of the test of no effect,
so tau* is positive precisely when that test rejects, and p(tau) -> 1 as tau
grows.

Testing the boundary null licenses the one-sided conclusion: under any
alternative with Y_i(1) <= Y_i(0) + tau for all i the statistic is
stochastically smaller, so rejecting at the boundary rejects the whole
composite null.

The statistic is the unadjusted difference in means even though assignment
was blocked. That is legitimate -- the reference distribution re-randomizes
within blocks, so the test is exact whatever statistic is used -- but it does
mean tau* is a bound on effects for this sample, not a block-weighted
estimate.

The p-value and tau* are Monte Carlo quantities. With the seed fixed they are
exactly reproducible on the same input file and numpy version.

Usage:
    python3 randomization_test.py [--input FILE] [--include FILE]
                                  [--num-randomizations N] [--seed S]
                                  [--alpha A] [--latex FILE]

--latex FILE writes the paper's table as a LaTeX tabular, one row per exam,
with columns

  Outcome                  the exam
  $n$                      consenting students with a score on that exam
  Tutorial mean            observed mean score of the treated students
  Control mean             observed mean score of the control students
  $\\what{\\tau}$ (pp)       their difference T_obs, in percentage points
  $p$-value                one-sided p-value of the test of no effect
  95\\% lower $\\tau$ (pp)   the bound tau* at level --alpha
"""

import argparse

import numpy as np

import data_utils as du
from data_utils import OUTCOMES, nanmean

# Statistics stored for every draw: A(S) and B(S) from the module docstring.
DRAW_KEYS = ("difference", "w_contrast")

SHIFT_TOL = 1e-4  # width at which the bisection for tau* stops


def draw_assignment(blocks, n, rng):
    """One assignment the design allows: True = treatment.

    Within each block, as many students are treated as were observed, chosen
    uniformly at random.
    """
    treat = np.zeros(n, dtype=bool)
    for _, idx, n_treated in blocks:
        treat[rng.permutation(idx)[:n_treated]] = True
    return treat


def draw_statistics(data, treat, observed_treat):
    """A(S) and B(S) for each outcome, under assignment treat.

    A(S) is the difference in means of the outcome. B(S) is the difference in
    means of the *observed* treatment indicator between the draw's treated and
    control groups, computed over the same students the outcome means use (so
    a missing score drops out of both). B equals 1 for the observed assignment
    and is what makes the search for tau* exact; see the module docstring.
    """
    w = observed_treat.astype(float)
    out = {}
    for name in OUTCOMES:
        y = data[name]
        finite = np.isfinite(y)
        out[name] = {
            "difference": nanmean(y[treat]) - nanmean(y[~treat]),
            "w_contrast": (nanmean(np.where(finite & treat, w, np.nan))
                           - nanmean(np.where(finite & ~treat, w, np.nan))),
        }
    return out


def run_randomizations(data, num_randomizations, rng):
    """A(S) and B(S) over num_randomizations draws from the design."""
    n = len(data["pretest"])
    blocks = du.build_blocks(data["pretest"], data["randomize"])
    observed_treat = data["randomize"] == 1
    draws = {name: {key: np.empty(num_randomizations) for key in DRAW_KEYS}
             for name in OUTCOMES}
    for i in range(num_randomizations):
        treat = draw_assignment(blocks, n, rng)
        stats_i = draw_statistics(data, treat, observed_treat)
        for name in OUTCOMES:
            for key in DRAW_KEYS:
                draws[name][key][i] = stats_i[name][key]
    return draws


# ---------------------------------------------- inverting the null of no effect --

def shift_pvalue(tau, t_obs, diff_draws, w_draws):
    """P-value of H_tau: Y_i(1) <= Y_i(0) + tau, from stored null draws.

    Implements p(tau) = P( A(S) >= T_obs - tau (1 - B(S)) ) with the add-one
    convention. Draws whose statistic is undefined (an arm with no
    non-missing score) are dropped. p(0) is the p-value of the test of no
    effect.
    """
    keep = np.isfinite(diff_draws) & np.isfinite(w_draws)
    a, b = diff_draws[keep], w_draws[keep]
    n = len(a)
    if n == 0 or not np.isfinite(t_obs):
        return np.nan
    return float((np.sum(a >= t_obs - tau * (1.0 - b)) + 1) / (n + 1))


def shift_bound(t_obs, diff_draws, w_draws, alpha=0.05, tol=SHIFT_TOL,
                max_expansions=60):
    """Smallest tau that H_tau survives at level alpha, by bisection.

    p(tau) is non-decreasing in tau (see the module docstring), so the search
    brackets the crossing and bisects to width tol. Returns a dict with

      tau        the bound tau*: H_tau is rejected for every tau < tau*,
                 kept at tau*
      p_at_tau   p(tau*), which is just above alpha
      p_below    p at the last rejected value, which is at most alpha
      p_at_zero  p(0), the p-value of the test of no effect
      n_draws    usable draws behind those p-values
      status     "ok", "always-rejected" or "never-rejected"

    "never-rejected" means even tau -> -infinity fails to reject: with the
    add-one convention the smallest attainable p-value is 1 / (N + 1), so this
    happens whenever alpha < 1 / (N + 1) -- ask for more randomizations.
    """
    keep = np.isfinite(diff_draws) & np.isfinite(w_draws)
    n = int(np.sum(keep))
    result = {"tau": np.nan, "p_at_tau": np.nan, "p_below": np.nan,
              "p_at_zero": np.nan, "n_draws": n, "status": "undefined"}
    if n == 0 or not np.isfinite(t_obs):
        return result

    def p(tau):
        return shift_pvalue(tau, t_obs, diff_draws, w_draws)

    result["p_at_zero"] = p(0.0)

    # Bracket the crossing: p(lo) <= alpha < p(hi).
    scale = max(1.0, abs(t_obs), float(np.nanmax(np.abs(diff_draws[keep]))))
    lo, hi = -scale, scale
    for _ in range(max_expansions):
        if p(hi) > alpha:
            break
        hi *= 2.0
    else:
        result["status"] = "always-rejected"     # p(tau) <= alpha out to +inf
        return result
    for _ in range(max_expansions):
        if p(lo) <= alpha:
            break
        lo *= 2.0
    else:
        result["status"] = "never-rejected"      # p(tau) > alpha down to -inf
        result["p_at_tau"] = p(lo)
        return result

    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if p(mid) > alpha:
            hi = mid
        else:
            lo = mid
    result.update({"tau": float(hi), "p_at_tau": p(hi), "p_below": p(lo),
                   "status": "ok"})
    return result


def summarize(data, draws, alpha=0.05):
    """Observed means, the p-value and tau* for each outcome."""
    treat = data["randomize"] == 1
    out = {}
    for name in OUTCOMES:
        y = data[name]
        t_mean, c_mean = nanmean(y[treat]), nanmean(y[~treat])
        diff, w = draws[name]["difference"], draws[name]["w_contrast"]
        bound = shift_bound(t_mean - c_mean, diff, w, alpha)
        out[name] = {
            "n": int(np.sum(np.isfinite(y))),
            "treatment": t_mean,
            "control": c_mean,
            "t_obs": t_mean - c_mean,
            "null_sd": float(np.nanstd(diff, ddof=1)),
            "p": bound["p_at_zero"],
            "bound": bound,
        }
    return out


# ------------------------------------------------------------- reporting ---

def report_header(data, dropped, args, unmatched_inclusions):
    print("=" * 78)
    print("Randomization test within the pretest blocks")
    print("=" * 78)
    du.print_data_header(data, dropped, args, unmatched_inclusions)
    print(f"Randomizations:                    {args.num_randomizations}"
          f"  (seed {args.seed})")
    print(f"Level for the lower bound:         alpha = {args.alpha}")
    print("Hypotheses (all p-values one-sided):")
    print("  no effect    H0: Y_i(1) <= Y_i(0) for all i, "
          "vs H1: the tutorials helped")
    print("  lower bound  H_tau: Y_i(1) <= Y_i(0) + tau for all i")
    du.print_blocks(data["pretest"], data["randomize"])


def report_results(results, args):
    print(f"\nDifference in means  ({args.num_randomizations} draws)")
    print(f"  {'outcome':<8}{'n':>5}{'mean_T':>10}{'mean_C':>10}{'T_obs':>10}"
          f"{'null sd':>9}{'p (1-sided)':>13}{'tau*':>10}{'p(tau*)':>10}")
    print(f"  {'-' * 85}")
    for name in OUTCOMES:
        r, b = results[name], results[name]["bound"]
        tau = f"{b['tau']:10.4f}" if np.isfinite(b["tau"]) else f"{'--':>10}"
        p_tau = (f"{b['p_at_tau']:10.4f}" if np.isfinite(b["p_at_tau"])
                 else f"{'--':>10}")
        print(f"  {name:<8}{r['n']:>5}{r['treatment']:>10.4f}"
              f"{r['control']:>10.4f}{r['t_obs']:>10.4f}{r['null_sd']:>9.4f}"
              f"{r['p']:>13.4f}{tau}{p_tau}")
    for name in OUTCOMES:
        b = results[name]["bound"]
        if b["status"] == "never-rejected":
            print(f"  ! {name}: no tau rejected: alpha < 1/(N+1) = "
                  f"{1 / (b['n_draws'] + 1):.4g}")
        elif b["status"] == "always-rejected":
            print(f"  ! {name}: every tau rejected (degenerate null)")
        elif b["status"] != "ok":
            print(f"  ! {name}: statistic undefined")
    print(f"  H_tau is rejected for every tau < tau* and survives at tau*, so "
          f"tau* is a\n  {1 - args.alpha:.0%} lower confidence bound on the "
          f"largest individual effect -- under\n  constant effects, on the "
          f"common effect.")


LATEX_HEADER = ("Outcome", "$n$", "Tutorial mean", "Control mean",
                r"$\what{\tau}$ (pp)", "$p$-value", r"95\% lower $\tau$ (pp)")


def latex_rows(results):
    """Cells of the paper's table, one row per exam."""
    rows = []
    for name in OUTCOMES:
        r = results[name]
        rows.append([
            name,
            r["n"],
            du.format_sig(r["treatment"]) + r"\%",
            du.format_sig(r["control"]) + r"\%",
            du.format_sig(r["t_obs"]),
            du.format_p(r["p"]),
            du.format_sig(r["bound"]["tau"]),
        ])
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    du.add_data_arguments(parser)
    parser.add_argument("--num-randomizations", "-N", type=int,
                        default=1_000_000,
                        help="number of re-randomizations "
                             "(default: %(default)s)")
    parser.add_argument("--seed", type=int, default=0,
                        help="RNG seed (default: %(default)s)")
    parser.add_argument("--alpha", type=float, default=0.05,
                        help="one-sided level for the lower bound tau* "
                             "(default: %(default)s)")
    args = parser.parse_args(argv)

    data, dropped, unmatched_inclusions = du.load_from_args(args)
    report_header(data, dropped, args, unmatched_inclusions)

    rng = np.random.default_rng(args.seed)
    draws = run_randomizations(data, args.num_randomizations, rng)
    results = summarize(data, draws, args.alpha)
    report_results(results, args)
    if args.latex:
        du.write_latex_table(args.latex, LATEX_HEADER, latex_rows(results))


if __name__ == "__main__":
    main()
