"""Import the explicit public research allowlist, never the companion chat log.

The destination must not exist. The ZIP is data: no bundled code is executed.
Install tools/requirements-import.txt only when reimporting a research bundle.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import zipfile

DATA = (
    "census.json", "repositories.json", "practice_evidence.json",
    "source_index.json", "openai_decisions_record.json", "llamacpp_route.json",
    "openrouter_routes.json", "watchlist.json", "public_probe_protocol.json",
    "metadata.json", "verification.json", "report_verification.json",
    "calculations.json", "reanalysis/provenance.json",
    "reanalysis/author_numbers.json", "reanalysis/sys1_reanalysis.json",
)
SCRIPTS = ("calculations.py", "reanalysis/recompute_sys1.py")
SECTIONS = ("findings", "scope", "contracts", "economics", "reanalysis",
            "studies", "repositories", "practice", "decisions")


def portable(value):
    if isinstance(value, dict):
        return {k: portable(v) for k, v in value.items()
                if not (k == "ref" and isinstance(v, str) and v.startswith("turn"))
                and not (k == "output" and isinstance(v, str) and v.startswith("/workspace/"))}
    if isinstance(value, list):
        return [portable(v) for v in value]
    if isinstance(value, str):
        return (value.replace("parent supplied Kev-derivative lead", "a Kev-derivative research lead")
                .replace("Parent research lead", "Research discovery lead")
                .replace("parent evalworkstreammayinspect", "not deeply inspected in this snapshot")
                .replace("core/sources.json", "source_index.json"))
    return value


def import_snapshot(bundle: Path, dest: Path):
    from bs4 import BeautifulSoup
    from markdownify import markdownify

    if dest.exists():
        raise ValueError(f"Destination already exists: {dest}")
    with zipfile.ZipFile(bundle) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        required = (*DATA, *SCRIPTS, "decision_api_research_2026-10-08.html")
        missing = set(required) - set(names)
        if missing:
            raise ValueError(f"Missing entries: {sorted(missing)}")
        if any(z.getinfo(n).file_size > 2_000_000 for n in required):
            raise ValueError("Oversized research entry")
        prepared = {n: json.dumps(portable(json.loads(z.read(n))), ensure_ascii=False, indent=2) + "\n"
                    for n in DATA}
        prepared.update({n: z.read(n).decode("utf-8") for n in SCRIPTS})
        soup = BeautifulSoup(z.read("decision_api_research_2026-10-08.html"), "html.parser")
        sources = {}
        for node in soup.select("[id]"):
            link = node.find("a", href=re.compile(r"^https://"))
            if link and node["id"].startswith(("src-", "source-")):
                sources["#" + node["id"]] = link["href"]
        sections = []
        for section_id in SECTIONS:
            section = soup.find("section", id=section_id)
            if not section:
                raise ValueError(f"Missing report section {section_id}")
            for a in section.find_all("a", href=True):
                if a["href"] in sources:
                    a["href"] = sources[a["href"]]
            sections.append(markdownify(str(section), heading_style="ATX"))
        report = "# Decision Models & APIs · 2026-10-08\n\n"
        report += "> 研究截点：2026-10-08 UTC。2026-10-09 整理为可维护的公开版。报价与产品状态属于该日期快照；本轮没有新的模型推理。\n\n"
        report += "\n\n".join(sections)
        report += ("\n\n## 数据与复现入口\n\n"
                   "完整结构化记录和阅读顺序见 [本期说明](README.md)。"
                   "来源记录见 [source_index.json](source_index.json)，"
                   "待核线索见 [watchlist.json](watchlist.json)。"
                   "历史逐条模型响应不随仓库分发；复算方法与输入条件见本期说明。\n")
        unresolved = re.findall(r"\]\((#(?:src|source)-[^)]+)\)", report)
        if unresolved:
            raise ValueError(f"Unresolved report sources: {unresolved[:5]}")
        report = re.sub(r"(\*\*[^*\n]+\*\*)(?=[\w\u4e00-\u9fff])", r"\1 ", report)
        prepared["report.md"] = report
        prepared["import-manifest.json"] = json.dumps({
            "schema": "decisions-lab.snapshot-import/1", "source_cutoff": "2026-10-08",
            "edited_on": "2026-10-09", "included": sorted(prepared),
            "excluded": ["companion conversation", "raw historical prediction projection",
                         "original absolute build path", "internal browser reference ids",
                         "original ZIP checksum manifest"],
            "transformations": ["nine HTML narrative sections converted to Markdown",
                                "numbered source anchors resolved to canonical URLs",
                                "internal orchestration wording made reader-facing",
                                "original report appendix records retained in structured JSON"],
            "claim_boundary": "Import does not reverify provider facts or run models."
        }, ensure_ascii=False, indent=2) + "\n"
        dest.mkdir(parents=True)
        for name, content in prepared.items():
            path = dest / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return len(prepared)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = import_snapshot(args.bundle, args.dest)
    except (ValueError, KeyError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"Import failed: {exc}\n")
    print(f"Imported {count} files to {args.dest}; no inference or bundled code executed.")
