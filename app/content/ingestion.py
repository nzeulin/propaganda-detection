"""Bounded article ingestion with DNS-pinned public destinations on every redirect."""

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit

import aiohttp
import trafilatura
from aiohttp.abc import AbstractResolver
from fastapi import HTTPException
from yarl import URL


def public_address(address: str):
    """Reject non-unicast and embedded private destinations, including IPv6 transition forms."""
    ip = ipaddress.ip_address(address)
    if not ip.is_global or ip.is_multicast or ip.is_reserved:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.is_site_local:
            return False
        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded and not public_address(str(embedded)):
            return False
        if ip.teredo or ip in ipaddress.ip_network("64:ff9b::/96"):
            return False
    return True


class PublicResolver(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        records = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), 5
        )
        addresses = {record[4][0] for record in records}
        if not addresses or any(not public_address(address) for address in addresses):
            raise ValueError("Only public Internet addresses are allowed.")
        # aiohttp connects directly to these validated IPs; it does not resolve them a second time.
        return [
            {
                "hostname": host,
                "host": address,
                "port": port,
                "family": socket.AF_INET6 if ":" in address else socket.AF_INET,
                "proto": 0,
                "flags": socket.AI_NUMERICHOST,
            }
            for address in addresses
        ]

    async def close(self):
        pass


async def fetch_article(url: str):
    try:
        async with asyncio.timeout(25):
            connector = aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False)
            async with aiohttp.ClientSession(
                connector=connector,
                trust_env=False,
                auto_decompress=False,
                timeout=aiohttp.ClientTimeout(total=12),
                headers={"User-Agent": "VeritasScope/0.1", "Accept-Encoding": "identity"},
            ) as client:
                current = URL(url)
                for _ in range(5):
                    parsed = urlsplit(str(current))
                    if (
                        parsed.scheme not in ("http", "https")
                        or not parsed.hostname
                        or parsed.username
                        or parsed.password
                        or parsed.port not in (None, 80, 443)
                    ):
                        raise ValueError("Use a public HTTP(S) article URL on port 80 or 443.")
                    # aiohttp bypasses resolvers for literal IPs, so validate those explicitly.
                    try:
                        literal = ipaddress.ip_address(parsed.hostname)
                    except ValueError:
                        literal = None
                    if literal is not None and not public_address(str(literal)):
                        raise ValueError("Private, loopback and reserved addresses are blocked.")
                    async with client.get(current, allow_redirects=False) as response:
                        if response.status in (301, 302, 303, 307, 308):
                            location = response.headers.get("Location")
                            if not location:
                                raise ValueError("Article redirect has no destination.")
                            current = current.join(URL(location))
                            continue
                        if response.status != 200:
                            raise ValueError(
                                f"Article server returned HTTP {response.status}; paste the text instead."
                            )
                        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                            raise ValueError(
                                "Server ignored the uncompressed fetch request; paste the text instead."
                            )
                        media = response.headers.get("Content-Type", "").split(";")[0].lower()
                        if media not in ("text/html", "application/xhtml+xml", "text/plain"):
                            raise ValueError(
                                "This URL is not an HTML article or plain text. Paste article text instead."
                            )
                        body = bytearray()
                        async for chunk in response.content.iter_chunked(16384):
                            body.extend(chunk)
                            if len(body) > 2_000_000:
                                raise ValueError(
                                    "Article exceeds the 2 MB fetch limit; paste a shorter text."
                                )
                        html = body.decode(response.charset or "utf-8", errors="replace")
                        if media == "text/plain":
                            text, title = html, None
                        else:
                            doc = trafilatura.bare_extraction(
                                html,
                                include_comments=False,
                                include_tables=False,
                                favor_precision=True,
                                with_metadata=True,
                            )
                            text, title = (doc.text, doc.title) if doc else (None, None)
                        if not text or len(text.strip()) < 80:
                            raise ValueError(
                                "No readable article found; paste its body text (login/JS pages are unsupported)."
                            )
                        return text, title, str(current)
                raise ValueError("Too many article redirects; paste the text instead.")
    except (ValueError, aiohttp.ClientError, TimeoutError, OSError, LookupError) as exc:
        raise HTTPException(422, f"Unable to read URL: {exc}") from exc


def normalize(original: str):
    text = original.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text or len(text) > 40000:
        raise HTTPException(422, "Article must contain 1–40,000 Unicode characters.")
    paragraphs = [
        {"id": f"p{i + 1}", "start": match.start(), "end": match.end(), "text": match.group()}
        for i, match in enumerate(re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", text))
        if match.group().strip()
    ]
    return text, paragraphs
