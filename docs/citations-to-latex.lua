local function is_upper(s)
  return s == string.upper(s)
end

function Cite(cite)
  local cite_type = string.sub(cite.citations[1].id, 0, 3)
  if cite_type == "fig" or cite_type == "tbl" or cite_type == "Fig" or cite_type == "Tbl" then
    local result = nil
    if is_upper(string.sub(cite_type, 0, 1)) then
       result = "\\Cref{"
    else
       result = "\\cref{"
    end
    for _, citation in ipairs(cite.citations) do
      label = citation.id
      if is_upper(string.sub(label, 0, 1)) then
        label = string.lower(string.sub(label, 0, 1)) .. string.sub(label, 2, #label)
      end
      result = result .. label .. ","
    end
    result = string.sub(result, 0, #result - 1) .. "}"
    print("lua cref", result)
    return pandoc.RawInline("latex", result)
  else
    local result = "\\cite{"
    for _, citation in ipairs(cite.citations) do
      result = result .. citation.id .. ","
    end
    result = string.sub(result, 0, #result - 1) .. "}"
    print("lua cite", result)
    return pandoc.RawInline("latex", result)
  end
end

function Table(table)
  if not table.attr.attributes.processed then
    local caption_string = pandoc.utils.stringify(table.caption)
    local label_start = string.find(caption_string, "{")
    local label_stop = string.find(caption_string, "}")
    local cmd = nil
    if label_start and label_stop then
      local label = string.sub(caption_string, label_start + 2, label_stop - 1)
      caption_string = string.sub(caption_string, 0, label_start - 1)
      cmd = "\\renewcommand\\tcap{" .. caption_string .. "\\label{" .. label .. "}}"
    else
      cmd = "\\renewcommand\\tcap{" .. caption_string .. "}"
    end
    print("lua table caption", cmd)
    table.caption = {}
    table.attr.attributes.processed = 'true'
    return {pandoc.RawInline("latex", cmd), table}
  else
    return table
  end
end

function Span(elem)
  style = elem.attributes["style"]
  if style == nil then
    return elem
  else
    if style == "hidden" then
      return {}
    elseif style == "red" then
      return {pandoc.RawInline("latex", "{\\color{red}"), elem, pandoc.RawInline("latex", "}")}
    else
      return elem
    end
  end
end

function Div(elem)
  return Span(elem)
end
