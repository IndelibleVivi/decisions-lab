"""Original synthetic tasks; editorial truth never enters native request bodies."""
from __future__ import annotations

import base64
import struct
import zlib

EXPERIMENTS = ("rule-compile", "probability", "visual-criteria")
STATES = ("00", "01", "10", "11")


def table(index):
    return "".join(str((index >> bit) & 1) for bit in range(4))


def _rule_text(index, style):
    names = ("A", "B") if style == 0 else ("P", "Q")
    selected = [state for pos, state in enumerate(STATES)
                if bool((index >> pos) & 1) == (style == 0)]
    terms = ["（" + "且".join(f"{name}{'成立' if bit == '1' else '不成立'}"
                             for name, bit in zip(names, state)) + "）"
             for state in selected]
    if style == 0:
        text = "仅当" + "或".join(terms) + "时触发；其他情况不触发。" if terms else "所有情况下都不触发。"
    else:
        text = "只要" + "或".join(terms) + "就不触发；除此之外触发。" if terms else "所有情况下都触发。"
    return text, names


def _choice(qid, instructions, choices, expected=None, acceptable=None, **extra):
    question = {"id": qid, "type": "choice", "instructions": instructions,
                "choices": [{"value": value, "description": desc} for value, desc in choices]}
    grade = {"kind": "choice", "acceptable": acceptable if acceptable is not None else [expected]}
    grade.update(extra)
    return question, grade


def _case(ident, experiment, input_value, questions, grades, **meta):
    return {"id": ident, "experiment": experiment, "input": input_value,
            "questions": questions, "rubric": {"questions": grades, **meta}}


def rule_cases():
    cases = []
    rules = [(index, 0) for index in range(16)] + [(index, 1) for index in range(8)]
    for index, style in rules:
        text, names = _rule_text(index, style)
        group = f"r{index:02d}-w{style}"
        for condition in ("baseline", "reversed", "opaque"):
            ids = [f"x{(i * 7 + 3) % 16:02d}" if condition == "opaque" else f"f{i:02d}"
                   for i in range(16)]
            choices = [(ids[i], f"顺序 00,01,10,11 的完整真值表为 {table(i)}")
                       for i in range(16)] + [("insufficient", "多个函数均满足输入约束，无法唯一确定。")]
            if condition == "reversed":
                choices.reverse()
            q, grade = _choice("function", "选择满足全部规则的唯一函数；若无法唯一确定，选 insufficient。",
                               choices, ids[index])
            cases.append(_case(f"{group}-compile-{condition}", "rule-compile", text, [q],
                               {"function": grade}, group=group, function_index=index,
                               structure="compiled", condition=condition, wording=style,
                               truth_table=table(index), choice_tables=dict(zip(ids, map(table, range(16))))))
        questions, grades = [], {}
        for pos, state in enumerate(STATES):
            qid = "s" + state
            questions.append({"id": qid, "type": "predicate",
                              "instructions": f"当 {names[0]}={state[0]}，{names[1]}={state[1]} 时，规则是否触发？"})
            grades[qid] = {"kind": "boolean", "expected": table(index)[pos] == "1"}
        cases.append(_case(f"{group}-apply", "rule-compile", text, questions, grades,
                           group=group, function_index=index, structure="per-state",
                           condition="baseline", wording=style, truth_table=table(index)))
    q, grade = _choice("function", "选择输入约束唯一确定的函数；如果有多个函数均相容，选 insufficient。",
                       [(f"f{i:02d}", f"顺序 00,01,10,11 的真值表为 {table(i)}") for i in range(16)]
                       + [("insufficient", "无法唯一确定一个函数。")], "insufficient")
    cases.append(_case("rule-necessary-only", "rule-compile", "只有 A 成立，才允许触发。", [q],
                       {"function": grade}, group="necessary", structure="underspecified",
                       condition="baseline", compatible_tables=[table(i) for i in range(16) if table(i)[:2] == "00"]))
    return cases


def world_truth(world):
    return {"a": world["10"] + world["11"], "b": world["01"] + world["11"],
            "and": world["11"], "or": 1 - world["00"], "xor": world["01"] + world["10"]}


def probability_cases():
    worlds = {"correlated": dict(zip(STATES, (.5, 0., 0., .5))),
              "anticorrelated": dict(zip(STATES, (0., .5, .5, 0.))),
              "split": dict(zip(STATES, (.2, .2, .3, .3)))}
    labels = {"a": "A=1", "b": "B=1", "and": "A=1 且 B=1",
              "or": "A=1 或 B=1", "xor": "A≠B"}
    numeric_choices = [(f"{i / 10:.1f}", f"{i / 10:.1f}") for i in range(11)]
    cases = []
    for group, world in worlds.items():
        text = ("每次抽样得到一个二值状态；00 表示 A=0,B=0，01 表示 A=0,B=1，"
                "10 表示 A=1,B=0，11 表示 A=1,B=1。四个互斥且穷尽状态的概率："
                + "，".join(f"{key}={world[key]:.1f}" for key in STATES) + "。")
        truth = world_truth(world)
        questions, grades = [], {}
        for key, label in labels.items():
            q, grade = _choice("p_" + key, f"事件「{label}」的概率是多少？", numeric_choices,
                               f"{truth[key]:.1f}", event=key, numeric_truth=truth[key])
            questions.append(q); grades[q["id"]] = grade
            cases.append(_case(f"prob-{group}-single-{key}", "probability", text, [q],
                               {q["id"]: grade}, group=group, condition="single", world=world))
        cases.append(_case(f"prob-{group}-bundled", "probability", text, questions, grades,
                           group=group, condition="bundled", world=world))
        maximum = max(world.values())
        q, grade = _choice("joint", "下一次抽样最可能得到哪个状态？",
                           [(state, f"A={state[0]}, B={state[1]}") for state in STATES],
                           acceptable=[state for state in STATES if world[state] == maximum])
        cases.append(_case(f"prob-{group}-joint", "probability", text, [q], {"joint": grade},
                           group=group, condition="joint", world=world))
        menus = (("coarse", [("A", "A=1，即状态10或11"), ("B", "A=0，即状态00或01")],
                  {"A": truth["a"], "B": 1 - truth["a"]}),
                 ("fine", [("A1", "状态10"), ("A2", "状态11"), ("B", "A=0，即状态00或01")],
                  {"A1": world["10"], "A2": world["11"], "B": world["00"] + world["01"]}))
        for condition, choices, masses in menus:
            q, grade = _choice("region", "下一次抽样最可能落入哪个互斥区域？", choices,
                               acceptable=[key for key, value in masses.items() if value == max(masses.values())])
            cases.append(_case(f"prob-{group}-{condition}", "probability", text, [q], {"region": grade},
                               group=group, condition=condition, world=world, event_masses=masses))
    return cases


