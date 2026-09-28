#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const token = process.env.NOTION_TOKEN;
const fixturePath = process.env.NOTION_MINDMAP_FIXTURE;
if (!token && !fixturePath) {
  throw new Error("NOTION_TOKEN が設定されていません。");
}

const dataSourceId =
  process.env.NOTION_MATERIAL_MASTER_ID ||
  "f2ee3fef-d924-42b2-ad1a-978691949b5b";
const rootTitle = process.env.NOTION_MINDMAP_ROOT || "パーキンソン病";
const projectRoot = resolve(import.meta.dirname, "..");
const output = resolve(
  projectRoot,
  process.env.NOTION_INTERACTIVE_MINDMAP_OUTPUT ||
    "lectures/11-neurology/interactive-mindmap.html",
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
  return items.map((item) => item.plain_text || "").join("").trim();
}

function relation(property) {
  return (property?.relation || []).map((item) => item.id);
}

function number(property) {
  return property?.number ?? Number.MAX_SAFE_INTEGER;
}

function checkbox(property) {
  return property?.checkbox === true;
}

function normalizePage(page) {
  const properties = page.properties || {};
  return {
    id: page.id,
    title: plain(properties["タイトル"]),
    slug: plain(properties.Slug),
    description: plain(properties["一言で説明"]),
    order: number(properties["表示順"]),
    visible: checkbox(properties["マインドマップ表示"]),
    parentIds: relation(properties["親項目"]),
    relatedDrugClassIds: relation(properties["関連薬効群"]),
    relatedDrugIds: relation(properties["関連薬剤"]),
  };
}

async function queryRows() {
  if (fixturePath) {
    const fixture = JSON.parse(await readFile(resolve(fixturePath), "utf8"));
    return fixture.map((row) => ({
      visible: true,
      description: "",
      slug: "",
      parentIds: [],
      relatedDrugClassIds: [],
      relatedDrugIds: [],
      ...row,
    }));
  }

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

  return results.map(normalizePage).filter((row) => row.visible && row.title);
}

