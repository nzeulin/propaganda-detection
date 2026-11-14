const HANDLE = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const DID = /^did:plc:[a-z2-7]{24}$/;

// Normalize presentation copied from chat, without extracting URLs from arbitrary
// prose or relaxing the server's profile-only / fixed-public-host restrictions.
export function parseBlueskyProfiles(input: string): string[] {
  if (input.length > 4000) throw new Error("Profile list exceeds 4,000 characters.");
  const entries = input
    .replace(/[\u200B-\u200D\u2060\uFEFF]/g, "")
    .replace(/^\s*(?:[-*+•]|\d+[.)])\s+/gm, "")
    .replace(/\[[^\]\r\n]*\]\((https:\/\/[^\s)]+)\)/g, "$1")
    .replace(/<(https:\/\/[^\s<>]+)>/g, "$1")
    .replace(/`([^`\r\n]+)`/g, "$1")
    .split(/[\s,]+/)
    .filter(Boolean);
  const actors = entries.map((entry, index) => {
    const value = entry.replace(/^(\*\*|__)(.+)\1$/, "$2");
    const profile = /^https:\/\/bsky\.app\/profile\/([^/?#\s]+)\/?$/.exec(value);
    const actor = (profile ? profile[1] : value).replace(/^@/, "").toLowerCase();
    if (value.length > 300 || actor.length > 200 || (!HANDLE.test(actor) && !DID.test(actor))) {
      throw new Error(`Profile ${index + 1} (${JSON.stringify(entry)}) is not a valid Bluesky profile. Use https://bsky.app/profile/reuters.com or @reuters.com. Remove extra text; post links and other websites are not supported.`);
    }
    return actor;
  });
  const unique = [...new Set(actors)];
  if (unique.length > 10) throw new Error("Choose at most 10 public Bluesky profiles per collection.");
  return unique;
}