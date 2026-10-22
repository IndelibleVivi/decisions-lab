"""Command-line interface for Choice and typed-values experiments.

Commands (all offline by default):
  typed-values prepare, import and score independent typed-value records offline
  validate      validate a suite file (schema, ids, split isolation)
  baseline-run  run the deterministic rules baseline; write a synthetic record
  demo          run a constructed offline demo with a wrong + unknown example
  prepare       build + print native request bodies for a route (no network)
  replay        replay a record against a suite and print coverage/eval
  routes        show encoded route profiles and provenance
  collect-live  opt-in live collection (guarded; not run by default)
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .cases import ALLOWED_ACTIONS, CaseError, load_suite
from .record import (
    EvalReport,
    RecordError,
    evaluate,
    load_and_evaluate,
    load_record,
    run_baseline,
    run_demo,
    threshold_coverage,
    write_record,
)
from .routes import ROUTE_KEYS, all_routes, build_request, get_route, protocol_profiles
from . import typed_values as tv
from . import api_lab as al

DEFAULT_SUITE = "experiments/next-action/cases.json"


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _fmt_acc(rep: EvalReport) -> str:
    return "n/a" if rep.accuracy is None else f"{rep.accuracy:.3f} ({rep.correct}/{rep.answered})"


def _usage_summary(record) -> dict:
    """Sum reported usage; keep cost null/unknown when absent."""
    latencies = [r.latency_ms for r in record.results if r.latency_ms is not None]
    costs_present = [r.cost for r in record.results if r.cost is not None]
    usage_present = [r.usage for r in record.results if r.usage is not None]
    return {
        "cases_with_latency": len(latencies),
        "latency_ms_total": sum(latencies) if latencies else None,
        "latency_ms_mean": (sum(latencies) / len(latencies)) if latencies else None,
        "cases_with_usage": len(usage_present),
        "cases_with_cost": len(costs_present),
        "cost": costs_present or None,
        "note": "Reported values only; null/unknown when the provider did not report them.",
    }


def _cmd_validate(args) -> int:
    suite = load_suite(args.suite)
    dev = suite.split("dev")
    test = suite.split("test")
    n_options: dict[int, int] = {}
    for c in suite.cases:
        n_options[len(c.acceptable)] = n_options.get(len(c.acceptable), 0) + 1
    print(
        f"OK: {len(suite.cases)} cases (dev={len(dev)}, test={len(test)}), "
        f"{len({c.source_group for c in suite.cases})} source groups"
    )
    print(f"acceptable-set sizes: {dict(sorted(n_options.items()))}")
    return 0


def _cmd_baseline_run(args) -> int:
    suite = load_suite(args.suite)
    record = run_baseline(suite, suite_path=str(args.suite))
    out = write_record(args.run_dir, record, clobber=args.clobber)
    rep = evaluate(record, suite, suite_path=str(args.suite))
    print(f"baseline record written: {out}")
    print(f"synthetic demonstration accuracy (not a model claim): {_fmt_acc(rep)}")
    return 0


def _cmd_demo(args) -> int:
    suite = load_suite(args.suite)
    record = run_demo(suite, suite_path=str(args.suite))
    out = write_record(args.run_dir, record, clobber=args.clobber)
    rep = evaluate(record, suite, suite_path=str(args.suite))
    print(f"demo record written: {out}")
    print("NOTE: all responses are SYNTHETIC constructed examples, not model inference.")
    print(
        f"demo: total={rep.total} answered={rep.answered} unknown={rep.unknown} "
        f"refusal={rep.refusal} errors={rep.errors} accuracy={_fmt_acc(rep)}"
    )
    return 0


def _cmd_prepare(args) -> int:
    suite = load_suite(args.suite)
    cases = suite.cases
    if args.case_id:
        by_id = suite.by_id()
        if args.case_id not in by_id:
            raise CaseError(f"unknown case id {args.case_id!r}")
        cases = [by_id[args.case_id]]
    if args.limit is not None:
        if args.limit <= 0:
            raise CaseError("--limit must be positive")
        cases = cases[: args.limit]
    route = get_route(args.route)
    preview = {
        "route": route.key,
        "label": route.label,
        "endpoint": route.endpoint,
        "native_model": route.native_model,
        "docs_url": route.docs_url,
        "protocol": protocol_profiles(),
        "docs_verified_at": protocol_profiles()["docs_verified_at"],
        "live_verified": protocol_profiles()["live_verified"],
        "requests": [
            {"case_id": c.id, "body": build_request(args.route, c)}
            for c in cases
        ],
    }
    _print_json(preview)
    return 0


def _cmd_replay(args) -> int:
    rep = load_and_evaluate(args.record, args.suite)
    record = load_record(args.record)
    payload = {
        "record": str(args.record),
        "suite": str(args.suite),
        "provenance": record.provenance,
        "synthetic": record.synthetic,
        "route": record.route,
        "native_model": record.native_model,
        "evaluation": rep.as_dict(),
        "actual_usage_cost": _usage_summary(record),
    }
    if args.threshold is not None:
        payload["threshold"] = threshold_coverage(record, threshold=args.threshold)
    _print_json(payload)
    return 0


def _cmd_routes(args) -> int:
    _print_json(
        {
            "routes": [
                {
                    "key": r.key,
                    "label": r.label,
                    "endpoint": r.endpoint,
                    "native_model": r.native_model,
                    "docs_url": r.docs_url,
                }
                for r in all_routes()
            ],
            "protocol_provenance": protocol_profiles(),
        }
    )
    return 0


def _cmd_collect_live(args) -> int:
    if not args.allow_network:
        print(
            "refused: live collection requires explicit --allow-network; "
            "default commands are offline",
            file=sys.stderr,
        )
        return 2
    # Import the network transport lazily so offline commands never even load
    # it; this keeps "offline means offline" auditable.
    from .live import LiveError, collect, plan_live

    plan = plan_live(
        args.suite,
        route_key=args.route,
        run_dir=args.run_dir,
        max_calls=args.max_calls,
        timeout_s=args.timeout,
        allow_network=args.allow_network,
        case_ids=args.case_id or None,
    )
    # checkpoint=True writes a partial record after each case so an
    # interrupted run stays inspectable. It is NOT automatic resume: a
    # retry requires a fresh run directory (see the run-dir clobber refusal).
    record = collect(plan, checkpoint=True)
    out = write_record(args.run_dir, record, clobber=True)
    print(f"live record written: {out}")
    print(
        "Reminder: route field shapes are documentation-verified (2026-10-09); "
        "confirm live behavior and pricing before trusting results."
    )
    return 0


def _tv_cases(args) -> tuple[tv.TypedSuite, list[tv.TypedCase]]:
    suite = tv.load_suite(args.suite)
    cases = tv.select_cases(
        suite,
        experiment_id=args.experiment_id,
        case_ids=args.case_id or None,
    )
    if args.limit is not None:
        if args.limit <= 0:
            raise tv.TypedValuesError("--limit must be positive")
        cases = cases[: args.limit]
    if not cases:
        raise tv.TypedValuesError("case selection is empty")
    return suite, cases


def _tv_write_and_evaluate(
    args,
    *,
    provenance: str,
    entries: list[tv.ResponseEntry],
    span_convention: dict[str, str] | None = None,
    notes: str = "",
) -> int:
    suite, cases = _tv_cases(args)
    record = tv.build_record(
        suite,
        cases,
        entries,
        provenance=provenance,
        span_convention=span_convention,
        notes=notes,
    )
    output = tv.write_record(args.run_dir, record)
    report = tv.replay_record(output, args.suite)
    print(f"{provenance} typed-values record written: {output}")
    print(
        "NOTE: offline records are not project live-provider verification."
        if provenance == tv.PROVENANCE_IMPORT
        else "NOTE: synthetic offline records, not provider inference."
    )
    print(json.dumps(report["evaluation"]["counts"], ensure_ascii=False))
    return 0


def _cmd_tv_validate(args) -> int:
    suite = tv.load_suite(args.suite)
    groups = len({case.source_group for case in suite.cases})
    print(
        f"OK: {len(suite.cases)} typed-values cases in "
        f"{len(suite.experiments)} experiments, {groups} source groups; status NOT_RUN"
    )
    return 0


def _cmd_tv_prepare(args) -> int:
    suite, cases = _tv_cases(args)
    _print_json(tv.prepare_payload(suite, cases))
    return 0


def _cmd_tv_baseline(args) -> int:
    suite, cases = _tv_cases(args)
    return _tv_write_and_evaluate(
        args,
        provenance=tv.PROVENANCE_BASELINE,
        entries=tv.baseline_entries(cases),
        notes="Deterministic template baseline over authored synthetic cases.",
    )


def _cmd_tv_demo(args) -> int:
    suite, cases = _tv_cases(args)
    return _tv_write_and_evaluate(
        args,
        provenance=tv.PROVENANCE_DEMO,
        entries=tv.demo_entries(cases),
        notes=(
            "Constructed offline demonstration from authored oracles; "
            "not provider output."
        ),
    )


def _cmd_tv_import(args) -> int:
    suite, cases = _tv_cases(args)
    entries, span_convention = tv.load_response_file(args.responses)
    selected_ids = {case.case_id for case in cases}
    supplied_ids = {entry.case_id for entry in entries}
    extra = sorted(supplied_ids - selected_ids)
    missing = sorted(selected_ids - supplied_ids)
    if extra:
        raise tv.TypedValuesError(
            f"response file contains cases outside this selection: {extra}"
        )
    if missing:
        raise tv.TypedValuesError(
            f"response file is missing selected cases: {missing}"
        )
    return _tv_write_and_evaluate(
        args,
        provenance=tv.PROVENANCE_IMPORT,
        entries=entries,
        span_convention=span_convention,
        notes="External offline JSON import; provenance is import, not live.",
    )


def _cmd_tv_replay(args) -> int:
    _print_json(tv.replay_record(args.record, args.suite))
    return 0


def _api_select(args):
    suite = al.load_suite(args.suite)
    return suite, al.select_rows(suite, experiment=args.experiment,
                                 case_ids=args.case_id, limit=args.limit)


def _cmd_api_validate(args):
    _print_json(al.validate_manifest(al.read_json(args.manifest)) if args.manifest
                else al.validate_suite(al.load_suite(args.suite)))
    return 0


def _cmd_api_list(args):
    suite = al.load_suite(args.suite)
    rows = suite.selected(args.experiment)
    _print_json({"provider_status": "NOT_RUN", "count": len(rows),
                 "experiments": sorted({r["experiment"] for r in suite.rows}),
                 "cases": [{"id": r["id"], "experiment": r["experiment"]} for r in rows]})
    return 0


def _cmd_api_prepare(args):
    suite, rows = _api_select(args)
    _print_json(al.prepare_payload(suite, rows, route=args.route, model=args.model))
    return 0


def _cmd_api_demo(args):
    suite, rows = _api_select(args)
    manifest = al.prepare_payload(suite, rows, route=args.route, model=args.model)
    record = al.build_record(manifest, al.synthetic_entries(manifest), provenance="synthetic")
    output = al.write_record(args.run_dir, record)
    _print_json({"record": str(output), "synthetic": True, "live_verified": False,
                 "coverage": al.replay_record(output)["coverage"]})
    return 0


def _cmd_api_import(args):
    manifest = al.read_json(args.manifest)
    document = al.load_responses(args.responses)
    record = al.build_record(manifest, document["responses"], provenance="imported",
                             allow_partial=args.allow_partial,
                             imported_synthetic=document.get("synthetic"))
    output = al.write_record(args.run_dir, record)
    _print_json({"record": str(output), "provenance": "imported", "live_verified": False,
                 "coverage": al.replay_record(output)["coverage"]})
    return 0


def _cmd_api_replay(args):
    overrides = al.read_json(args.rubric) if args.rubric else None
    result = al.replay_record(args.record, overrides=overrides)
    if args.output:
        al.write_evaluation(args.output, result)
    _print_json(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m decision_lab",
        description=(
            "Decisions Lab: run next-action, typed-values and API capability experiments. "
            "Default commands are offline; the lab never executes recommended actions."
        ),
        epilog=(
            "Actions: " + ", ".join(ALLOWED_ACTIONS) + ". "
            "Routes: " + ", ".join(ROUTE_KEYS) + "."
        ),
    )
    p.add_argument("--version", action="version", version=f"decision_lab {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_typed_selection(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("suite", nargs="?", default=tv.DEFAULT_SUITE)
        parser.add_argument(
            "--experiment",
            dest="experiment_id",
            default=None,
            help="restrict to an experiment id",
        )
        parser.add_argument(
            "--case-id",
            action="append",
            default=None,
            help="restrict to a case id (may be repeated)",
        )
        parser.add_argument("--limit", type=int, default=None)

    tv_parser = sub.add_parser(
        "typed-values",
        help="offline Clairic typed-values prepare/demo/import/replay",
    )
    tv_sub = tv_parser.add_subparsers(dest="typed_command", required=True)

    sp = tv_sub.add_parser("validate", help="validate the 3-experiment / 7-case suite")
    sp.add_argument("suite", nargs="?", default=tv.DEFAULT_SUITE)
    sp.set_defaults(func=_cmd_tv_validate)

    sp = tv_sub.add_parser("prepare", help="print native requests without oracle data")
    add_typed_selection(sp)
    sp.set_defaults(func=_cmd_tv_prepare)

    sp = tv_sub.add_parser("baseline-run", help="run the template baseline offline")
    add_typed_selection(sp)
    sp.add_argument("--run-dir", required=True)
    sp.set_defaults(func=_cmd_tv_baseline)

    sp = tv_sub.add_parser("demo", help="write constructed synthetic examples offline")
    add_typed_selection(sp)
    sp.add_argument("--run-dir", required=True)
    sp.set_defaults(func=_cmd_tv_demo)

    sp = tv_sub.add_parser("import", help="record responses from an external JSON file")
    add_typed_selection(sp)
    sp.add_argument("--responses", required=True)
    sp.add_argument("--run-dir", required=True)
    sp.set_defaults(func=_cmd_tv_import)

    sp = tv_sub.add_parser("replay", help="recompute and score a typed-values record")
    sp.add_argument("record")
    sp.add_argument("suite", nargs="?", default=tv.DEFAULT_SUITE)
    sp.set_defaults(func=_cmd_tv_replay)

    api_parser = sub.add_parser("api-lab", help="offline native multi-question capability experiments")
    api_sub = api_parser.add_subparsers(dest="api_command", required=True)

    def add_api_selection(parser):
        parser.add_argument("suite", nargs="?", default=al.DEFAULT_SUITE)
        parser.add_argument("--experiment")
        parser.add_argument("--case-id", action="append")
        parser.add_argument("--limit", type=int)

    sp = api_sub.add_parser("validate")
    sp.add_argument("suite", nargs="?", default=al.DEFAULT_SUITE)
    sp.add_argument("--manifest")
    sp.set_defaults(func=_cmd_api_validate)

    sp = api_sub.add_parser("list")
    sp.add_argument("suite", nargs="?", default=al.DEFAULT_SUITE)
    sp.add_argument("--experiment")
    sp.set_defaults(func=_cmd_api_list)

    for name, func in (("prepare", _cmd_api_prepare), ("demo", _cmd_api_demo)):
        sp = api_sub.add_parser(name)
        add_api_selection(sp)
        sp.add_argument("--route", required=True, choices=al.ROUTES)
        sp.add_argument("--model")
        if name == "demo":
            sp.add_argument("--run-dir", required=True)
        sp.set_defaults(func=func)

    sp = api_sub.add_parser("import")
    sp.add_argument("--manifest", required=True)
    sp.add_argument("--responses", required=True)
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--allow-partial", action="store_true")
    sp.set_defaults(func=_cmd_api_import)

    for name in ("replay", "report"):
        sp = api_sub.add_parser(name)
        sp.add_argument("record")
        sp.add_argument("--rubric")
        sp.add_argument("--output", help="save a new evaluation without modifying inference evidence")
        sp.set_defaults(func=_cmd_api_replay)

    sp = sub.add_parser("validate", help="validate a suite file")
    sp.add_argument("suite", nargs="?", default=DEFAULT_SUITE)
    sp.set_defaults(func=_cmd_validate)

    sp = sub.add_parser("baseline-run", help="run the deterministic rules baseline; write a record")
    sp.add_argument("suite", nargs="?", default=DEFAULT_SUITE)
    sp.add_argument("--run-dir", required=True, help="NEW local run directory")
    sp.add_argument("--clobber", action="store_true", help="allow overwriting an existing run dir")
    sp.set_defaults(func=_cmd_baseline_run)

    sp = sub.add_parser("demo", help="offline constructed demo (wrong + unknown examples)")
    sp.add_argument("suite", nargs="?", default=DEFAULT_SUITE)
    sp.add_argument("--run-dir", required=True, help="NEW local run directory")
    sp.add_argument("--clobber", action="store_true")
    sp.set_defaults(func=_cmd_demo)

    sp = sub.add_parser("prepare", help="build native request bodies (no network)")
    sp.add_argument("suite", nargs="?", default=DEFAULT_SUITE)
    sp.add_argument("--route", required=True, choices=list(ROUTE_KEYS))
    sp.add_argument("--case-id", default=None)
    sp.add_argument("--limit", type=int, default=None)
    sp.set_defaults(func=_cmd_prepare)

    sp = sub.add_parser("replay", help="replay a record against a suite; print evaluation")
    sp.add_argument("record", help="record.json or run directory")
    sp.add_argument("suite", nargs="?", default=DEFAULT_SUITE)
    sp.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="optional maxP threshold for selective-coverage evaluation",
    )
    sp.set_defaults(func=_cmd_replay)

    sp = sub.add_parser("routes", help="show encoded route profiles and provenance")
    sp.set_defaults(func=_cmd_routes)

    sp = sub.add_parser("collect-live", help="opt-in live collection (guarded; not run by default)")
    sp.add_argument("suite", nargs="?", default=DEFAULT_SUITE)
    sp.add_argument("--route", required=True, choices=list(ROUTE_KEYS))
    sp.add_argument("--run-dir", required=True, help="NEW local run directory")
    sp.add_argument("--max-calls", type=int, required=True)
    sp.add_argument("--timeout", type=float, default=30.0)
    sp.add_argument("--case-id", action="append", default=None, help="restrict to specific case ids")
    sp.add_argument(
        "--allow-network",
        action="store_true",
        help="explicit switch acknowledging outbound network use",
    )
    sp.set_defaults(func=_cmd_collect_live)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (CaseError, RecordError, tv.TypedValuesError, al.ApiLabError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except AssertionError as exc:
        print(f"internal invariant failure: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - last-resort readable error
        # Includes LiveError, which is imported lazily by collect-live.
        if type(exc).__name__ == "LiveError":
            print(f"error: {exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