function buildTree(rows) {
  const byId = new Map(rows.map((row) => [row.id, { ...row, children: [] }]));
  const root = [...byId.values()].find((row) => row.title === rootTitle);
  if (!root) throw new Error(`ルート項目「${rootTitle}」が見つかりません。`);

  const orphans = [];
  for (const node of byId.values()) {
    if (node.id === root.id) continue;
    const parent = node.parentIds.map((id) => byId.get(id)).find(Boolean);
    if (!parent) {
      orphans.push(node.title);
      continue;
    }
    parent.children.push(node);
  }
  if (orphans.length) {
    throw new Error(`親項目を確認してください: ${orphans.join("、")}`);
  }

  const sortChildren = (node) => {
    node.children.sort((a, b) => a.order - b.order || a.title.localeCompare(b.title, "ja"));
    node.children.forEach(sortChildren);
  };
  sortChildren(root);
  return root;
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function nodeAttributes(node) {
  const attributes = [];
  if (node.slug) attributes.push(`data-slug="${escapeHtml(node.slug)}"`);
  if (node.relatedDrugClassIds.length) {
    attributes.push(`data-related-drug-classes="${escapeHtml(node.relatedDrugClassIds.join(","))}"`);
  }
  if (node.relatedDrugIds.length) {
    attributes.push(`data-related-drugs="${escapeHtml(node.relatedDrugIds.join(","))}"`);
  }
  return attributes.length ? ` ${attributes.join(" ")}` : "";
}

function renderNode(node, depth) {
  const title = escapeHtml(node.title);
  const description = node.description
    ? `<small>${escapeHtml(node.description)}</small>`
    : "";
  if (!node.children.length) {
    return `<div class="leaf"${nodeAttributes(node)}>${title}${description}</div>`;
  }

  const isCaution = node.title.includes("注意点") || node.title.includes("看護");
  const className = isCaution ? ' class="safety-node"' : "";
  const open = depth <= 2 ? " open" : "";
  const children = node.children.map((child) => renderNode(child, depth + 1)).join("\n");
  return `<details${open} data-level="${depth}"${className}${nodeAttributes(node)}>
  <summary>${title}</summary>
  ${description ? `<div class="node-note">${description}</div>` : ""}
  ${children}
</details>`;
}

function branchKind(title) {
  if (title === "病態") return "pathology";
  if (title === "症状") return "symptoms";
  if (title === "薬物治療") return "treatment";
  return "other";
}

function renderHtml(root) {
  const branches = root.children
    .map((node) => `<div class="branch" data-kind="${branchKind(node.title)}">${renderNode(node, 1)}</div>`)
    .join("\n");
  const branchCount = root.children.length;

  return `<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="Notion教材マスター">
  <title>${escapeHtml(root.title)}｜開閉式マインドマップ</title>
  <style>
    :root { color-scheme: light; --navy:#17365d; --blue:#2f75b5; --pale-blue:#eaf3fb; --pale-green:#eaf5ed; --pale-orange:#fff1e6; --pale-red:#fdeceb; --ink:#28323c; --muted:#66727e; --line:#b9c7d5; --surface:#fff; --page:#f5f8fb; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--page); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif; line-height:1.55; }
    header { background:var(--surface); border-bottom:1px solid #dbe4ec; padding:18px clamp(16px,4vw,48px); }
    h1 { margin:0; color:var(--navy); font-size:clamp(1.35rem,3vw,2rem); }
    header p { margin:4px 0 0; color:var(--muted); }
    .toolbar { display:flex; flex-wrap:wrap; gap:8px; padding:14px clamp(16px,4vw,48px); background:var(--surface); border-bottom:1px solid #dbe4ec; position:sticky; top:0; z-index:5; }
    button,.back-link { border:1px solid #b8c7d6; border-radius:8px; background:#fff; color:var(--navy); padding:8px 13px; font:inherit; font-weight:600; text-decoration:none; cursor:pointer; }
    button:hover,button:focus-visible,.back-link:hover,.back-link:focus-visible { background:var(--pale-blue); outline:3px solid rgba(47,117,181,.2); outline-offset:1px; }
    button.primary { background:var(--navy); color:#fff; border-color:var(--navy); }
    .back-link { margin-left:auto; }
    main { padding:24px clamp(12px,3vw,40px) 48px; overflow-x:auto; }
    .map { min-width:920px; display:flex; flex-direction:column; align-items:center; }
    .root-node { background:var(--navy); color:#fff; padding:13px 25px; border-radius:999px; font-size:1.18rem; font-weight:700; box-shadow:0 6px 18px rgba(23,54,93,.18); }
    .trunk { width:2px; height:28px; background:var(--line); }
    .branches { position:relative; display:grid; grid-template-columns:repeat(${branchCount},minmax(240px,1fr)); gap:18px; width:100%; align-items:start; }
    .branches::before { content:""; position:absolute; top:0; left:${50 / branchCount}%; right:${50 / branchCount}%; height:2px; background:var(--line); }
    .branch { position:relative; padding-top:22px; }
    .branch::before { content:""; position:absolute; top:0; left:50%; width:2px; height:22px; background:var(--line); }
    details { margin:0 0 9px; }
    details details { margin:8px 0 0 16px; position:relative; }
    details details::before { content:""; position:absolute; left:-11px; top:0; bottom:8px; border-left:1px solid var(--line); }
    summary,.leaf { border:1px solid #cbd7e2; border-radius:9px; background:var(--surface); padding:9px 11px; box-shadow:0 2px 7px rgba(38,59,79,.06); }
    summary { cursor:pointer; font-weight:700; color:var(--navy); list-style:none; display:flex; align-items:center; gap:7px; }
    summary::-webkit-details-marker { display:none; }
    summary::before { content:"+"; width:1.2em; text-align:center; color:var(--blue); }
    details[open] > summary::before { content:"−"; }
    summary:hover { border-color:var(--blue); }
    .leaf { margin:7px 0 0 16px; font-size:.94rem; }
    .leaf small,.node-note { display:block; color:var(--muted); margin-top:2px; font-size:.86rem; }
    .node-note { margin:4px 10px 7px 32px; }
    .branch[data-kind="pathology"] > details > summary { background:var(--pale-blue); }
    .branch[data-kind="symptoms"] > details > summary { background:var(--pale-green); }
    .branch[data-kind="treatment"] > details > summary { background:var(--pale-orange); }
    details.safety-node > summary { background:var(--pale-red); }
    .help { max-width:860px; margin:26px auto 0; color:var(--muted); text-align:center; font-size:.92rem; }
    @media (max-width:700px) { .toolbar{position:static}.back-link{width:100%;margin-left:0;text-align:center}main{overflow:visible}.map{min-width:0;align-items:stretch}.root-node{align-self:center}.trunk,.branches::before,.branch::before{display:none}.branches{grid-template-columns:1fr;gap:10px;margin-top:18px}.branch{padding-top:0} }
  </style>
</head>
<body>
  <header><h1>${escapeHtml(root.title)}｜開閉式マインドマップ</h1><p>Notion教材マスターから生成。項目名をクリックすると詳しい内容を開閉できます。</p></header>
  <nav class="toolbar" aria-label="マインドマップ操作">
    <button type="button" class="primary" data-depth="2">通常表示</button>
    <button type="button" data-depth="1">全体像だけ</button>
    <button type="button" data-action="expand">すべて開く</button>
    <button type="button" data-action="collapse">すべて閉じる</button>
    <a class="back-link" href="../../index.html">講義サイトへ戻る</a>
  </nav>
  <main>
    <section class="map" aria-label="${escapeHtml(root.title)}のマインドマップ">
      <div class="root-node">${escapeHtml(root.title)}</div><div class="trunk" aria-hidden="true"></div>
      <div class="branches">${branches}</div>
    </section>
    <p class="help">薬効群・薬剤の「＋」を開くと、それぞれに紐づく看護・注意点を確認できます。スマートフォンでは縦に並びます。</p>
  </main>
  <script>
    const allDetails=[...document.querySelectorAll("details")];
    function setDepth(depth){allDetails.forEach((item)=>{item.open=Number(item.dataset.level||1)<=depth;});}
    document.querySelector('[data-action="expand"]').addEventListener("click",()=>allDetails.forEach((item)=>{item.open=true;}));
    document.querySelector('[data-action="collapse"]').addEventListener("click",()=>allDetails.forEach((item)=>{item.open=false;}));
    document.querySelectorAll("[data-depth]").forEach((button)=>button.addEventListener("click",()=>setDepth(Number(button.dataset.depth))));
  </script>
</body>
</html>\n`;
}

const rows = await queryRows();
const tree = buildTree(rows);
await writeFile(output, renderHtml(tree), "utf8");
console.log(`updated: ${output} (${rows.length} items)`);
