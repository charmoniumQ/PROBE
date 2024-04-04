local function is_upper(s)
  return s == string.upper(s)
end

local function dump(o)
   if type(o) == 'table' then
      local s = '{ '
      for k,v in pairs(o) do
         if type(k) ~= 'number' then k = '"'..k..'"' end
         s = s .. '['..k..'] = ' .. dump(v) .. ','
      end
      return s .. '} '
   else
      return tostring(o)
   end
end

local function color(elem, color)
  return {pandoc.RawInline("latex", "{\\color{" .. color .. "}"), elem, pandoc.RawInline("latex", "}")}
end

styles = {}

return {
  {
    Meta = function (elem)
      if elem.styles ~= nil then
        styles = elem.styles
      end
      return elem
    end,
  },
  {
    Table = function (table)
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
        table.caption = {}
        table.attr.attributes.processed = 'true'
        return {pandoc.RawInline("latex", cmd), table}
      else
        return table
      end
    end
  },
  {
    Div = function (elem)
      if elem.attr.classes == nil or elem.attr.classes[1] == nil then
        return elem
      else
        class = elem.attr.classes[1]
        style = pandoc.utils.stringify(styles[class])
        if style == "removed" then
          return {}
        elseif style == "default" then
          return elem
        elseif style == "red" then
          return color(elem, "myred")
        elseif style == "green" then
          return color(elem, "mygreen")
        else
          print("Unknown style", style)
          return elem
        end
      end
    end,
  },
  {
    Span = function(elem)
      if elem.attr.classes == nil or elem.attr.classes[1] == nil then
        return elem
      else
        class = elem.attr.classes[1]
        style = pandoc.utils.stringify(styles[class])
        if style == "removed" then
          return {}
        elseif style == "default" then
          return elem
        elseif style == "red" then
          return color(elem, "myred")
        elseif style == "green" then
          return color(elem, "mygreen")
        else
          print("Unknown style", style)
          return elem
        end
      end
    end,
  },
  {
    Cite = function (cite)
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
        return pandoc.RawInline("latex", result)
      else
        local result = "\\cite{"
        for _, citation in ipairs(cite.citations) do
          result = result .. citation.id .. ","
        end
        result = string.sub(result, 0, #result - 1) .. "}"
        return pandoc.RawInline("latex", result)
      end
    end,
  },
}
