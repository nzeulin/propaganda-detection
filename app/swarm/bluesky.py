"""Bounded, opt-in collection of public authored posts, not platform-wide search.

Run with ``python -m app.swarm.bluesky --actor bsky.app --actor atproto.com``.
Only the fixed public AppView is contacted. Submitted links/media are never fetched.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ValidationError

from app.core.ingestion import DatasetInput, ImportRow, prepare_dataset
from app.swarm.engine import normalized_url

PUBLIC_API = "https://public.api.bsky.app/xrpc"
MAX_RESPONSE_BYTES = 2_000_000
MAX_ACTORS = 10
MAX_POSTS_PER_ACTOR = 200
MAX_PAGES_PER_ACTOR = 3
COLLECTION_VERSION = "bluesky-public-inputs-v2"


def normalize_actor(value):
    """Accept handles or exact HTTPS Bluesky profile URLs, never arbitrary URLs."""
    if len(value) > 300:
        raise ValueError("Profile input is too long")
    value = value.strip()
    if value.startswith("https://"):
        parts = urlsplit(value)
        if (
            parts.netloc != "bsky.app" or parts.query or parts.fragment
            or not re.fullmatch(r"/profile/[^/]+/?", parts.path)
        ):
            raise ValueError("Use a public https://bsky.app/profile/HANDLE URL, not a post or other website")
        value = parts.path.strip("/").split("/")[1]
    value = value.removeprefix("@").lower()
    if not (
        re.fullmatch(r"did:plc:[a-z2-7]{24}", value)
        or re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?", value)
    ) or len(value) > 200:
        raise ValueError("Enter a Bluesky handle such as bsky.app or an HTTPS Bluesky profile URL")
    return value


def normalize_source(value):
    """Return an actor or exact post URL; never expand a post into a feed."""
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError("Enter a Bluesky profile, handle or post URL of at most 300 characters")
    value = value.strip()
    if value.startswith("https://"):
        parts = urlsplit(value)
        post = re.fullmatch(r"/profile/([^/]+)/post/([a-zA-Z0-9._~:-]{1,512})/?", parts.path)
        if post:
            if parts.netloc != "bsky.app" or parts.query or parts.fragment or post[2] in {".", ".."}:
                raise ValueError("Use an exact HTTPS bsky.app profile or post URL without query or fragment")
            actor = normalize_actor(post[1])
            return f"https://bsky.app/profile/{actor}/post/{post[2]}"
    return normalize_actor(value)


def _check_cancelled(cancellation):
    if cancellation is not None and cancellation.is_set():
        raise CollectionError("Public collection cancelled; no dataset was imported")


class CollectionError(RuntimeError):
    """A collection failure, never replaced with synthetic or scraped data."""


def _read_json(client, method, params, *, cancellation=None):
    _check_cancelled(cancellation)
    try:
        with client.stream("GET", f"{PUBLIC_API}/{method}", params=params) as response:
            if response.status_code != 200:
                raise CollectionError(
                    f"{method} returned HTTP {response.status_code}. Collection stopped; "
                    "no automatic retries, alternate hosts, or synthetic fallback were used."
                )
            content = bytearray()
            for chunk in response.iter_bytes():
                _check_cancelled(cancellation)
                content.extend(chunk)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise CollectionError("Public API response exceeded the 2 MB safety limit")
            try:
                value = json.loads(content)
            except (ValueError, UnicodeError) as exc:
                raise CollectionError("Public API returned an unreadable JSON response") from exc
            if not isinstance(value, dict):
                raise CollectionError("Public API returned an unexpected response shape")
            return value
    except httpx.HTTPError as exc:
        raise CollectionError(f"Public API request failed ({type(exc).__name__}); no automatic retry") from exc


def _structured_links(record):
    """Keep original text unchanged; preserve all rich-text URLs in provenance."""
    candidates = []
    facets = record.get("facets", [])
    for facet in facets if isinstance(facets, list) else []:
        features = facet.get("features", []) if isinstance(facet, dict) else []
        for feature in features if isinstance(features, list) else []:
            if isinstance(feature, dict) and feature.get("$type") == "app.bsky.richtext.facet#link":
                candidates.append(feature.get("uri"))
    embed = record.get("embed")
    if isinstance(embed, dict):
        media = embed.get("media", embed)
        external = media.get("external") if isinstance(media, dict) else None
        if isinstance(external, dict):
            candidates.append(external.get("uri"))
    links, seen = [], set()
    for candidate in candidates:
        key = normalized_url(candidate) if isinstance(candidate, str) else None
        if key is not None and key not in seen:
            links.append(candidate)
            seen.add(key)
    return links


def normalize_authored_post(entry, did):
    """Return (import row, provenance, skip reason); never substitute indexedAt."""
    if not isinstance(entry, dict):
        return None, None, "malformed_entry"
    reason = entry.get("reason")
    if isinstance(reason, dict) and reason.get("$type") == "app.bsky.feed.defs#reasonRepost":
        return None, None, "repost_not_collected"
    post = entry.get("post")
    if not isinstance(post, dict):
        return None, None, "missing_post"
    author, record, uri = post.get("author"), post.get("record"), post.get("uri")
    if not isinstance(author, dict) or author.get("did") != did:
        return None, None, "not_selected_author"
    if not isinstance(record, dict) or record.get("$type") != "app.bsky.feed.post":
        return None, None, "not_a_post_record"
    prefix = f"at://{did}/app.bsky.feed.post/"
    if not isinstance(uri, str) or not uri.startswith(prefix) or not uri[len(prefix):] or "/" in uri[len(prefix):]:
        return None, None, "invalid_post_uri"
    created_at = record.get("createdAt")
    if not isinstance(created_at, str) or not created_at:
        return None, None, "missing_posting_timestamp"
    links = _structured_links(record)
    try:
        row = ImportRow(
            account_id=did,
            content_id=uri,
            action="created",
            timestamp=created_at,
            text=record.get("text", ""),
            url=links[0] if links else None,
            platform="bluesky",
        ).model_dump(exclude_none=True)
    except (ValidationError, ValueError, OverflowError):
        return None, None, "invalid_post_fields"
    rkey = uri[len(prefix):]
    provenance = {
        "content_id": uri,
        "account_did": did,
        "author_handle_at_collection": author.get("handle"),
        "source_post_url": f"https://bsky.app/profile/{quote(did, safe=':')}/post/{quote(rkey, safe='')}",
        "post_created_at": created_at,
        "source_indexed_at": post.get("indexedAt"),
        "post_cid": post.get("cid"),
        "structured_urls": links,
        "record_sha256": hashlib.sha256(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "original_record": record,
    }
    return row, provenance, None


def collect_author_feeds(actors, per_actor=100, *, client=None, cancellation=None):
    """Collect capped public feeds and/or exact linked posts (legacy entry name).

    A post URL imports only that post, not the author's feed or amplification.
    This is not a keyword search, bot-labeled dataset, or complete network sample.
    The caller owns an injected HTTP client; default clients are always closed.
    """
    if not actors or len(actors) > MAX_ACTORS or any(
        not isinstance(actor, str) or not actor.strip() or len(actor) > 300 for actor in actors
    ):
        raise ValueError(f"Supply between 1 and {MAX_ACTORS} public profiles, handles or post URLs")
    if type(per_actor) is not int or not 1 <= per_actor <= MAX_POSTS_PER_ACTOR:
        raise ValueError(f"Posts per account must be between 1 and {MAX_POSTS_PER_ACTOR}")
    selections = list(dict.fromkeys(normalize_source(actor) for actor in actors))
    post_urls = [value for value in selections if value.startswith("https://")]
    profile_count = len(selections) - len(post_urls)
    started = datetime.now(UTC).isoformat()
    rows, sources, account_reports = [], {}, []
    accounts, seen = set(), set()
    requests = 0
    context = nullcontext(client) if client is not None else httpx.Client(
        timeout=httpx.Timeout(25),
        follow_redirects=False,
        headers={"User-Agent": "VeritasScope/0.1 (public author-feed research prototype)"},
    )
    with context as transport:
        for selection in selections:
            is_post = selection.startswith("https://")
            actor = selection.split("/")[4] if is_post else selection
            profile = _read_json(transport, "app.bsky.actor.getProfile", {"actor": actor}, cancellation=cancellation)
            requests += 1
            did, handle = profile.get("did"), profile.get("handle")
            if not isinstance(did, str) or not did.startswith("did:") or not isinstance(handle, str):
                raise CollectionError("Public profile was missing its stable account ID or handle")
            if is_post:
                uri = f"at://{did}/app.bsky.feed.post/{selection.rsplit('/', 1)[1]}"
                data = _read_json(transport, "app.bsky.feed.getPosts", {"uris": [uri]}, cancellation=cancellation)
                requests += 1
                posts = data.get("posts")
                if not isinstance(posts, list) or len(posts) != 1 or not isinstance(posts[0], dict) or posts[0].get("uri") != uri:
                    raise CollectionError(f"The public API did not return the exact requested post: {selection}. No dataset was imported.")
                row, source, skip = normalize_authored_post({"post": posts[0]}, did)
                if skip:
                    raise CollectionError(f"Requested post could not be imported ({skip}): {selection}. No dataset was imported.")
                duplicate = uri in seen
                if not duplicate:
                    seen.add(uri)
                    rows.append(row)
                    sources[uri] = source
                sources[uri].setdefault("requested_post_urls", []).append(selection)
                account_reports.append({
                    "requested_actor": actor, "requested_source": selection, "source_type": "post",
                    "did": did, "handle": handle, "pages": 0, "feed_entries_received": 0,
                    "posts_collected": int(not duplicate), "stop_reason": "duplicate_post" if duplicate else "selected_post",
                    "more_feed_available": False, "skipped_entries": {"duplicate_post": 1} if duplicate else {},
                    "oldest_post_utc": row["timestamp"], "newest_post_utc": row["timestamp"],
                })
                continue
            if did in accounts:
                account_reports.append({"requested_actor": actor, "did": did, "stop_reason": "duplicate_account_alias"})
                continue
            accounts.add(did)
            cursor, used_cursors, skipped = None, set(), Counter()
            report = {
                "requested_actor": actor, "requested_source": selection, "source_type": "profile",
                "did": did, "handle": handle,
                "pages": 0, "feed_entries_received": 0, "posts_collected": 0,
                "stop_reason": "page_limit", "more_feed_available": False,
            }
            for _ in range(MAX_PAGES_PER_ACTOR):
                params = {
                    "actor": did, "limit": min(100, per_actor - report["posts_collected"]),
                    "filter": "posts_no_replies", "includePins": "false",
                }
                if cursor:
                    params["cursor"] = cursor
                data = _read_json(transport, "app.bsky.feed.getAuthorFeed", params, cancellation=cancellation)
                requests += 1
                feed = data.get("feed")
                if not isinstance(feed, list):
                    raise CollectionError("Public author feed was missing its feed array")
                report["pages"] += 1
                report["feed_entries_received"] += len(feed)
                for entry in feed:
                    _check_cancelled(cancellation)
                    row, source, skip = normalize_authored_post(entry, did)
                    if skip:
                        skipped[skip] += 1
                        continue
                    if row["content_id"] in seen:
                        skipped["duplicate_post"] += 1
                        continue
                    seen.add(row["content_id"])
                    rows.append(row)
                    sources[row["content_id"]] = source
                    report["posts_collected"] += 1
                    if report["posts_collected"] >= per_actor:
                        break
                next_cursor = data.get("cursor")
                report["more_feed_available"] = bool(next_cursor)
                if report["posts_collected"] >= per_actor:
                    report["stop_reason"] = "post_limit"
                    break
                if not feed or not next_cursor:
                    report["stop_reason"] = "feed_exhausted"
                    break
                if not isinstance(next_cursor, str) or next_cursor in used_cursors:
                    report["stop_reason"] = "repeated_or_invalid_cursor"
                    break
                used_cursors.add(next_cursor)
                cursor = next_cursor
            report["skipped_entries"] = dict(skipped)
            account_rows = [row for row in rows if row["account_id"] == did]
            report["oldest_post_utc"] = min((row["timestamp"] for row in account_rows), default=None)
            report["newest_post_utc"] = max((row["timestamp"] for row in account_rows), default=None)
            account_reports.append(report)
    rows.sort(key=lambda row: (row["timestamp"], row["content_id"]))
    warnings = [
        "Selected public sources only, not a keyword search or representative platform sample.",
        "Only authored posts are imported. Repost wrappers and reply relationships are not reconstructed.",
        "Posting times come from author-provided createdAt; indexedAt is preserved separately, never substituted.",
        "No bot labels or independent ground truth are available; no detection accuracy can be inferred.",
    ]
    if profile_count:
        warnings.append("Per-account post/page caps and source API filtering can omit activity; account time ranges may differ.")
    if post_urls:
        warnings.append(
            "Post URLs import only the exact linked posts, including a reply's text if explicitly linked. "
            "They do not expand author feeds or collect replies/reposts. A single post cannot establish recurring coordination."
        )
    extra_urls = sum(max(0, len(source["structured_urls"]) - 1) for source in sources.values())
    if extra_urls:
        warnings.append(
            f"{extra_urls} additional structured URL destinations are preserved in provenance but not mapped "
            "to the import format's single URL field. Original text is unchanged."
        )
    if not rows:
        warnings.append("No valid authored posts were collected. No detector-ready import can be created.")
    manifest = {
        "source": "bluesky", "method": "public_mixed_sources" if post_urls and profile_count else
        "public_selected_posts" if post_urls else "public_author_feeds", "synthetic": False,
        "endpoint": PUBLIC_API, "started_at_utc": started, "finished_at_utc": datetime.now(UTC).isoformat(),
        "requested_sources": selections, "requested_profile_count": profile_count,
        "requested_post_count": len(post_urls),
        "per_account_post_limit": per_actor, "per_account_page_limit": MAX_PAGES_PER_ACTOR,
        "api_requests": requests, "post_count": len(rows),
        "accounts_with_posts": len({row["account_id"] for row in rows}),
        "accounts": account_reports, "warnings": warnings,
        "oldest_post_utc": min((row["timestamp"] for row in rows), default=None),
        "newest_post_utc": max((row["timestamp"] for row in rows), default=None),
    }
    # Apply the same complete-import validation as the real dataset endpoint.
    _check_cancelled(cancellation)
    if rows:
        prepare_dataset(DatasetInput(name="Bluesky public source snapshot", rows=rows))
    return rows, {"collection": manifest, "posts": sources}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor", action="append", required=True, help="Public handle, DID, profile URL or exact post URL; repeatable")
    parser.add_argument("--per-actor", type=int, default=100, help="Maximum posts per profile (1–200); post URLs import one post each")
    parser.add_argument("--output-dir", type=Path, help="New output directory; defaults to ignored .local-data/bluesky")
    args = parser.parse_args(argv)
    output = args.output_dir or Path(".local-data/bluesky") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    if output.exists():
        parser.error("Output directory already exists; choose a new directory to avoid overwriting evidence")
    try:
        rows, provenance = collect_author_feeds(args.actor, args.per_actor)
    except (CollectionError, ValueError) as exc:
        parser.exit(1, f"Collection failed: {exc}\n")
    if not rows:
        parser.exit(1, "No valid authored posts found. No files written.\n")
    output.mkdir(parents=True, exist_ok=False)
    for filename, value in (("rows.json", rows), ("provenance.json", provenance)):
        (output / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_directory": str(output), **provenance["collection"]}, indent=2))


if __name__ == "__main__":
    main()