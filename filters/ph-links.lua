-- Semantic pharmacology links for Quarto/Pandoc.
-- Usage: [心拍出量]{.ph-link data-kind="keyword" data-slug="cardiac-output"}

local function as_text(value)
  if value == nil then return nil end
  return pandoc.utils.stringify(value)
end

local function has_class(classes, wanted)
  for _, class_name in ipairs(classes) do
    if class_name == wanted then return true end
  end
  return false
end

local function add_class(classes, class_name)
  if not has_class(classes, class_name) then
    table.insert(classes, class_name)
  end
end

function Pandoc(doc)
  local registry = doc.meta["ph-links"] or {}

  local function resolve(span)
    if not has_class(span.classes, "ph-link") then return nil end

    local kind = span.attributes["data-kind"]
    local slug = span.attributes["data-slug"]
    if not kind or not slug then
      io.stderr:write("ph-links: data-kind and data-slug are required\n")
      add_class(span.classes, "ph-link-missing")
      return span
    end

    local group = registry[kind]
    local entry = group and group[slug]
    if not entry then
      io.stderr:write("ph-links: unresolved slug " .. kind .. "/" .. slug .. "\n")
      add_class(span.classes, "ph-link-missing")
      return span
    end

    local url
    local status = "active"
    if type(entry) == "table" and entry.url then
      url = as_text(entry.url)
      status = as_text(entry.status) or status
    else
      url = as_text(entry)
    end

    add_class(span.classes, "ph-link-" .. kind)

    if status ~= "active" or not url or url == "" then
      add_class(span.classes, "ph-link-planned")
      span.attributes.title = "公開準備中: " .. kind .. "/" .. slug
      return span
    end

    span.attributes.target = "_blank"
    span.attributes.rel = "noopener"
    span.attributes.title = span.attributes.title or (kind .. ": " .. slug)
    return pandoc.Link(span.content, url, "", span.attr)
  end

  doc.blocks = doc.blocks:walk({ Span = resolve })
  return doc
end
