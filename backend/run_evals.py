"""BS Detector eval harness.

Run from the backend directory:

    python run_evals.py            # run the pipeline live once, then score it
    python run_evals.py --cached   # score the last saved run (no API cost)
    python run_evals.py --runs 5   # run N times live, report mean +/- std + extra
                                    # error indicators, and write the findings report

It runs the multi-agent pipeline over the case file, compares the produced flags
against a hand-labeled ground truth (evals/ground_truth.json), and reports
precision, recall, and hallucination rate — with per-flaw detail behind the numbers.

The --runs mode adds the indicators that the single run can't show: run-to-run
variance, F1, per-agent precision (where over-flagging comes from), confidence
calibration, fact-vs-legal-conclusion breakdown, and silent-vs-explicit abstention.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from evals.metrics import (
    EvalResult,
    agent_breakdown,
    confidence_breakdown,
    evaluate,
    is_legal_conclusion,
    _tokens,
)
from main import load_documents

HERE = Path(__file__).parent
GROUND_TRUTH = HERE / "evals" / "ground_truth.json"
CACHE = HERE / "evals" / "last_run.json"
RUNS_DIR = HERE / "evals" / "runs"
REPORT = HERE.parent / "docs" / "eval-findings.md"


def _run_once_live() -> dict:
    """Run the pipeline live and return the full report dict. Also refreshes CACHE."""
    # Imported lazily so --cached works without an API key / network.
    from pipeline import run_pipeline

    state = run_pipeline(load_documents())
    report = {
        "citations": [c.model_dump() for c in state.citations],
        "flags": [f.model_dump() for f in state.flags],
        "judicial_memo": state.judicial_memo,
        "errors": state.errors,
    }
    CACHE.write_text(json.dumps(report, indent=2))
    return report


def _get_flags(use_cached: bool) -> list[dict]:
    if use_cached:
        if not CACHE.exists():
            sys.exit("No cached run found. Run once without --cached first.")
        return json.loads(CACHE.read_text())["flags"]

    print("Running pipeline (this calls the LLM and may take ~1 min)...\n")
    report = _run_once_live()
    if report["errors"]:
        print(f"  (pipeline recorded {len(report['errors'])} node error(s); see below)\n")
    return report["flags"]


def _bar(value: float) -> str:
    filled = round(value * 20)
    return "█" * filled + "░" * (20 - filled)


# --------------------------------------------------------------------------- #
# Single-run detailed printout (default + --cached)
# --------------------------------------------------------------------------- #
def print_single(flags: list[dict], ground_truth: dict) -> None:
    result = evaluate(flags, ground_truth)
    flaws_by_id = {f["id"]: f for f in ground_truth["flaws"]}

    print("=" * 70)
    print("BS DETECTOR — EVAL REPORT")
    print("=" * 70)
    print(f"\nFlags produced: {len(flags)}   Ground-truth flaws: {len(ground_truth['flaws'])}")
    print(f"Verifiable flaws (recall denominator): {len(result.verifiable_flaw_ids)}\n")

    print(f"Precision          {result.precision:5.0%}  {_bar(result.precision)}")
    print("  share of confident flags that match a real flaw (penalizes false alarms)")
    print(f"Recall             {result.recall:5.0%}  {_bar(result.recall)}")
    print("  share of text-verifiable flaws the pipeline caught")
    print(f"Hallucination rate {result.hallucination_rate:5.0%}  {_bar(result.hallucination_rate)}")
    print("  share of flags confidently asserting a flaw that does not exist")
    print(f"F1 (precision/recall) {result.f1:5.0%}  {_bar(result.f1)}\n")

    print("-" * 70)
    print("RECALL DETAIL (verifiable flaws)")
    for fid in sorted(result.verifiable_flaw_ids):
        caught = fid in result.caught_verifiable_ids
        mark = "✓ caught " if caught else "✗ MISSED "
        print(f"  {mark} {fid}: {flaws_by_id[fid]['summary'][:70]}")

    non_verifiable = [f["id"] for f in ground_truth["flaws"] if not f["verifiable"]]
    print("\nHONESTY DETAIL (non-verifiable flaws — abstention is the correct answer)")
    for fid in non_verifiable:
        print(f"  · {fid}: {flaws_by_id[fid]['summary'][:70]}")

    if result.hallucinated_flags:
        print("\n" + "-" * 70)
        print(f"HALLUCINATIONS ({len(result.hallucinated_flags)}) — confident flags matching no flaw:")
        for f in result.hallucinated_flags:
            tag = " [legal-conclusion]" if is_legal_conclusion(f) else ""
            print(f"  ! [{f['type']}/{f['confidence']}]{tag} {f['claim_in_msj'][:60]}")

    if result.unmatched_flags:
        print("\n" + "-" * 70)
        print(f"HEDGED / UNMATCHED ({len(result.unmatched_flags)}) — not credited, not punished:")
        for f in result.unmatched_flags:
            print(f"  ? [{f['type']}/{f['verdict']}] {f['claim_in_msj'][:60]}")

    _print_extra_indicators([result], ground_truth, [flags])
    print("\n" + "=" * 70)


# --------------------------------------------------------------------------- #
# Extra error indicators (shared by single and multi run)
# --------------------------------------------------------------------------- #
def _explicit_abstentions(flags: list[dict], ground_truth: dict) -> dict[str, bool]:
    """For each non-verifiable flaw, did any flag *explicitly* abstain on it
    (verdict could_not_verify + keyword overlap)? False == silently dropped."""
    out: dict[str, bool] = {}
    for flaw in ground_truth["flaws"]:
        if flaw["verifiable"]:
            continue
        kw_sets = [_tokens(kw) for kw in flaw["match_keywords"]]
        explicit = any(
            f.get("verdict") == "could_not_verify"
            and any(kw and kw <= _tokens(" ".join(str(f.get(k, "")) for k in ("claim_in_msj", "evidence"))) for kw in kw_sets)
            for f in flags
        )
        out[flaw["id"]] = explicit
    return out


def _merge_breakdowns(per_run: list[dict]) -> dict[str, dict]:
    """Sum tp/fp/hedged across run-level breakdown dicts (agent or confidence)."""
    merged: dict[str, dict] = {}
    for run in per_run:
        for key, s in run.items():
            b = merged.setdefault(key, {"tp": 0, "fp": 0, "hedged": 0})
            b["tp"] += s["tp"]
            b["fp"] += s["fp"]
            b["hedged"] += s["hedged"]
    for s in merged.values():
        confident = s["tp"] + s["fp"]
        s["precision"] = s["tp"] / confident if confident else 1.0
        s["accuracy"] = s["tp"] / confident if confident else None
    return merged


def _legal_conclusion_fps(results: list[EvalResult]) -> tuple[int, int]:
    """(legal-conclusion FPs, total FPs) summed across all runs."""
    all_fp = [f for r in results for f in r.hallucinated_flags]
    legal = [f for f in all_fp if is_legal_conclusion(f)]
    return len(legal), len(all_fp)


def _print_extra_indicators(results: list[EvalResult], ground_truth: dict, all_runs: list[list[dict]]) -> None:
    agents = _merge_breakdowns([agent_breakdown(r) for r in results])
    confs = _merge_breakdowns([confidence_breakdown(r) for r in results])
    n = len(results)
    suffix = f" (summed over {n} runs)" if n > 1 else ""

    print("\n" + "-" * 70)
    print(f"PER-AGENT PRECISION (where over-flagging comes from){suffix}")
    for agent, s in sorted(agents.items()):
        print(f"  {agent:<18} tp={s['tp']} fp={s['fp']} hedged={s['hedged']}  precision={s['precision']:.0%}")

    print(f"\nCONFIDENCE CALIBRATION (is 'high' more trustworthy than 'medium'?){suffix}")
    for level in ("high", "medium", "low"):
        s = confs.get(level)
        if not s:
            continue
        acc = f"{s['accuracy']:.0%}" if s["accuracy"] is not None else "n/a"
        print(f"  {level:<7} tp={s['tp']} fp={s['fp']} hedged={s['hedged']}  accuracy={acc}")

    legal, total_fp = _legal_conclusion_fps(results)
    print(
        f"\nFACT vs LEGAL-CONCLUSION: {legal}/{total_fp} "
        f"false positives are legal conclusions mislabeled as fact_contradiction{suffix}"
    )

    # Abstention is computed over the union of flags across runs passed in.
    merged = [f for run in all_runs for f in run]
    abst = _explicit_abstentions(merged, ground_truth)
    silent = [fid for fid, ex in abst.items() if not ex]
    print(
        f"\nABSTENTION: {len(abst) - len(silent)}/{len(abst)} non-verifiable flaws explicitly "
        f"marked could_not_verify; {len(silent)} silently dropped ({', '.join(silent) or 'none'})"
    )


# --------------------------------------------------------------------------- #
# Multi-run mode (--runs N)
# --------------------------------------------------------------------------- #
def _stat(values: list[float]) -> tuple[float, float, float, float]:
    """mean, std (population), min, max."""
    mean = statistics.fmean(values)
    std = statistics.pstdev(values) if len(values) > 1 else 0.0
    return mean, std, min(values), max(values)


def run_multi(n: int, ground_truth: dict, reuse: bool = False) -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    flaws_by_id = {f["id"]: f for f in ground_truth["flaws"]}
    verifiable_ids = sorted(f["id"] for f in ground_truth["flaws"] if f["verifiable"])

    reports: list[dict] = []
    results: list[EvalResult] = []
    if reuse:
        saved = sorted(RUNS_DIR.glob("run_*.json"))
        if not saved:
            sys.exit("No saved runs in evals/runs/. Run without --reuse first.")
        print(f"Reusing {len(saved)} saved run(s) from evals/runs/ (no API cost)...\n")
        for path in saved:
            report = json.loads(path.read_text())
            reports.append(report)
            results.append(evaluate(report["flags"], ground_truth))
        n = len(reports)
    else:
        print(f"Running pipeline {n}x live (this calls the LLM each time; ~1 min/run)...\n")
        for i in range(1, n + 1):
            print(f"  run {i}/{n} ...", flush=True)
            report = _run_once_live()
            (RUNS_DIR / f"run_{i}.json").write_text(json.dumps(report, indent=2))
            reports.append(report)
            results.append(evaluate(report["flags"], ground_truth))

    # Aggregate metric distributions.
    metrics = {
        "Precision": [r.precision for r in results],
        "Recall": [r.recall for r in results],
        "Hallucination": [r.hallucination_rate for r in results],
        "F1": [r.f1 for r in results],
    }
    # Flaw stability: how many runs caught each verifiable flaw.
    stability = {
        fid: sum(1 for r in results if fid in r.caught_verifiable_ids)
        for fid in verifiable_ids
    }
    # Errors across runs.
    total_errors = sum(len(rep["errors"]) for rep in reports)
    all_runs_flags = [rep["flags"] for rep in reports]

    # ---- terminal printout ----
    print("\n" + "=" * 70)
    print(f"BS DETECTOR — MULTI-RUN EVAL ({n} runs, temperature=0)")
    print("=" * 70)
    print("\nMETRIC               mean    std     min     max")
    for name, vals in metrics.items():
        m, s, lo, hi = _stat(vals)
        print(f"  {name:<16} {m:5.0%}  ±{s:4.0%}  {lo:5.0%}  {hi:5.0%}")

    print("\nFLAW STABILITY (verifiable flaws caught, out of {} runs)".format(n))
    for fid in verifiable_ids:
        c = stability[fid]
        bar = "█" * c + "░" * (n - c)
        print(f"  {fid} {bar} {c}/{n}  {flaws_by_id[fid]['summary'][:55]}")

    # Structural breakdowns are aggregated across all runs; abstention uses their union.
    _print_extra_indicators(results, ground_truth, all_runs_flags)
    print(f"\nNODE ERRORS across {n} runs: {total_errors}")
    print("\n" + "=" * 70)

    # ---- write findings report ----
    _write_report(n, metrics, stability, verifiable_ids, flaws_by_id, results, reports, ground_truth)
    print(f"\nReport written to {REPORT.relative_to(HERE.parent)}")


def _write_report(n, metrics, stability, verifiable_ids, flaws_by_id, results, reports, ground_truth) -> None:
    all_runs_flags = [rep["flags"] for rep in reports]
    abst = _explicit_abstentions([f for run in all_runs_flags for f in run], ground_truth)
    silent = [fid for fid, ex in abst.items() if not ex]
    total_errors = sum(len(rep["errors"]) for rep in reports)
    agents = _merge_breakdowns([agent_breakdown(r) for r in results])
    confs = _merge_breakdowns([confidence_breakdown(r) for r in results])
    n_legal_fp, n_total_fp = _legal_conclusion_fps(results)
    legal_fps = [f for r in results for f in r.hallucinated_flags if is_legal_conclusion(f)]

    L: list[str] = []
    L.append("# BS Detector — Eval Findings\n")
    L.append(
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
        f"from {n} live pipeline runs (temperature=0). gpt-4o._\n"
    )
    L.append(
        "This report goes beyond the three headline metrics to surface the error "
        "indicators that a single run hides: run-to-run variance, where over-flagging "
        "originates, whether confidence is calibrated, and how the pipeline behaves on "
        "claims it cannot verify.\n"
    )

    L.append("## 1. Metric distribution\n")
    L.append("| Metric | mean | std | min | max |")
    L.append("|---|---|---|---|---|")
    for name, vals in metrics.items():
        m, s, lo, hi = _stat(vals)
        L.append(f"| {name} | {m:.0%} | ±{s:.0%} | {lo:.0%} | {hi:.0%} |")
    L.append(
        "\n**Indicator:** even at `temperature=0` the metrics move between runs — "
        "the spread above is itself a reliability finding, not noise to hide.\n"
    )

    L.append(f"## 2. Flaw stability (caught in how many of {n} runs)\n")
    L.append("| Flaw | caught | summary |")
    L.append("|---|---|---|")
    for fid in verifiable_ids:
        L.append(f"| {fid} | {stability[fid]}/{n} | {flaws_by_id[fid]['summary'][:90]} |")
    flaky = [fid for fid in verifiable_ids if 0 < stability[fid] < n]
    missed = [fid for fid in verifiable_ids if stability[fid] == 0]
    L.append(
        f"\n**Indicator:** consistently missed: {', '.join(missed) or 'none'}; "
        f"flaky (run-dependent): {', '.join(flaky) or 'none'}.\n"
    )

    L.append(f"## 3. Per-agent precision (source of over-flagging, summed over {n} runs)\n")
    L.append("| Agent | TP | FP | hedged | precision |")
    L.append("|---|---|---|---|---|")
    for agent, s in sorted(agents.items()):
        L.append(f"| {agent} | {s['tp']} | {s['fp']} | {s['hedged']} | {s['precision']:.0%} |")
    L.append("")

    L.append(f"## 4. Confidence calibration (summed over {n} runs)\n")
    L.append("| Level | TP | FP | hedged | accuracy |")
    L.append("|---|---|---|---|---|")
    for level in ("high", "medium", "low"):
        s = confs.get(level)
        if not s:
            continue
        acc = f"{s['accuracy']:.0%}" if s["accuracy"] is not None else "n/a"
        L.append(f"| {level} | {s['tp']} | {s['fp']} | {s['hedged']} | {acc} |")
    L.append(
        "\n**Indicator:** if `high` accuracy exceeds `medium`, the confidence signal is "
        "usable as a triage gate (auto-surface high, route medium to human review).\n"
    )

    L.append("## 5. Fact vs. legal conclusion (characterizing the false positives)\n")
    base = (
        f"{n_legal_fp} of {n_total_fp} false positives (across {n} runs) are *legal "
        "conclusions* mislabeled as factual contradictions"
    )
    if legal_fps:
        L.append(base + ". Examples:\n")
        seen: set[str] = set()
        for f in legal_fps:
            claim = f["claim_in_msj"]
            if claim in seen:
                continue
            seen.add(claim)
            L.append(f"- **[{f['type']}/{f['confidence']}]** {claim}")
            if f.get("evidence"):
                L.append(f"  - evidence offered: _{f['evidence'][:200]}_")
    else:
        L.append(base + ".\n")
    # The dominant FP source is whichever agent emits the most false positives.
    top_agent = max(agents.items(), key=lambda kv: kv[1]["fp"], default=(None, {"fp": 0}))
    if top_agent[0] and top_agent[1]["fp"] >= max(1, n_legal_fp):
        L.append(
            f"\n**Indicator:** legal-conclusion mislabeling is a *minor* contributor "
            f"({n_legal_fp}/{n_total_fp}). The dominant source of false positives is "
            f"**{top_agent[0]}** ({top_agent[1]['fp']} FPs, {top_agent[1]['precision']:.0%} "
            "precision) — it confidently asserts citation problems it cannot actually "
            "verify. The biggest precision lever is forcing that agent to abstain "
            "(`could_not_verify`) instead of guessing, not a legal-conclusion gate.\n"
        )
    else:
        L.append(
            "\n**Indicator:** the cheapest precision win is a gate that rejects flags whose "
            "`claim` is a legal conclusion rather than a record fact.\n"
        )

    L.append("## 6. Abstention behavior (non-verifiable flaws)\n")
    L.append(
        f"{len(abst) - len(silent)}/{len(abst)} non-verifiable flaws were *explicitly* "
        f"marked `could_not_verify`; **{len(silent)} were silently dropped** "
        f"({', '.join(silent) or 'none'}).\n"
    )
    L.append(
        "**Indicator:** silent omission and honest abstention look identical to a user. "
        "The pipeline should emit an explicit `could_not_verify` for suspect citations "
        "(Whitmore, Kellerman, Seabright) instead of producing nothing.\n"
    )

    L.append(f"## 7. Node errors\n\n{total_errors} node failures across {n} runs "
             "(graceful-degradation wrapper recorded them in `state.errors`).\n")

    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the BS Detector pipeline.")
    parser.add_argument("--cached", action="store_true", help="Score the last saved run")
    parser.add_argument("--runs", type=int, default=1, help="Run the pipeline N times live")
    parser.add_argument("--reuse", action="store_true",
                        help="Re-aggregate the saved runs in evals/runs/ (no API cost)")
    args = parser.parse_args()

    ground_truth = json.loads(GROUND_TRUTH.read_text())

    if args.reuse:
        run_multi(args.runs, ground_truth, reuse=True)
        return

    if args.runs > 1:
        if args.cached:
            sys.exit("--runs and --cached are mutually exclusive.")
        run_multi(args.runs, ground_truth)
        return

    flags = _get_flags(args.cached)
    print_single(flags, ground_truth)


if __name__ == "__main__":
    main()
