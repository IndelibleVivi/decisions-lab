"""Query the dated research catalogue without network access."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    index = json.loads((ROOT / "catalog/index.json").read_text(encoding="utf-8"))
    source = ROOT / index["source_root"]
    return index, {name: json.loads((source / f"{name}.json").read_text(encoding="utf-8"))
                   for name in ("census", "repositories", "source_index", "watchlist")}


def project_markdown():
    index, data = load()
    records = {r["id"]: r for r in data["repositories"]["repositories"]}
    lines = ["# 相关项目地图", "", f"> 来源截点：{index['snapshot']}。以下审读深度来自该期调查；未在本项目重新运行上游测试或模型。", "",
             "从要解决的问题选择阅读入口。模型、SDK、运行时和评测仓库分别归类；兼容接口不保证语义、质量或许可相同。", ""]
    latest = index.get("latest_update")
    if latest:
        lines += [f"新变化与新用法另见 [{latest['date']} 定向增量](../{latest['reader']}) 和 [妙妙玩法配方册](playbook.md)。下面仍是 {index['snapshot']} 的项目地图，不将旧审读自动标为新验证。", ""]
    for group in index["groups"]:
        lines += [f"## {group['title']}", "", group["question"], "",
                  "| 项目 | 值得看什么 | 调查读到了哪里 |", "| --- | --- | --- |"]
        for key in group["projects"]:
            r = records[key]
            name = r["repo"].removeprefix("https://github.com/")
            lines.append(f"| [{name}]({r['repo']}) | {r['summary_value']} | {r['summary_inspection']} |")
        lines.append("")
        for key in group["projects"]:
            r = records[key]
            if r.get("limits"):
                lines += [f"**{r['repo'].split('/')[-1]} 的边界：** {index.get('editorial_limits_zh', {}).get(key, r['limits'])}", ""]
    lines += ["## 继续追踪的线索", "", "以下线索尚未达到已核实体或代码审读的相同证据深度。保留线索，避免把列表中的名字当成已验证产品。", ""]
    for r in data["watchlist"]["unverified_candidates"]:
        label = f"[{r['name']}]({r['lead_url']})" if r.get("lead_url") else r["name"]
        lines += [f"- **{label}**：{index.get('editorial_watchlist_zh', {}).get(r['name'], r['status'])}"]
    lines += ["", "完整固定 revision、源码位置、机制、许可与局限见 [结构化项目记录](../research/2026-10-08/repositories.json)。",
              "此页由 `python3 tools/catalog.py render` 从 catalog 的分组和日期快照生成；修订事实应进入有日期的新证据。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("models", "projects", "sources", "watchlist", "updates", "recipes", "capabilities", "render"))
    parser.add_argument("--query", default="", help="case-insensitive substring across the complete record")
    parser.add_argument("--json", action="store_true", help="return complete matching records")
    parser.add_argument("--date", help="select a recorded update date (updates only; default: latest)")
    args = parser.parse_args()
    index, data = load()
    if args.date and args.kind != "updates":
        parser.error("--date is supported only for updates; other catalogs retain their own source date")
    if args.kind == "render":
        target = ROOT / "docs/projects.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(project_markdown(), encoding="utf-8")
        print("Generated docs/projects.md from dated sources.")
        return
    as_of = index["snapshot"]
    records = {"models": data["census"]["entities"],
               "projects": data["repositories"]["repositories"],
               "sources": data["source_index"]["sources"],
               "watchlist": data["watchlist"]["unverified_candidates"]}.get(args.kind)
    if args.kind == "updates":
        selected = index["latest_update"]
        if args.date:
            history = {entry["date"]: entry for entry in index["update_history"]}
            if args.date not in history:
                parser.error("unknown update date; available: " + ", ".join(sorted(history)))
            selected = history[args.date]
        update = json.loads((ROOT / selected["path"]).read_text(encoding="utf-8"))
        records, as_of = update["changes"], update["checked_at"]
    elif args.kind == "recipes":
        book = json.loads((ROOT / index["recipes"]).read_text(encoding="utf-8"))
        records, as_of = book["recipes"], book["updated_at"]
    elif args.kind == "capabilities":
        book = json.loads((ROOT / index["capabilities"]).read_text(encoding="utf-8"))
        records, as_of = book["capabilities"], book["checked_at"]
    hits = [r for r in records if args.query.casefold() in json.dumps(r, ensure_ascii=False).casefold()]
    if args.json:
        print(json.dumps({"as_of": as_of, "kind": args.kind, "count": len(hits), "records": hits}, ensure_ascii=False, indent=2))
    else:
        print(f"{args.kind}: {len(hits)} records · as of {as_of}")
        for r in hits:
            print(r.get("id", r.get("title", r.get("name", ""))), "—", r.get("title", r.get("name", r.get("repo", r.get("url", "")))))


if __name__ == "__main__":
    main()
