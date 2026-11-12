#!/usr/bin/env python3
"""Authenticated customer catalog load test for report NFR01. Requires httpx."""

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import getpass
import ipaddress
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter
from urllib.parse import urlsplit

import httpx


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def validate_base_url(value: str) -> None:
    url = urlsplit(value)
    if (url.scheme not in {"http", "https"} or not url.hostname or url.username is not None
            or url.path not in {"", "/"} or url.query or url.fragment):
        raise ValueError("--base-url must be an HTTP(S) origin without credentials, path, or query.")
    if url.scheme == "http":
        try:
            loopback = ipaddress.ip_address(url.hostname).is_loopback
        except ValueError:
            loopback = url.hostname == "localhost"
        if not loopback:
            raise ValueError("Use HTTPS for non-local servers so the benchmark password is encrypted.")


async def sign_in(client: httpx.AsyncClient, email: str, password: str) -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    if response.status_code in {401, 403}:
        raise ValueError("Sign-in failed. Check that the benchmark customer account is active and its password is correct.")
    if response.status_code == 429:
        raise ValueError("Sign-in is rate limited. Wait five minutes before trying again.")
    response.raise_for_status()
    payload = response.json()
    user = payload.get("user") if isinstance(payload, dict) else None
    if not isinstance(user, dict) or user.get("role") != "customer":
        raise ValueError("Use a customer account. Staff accounts cannot browse the catalog.")
    if not client.cookies.get("gather_session"):
        raise ValueError("The server did not set a customer session cookie.")


async def run(args: argparse.Namespace, email: str, password: str) -> dict:
    limits = httpx.Limits(max_connections=args.users, max_keepalive_connections=args.users)
    endpoints = ["/api/restaurants", "/api/menu"]
    records: list[tuple[str, float, bool, str]] = []
    active = peak = 0
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=args.timeout,
                                 limits=limits, follow_redirects=False) as client:
        # Log in once and share the cookie. Neither login nor warm-up is timed.
        await sign_in(client, email, password)
        response = await client.get("/api/restaurants")
        if response.status_code in {401, 403}:
            raise ValueError("Catalog access was denied after sign-in. Check the customer session and use HTTPS if secure cookies are enabled.")
        response.raise_for_status()
        restaurants = response.json().get("restaurants", [])
        if not restaurants:
            raise ValueError("Add at least one restaurant before benchmarking catalog and menu detail.")
        endpoints.append(f"/api/restaurants/{restaurants[0]['id']}")
        for endpoint in endpoints:
            (await client.get(endpoint)).raise_for_status()

        async def worker(worker_number: int) -> None:
            nonlocal active, peak
            for number in range(worker_number, args.requests, args.users):
                endpoint = endpoints[number % len(endpoints)]
                active += 1
                peak = max(peak, active)
                start = perf_counter()
                error = ""
                try:
                    result = await client.get(endpoint)
                    good = result.status_code == 200
                    if not good:
                        error = f"HTTP {result.status_code}"
                except httpx.HTTPError as exc:
                    good, error = False, type(exc).__name__
                elapsed = perf_counter() - start
                active -= 1
                records.append((endpoint, elapsed, good, error))

        started = perf_counter()
        await asyncio.gather(*(worker(n) for n in range(args.users)))
        duration = perf_counter() - started

    grouped = defaultdict(list)
    for endpoint, elapsed, good, error in records:
        grouped[endpoint].append((elapsed, good))

    def summary(samples: list[tuple[float, bool]]) -> dict:
        latencies = [sample[0] for sample in samples]
        failures = sum(not sample[1] for sample in samples)
        within_target = sum(good and latency <= args.target for latency, good in samples)
        return {
            "requests": len(samples),
            "failures": failures,
            "p50_ms": round(percentile(latencies, .5) * 1000, 2),
            "p95_ms": round(percentile(latencies, .95) * 1000, 2),
            "max_ms": round(max(latencies) * 1000, 2),
            "successful_within_target_percent": round(100 * within_target / len(samples), 2),
            "passed": failures == 0 and percentile(latencies, .95) <= args.target,
        }

    overall = summary([(elapsed, good) for _, elapsed, good, _ in records])
    endpoint_results = {endpoint: summary(samples) for endpoint, samples in grouped.items()}
    return {
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "authenticated_role": "customer",
        "session_count": 1,
        "concurrent_users": args.users,
        "peak_requests_in_flight": peak,
        "duration_seconds": round(duration, 2),
        "requests_per_second": round(len(records) / duration, 2),
        "target_p95_ms": args.target * 1000,
        "overall": overall,
        "endpoints": endpoint_results,
        "errors": dict((error, sum(r[3] == error for r in records))
                       for error in sorted({r[3] for r in records if r[3]})),
        "passed": overall["passed"] and all(s["passed"] for s in endpoint_results.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    account = parser.add_mutually_exclusive_group()
    account.add_argument("--demo", action="store_true", help="Use the seeded development customer.")
    account.add_argument("--email", help="Customer email; defaults to GATHER_LOAD_TEST_EMAIL.")
    parser.add_argument("--users", type=int, default=200)
    parser.add_argument("--requests", type=int, default=2000)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--target", type=float, default=2,
                        help="Maximum allowed p95 response time, seconds (default 2).")
    parser.add_argument("--output", type=Path, help="Optional JSON evidence file.")
    args = parser.parse_args()
    if not 1 <= args.users <= 200:
        parser.error("--users must be between 1 and 200 for the stated NFR01 test.")
    if args.requests < args.users or args.timeout <= 0 or args.target <= 0:
        parser.error("Requests must cover all users; timeout and target must be positive.")
    try:
        validate_base_url(args.base_url)
        email = "customer@localtable.vn" if args.demo else args.email or os.getenv("GATHER_LOAD_TEST_EMAIL")
        if not email:
            parser.error("Choose --demo for the seeded account, or supply --email / GATHER_LOAD_TEST_EMAIL.")
        password = os.getenv("GATHER_LOAD_TEST_PASSWORD")
        if not password and args.demo:
            password = "Demo123!"
        if not password:
            if not sys.stdin.isatty():
                parser.error("Set GATHER_LOAD_TEST_PASSWORD for non-interactive runs.")
            password = getpass.getpass("Customer password: ")
        result = asyncio.run(run(args, email, password))
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        print(f"Cannot prepare catalog load test: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
