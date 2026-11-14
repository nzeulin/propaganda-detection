const HANDLE = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const DID = /^did:plc:[a-z2-7]{24}$/;

// Normalize presentation copied from chat, without extracting URLs from arbitrary
// prose or relaxing the server's fixed-public-host restrictions. Post URLs stay
// post URLs: they must never silently become whole-profile feed requests.
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
    const post = /^https:\/\/bsky\.app\/profile\/([^/?#\s]+)\/post\/([a-zA-Z0-9._~:-]{1,512})\/?$/.exec(value);
    const profile = /^https:\/\/bsky\.app\/profile\/([^/?#\s]+)\/?$/.exec(value);
    const actor = (post ? post[1] : profile ? profile[1] : value).replace(/^@/, "").toLowerCase();
    if (value.length > 300 || actor.length > 200 || (!HANDLE.test(actor) && !DID.test(actor)) || (post && [".", ".."].includes(post[2]))) {
      throw new Error(`Input ${index + 1} (${JSON.stringify(entry)}) is not a valid Bluesky profile or post URL. Use @reuters.com, https://bsky.app/profile/reuters.com, or https://bsky.app/profile/HANDLE/post/POST_ID. Other websites, query strings and extra text are not supported.`);
    }
    return post ? `https://bsky.app/profile/${actor}/post/${post[2]}` : actor;
  });
  const unique = [...new Set(actors)];
  if (unique.length > 10) throw new Error(`Too many sources: ${unique.length} unique inputs. Maximum 10 Bluesky profiles or post URLs per run.`);
  return unique;
}