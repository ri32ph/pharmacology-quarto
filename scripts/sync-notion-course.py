#!/usr/bin/env python3
"""Generate Quarto slide fragments from published Notion student materials.

The first pilot targets lecture 03. Notion remains the source of truth while
the hand-written Quarto fragments remain in Git as a safe build fallback.

Usage:
    NOTION_TOKEN=... python3 scripts/sync-notion-course.py
    NOTION_TOKEN=... python3 scripts/sync-notion-course.py --activate
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_VERSION = "2025-09-03"
MATERIALS_SOURCE = "3cfa2d0d-cc9d-8033-a4d4-000b506e846e"
LECTURE_PREFIX = "03-"
OUTPUT_DIR = ROOT / "generated" / "notion" / "03"
PUBLISHED_STATES = {"公開可", "配布可"}

PHASES = {
    "基礎理解": ROOT / "lectures/03-circulation-fluid/pre-class/01-circulation-basics.qmd",
    "臨床判断": ROOT / "lectures/03-circulation-fluid/face-to-face/01-cases-and-diuretics.qmd",
    "統合・定着": ROOT / "lectures/03-circulation-fluid/reflection/01-reflection.qmd",
}

DRUG_LINKS = {
    "Ca拮抗薬": "calcium-channel-blockers",
    "ACE阻害薬": "ace-inhibitors",
    "ARB": "angiotensin-receptor-blockers",
    "β遮断薬": "beta-blockers",
    "MRA": "mineralocorticoid-receptor-antagonists",
    "ループ利尿薬": "loop-diuretics",
    "サイアザイド系利尿薬": "thiazide-diuretics",
}


def request_json(url: str, token: str, payload: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": API_VERSION,
        "Content-Type": "application/json",
    }
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=body, headers=headers, method="POST" if body else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion API error {error.code}: {detail}") from error


def query_materials(token: str) -> list[dict]:
    url = f"https://api.notion.com/v1/data_sources/{MATERIALS_SOURCE}/query"
    payload: dict = {
        "filter": {
            "and": [
                {"property": "名前", "title": {"starts_with": LECTURE_PREFIX}},
                {"property": "選択", "select": {"is_not_empty": True}},
            ]
        },
        "sorts": [{"property": "名前", "direction": "ascending"}],
        "page_size": 100,
    }
    rows: list[dict] = []
    while True:
        result = request_json(url, token, payload)
        rows.extend(result.get("results", []))
        if not result.get("has_more"):
            return rows
        payload["start_cursor"] = result["next_cursor"]


def plain_text(items: list[dict] | None) -> str:
    return "".join(item.get("plain_text", "") for item in (items or [])).strip()


def title_value(prop: dict | None) -> str:
    return plain_text((prop or {}).get("title"))


def select_value(prop: dict | None) -> str:
    return ((prop or {}).get("select") or {}).get("name", "")


def relation_ids(prop: dict | None) -> list[str]:
    return [item["id"] for item in (prop or {}).get("relation", []) if item.get("id")]


def fetch_children(block_id: str, token: str) -> list[dict]:
    url = f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100"
    blocks: list[dict] = []
    while True:
        result = request_json(url, token)
        blocks.extend(result.get("results", []))
        if not result.get("has_more"):
            return blocks
        cursor = result["next_cursor"]
        url = f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100&start_cursor={cursor}"


def rich_text(items: list[dict] | None) -> str:
    parts: list[str] = []
    for item in items or []:
        text = item.get("plain_text", "")
        annotations = item.get("annotations") or {}
        href = item.get("href")
        if annotations.get("code"):
            text = f"`{text}`"
        else:
            if annotations.get("bold"):
                text = f"**{text}**"
            if annotations.get("italic"):
                text = f"*{text}*"
        if href:
            text = f"[{text}]({href})"
        parts.append(text)
    return "".join(parts).strip()


def add_dictionary_links(text: str) -> str:
    for label, slug in sorted(DRUG_LINKS.items(), key=lambda item: -len(item[0])):
        replacement = f'[{label}]{{.ph-link data-kind="drug-class" data-slug="{slug}"}}'
        text = re.sub(rf"(?<![\w\]]){re.escape(label)}(?![\w\[])" , replacement, text)
    return text


def table_markdown(block: dict, token: str) -> list[str]:
    rows = fetch_children(block["id"], token)
    cells = [
        [add_dictionary_links(rich_text(cell)) for cell in row.get("table_row", {}).get("cells", [])]
        for row in rows
        if row.get("type") == "table_row"
    ]
    if not cells:
        return []
    width = max(len(row) for row in cells)
    cells = [row + [""] * (width - len(row)) for row in cells]
    output = ["| " + " | ".join(cells[0]) + " |"]
    output.append("| " + " | ".join(["---"] * width) + " |")
    output.extend("| " + " | ".join(row) + " |" for row in cells[1:])
    return output + [""]


def section_items(blocks: list[dict], heading: str) -> list[str]:
    """Return plain text items beneath a Notion heading until the next heading."""
    collecting = False
    items: list[str] = []
    for block in blocks:
        kind = block.get("type", "")
        value = block.get(kind) or {}
        text = rich_text(value.get("rich_text"))
        if kind in {"heading_1", "heading_2", "heading_3"}:
            if collecting:
                break
            collecting = text == heading
            continue
        if collecting and text:
            items.append(text)
    return items


def first_table_cells(blocks: list[dict], token: str) -> list[list[str]]:
    for block in blocks:
        if block.get("type") != "table":
            continue
        rows = fetch_children(block["id"], token)
        return [
            [rich_text(cell) for cell in row.get("table_row", {}).get("cells", [])]
            for row in rows
            if row.get("type") == "table_row"
        ]
    return []


def visual_model_slides(unit: str, phase: str, blocks: list[dict], token: str) -> list[str]:
    """Create the 03-01 visual model while keeping all facts in Notion slides too."""
    if not unit.startswith("03-01"):
        return []

    if phase == "基礎理解":
        return [
            "## 血圧を決める仕組み {.model-slide .concept-slide}",
            "",
            '<div class="bp-model" role="img" aria-label="血圧は心拍出量と末梢血管抵抗で決まる">',
            '  <div class="bp-equation">',
            '    <div class="bp-node bp-main"><span>血圧</span><small>組織へ血液を届ける力</small></div>',
            '    <div class="bp-symbol">≒</div>',
            '    <div class="bp-node bp-heart"><span>心拍出量</span><small>心拍数 × 一回拍出量</small></div>',
            '    <div class="bp-symbol">×</div>',
            '    <div class="bp-node bp-vessel"><span>末梢血管抵抗</span><small>血管の収縮・拡張</small></div>',
            '  </div>',
            '  <div class="bp-connections">',
            '    <div class="bp-action heart"><b>心臓</b><span>β遮断薬：心拍数・収縮力を抑える</span></div>',
            '    <div class="bp-action vessel"><b>血管</b><span>Ca拮抗薬：血管を拡張する</span></div>',
            '    <div class="bp-action kidney"><b>腎臓</b><span>RAA系・利尿薬：体液量を調節する</span></div>',
            '  </div>',
            '  <p class="model-takeaway">値だけでなく、<strong>どこが変わって血圧が下がったか</strong>を考える</p>',
            '</div>',
            "",
        ]

    if phase == "臨床判断":
        case_text = " ".join(section_items(blocks, "症例"))
        considerations = section_items(blocks, "考える要点")
        checks = "、".join(section_items(blocks, "追加確認"))
        cards = "\n".join(
            f'<div class="judgement-card"><span>{index}</span><p>{html.escape(item)}</p></div>'
            for index, item in enumerate(considerations[:3], 1)
        )
        return [
            "## 症例から降圧効果を判断する {.model-slide .case-slide}",
            "",
            '<div class="case-model">',
            '  <div class="patient-card">',
            '    <div class="patient-card-label">CASE 03-01</div>',
            f'    <p>{html.escape(case_text)}</p>',
            '  </div>',
            '  <div class="case-question">血圧は改善した。それだけで「適切」と判断できる？</div>',
            f'  <div class="judgement-grid">{cards}</div>',
            f'  <div class="check-strip"><b>追加確認</b><span>{html.escape(checks)}</span></div>',
            '</div>',
            "",
        ]

    if phase == "統合・定着":
        rows = first_table_cells(blocks, token)
        if not rows:
            return []
        header = rows[0]
        body_rows = "\n".join(
            '<div class="drug-compare-row">'
            + "".join(f'<div>{html.escape(cell)}</div>' for cell in row)
            + "</div>"
            for row in rows[1:]
        )
        header_cells = "".join(f'<div>{html.escape(cell)}</div>' for cell in header)
        return [
            "## 降圧薬を作用と観察で比較する {.model-slide .compare-slide}",
            "",
            '<div class="drug-compare" role="table" aria-label="降圧薬の比較">',
            f'  <div class="drug-compare-row header">{header_cells}</div>',
            f'  {body_rows}',
            '</div>',
            '<p class="model-takeaway">薬効群の暗記ではなく、<strong>作用 → 起こり得る変化 → 観察</strong>でつなぐ</p>',
            "",
        ]

    return []


def blocks_to_markdown(blocks: list[dict], token: str, unit: str) -> list[str]:
    lines: list[str] = []
    numbered = 0
    for block in blocks:
        kind = block.get("type", "")
        value = block.get(kind) or {}
        text = add_dictionary_links(rich_text(value.get("rich_text")))
        if kind not in {"numbered_list_item"}:
            numbered = 0
        if kind == "paragraph":
            if text:
                lines.extend([text, ""])
        elif kind in {"heading_1", "heading_2"}:
            lines.extend([f"## {unit}｜{text}", ""])
        elif kind == "heading_3":
            lines.extend([f"### {text}", ""])
        elif kind == "bulleted_list_item":
            lines.append(f"- {text}")
        elif kind == "numbered_list_item":
            numbered += 1
            lines.append(f"{numbered}. {text}")
        elif kind == "to_do":
            mark = "x" if value.get("checked") else " "
            lines.append(f"- [{mark}] {text}")
        elif kind in {"quote", "callout"}:
            if text:
                lines.extend([f"> {line}" for line in text.splitlines()] + [""])
        elif kind == "code":
            language = value.get("language", "")
            lines.extend([f"```{language}", text, "```", ""])
        elif kind == "equation":
            expression = value.get("expression", "")
            lines.extend([f"$${expression}$$", ""])
        elif kind == "table":
            lines.extend(table_markdown(block, token))
        elif kind == "divider":
            lines.extend(["", "---", ""])
        if block.get("has_children") and kind not in {"table"}:
            lines.extend(blocks_to_markdown(fetch_children(block["id"], token), token, unit))
    return lines


def normalize_unit(material_name: str) -> str:
    return material_name.split("｜", 1)[0].strip()


def generate(token: str) -> dict[str, str]:
    grouped: dict[str, list[tuple[str, str, list[dict]]]] = {phase: [] for phase in PHASES}
    for row in query_materials(token):
        props = row.get("properties", {})
        material_name = title_value(props.get("名前"))
        phase = select_value(props.get("選択"))
        if phase not in grouped:
            continue
        student_ids = relation_ids(props.get("学生用教材"))
        if len(student_ids) != 1:
            print(f"skip {material_name}: expected one student material", file=sys.stderr)
            continue
        page = request_json(f"https://api.notion.com/v1/pages/{student_ids[0]}", token)
        page_props = page.get("properties", {})
        status = select_value(page_props.get("公開状態"))
        if status not in PUBLISHED_STATES:
            print(f"skip {material_name}: status={status or 'empty'}", file=sys.stderr)
            continue
        blocks = fetch_children(student_ids[0], token)
        grouped[phase].append((material_name, student_ids[0], blocks))

    generated: dict[str, str] = {}
    for phase, pages in grouped.items():
        if not pages:
            raise RuntimeError(f"No published Notion materials found for {phase}")
        lines = [f"<!-- Generated from Notion: lecture 03 / {phase}. Do not edit. -->", ""]
        for material_name, page_id, blocks in sorted(pages):
            unit = normalize_unit(material_name)
            lines.extend([f"## {unit}", "", f"<!-- notion-page-id: {page_id} -->", ""])
            lines.extend(visual_model_slides(unit, phase, blocks, token))
            lines.extend(blocks_to_markdown(blocks, token, unit))
        generated[phase] = "\n".join(lines).rstrip() + "\n"
    return generated


def write_files(generated: dict[str, str], activate: bool) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filenames = {"基礎理解": "foundations.qmd", "臨床判断": "clinical.qmd", "統合・定着": "integration.qmd"}
    for phase, content in generated.items():
        (OUTPUT_DIR / filenames[phase]).write_text(content, encoding="utf-8")
        if activate:
            PHASES[phase].write_text(content, encoding="utf-8")
    manifest = {
        "source": "Notion",
        "lecture": "03",
        "phases": {phase: filenames[phase] for phase in PHASES},
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate", action="store_true", help="replace lecture 03 fragments for this build")
    args = parser.parse_args()
    token = os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY")
    if not token:
        print("NOTION_TOKEN (or NOTION_API_KEY) is required", file=sys.stderr)
        return 2
    generated = generate(token)
    write_files(generated, args.activate)
    counts = {phase: content.count("notion-page-id") for phase, content in generated.items()}
    print("Notion lecture sync complete: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
