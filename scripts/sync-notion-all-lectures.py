#!/usr/bin/env python3
"""Generate the public 15-lecture portal from the Notion student-material DB."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_VERSION = "2025-09-03"
MATERIALS_SOURCE = os.environ.get(
    "NOTION_STUDENT_MATERIALS_ID", "3cfa2d0d-cc9d-8033-a4d4-000b506e846e"
)
OUTPUT_ROOT = ROOT / "lectures" / "notion"
PUBLISHED_STATES = {"公開可", "配布可"}
PHASE_ORDER = ("基礎理解", "臨床判断", "統合・定着")
PHASE_FILES = {
    "基礎理解": "foundations.qmd",
    "臨床判断": "clinical.qmd",
    "統合・定着": "integration.qmd",
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


def plain_text(items: list[dict] | None) -> str:
    return "".join(item.get("plain_text", "") for item in (items or [])).strip()


def title_value(prop: dict | None) -> str:
    return plain_text((prop or {}).get("title"))


def select_value(prop: dict | None) -> str:
    return ((prop or {}).get("select") or {}).get("name", "")


def relation_ids(prop: dict | None) -> list[str]:
    return [item["id"] for item in (prop or {}).get("relation", []) if item.get("id")]


def query_materials(token: str) -> list[dict]:
    url = f"https://api.notion.com/v1/data_sources/{MATERIALS_SOURCE}/query"
    payload: dict = {
        "filter": {"property": "選択", "select": {"is_not_empty": True}},
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


def fetch_children(block_id: str, token: str) -> list[dict]:
    url = f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100"
    blocks: list[dict] = []
    while True:
        result = request_json(url, token)
        blocks.extend(result.get("results", []))
        if not result.get("has_more"):
            return blocks
        url = (
            f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100"
            f"&start_cursor={result['next_cursor']}"
        )


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


def table_markdown(block: dict, token: str) -> list[str]:
    rows = fetch_children(block["id"], token)
    cells = [
        [rich_text(cell) for cell in row.get("table_row", {}).get("cells", [])]
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


def blocks_to_markdown(blocks: list[dict], token: str, unit: str) -> list[str]:
    lines: list[str] = []
    numbered = 0
    for block in blocks:
        kind = block.get("type", "")
        value = block.get(kind) or {}
        text = rich_text(value.get("rich_text"))
        if kind != "numbered_list_item":
            numbered = 0
        if kind == "paragraph" and text:
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
        elif kind in {"quote", "callout"} and text:
            lines.extend([f"> {line}" for line in text.splitlines()] + [""])
        elif kind == "code":
            lines.extend([f"```{value.get('language', '')}", text, "```", ""])
        elif kind == "equation":
            lines.extend([f"$${value.get('expression', '')}$$", ""])
        elif kind == "table":
            lines.extend(table_markdown(block, token))
        elif kind == "divider":
            lines.extend(["", "---", ""])
        if block.get("has_children") and kind != "table":
            lines.extend(blocks_to_markdown(fetch_children(block["id"], token), token, unit))
    return lines


def lecture_number(name: str) -> str | None:
    match = re.match(r"^(\d{2})(?:-|\b)", name.strip())
    if not match:
        return None
    number = int(match.group(1))
    return f"{number:02d}" if 1 <= number <= 15 else None


def unit_code(name: str) -> str | None:
    match = re.match(r"^(\d{2}(?:-\d{2})?)\b", name.strip())
    return match.group(1) if match else None


def unit_label(name: str) -> str:
    return name.split("｜", 1)[0].strip()


def yaml_text(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def frontmatter(title: str, subtitle: str) -> list[str]:
    return [
        "---",
        f"title: {yaml_text(title)}",
        f"subtitle: {yaml_text(subtitle)}",
        "format:",
        "  revealjs:",
        "    width: 1280",
        "    height: 720",
        "    center: false",
        "    slide-number: true",
        "    transition: fade",
        "lang: ja",
        "---",
        "",
    ]


def load_published_materials(token: str) -> dict[str, dict[str, dict]]:
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in query_materials(token):
        props = row.get("properties", {})
        name = title_value(props.get("名前"))
        number = lecture_number(name)
        code = unit_code(name)
        phase = select_value(props.get("選択"))
        if number is None or code is None or phase not in PHASE_ORDER:
            continue
        student_ids = relation_ids(props.get("学生用教材"))
        if len(student_ids) != 1:
            print(f"skip {name}: expected one student material", file=sys.stderr)
            continue
        page = request_json(f"https://api.notion.com/v1/pages/{student_ids[0]}", token)
        status = select_value(page.get("properties", {}).get("公開状態"))
        if status not in PUBLISHED_STATES:
            print(f"skip {name}: status={status or 'empty'}", file=sys.stderr)
            continue
        unit = grouped[number].setdefault(
            code, {"code": code, "label": unit_label(name), "phases": {}}
        )
        unit["phases"][phase] = {
            "name": name,
            "unit": unit_label(name),
            "page_id": student_ids[0],
            "blocks": fetch_children(student_ids[0], token),
        }
    return grouped


def phase_content(number: str, phase: str, material: dict, token: str) -> str:
    lines = frontmatter(
        f"{material['unit']}｜{phase}",
        "Notionの学生用教材から生成",
    )
    lines.extend(
        [
            f"## {material['unit']}",
            "",
            f"<!-- notion-page-id: {material['page_id']} -->",
            "",
        ]
    )
    lines.extend(blocks_to_markdown(material["blocks"], token, material["unit"]))
    return "\n".join(lines).rstrip() + "\n"


def full_content(unit: dict, token: str) -> str:
    phases = unit["phases"]
    lines = frontmatter(f"{unit['label']}｜全体版", "基礎理解・臨床判断・統合・定着")
    for phase in PHASE_ORDER:
        material = phases.get(phase)
        if not material:
            continue
        lines.extend([f"## {phase}", ""])
        lines.extend(blocks_to_markdown(material["blocks"], token, material["unit"]))
    return "\n".join(lines).rstrip() + "\n"


def landing_content(
    grouped: dict[str, dict[str, dict]],
    *,
    link_prefix: str = "",
    css_path: str = "../../lecture-index.css",
    root_page: bool = False,
) -> str:
    rows: list[str] = []
    for number in sorted(grouped):
        units = grouped[number]
        overview = units.get(number)
        group_label = overview["label"] if overview else f"第{int(number)}回"
        rows.append(
            '<div class="lecture-group-title">'
            f'<strong>{html.escape(group_label)}</strong>'
            '<span>小単元ごとに学習段階を選択</span></div>'
        )
        for code, unit in sorted(units.items()):
            phases = unit["phases"]
            links = []
            for phase, css_class in (("基礎理解", "pre"), ("臨床判断", "classroom"), ("統合・定着", "review")):
                filename = PHASE_FILES[phase].replace(".qmd", ".html")
                if phases.get(phase):
                    links.append(f'<a class="phase-cell {css_class}" href="{link_prefix}{number}/{code}/{filename}">{phase}</a>')
                else:
                    links.append(f'<span class="phase-cell {css_class} disabled">未公開</span>')
            rows.append(
                '<section class="lecture-row unit-row">'
                f'<div class="lecture-info"><strong>{html.escape(unit["label"])}</strong><span>Notion学生用教材</span></div>'
                + "".join(links)
                + f'<a class="phase-cell full" href="{link_prefix}{number}/{code}/full.html">全体版を開く</a>'
                + '<div class="drug-class-cell"><span class="coming-soon">Notion連動</span></div>'
                + "</section>"
            )
    content = [
            "---",
            'title: "看護薬理学"' if root_page else 'title: "看護薬理学｜Notion連動講義"',
            'subtitle: "講義資料"' if root_page else "",
            "format:",
            "  html:",
            "    toc: false",
            "    page-layout: full",
            f"    css: {css_path}",
            "---",
            "",
            "::: {.course-intro}",
            "## 15回の講義資料",
            "",
            "Notionで公開可または配布可にした教材だけを掲載しています。",
            ":::",
            "",
            "```{=html}",
            '<div class="course-table">',
            '<div class="grid-header" aria-hidden="true"><span>講義・小単元</span><span>基礎理解</span><span>臨床判断</span><span>統合・定着</span><span>全体版</span><span></span></div>',
            *rows,
            "</div>",
            "```",
            "",
        ]
    if root_page:
        content.extend(
            [
                "::: {.related-site}",
                "### 関連教材",
                "",
                "[開閉できるマインドマップ](lectures/11-neurology/interactive-mindmap.html){.lecture-button}",
                "",
                "[YakuriLab 辞書・Simulator](https://yakuri-lab.vercel.app/dictionary/){.lecture-button .secondary}",
                ":::",
                "",
            ]
        )
    else:
        content.extend(["[講義サイトへ戻る](../../index.html)", ""])
    return "\n".join(content)


def write_site(
    grouped: dict[str, dict[str, dict]], token: str, activate_index: bool = False
) -> None:
    if not grouped:
        raise RuntimeError("公開対象のNotion学生用教材が見つかりません。")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for number, units in grouped.items():
        for code, unit in units.items():
            unit_dir = OUTPUT_ROOT / number / code
            unit_dir.mkdir(parents=True, exist_ok=True)
            for phase in PHASE_ORDER:
                material = unit["phases"].get(phase)
                if material:
                    (unit_dir / PHASE_FILES[phase]).write_text(
                        phase_content(number, phase, material, token), encoding="utf-8"
                    )
            (unit_dir / "full.qmd").write_text(full_content(unit, token), encoding="utf-8")
    (OUTPUT_ROOT / "index.qmd").write_text(landing_content(grouped), encoding="utf-8")
    if activate_index:
        (ROOT / "index.qmd").write_text(
            landing_content(
                grouped,
                link_prefix="lectures/notion/",
                css_path="lecture-index.css",
                root_page=True,
            ),
            encoding="utf-8",
        )
    manifest = {
        "source": "Notion student materials",
        "lectures": {
            number: {
                code: sorted(unit["phases"]) for code, unit in sorted(units.items())
            }
            for number, units in sorted(grouped.items())
        },
    }
    (OUTPUT_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--activate-index",
        action="store_true",
        help="replace the homepage for this build; the committed manual page remains the fallback",
    )
    args = parser.parse_args()
    token = os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY")
    if not token:
        print("NOTION_TOKEN (or NOTION_API_KEY) is required", file=sys.stderr)
        return 2
    grouped = load_published_materials(token)
    write_site(grouped, token, activate_index=args.activate_index)
    print(
        "Notion all-lecture sync complete: "
        + ", ".join(f"{number}={len(units)} units" for number, units in sorted(grouped.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
