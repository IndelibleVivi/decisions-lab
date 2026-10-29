"""Local research sessions. No transport, credentials, or provider execution."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

from . import api_lab as al, api_tasks, collection, evidence, evidence_workflow as ew, typed_dag as td
from . import interpretation

SCHEMA = "decisions-lab.study/1"
BUNDLE_SCHEMA = "decisions-lab.study-bundle/1"
ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 32 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def clone(value):
    return copy.deepcopy(value)


def seal(value):
    value["digest"] = al.digest({k: v for k, v in value.items() if k != "digest"})
    return value


def check_seal(value):
    al.require(isinstance(value, dict) and value.get("digest") == al.digest(
        {k: v for k, v in value.items() if k != "digest"}), "study integrity mismatch")


def imported_json(data, key):
    """Keep native JSON numbers intact across a browser upload."""
    if key + "_json" not in data:
        return data[key]
    raw = data[key + "_json"]
    al.require(isinstance(raw, str), "import must contain JSON text")
    return json.loads(raw, object_pairs_hook=collection._strict_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def template(kind):
    common = {"kind": kind, "replicates": 1, "hypotheses": "", "next_question": ""}
    if kind == "api-lab":
        rows = [r for r in api_tasks.all_cases() if r["experiment"] == "probability"]
        return {**common, "title": "相同事件，不同测量", "question": "原生路线改变时，事件概率误差是否仍然可比较？",
                "hypotheses": "H1：相同事件的数值误差可配对。\nH2：原生 confidence 的含义不足以支持共同门槛。",
                "cases": rows,
                "conditions": [{"id": "a", "label": "精确 oracle · Decisions", "route": "decisions", "policy": "perfect"},
                               {"id": "b", "label": "均匀对照 · Jev", "route": "jev", "policy": "uniform"}]}
    if kind == "active-evidence":
        return {**common, "title": "何时值得继续取证", "question": "一步 VOI 会错过互补证据吗？",
                "suite": evidence.build_suite(seed=20261029),
                "conditions": [{"id": "a", "label": "一步 VOI", "route": "decisions", "policy": "myopic"},
                               {"id": "b", "label": "多步 oracle", "route": "decisions", "policy": "optimal"}]}
    if kind == "typed-dag":
        return {**common, "title": "字段相同，决定不同", "question": "正确抽取能否弥补 schema 中缺失的证据？",
                "suite": td.build_suite(seed=20261029),
                "conditions": [{"id": "a", "label": "仅字段", "route": "decisions", "policy": "oracle", "arm": "fields-only"},
                               {"id": "b", "label": "来源回查 · gold", "route": "decisions", "policy": "oracle", "arm": "source-linked", "intervention": "retrieval"}]}
    raise al.ApiLabError("unknown research family")


def initial_records(definition):
    """Compile frozen treatments, preserving unsupported native conditions as errors."""
    al.require(isinstance(definition, dict), "definition must be an object")
    kind = definition.get("kind")
    al.require(kind in ("api-lab", "active-evidence", "typed-dag"), "unknown research family")
    for field in ("title", "question"):
        al.require(isinstance(definition.get(field), str) and definition[field].strip(), f"{field} is required")
        al.require(len(definition[field]) <= 2000, f"{field} is too long")
    reps = definition.get("replicates")
    al.require(type(reps) is int and 1 <= reps <= 10, "replicates must be 1–10")
    conditions = definition.get("conditions")
    al.require(isinstance(conditions, list) and 2 <= len(conditions) <= 6, "use 2–6 conditions")
    records = {}
    for condition in conditions:
        al.require(isinstance(condition, dict), "condition must be an object")
        ident = condition.get("id")
        al.require(isinstance(ident, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,30}", ident)
                   and ident not in records, "condition IDs must be unique safe identifiers")
        al.require(isinstance(condition.get("label"), str) and condition["label"].strip(), "condition label required")
        route = condition.get("route")
        kwargs = {"route": route, "model": condition.get("model") or None,
                  "account_id": condition.get("account_id") or None, "replicates": reps}
        policy = condition.get("policy")
        if kind == "api-lab":
            al.require(policy in ("perfect", "uniform", "wrong"), "invalid API control policy")
            rows = definition.get("cases")
            al.require(isinstance(rows, list) and 0 < len(rows) <= 120, "use 1–120 authoring cases")
            manifest = al.prepare_payload(al.Suite({}, rows), rows, **kwargs)
            records[ident] = al.build_record(manifest, [], provenance="imported", allow_partial=True)
        elif kind == "active-evidence":
            al.require(policy in evidence.POLICIES, "invalid evidence control policy")
            records[ident] = ew.start(definition["suite"], **kwargs)
        else:
            al.require(policy in td.DEMO_POLICIES, "invalid DAG control policy")
            records[ident] = td.start(definition["suite"], condition=condition.get("arm", "fields-only"),
                                     intervention=condition.get("intervention"), **kwargs)
    return records


def run_control(definition, condition, initial):
    kwargs = {"route": initial.get("route"), "model": initial.get("model"),
              "account_id": initial.get("account_id"), "replicates": definition["replicates"]}
    if definition["kind"] == "api-lab":
        manifest = initial["manifest"]
        return al.build_record(manifest, al.oracle_entries(manifest, condition["policy"]), provenance="synthetic")
    if definition["kind"] == "active-evidence":
        return ew.demo(definition["suite"], policy=condition["policy"], **kwargs)
    return td.demo(definition["suite"], condition=initial["condition"], intervention=initial["intervention"],
                   policy=condition["policy"], **kwargs)


def native_plan(record):
    if record["schema"] == collection.SCHEMA:
        return record["plan"]["manifest"]
    if record["schema"] == al.RECORD_VERSION:
        return record["manifest"]
    if record["schema"] == ew.SCHEMA:
        return ew.prepare_round(record)
    return td.prepare_stage(record)


def bind_import(initial, current, value):
    """Bind a full workflow or next native round to the exact frozen treatment."""
    al.require(isinstance(value, dict), "import must be a JSON object")
    if initial["schema"] == al.RECORD_VERSION:
        if value.get("schema") == al.RESPONSE_VERSION:
            value = al.build_record(initial["manifest"], value["responses"], provenance="imported",
                                    allow_partial=True, imported_synthetic=value.get("synthetic"))
        interpretation.evaluate_record(value)
        manifest = value.get("plan", {}).get("manifest") if value.get("schema") == collection.SCHEMA else value.get("manifest")
        al.require(value.get("schema") in (al.RECORD_VERSION, collection.SCHEMA) and manifest == initial["manifest"],
                   "import does not match this frozen native manifest")
    elif value.get("schema") == initial["schema"]:
        for key in initial:
            if key not in ("rounds", "evidence_digest"):
                al.require(value.get(key) == initial[key], f"workflow differs from frozen {key}")
        interpretation.evaluate_record(value)
    else:
        value = ew.apply_round(current, value) if initial["schema"] == ew.SCHEMA else td.apply_stage(current, value)
    return clone(value)


class Store:
    """Atomic JSON storage, local-source interpreter registry, and revision checks."""
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        if self.root.is_relative_to(ROOT):
            al.require(self.root != ROOT and self.root.relative_to(ROOT).parts[0] == "runs",
                       "Studio workspace inside the repository must be under runs/")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.studies = self.root / "studies"
        self.sources = self.root / "interpreters"
        self.studies.mkdir(exist_ok=True, mode=0o700)
        self.sources.mkdir(exist_ok=True, mode=0o700)

    def _path(self, ident):
        al.require(isinstance(ident, str) and re.fullmatch(r"[a-f0-9]{32}", ident), "invalid study ID")
        path = self.studies / (ident + ".json")
        al.require(not path.is_symlink(), "symlink study refused")
        return path

    def _save(self, study):
        study["updated_at"] = now()
        seal(study)
        raw = json.dumps(study, ensure_ascii=False, indent=2, allow_nan=False)
        al.require(len(raw.encode()) <= MAX_BYTES, "study exceeds 32 MiB; export before starting a new session")
        fd, name = tempfile.mkstemp(prefix=".study-", dir=self.studies)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self._path(study["id"]))
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return clone(study)

    def get(self, ident):
        try:
            study = al.read_json(self._path(ident))
        except FileNotFoundError as exc:
            raise al.ApiLabError("study not found") from exc
        check_seal(study)
        return study

    def list(self):
        result = []
        for path in sorted(self.studies.glob("*.json")):
            study = self.get(path.stem)
            result.append({"id": study["id"], "title": study["definition"]["title"], "kind": study["definition"]["kind"],
                           "state": study["state"], "revision": study["revision"], "updated_at": study["updated_at"],
                           "analyses": len(study["analyses"])})
        return sorted(result, key=lambda x: x["updated_at"], reverse=True)

    def _new(self, definition, parent=None):
        initial_records(definition)
        return self._save({"schema": SCHEMA, "id": uuid.uuid4().hex, "revision": 1, "created_at": now(),
                           "state": "draft", "definition": clone(definition), "parent": parent,
                           "frozen": None, "runs": {}, "analyses": [], "notes": []})

    def snapshot(self):
        files = {path.name: path.read_bytes() for path in sorted(Path(__file__).parent.glob("*.py"))}
        manifest = {"python": sys.version, "implementation": sys.implementation.name,
                    "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
        ident = al.digest(manifest)
        directory = self.sources / ident
        if not directory.exists():
            stage = Path(tempfile.mkdtemp(prefix=".source-", dir=self.sources))
            (stage / "decision_lab").mkdir()
            for name, raw in files.items():
                (stage / "decision_lab" / name).write_bytes(raw)
            (stage / "interpreter.json").write_text(json.dumps(manifest), encoding="utf-8")
            os.rename(stage, directory)
        return {"id": ident, **manifest}

    def _historical(self, source, payload):
        ident = source.get("id")
        al.require(isinstance(ident, str) and re.fullmatch(r"[a-f0-9]{64}", ident), "invalid interpreter ID")
        directory = self.sources / ident
        al.require(directory.is_dir() and not directory.is_symlink(),
                   "original interpreter unavailable here; imported bundles never install executable code")
        manifest = al.read_json(directory / "interpreter.json")
        al.require(al.digest(manifest) == ident and source == {"id": ident, **manifest}, "interpreter identity mismatch")
        al.require(manifest["python"] == sys.version, "original Python runtime differs; historical reproduction unavailable")
        package = directory / "decision_lab"
        al.require(not package.is_symlink(), "symlink interpreter refused")
        al.require(set(p.name for p in package.glob("*.py")) == set(manifest["files"]), "interpreter file set changed")
        for name, digest in manifest["files"].items():
            al.require(re.fullmatch(r"[a-z_]+\.py", name), "unsafe interpreter filename")
            path = package / name
            al.require(not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                       "retained interpreter source changed")
        # -I ignores user site and PYTHONPATH; this path comes only from the local registry.
        script = "import sys,json;sys.path.insert(0,sys.argv[1]);from decision_lab.interpretation import analyse;print(json.dumps(analyse(json.load(sys.stdin)),ensure_ascii=False,allow_nan=False))"
        result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(directory)],
                                input=json.dumps(payload), text=True, capture_output=True, timeout=45)
        al.require(result.returncode == 0, "retained interpreter failed: " + result.stderr[-1600:])
        return json.loads(result.stdout)

    def _payload(self, study, run_ids=None):
        selected = {}
        for ident, runs in study["runs"].items():
            selected[ident] = next((r for r in runs if run_ids and r["id"] == run_ids.get(ident)), None) if run_ids else runs[-1]
            al.require(selected[ident] is not None, "analysis references missing evidence")
        return {"records": {key: value["record"] for key, value in selected.items()},
                "pairings": study["frozen"].get("pairings", {})}, {key: value["id"] for key, value in selected.items()}

    def _analyse(self, study, mode="current", original=None):
        payload, ids = self._payload(study, original["run_ids"] if original else None)
        source = original["interpreter"] if mode == "historical" else self.snapshot()
        result = self._historical(source, payload) if mode == "historical" else interpretation.analyse(payload)
        item = {"id": uuid.uuid4().hex, "created_at": now(), "mode": mode, "interpreter": source,
                "run_ids": ids, "result": result, "basis": original["id"] if original else None,
                "diff": interpretation.differences(original["result"], result) if original else None}
        study["analyses"].append(item)
        return item

    def command(self, action, data):
        # One writer per workspace, including two Studio server processes.
        with (self.root / ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self._command(action, data)

    def _command(self, action, data):
        if action == "create":
            return self._new(data.get("definition") or template(data.get("kind", "api-lab")))
        if action == "import-bundle":
            bundle = imported_json(data, "bundle")
            al.require(isinstance(bundle, dict) and bundle.get("schema") == BUNDLE_SCHEMA, "invalid study bundle")
            study = clone(bundle["study"])
            check_seal(study)
            al.require(study.get("schema") == SCHEMA and study.get("state") in ("draft", "frozen"), "invalid study schema")
            compiled = initial_records(study["definition"])
            if study["state"] == "frozen":
                al.require(study["frozen"]["design_digest"] == al.digest(study["definition"]), "frozen design changed")
                al.require(set(compiled) == set(study["frozen"]["initial"]) == set(study["runs"]), "bundle conditions differ")
                for ident, expected in compiled.items():
                    retained = study["frozen"]["initial"][ident]
                    if expected["schema"] == al.RECORD_VERSION:
                        al.require(expected["manifest"] == retained.get("manifest"), "bundle design and manifest disagree")
                    else:
                        al.require(expected == retained, "bundle design and workflow disagree")
                for ident, runs in study["runs"].items():
                    al.require(ident in study["frozen"]["initial"], "foreign condition in bundle")
                    al.require(isinstance(runs, list) and runs, "empty run history")
                    for run in runs:
                        bind_import(study["frozen"]["initial"][ident], study["frozen"]["initial"][ident], run["record"])
            for analysis in study["analyses"]:
                analysis["origin"] = "imported report; not independently authenticated"
                self._payload(study, analysis["run_ids"])
            study.update(id=uuid.uuid4().hex, revision=1, parent={"kind": "import", "id": study["id"]})
            if study["state"] == "frozen":
                self._analyse(study)
            return self._save(study)
        study = self.get(data.get("id"))
        al.require(data.get("revision") == study["revision"], "revision conflict: reopen the study before saving")
        if action == "fork":
            return self._new(study["definition"], {"kind": "fork", "id": study["id"], "revision": study["revision"]})
        if action == "save":
            al.require(study["state"] == "draft", "design is frozen; fork to change conditions")
            initial_records(data["definition"])
            study["definition"] = clone(data["definition"])
        elif action == "freeze":
            al.require(study["state"] == "draft", "already frozen")
            initial = initial_records(study["definition"])
            pairings = {}
            if study["definition"]["kind"] == "api-lab":
                from . import comparison, ledger
                keys = list(initial)
                projections = {key: ledger.from_api(value["manifest"], [], metadata={"synthetic": None, "provenance": "imported"}) for key, value in initial.items()}
                for key in keys[1:]:
                    pairings[key] = comparison.make_pairing_spec(projections[keys[0]], projections[key])
            study["state"] = "frozen"
            study["frozen"] = {"at": now(), "design_digest": al.digest(study["definition"]), "initial": initial,
                               "pairings": pairings, "interpreter": self.snapshot()}
            study["runs"] = {key: [{"id": uuid.uuid4().hex, "created_at": now(), "origin": "planned", "record": value}] for key, value in initial.items()}
            self._analyse(study)
        elif action in ("run", "import-record"):
            al.require(study["state"] == "frozen", "freeze the design first")
            conditions = study["definition"]["conditions"]
            if action == "run":
                for condition in conditions:
                    ident = condition["id"]
                    value = run_control(study["definition"], condition, study["frozen"]["initial"][ident])
                    study["runs"][ident].append({"id": uuid.uuid4().hex, "created_at": now(), "origin": "synthetic control", "record": value})
            else:
                ident = data.get("condition")
                al.require(ident in study["runs"], "unknown condition")
                value = bind_import(study["frozen"]["initial"][ident], study["runs"][ident][-1]["record"], imported_json(data, "record"))
                study["runs"][ident].append({"id": uuid.uuid4().hex, "created_at": now(), "origin": "user import", "record": value})
            self._analyse(study)
        elif action in ("reanalyse", "reproduce"):
            original = next((a for a in study["analyses"] if a["id"] == data.get("analysis")), None)
            al.require(original is not None, "choose a retained analysis")
            self._analyse(study, "historical" if action == "reproduce" else "current", original)
        elif action == "note":
            text = data.get("text")
            al.require(isinstance(text, str) and 0 < len(text.strip()) <= 20000, "note requires 1–20000 characters")
            analysis = data.get("analysis")
            al.require(analysis is None or any(a["id"] == analysis for a in study["analyses"]), "unknown analysis")
            study["notes"].append({"id": uuid.uuid4().hex, "at": now(), "text": text,
                                   "analysis": analysis, "counterexample": data.get("counterexample") or None})
        else:
            raise al.ApiLabError("unknown Studio action")
        study["revision"] += 1
        return self._save(study)

    def export(self, ident):
        return {"schema": BUNDLE_SCHEMA, "study": self.get(ident),
                "notice": "Local evidence export. No executable interpreter is included. Review before sharing; may contain private inputs."}
