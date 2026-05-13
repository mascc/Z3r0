export function normalizeMarkdownForRender(text: string, streaming: boolean) {
  const normalized = text.replace(/\r\n?/g, "\n");
  if (!streaming) return normalized;

  const openFence = getOpenMarkdownFence(normalized);
  if (!openFence) return normalized;
  return `${normalized.endsWith("\n") ? normalized : `${normalized}\n`}${openFence}`;
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
