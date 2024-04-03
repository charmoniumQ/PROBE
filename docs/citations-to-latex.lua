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

local function red(elem)
  return {pandoc.RawInline("latex", "\\textcolor{myred}{{"), elem, pandoc.RawInline("latex", "}}")}
end

local function green(elem)
  return {pandoc.RawInline("latex", "\\textcolor{mygreen}{{"), elem, pandoc.RawInline("latex", "}}")}
end

return {
  {
    Meta = function (elem)
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
      if #elem.attr.classes == 0 then
        return elem
      else
        div_classes = elem.attr.classes
        local function wrap_in_span(elem)
          return pandoc.Span(elem, pandoc.Attr("", div_classes))
        end
        new_elem = elem:walk {
          -- Header = function(elem)
          --   return pandoc.Header(elem.level, wrap_in_span(elem.content), elem.attr)
          -- end,
          Para = function(elem)
            return pandoc.Para(wrap_in_span(elem.content))
          end,
        }
        return new_elem
      end
    end,
  },
  {
    Span = function(elem)
      if elem.classes:includes('removed') then
        return red(elem)
      elseif elem.classes:includes('added') then
        return green(elem)
      elseif elem.classes:includes('only-in-new') then
        return {}
      elseif elem.classes:includes('only-in-old') then
        return elem
      else
        return elem
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
