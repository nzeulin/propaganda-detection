export type EntityLabels = Map<string, { full: string; compact: string }>;

function shorten(value: string, limit = 24): string {
  const characters = Array.from(value);
  if (characters.length <= limit) return value;
  const head = Math.ceil((limit - 1) * 2 / 3);
  return `${characters.slice(0, head).join("")}…${characters.slice(-(limit - head - 1)).join("")}`;
}

export function createEntityLabels(
  nodes: readonly { id: string; kind: string; data: { source_id: string; handle?: string } }[],
  accountLabels: Record<string, string> = {},
): EntityLabels {
  const labels: EntityLabels = new Map(Object.entries(accountLabels).map(([id, full]) => [id, { full, compact: full }]));
  const accounts = new Set(Object.keys(accountLabels));
  for (const node of nodes) {
    const full = node.kind === "account" && node.data.handle
      ? `@${node.data.handle.replace(/^@/, "")}`
      : accountLabels[node.id] || node.data.source_id || node.id;
    labels.set(node.id, { full, compact: full });
    if (node.kind === "account") accounts.add(node.id);
  }

  // Include off-map accounts so pagination and selections cannot change collision suffixes.
  const groups = new Map<string, string[]>();
  for (const id of accounts) {
    const label = labels.get(id)!;
    label.compact = shorten(label.full.replace(/^(@\S+)\.bsky\.social$/i, "$1"));
    const group = groups.get(label.compact) || [];
    group.push(id);
    groups.set(label.compact, group);
  }
  const used = new Set([...groups].filter(([, ids]) => ids.length === 1).map(([name]) => name));
  for (const [name, ids] of [...groups].sort(([a], [b]) => a.localeCompare(b))) {
    if (ids.length === 1) continue;
    ids.sort((a, b) => labels.get(a)!.full.localeCompare(labels.get(b)!.full) || a.localeCompare(b));
    let index = 1;
    for (const id of ids) {
      let compact: string;
      do {
        const suffix = ` · ${index++}`;
        compact = shorten(name, 24 - suffix.length) + suffix;
      } while (used.has(compact));
      labels.get(id)!.compact = compact;
      used.add(compact);
    }
  }
  return labels;
}

export function entityLabel(id: string, labels: EntityLabels, compact = false): string {
  const label = labels.get(id);
  return (compact ? label?.compact : label?.full) || id;
}
