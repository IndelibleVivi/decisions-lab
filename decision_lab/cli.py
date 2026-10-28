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
    _print_json(al.prepare_payload(suite, rows, route=args.route, model=args.model,
                                   replicates=args.replicates,
                                   account_id=getattr(args, "account_id", None)))
    return 0


def _cmd_api_demo(args):
    suite, rows = _api_select(args)
    manifest = al.prepare_payload(suite, rows, route=args.route, model=args.model,
                                  replicates=args.replicates,
                                  account_id=getattr(args, "account_id", None))
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


def _cmd_research(args):
    from . import collection, comparison, generators, ledger, rule_workflow
    command = args.research_command
    if command.startswith("typed-dag-"):
        from . import typed_dag
        if command == "typed-dag-suite":
            result = typed_dag.build_suite(seed=args.seed)
        elif command in ("typed-dag-start", "typed-dag-demo"):
            suite = al.read_json(args.suite) if args.suite else typed_dag.build_suite(seed=args.seed)
            operation = typed_dag.start if command == "typed-dag-start" else typed_dag.demo
            extra = {"policy": args.policy} if command == "typed-dag-demo" else {}
            result = operation(suite, route=args.route, model=args.model,
                               account_id=args.account_id, replicates=args.replicates,
                               condition=args.condition, intervention=args.intervention, **extra)
        elif command == "typed-dag-prepare":
            result = typed_dag.prepare_stage(al.read_json(args.record))
        elif command == "typed-dag-apply":
            result = typed_dag.apply_stage(al.read_json(args.record), args.source)
        elif command == "typed-dag-report":
            result = typed_dag.report(al.read_json(args.record))
        elif command == "typed-dag-compare":
            result = typed_dag.compare(al.read_json(args.left), al.read_json(args.right))
        else:
            raise al.ApiLabError("unknown typed DAG command")
    elif command.startswith("evidence-"):
        from . import evidence, evidence_workflow
        if command == "evidence-suite":
            result = evidence.build_suite(seed=args.seed)
        elif command in ("evidence-run", "evidence-start", "evidence-demo"):
            suite = al.read_json(args.suite) if args.suite else evidence.build_suite(seed=args.seed)
            if command == "evidence-run":
                result = evidence.run_suite(suite, policy=args.policy, replicates=args.replicates)
            elif command == "evidence-start":
                result = evidence_workflow.start(suite, route=args.route, model=args.model,
                                                 account_id=args.account_id, replicates=args.replicates)
            else:
                result = evidence_workflow.demo(suite, route=args.route, model=args.model,
                                                account_id=args.account_id, replicates=args.replicates,
                                                policy=args.policy)
        elif command == "evidence-prepare":
            result = evidence_workflow.prepare_round(al.read_json(args.record))
        elif command == "evidence-apply":
            result = evidence_workflow.apply_round(al.read_json(args.record), args.source)
        elif command == "evidence-report":
            record = al.read_json(args.record)
            result = (evidence.replay(record) if record.get("schema") == evidence.RUN_SCHEMA
                      else evidence_workflow.report(record))
        elif command == "evidence-compare":
            result = evidence_workflow.compare(al.read_json(args.left), al.read_json(args.right))
        else:
            raise al.ApiLabError("unknown evidence command")
    elif command == "generate":
        result = generators.generate_dataset(args.kind, seed=args.seed, units=args.units)
    elif command == "probes":
        from .conformance import prepare_probes
        result = prepare_probes(args.route, args.model, account_id=args.account_id)
    elif command == "partition-events":
        from .api_tasks import partition_event_cases
        rows = partition_event_cases()
        result = al.prepare_payload(al.Suite({}, rows), rows, route=args.route,
                                    model=args.model, replicates=args.replicates,
                                    account_id=args.account_id)
    elif command == "role-scenarios":
        from . import role_tasks
        result = role_tasks.prepare(args.route, model=args.model, account_id=args.account_id,
                                    replicates=args.replicates, seed=args.seed)
    elif command == "role-report":
        from . import role_tasks
        data = collection.load_collection(args.record)
        al.require(data["plan"]["kind"] == "api-lab", "role-report requires an api-lab collection")
        latest = {attempt["request_id"]: attempt for attempt in data["attempts"]}
        entries = [{"request_id": ident, "response": attempt["parsed"],
                    "http_status": attempt["http_status"], "latency_ms": attempt["elapsed_ms"],
                    **({"error": attempt["state"]} if attempt["state"] != "ok" else {})}
                   for ident, attempt in latest.items()]
        result = role_tasks.evaluate(data["plan"]["manifest"], entries)
        result.update(collection_provenance=data["provenance"],
                      synthetic=data["synthetic"], actual_attempts=len(data["attempts"]))
    elif command == "oracle":
        manifest = al.read_json(args.manifest)
        record = al.build_record(manifest, al.oracle_entries(manifest, mode=args.mode), provenance="synthetic")
        result = {"record": str(al.write_record(args.run_dir, record)), "synthetic": True, "live_verified": False}
    elif command == "rule-workflow":
        dataset = al.read_json(args.dataset) if args.dataset else generators.generate_dataset("rules", seed=args.seed, units=args.units)
        result = rule_workflow.run_rule_workflow(dataset, compiler=args.compiler, control=args.control,
                                                max_rounds=args.max_rounds, uses=args.uses, seed=args.seed,
                                                proposals=al.read_json(args.proposals) if args.proposals else None)
    elif command == "rule-replay":
        result = rule_workflow.replay_workflow(al.read_json(args.record))
    elif command == "plan":
        if args.kind == "api-lab":
            al.require(args.manifest, "api-lab plan requires --manifest")
            result = collection.api_plan(al.read_json(args.manifest))
        else:
            suite = tv.load_suite(args.suite)
            cases = tv.select_cases(suite, case_ids=args.case_id)
            if args.limit is not None:
                al.require(args.limit > 0, "limit must be positive")
                cases = cases[:args.limit]
            result = collection.typed_plan(suite, cases, replicates=args.replicates)
    elif command == "collect":
        result = collection.collect(al.read_json(args.plan), args.run_dir, allow_network=args.allow_network,
                                    max_calls=args.max_calls, max_questions=args.max_questions,
                                    max_estimated_tokens=args.max_estimated_tokens, max_attempts=args.max_attempts,
                                    timeout_s=args.timeout, retry_delay_s=args.retry_delay, seed=args.seed,
                                    resume=args.resume, retry_uncertain=args.retry_uncertain)
        result = {"state": result["state"], "attempts": len(result["attempts"]), "live_verified": False,
                  "record": str(__import__("pathlib").Path(args.run_dir) / "collection.json")}
    elif command == "ledger":
        result = ledger.load_ledger(args.record, suite_path=args.suite)
    elif command == "compare":
        left = ledger.load_ledger(args.left, suite_path=args.suite)
        right = ledger.load_ledger(args.right, suite_path=args.suite)
        left.setdefault("run_id", args.left)
        right.setdefault("run_id", args.right)
        result = comparison.compare_runs(left, right, seed=args.seed, bootstrap_samples=args.bootstrap_samples,
                                         failure_loss=args.failure_loss, split=args.split, condition=args.condition,
                                         plan=al.read_json(args.analysis_plan) if args.analysis_plan else None)
    elif command == "freeze-plan":
        result = comparison.freeze_analysis_plan(dataset_id=args.dataset_id, comparison=[args.left, args.right],
                                                 failure_loss=args.failure_loss, split=args.split,
                                                 condition=args.condition)
    else:
        raise al.ApiLabError("unknown research command")
    if getattr(args, "output", None):
        path = al._safe_output(args.output)
        al._write(path, result)
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
        sp.add_argument("--account-id", help="Cloudflare account ID; required for Clef routes")
        sp.add_argument("--replicates", type=int, default=1)
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

    research = sub.add_parser("research", help="offline research generation, evidence and comparison; opt-in collection")
    rs = research.add_subparsers(dest="research_command", required=True)
    def research_parser(name):
        parser = rs.add_parser(name)
        parser.add_argument("--output", help="new local JSON file; source tree restricted to runs/")
        parser.set_defaults(func=_cmd_research)
        return parser
    sp = research_parser("typed-dag-suite")
    sp.add_argument("--seed", type=int, default=0)
    for name in ("typed-dag-start", "typed-dag-demo"):
        sp = research_parser(name)
        sp.add_argument("--suite", help="retained typed DAG task design")
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--replicates", type=int, default=1)
        sp.add_argument("--condition", choices=("direct", "fields-only", "source-linked"), default="fields-only")
        sp.add_argument("--intervention", choices=("extraction", "calculation", "retrieval"))
        if name == "typed-dag-demo":
            sp.add_argument("--policy", choices=("oracle", "wrong-field", "wrong-evidence", "wrong-version", "wrong-decision"), default="oracle")
        sp.add_argument("--route", choices=al.ROUTES, default="decisions")
        sp.add_argument("--model")
        sp.add_argument("--account-id")
    for name in ("typed-dag-prepare", "typed-dag-apply", "typed-dag-report"):
        sp = research_parser(name)
        sp.add_argument("record", help="retained typed DAG workflow JSON")
        if name == "typed-dag-apply":
            sp.add_argument("source", help="retained native record or collection from this stage")
    sp = research_parser("typed-dag-compare")
    sp.add_argument("left")
    sp.add_argument("right")
    sp = research_parser("evidence-suite")
    sp.add_argument("--seed", type=int, default=0)
    for name in ("evidence-run", "evidence-start", "evidence-demo"):
        sp = research_parser(name)
        sp.add_argument("--suite", help="finite evidence suite; otherwise use the original synthetic design")
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--replicates", type=int, default=1)
        if name in ("evidence-run", "evidence-demo"):
            sp.add_argument("--policy", choices=("checklist", "stop", "myopic", "optimal"), default="optimal")
        if name != "evidence-run":
            sp.add_argument("--route", required=name == "evidence-start", default="decisions", choices=al.ROUTES)
            sp.add_argument("--model")
            sp.add_argument("--account-id")
    for name in ("evidence-prepare", "evidence-apply", "evidence-report"):
        sp = research_parser(name)
        sp.add_argument("record", help="retained evidence workflow or synthetic run JSON")
        if name == "evidence-apply":
            sp.add_argument("source", help="api-lab record or collection from this exact round")
    sp = research_parser("evidence-compare")
    sp.add_argument("left")
    sp.add_argument("right")
    sp = research_parser("probes")
    sp.add_argument("--route", required=True, choices=al.ROUTES)
    sp.add_argument("--model")
    sp.add_argument("--account-id")
    sp = research_parser("partition-events")
    sp.add_argument("--route", required=True, choices=al.ROUTES)
    sp.add_argument("--model")
    sp.add_argument("--account-id")
    sp.add_argument("--replicates", type=int, default=1)
    sp = research_parser("role-scenarios")
    sp.add_argument("--route", required=True, choices=al.ROUTES)
    sp.add_argument("--model")
    sp.add_argument("--account-id")
    sp.add_argument("--replicates", type=int, default=2)
    sp.add_argument("--seed", type=int, default=20261024)
    sp = research_parser("role-report")
    sp.add_argument("record")
    sp = research_parser("oracle")
    sp.add_argument("--manifest", required=True)
    sp.add_argument("--mode", choices=("perfect", "uniform", "wrong"), default="perfect")
    sp.add_argument("--run-dir", required=True)
    sp = research_parser("generate")
    sp.add_argument("--kind", required=True, choices=("probability", "documents", "rules", "geometry"))
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--units", type=int, default=20)
    sp = research_parser("rule-workflow")
    sp.add_argument("--dataset")
    sp.add_argument("--proposals")
    sp.add_argument("--compiler", choices=("imperfect", "exact", "memorize"), default="imperfect")
    sp.add_argument("--control", choices=("counterexample", "repeated-original", "random-feedback"), default="counterexample")
    sp.add_argument("--max-rounds", type=int, default=8)
    sp.add_argument("--uses", type=int, default=100)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--units", type=int, default=20)
    sp = research_parser("rule-replay")
    sp.add_argument("record")
    sp = research_parser("plan")
    sp.add_argument("--kind", required=True, choices=("api-lab", "typed-values"))
    sp.add_argument("--manifest")
    sp.add_argument("--suite", default=tv.DEFAULT_SUITE)
    sp.add_argument("--case-id", action="append")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--replicates", type=int, default=1)
    sp = research_parser("collect")
    sp.add_argument("plan")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--allow-network", action="store_true")
    sp.add_argument("--max-calls", required=True, type=int)
    sp.add_argument("--max-questions", required=True, type=int)
    sp.add_argument("--max-estimated-tokens", required=True, type=int)
    sp.add_argument("--max-attempts", type=int, default=1)
    sp.add_argument("--timeout", type=float, default=30)
    sp.add_argument("--retry-delay", type=float, default=1)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--resume", action="store_true")
    sp.add_argument("--retry-uncertain", action="store_true")
    sp = research_parser("ledger")
    sp.add_argument("record")
    sp.add_argument("--suite")
    sp = research_parser("compare")
    sp.add_argument("left")
    sp.add_argument("right")
    sp.add_argument("--suite")
    sp.add_argument("--split")
    sp.add_argument("--condition")
    sp.add_argument("--analysis-plan")
    sp.add_argument("--failure-loss", type=float, default=1.0)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--bootstrap-samples", type=int, default=2000)
    sp = research_parser("freeze-plan")
    sp.add_argument("--dataset-id", required=True)
    sp.add_argument("--left", required=True)
    sp.add_argument("--right", required=True)
    sp.add_argument("--split", default="test")
    sp.add_argument("--condition")
    sp.add_argument("--failure-loss", type=float, default=1.0)

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
    except (CaseError, RecordError, tv.TypedValuesError, al.ApiLabError, KeyError, ValueError) as exc:
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