def relation(left, right):
    x, y, w, h = left; a, b, u, v = right
    contains = ((x < a and y < b and a + u < x + w and b + v < y + h)
                or (a < x and b < y and x + w < a + u and y + h < b + v))
    if contains:
        return "contains"
    ix, iy = min(x + w, a + u) - max(x, a), min(y + h, b + v) - max(y, b)
    if (ix == 0 and iy > 0) or (iy == 0 and ix > 0):
        return "touching"
    if ix < 0 or iy < 0:
        return "disjoint"
    raise ValueError("layout is outside the three authored relation classes")


def png(rectangles, colors, background=(247, 245, 239), width=320, height=320):
    pixels = bytearray(bytes(background) * width * height)
    for index, ((x, y, w, h), color) in enumerate(zip(rectangles, colors)):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if not (0 <= xx < width and 0 <= yy < height):
                    raise ValueError("rectangle leaves image")
                if index == 0 and min(xx - x, x + w - 1 - xx, yy - y, y + h - 1 - yy) >= 3:
                    continue
                offset = 3 * (yy * width + xx)
                pixels[offset:offset + 3] = bytes(color)
    raw = b"".join(b"\0" + bytes(pixels[y * width * 3:(y + 1) * width * 3]) for y in range(height))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def visual_cases():
    families = ("contains", "touching", "disjoint")
    standard_boxes = (((35, 35, 235, 235), (95, 100, 70, 65)),
                      ((35, 50, 165, 185), (200, 100, 65, 65)),
                      ((25, 45, 115, 150), (175, 105, 75, 60)))
    palette = ((196, 77, 69), (36, 126, 158), (137, 88, 165), (52, 137, 105),
               (178, 112, 39), (93, 112, 185), (184, 86, 135), (46, 139, 140))
    descriptions = {"contains": "一个形状严格包含另一个，边界不相交。",
                    "touching": "两形状只在边界接触，内部不相交，且没有包含关系。",
                    "disjoint": "两形状完全分离，中间有间隔。"}
    references = {family: base64.b64encode(png(boxes, ((36, 126, 158), (196, 77, 69)))).decode()
                  for family, boxes in zip(families, standard_boxes)}
    cases = []
    for family_index, family in enumerate(families):
        for nuisance in range(8):
            n = family_index * 8 + nuisance + 1
            dx, dy = (nuisance % 4) * 5, (nuisance % 3) * 5
            if family == "contains":
                boxes = ((25 + dx, 30 + dy, 235 - nuisance, 225 - nuisance),
                         (90 + dx, 95 + dy, 55 + nuisance, 60))
            elif family == "touching":
                boxes = ((25 + dx, 35 + dy, 150 - nuisance, 185 - nuisance),
                         (175 + dx - nuisance, 90 + dy, 60 + nuisance, 65))
            else:
                boxes = ((20 + dx, 30 + dy, 110 - nuisance, 145),
                         (160 + dx, 100 + dy, 65 + nuisance, 60))
            if relation(*boxes) != family:
                raise ValueError("visual generator and geometry disagree")
            target = base64.b64encode(png(boxes, (palette[nuisance], palette[(nuisance + 3) % 8]),
                                          (247, 245, 239) if nuisance % 2 else (234, 242, 244))).decode()
            for condition in ("text", "image", "text+image", "swapped-image"):
                mapping = dict(zip(("K1", "K2", "K3"), families if condition != "swapped-image"
                                   else (families[1], families[2], families[0])))
                assets = {f"t{n:03d}": {"type": "image", "format": "png", "data_base64": target}}
                criteria = []
                for index, (label, defined_family) in enumerate(mapping.items(), 1):
                    ref = f"r{index:02d}"
                    if condition != "text":
                        assets[ref] = {"type": "image", "format": "png", "data_base64": references[defined_family]}
                    description = descriptions[defined_family] if condition in ("text", "text+image") else ""
                    if condition != "text":
                        description += " " + ref
                    criteria.append((label, description.strip()))
                q, grade = _choice("relation", "按目标图中两形状的空间关系，选择与criteria定义相符的类别。",
                                   criteria, next(label for label, definition in mapping.items() if definition == family))
                cases.append(_case(f"visual-{n:03d}-{condition}", "visual-criteria",
                                   {"target": f"t{n:03d}"}, [q], {"relation": grade},
                                   group=f"visual-{n:03d}", condition=condition, family=family,
                                   geometry=[list(box) for box in boxes], mapping=mapping, assets=assets))
    return cases


def all_cases():
    return rule_cases() + probability_cases() + visual_cases()
