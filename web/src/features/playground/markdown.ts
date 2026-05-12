export function normalizeMarkdownForRender(text: string, streaming: boolean) {
  const normalized = text.replace(/\r\n?/g, "\n");
  const spaced = normalizeMarkdownBlockBreaks(normalized);
  if (!streaming) return spaced;

  const openFence = getOpenMarkdownFence(spaced);
  if (!openFence) return spaced;
  return `${spaced.endsWith("\n") ? spaced : `${spaced}\n`}${openFence}`;
}

function normalizeMarkdownBlockBreaks(markdown: string) {
  const lines = markdown.split("\n");
  const out: string[] = [];
  let fence = "";

  for (const rawLine of lines) {
    const expandedLines = fence ? [rawLine] : splitInlineMarkdownBlockStarts(rawLine);
    for (const expandedLine of expandedLines) {
      const line = fence ? expandedLine : normalizeMarkdownLine(expandedLine);
      const currentFence = markdownFenceMarker(line);
      if (fence) {
        out.push(line);
        if (currentFence && currentFence[0] === fence[0] && currentFence.length >= fence.length) {
          fence = "";
        }
        continue;
      }

      if (shouldInsertMarkdownBlockBreakAfter(out, line)) {
        out.push("");
      }

      const blockType = markdownBlockType(line);
      if (blockType && shouldInsertMarkdownBlockBreak(out, blockType)) {
        out.push("");
      }
      out.push(line);
      if (currentFence) fence = currentFence;
    }
  }

  return out.join("\n");
}

function splitInlineMarkdownBlockStarts(line: string) {
  if (markdownTableLine(line)) return [line];

  const match = line.match(/^(.+?)((?:#{1,6}\s*\S|`{3,}|~{3,}|(?:[-*+]|\d{1,9}[.)])\s+\S|>\s*\S|(?:-{3,}|\*{3,}|_{3,})\s*$).*)$/);
  if (!match) return [line];
  const [, before, blockStart] = match;
  if (!before.trim() || /\s$/.test(before)) return [line];
  return [before.trimEnd(), "", blockStart];
}

function normalizeMarkdownLine(line: string) {
  return line.replace(/^(#{1,6})(\S)/, "$1 $2");
}

function shouldInsertMarkdownBlockBreakAfter(lines: string[], nextLine: string) {
  const previous = lines[lines.length - 1] ?? "";
  if (!previous.trim() || !nextLine.trim()) return false;

  const previousType = markdownBlockType(previous);
  const nextType = markdownBlockType(nextLine);
  return Boolean(previousType && !nextType && !["list", "quote", "table"].includes(previousType));
}

function shouldInsertMarkdownBlockBreak(lines: string[], nextType: string) {
  const previous = lines[lines.length - 1] ?? "";
  if (!previous.trim()) return false;

  const previousType = markdownBlockType(previous);
  return previousType !== nextType || !["list", "quote", "table"].includes(nextType);
}

function markdownBlockType(line: string) {
  if (!line.trim() || /^\s/.test(line)) return "";
  if (markdownFenceMarker(line)) return "fence";
  if (/^#{1,6}\s+\S/.test(line)) return "heading";
  if (/^(?:[-*+]\s+|\d{1,9}[.)]\s+)/.test(line)) return "list";
  if (/^>\s?/.test(line)) return "quote";
  if (markdownTableLine(line)) return "table";
  if (/^(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) return "rule";
  return "";
}

function markdownTableLine(line: string) {
  return /^\s*\|.+\|\s*$/.test(line);
}

function getOpenMarkdownFence(markdown: string) {
  let open = "";
  for (const line of markdown.split("\n")) {
    const marker = markdownFenceMarker(line);
    if (!marker) continue;
    if (!open) {
      open = marker;
      continue;
    }
    if (marker[0] === open[0] && marker.length >= open.length) {
      open = "";
    }
  }
  return open;
}

function markdownFenceMarker(line: string) {
  return line.match(/^\s{0,3}(`{3,}|~{3,})/)?.[1] ?? "";
}
