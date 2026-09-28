#!/usr/bin/env node

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const token = process.env.NOTION_TOKEN;
if (!token) throw new Error("NOTION_TOKEN が設定されていません。");

const dataSourceId =
  process.env.NOTION_MATERIAL_MASTER_ID ||
  "f2ee3fef-d924-42b2-ad1a-978691949b5b";
const rootTitle = process.env.NOTION_MINDMAP_ROOT || "パーキンソン病";
const root = resolve(import.meta.dirname, "..");
const output = resolve(
  root,
  process.env.NOTION_MINDMAP_OUTPUT ||
    "lectures/11-neurology/parkinson-mindmap.qmd",
);

const headers = {
  Authorization: `Bearer ${token}`,
  "Content-Type": "application/json",
  "Notion-Version": "2025-09-03",
};

async function notion(path, options = {}) {
  const response = await fetch(`https://api.notion.com/v1${path}`, {
    ...options,
    headers: { ...headers, ...options.headers },
  });
  if (!response.ok) {
    throw new Error(`Notion API ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

function plain(property) {
  const items = property?.title || property?.rich_text || [];
  return items.map((item) => item.plain_text || "").join("");
}

function select(property) {
  return property?.select?.name || "";
}

function checkbox(property) {
  return property?.checkbox === true;
}

function number(property) {
  return property?.number ?? Number.MAX_SAFE_INTEGER;
}

function safeLabel(value) {
  return value.replaceAll("\n", " ").replace(/[{}]/g, "").trim();
}

async function queryRows() {
  const results = [];
  let cursor;
  do {
    const body = {
      page_size: 100,
      filter: {
        and: [
          { property: "マインドマップ表示", checkbox: { equals: true } },
          { property: "大項目", rich_text: { equals: rootTitle } },
        ],
      },
      sorts: [{ property: "表示順", direction: "ascending" }],
      ...(cursor ? { start_cursor: cursor } : {}),
    };
    const page = await notion(`/data_sources/${dataSourceId}/query`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    results.push(...page.results);
    cursor = page.has_more ? page.next_cursor : undefined;
  } while (cursor);

  return results
    .map((page) => ({
      title: plain(page.properties["タイトル"]),
      major: plain(page.properties["大項目"]),
      middle: plain(page.properties["中項目"]),
      minor: plain(page.properties["小項目"]),
      level: select(page.properties["スライドレベル"]),
      order: number(page.properties["表示順"]),
      visible: checkbox(page.properties["マインドマップ表示"]),
    }))
    .filter((row) => row.visible && row.major === rootTitle)
    .sort((a, b) => a.order - b.order);
}

function branchLines(rows, middle, indent = "    ") {
  const selected = rows.filter((row) => row.middle === middle);
  const level2 = selected.filter((row) => row.level.startsWith("2｜"));
  const level3 = selected.filter((row) => row.level.startsWith("3｜"));
  const lines = [`${indent}${safeLabel(middle)}`];

  if (!level2.length) {
    for (const row of level3) lines.push(`${indent}  ${safeLabel(row.title)}`);
    return lines;
  }

  for (const group of level2) {
    lines.push(`${indent}  ${safeLabel(group.title)}`);
    const children = level3.filter((row) => row.minor === group.title);
    for (const child of children) {
      lines.push(`${indent}    ${safeLabel(child.title)}`);
    }
  }
  return lines;
}

function diagram(rows, branches) {
  const lines = ["```{mermaid}", "mindmap", `  root((${safeLabel(rootTitle)}))`];
  for (const branch of branches) lines.push(...branchLines(rows, branch));
  lines.push("```");
  return lines.join("\n");
}

const rows = await queryRows();
if (!rows.length) {
  throw new Error(`${rootTitle} のマインドマップ表示対象がありません。`);
}

const qmd = `---
title: "${rootTitle}"
subtitle: "教材マスターから生成したマインドマップ"
format:
  revealjs:
    width: 1280
    height: 720
    center: false
    slide-number: true
    transition: fade
lang: ja
---

## 全体像

${diagram(rows.filter((row) => !row.level.startsWith("3｜")), ["病態", "症状", "薬物治療", "注意点"])}

---

## 病態と症状

${diagram(rows, ["病態", "症状"])}

---

## 薬物治療

${diagram(rows, ["薬物治療"])}

---

## 看護で確認する注意点

${diagram(rows, ["注意点"])}
`;

await mkdir(dirname(output), { recursive: true });
await writeFile(output, qmd, "utf8");
console.log(`updated: ${output} (${rows.length} items)`);
