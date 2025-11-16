#!/usr/bin/env python3
"""
Bootstrap Jackett + FlareSolverr for torrent_finder.

The script can:
- Spin up both services via Docker (linuxserver/jackett + ghcr.io/flaresolverr/flaresolverr).
- Detect existing installations and reuse them.
- Configure Jackett with a curated list of public trackers.
- Wire Jackett up to FlareSolverr and surface the Torznab API key (optionally injecting it
  into torrent_finder's config.json).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urljoin, urlparse

import requests
from requests import Response
from requests.exceptions import RequestException


DEFAULT_TRACKERS = (
    "1337x",
    "torrentgalaxyclone",
    "yts",
    "eztv",
    "nyaasi",
    "limetorrents",
)
DEFAULT_STACK_DIR = Path.home() / ".local/share/torrent_finder/stack"
DEFAULT_TIMEOUT = 180  # seconds


class SetupError(RuntimeError):
    """Raised when the stack cannot be prepared."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Jackett + FlareSolverr and auto-configure Jackett.")
    parser.add_argument(
        "--jackett-url",
        default="http://127.0.0.1:9117",
        help="Base URL for Jackett (only used for detection + API calls).",
    )
    parser.add_argument(
        "--flaresolverr-url",
        default="http://127.0.0.1:8191",
        help="Base URL for FlareSolverr (used for health checks + Jackett config).",
    )
    parser.add_argument(
        "--stack-dir",
        type=Path,
        default=DEFAULT_STACK_DIR,
        help=f"Where to write docker-compose.yml and persistent volumes (default: {DEFAULT_STACK_DIR})",
    )
    parser.add_argument(
        "--trackers",
        nargs="+",
        default=list(DEFAULT_TRACKERS),
        help="Space-separated Jackett indexer IDs to auto-configure.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Seconds to wait for each service to become reachable (default: {DEFAULT_TIMEOUT}).",
    )
    parser.add_argument(
        "--torznab-path",
        default="/torznab/all",
        help="Relative Torznab path that will be written to config.json when updating.",
    )
    parser.add_argument(
        "--config-file",
        type=Path,
        default=Path("config.json"),
        help="torrent_finder configuration to update with the Jackett API key (if eligible).",
    )
    parser.add_argument(
        "--force-config-update",
        action="store_true",
        help="Overwrite torznab.url/apikey in the config file even when they are already populated.",
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        help="Assume Jackett/FlareSolverr are already handled externally and skip docker compose.",
    )
    parser.add_argument(
        "--compose-command",
        default="",
        help="Override the docker compose command, e.g. 'docker compose' or 'docker-compose'.",
    )
    return parser.parse_args()


def normalize_url(url: str) -> str:
    if "://" not in url:
        url = f"http://{url}"
    return url.rstrip("/")


def run_command(cmd: Sequence[str], cwd: Path | None = None) -> None:
    display = " ".join(cmd)
    print(f"[cmd] {display}")
    subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None)


def detect_compose_command(override: str | None = None) -> Sequence[str]:
    if override:
        return shlex.split(override)

    docker = shutil.which("docker")
    if docker:
        try:
            subprocess.run([docker, "compose", "version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return [docker, "compose"]
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    docker_compose = shutil.which("docker-compose")
    if docker_compose:
        try:
            subprocess.run([docker_compose, "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return [docker_compose]
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    raise SetupError("Could not locate a working docker compose command. Install Docker or pass --compose-command.")


def resolve_ids() -> tuple[int, int]:
    uid = getattr(os, "getuid", lambda: 1000)()
    gid = getattr(os, "getgid", lambda: 1000)()
    return uid, gid


def write_compose_file(stack_dir: Path, jackett_port: int, flaresolverr_port: int) -> Path:
    stack_dir.mkdir(parents=True, exist_ok=True)
    config_dir = stack_dir / "jackett" / "config"
    downloads_dir = stack_dir / "downloads"
    config_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)

    uid, gid = resolve_ids()
    compose_path = stack_dir / "docker-compose.yml"
    content = textwrap.dedent(
        f"""
        version: "3.9"
        services:
          jackett:
            image: lscr.io/linuxserver/jackett:latest
            container_name: torrent-finder-jackett
            environment:
              - PUID={uid}
              - PGID={gid}
              - TZ=UTC
              - AUTO_UPDATE=true
            volumes:
              - {config_dir}:/config
              - {downloads_dir}:/downloads
            ports:
              - "{jackett_port}:9117"
            restart: unless-stopped

          flaresolverr:
            image: ghcr.io/flaresolverr/flaresolverr:latest
            container_name: torrent-finder-flaresolverr
            environment:
              - LOG_LEVEL=info
            ports:
              - "{flaresolverr_port}:8191"
            restart: unless-stopped
        """
    ).strip()
    compose_path.write_text(content + "\n", encoding="utf-8")
    return compose_path


def url_for(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def jackett_status(session: requests.Session, base_url: str) -> tuple[bool, dict | None]:
    try:
        resp = session.get(url_for(base_url, "api/v2.0/server/config"), timeout=5)
        if resp.ok:
            return True, resp.json()
    except RequestException:
        return False, None
    return False, None


def wait_for_jackett(session: requests.Session, base_url: str, timeout: int) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        ok, cfg = jackett_status(session, base_url)
        if ok and cfg:
            return cfg
        time.sleep(3)
    raise SetupError(f"Jackett did not become ready within {timeout} seconds.")


def flaresolverr_ready(session: requests.Session, base_url: str) -> bool:
    try:
        resp = session.get(url_for(base_url, "health"), timeout=5)
        return resp.ok
    except RequestException:
        return False


def wait_for_flaresolverr(session: requests.Session, base_url: str, timeout: int) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if flaresolverr_ready(session, base_url):
            return
        time.sleep(3)
    raise SetupError(f"FlareSolverr did not become ready within {timeout} seconds.")


def configured_indexers(session: requests.Session, base_url: str) -> set[str]:
    try:
        resp = session.get(url_for(base_url, "api/v2.0/indexers"), params={"configured": "true"}, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        return {item["id"] for item in payload}
    except (RequestException, ValueError, KeyError) as exc:
        raise SetupError(f"Could not enumerate configured indexers: {exc}") from exc


def configure_indexer(session: requests.Session, base_url: str, tracker_id: str) -> bool:
    config_url = url_for(base_url, f"api/v2.0/indexers/{tracker_id}/config")
    try:
        resp = session.get(config_url, timeout=15)
        resp.raise_for_status()
        config_items = resp.json()
    except RequestException as exc:
        print(f"[warn] Failed to pull config for {tracker_id}: {exc}")
        return False

    if not isinstance(config_items, list):
        print(f"[warn] Unexpected config schema for {tracker_id}, skipping.")
        return False

    try:
        resp = session.post(config_url, json=config_items, timeout=30)
        resp.raise_for_status()
        print(f"[ok] Configured {tracker_id}.")
        return True
    except RequestException as exc:
        print(f"[warn] Could not configure {tracker_id}: {exc}")
        return False


def ensure_trackers(session: requests.Session, base_url: str, tracker_ids: Iterable[str]) -> list[str]:
    already = configured_indexers(session, base_url)
    added: list[str] = []
    for tracker_id in tracker_ids:
        if tracker_id in already:
            print(f"[skip] {tracker_id} already configured.")
            continue
        if configure_indexer(session, base_url, tracker_id):
            added.append(tracker_id)
    return added


def ensure_flaresolverr_link(session: requests.Session, base_url: str, config: dict, flaresolverr_url: str) -> dict:
    desired = flaresolverr_url
    updated = dict(config)
    changed = False

    if updated.get("flaresolverrurl") != desired:
        updated["flaresolverrurl"] = desired
        changed = True

    if updated.get("flaresolverr_maxtimeout", 0) < 120000:
        updated["flaresolverr_maxtimeout"] = 120000
        changed = True

    if not changed:
        return config

    try:
        resp = session.post(url_for(base_url, "api/v2.0/server/config"), json=updated, timeout=15)
        resp.raise_for_status()
        print("[ok] Linked Jackett to FlareSolverr.")
        return resp.json()
    except RequestException as exc:
        raise SetupError(f"Failed to update Jackett server config: {exc}") from exc


def update_app_config(config_path: Path, torznab_url: str, api_key: str, force: bool) -> bool:
    if not config_path.exists():
        return False

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SetupError(f"Cannot read {config_path}: {exc}") from exc

    section = data.setdefault("torznab", {})
    changed = False

    if force or section.get("apikey") in (None, "", "CHANGE_ME"):
        section["apikey"] = api_key
        changed = True

    if force or not section.get("url"):
        section["url"] = torznab_url
        changed = True

    if changed:
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def compose_ports_from_url(url: str) -> int:
    parsed = urlparse(url)
    if not parsed.hostname:
        raise SetupError(f"Invalid URL: {url}")
    if parsed.scheme == "https":
        default_port = 443
    else:
        default_port = 80
    return parsed.port or default_port


def main() -> None:
    args = parse_args()

    jackett_url = normalize_url(args.jackett_url)
    flaresolverr_url = normalize_url(args.flaresolverr_url)
    torznab_url = url_for(jackett_url, args.torznab_path)

    session = requests.Session()

    jackett_ok, config = jackett_status(session, jackett_url)
    flare_ok = flaresolverr_ready(session, flaresolverr_url)

    compose_cmd: Sequence[str] | None = None
    compose_file: Path | None = None

    if not args.no_docker and (not jackett_ok or not flare_ok):
        compose_cmd = detect_compose_command(args.compose_command or None)
        jackett_port = compose_ports_from_url(jackett_url)
        flaresolverr_port = compose_ports_from_url(flaresolverr_url)
        compose_file = write_compose_file(args.stack_dir.expanduser(), jackett_port, flaresolverr_port)
        print(f"[info] Written compose file to {compose_file}")
        run_command([*compose_cmd, "-f", str(compose_file), "up", "-d"], cwd=args.stack_dir)
        time.sleep(5)

    if not jackett_ok:
        config = wait_for_jackett(session, jackett_url, args.timeout)
    else:
        config = config or wait_for_jackett(session, jackett_url, args.timeout)

    if not flare_ok:
        wait_for_flaresolverr(session, flaresolverr_url, args.timeout)

    config = ensure_flaresolverr_link(session, jackett_url, config, flaresolverr_url)
    api_key = config.get("api_key", "")
    if not api_key:
        raise SetupError("Jackett did not report an API key.")

    added = ensure_trackers(session, jackett_url, args.trackers)

    config_changed = update_app_config(args.config_file, torznab_url, api_key, args.force_config_update)

    print("\n=== Summary ===")
    print(f"Jackett URL       : {jackett_url}")
    print(f"FlareSolverr URL  : {flaresolverr_url}")
    print(f"Torznab endpoint  : {torznab_url}")
    print(f"API key           : {api_key}")
    if compose_file:
        print(f"Docker compose    : {compose_file}")
    print(f"Trackers added    : {', '.join(added) if added else 'none (already present)'}")
    print(f"Config updated    : {'yes' if config_changed else 'no changes'}")
    print(
        "\nNext steps:\n"
        f"  1. Visit {jackett_url} in your browser.\n"
        "  2. Add or update your Jackett indexers (none are added automatically).\n"
        "  3. Copy the Torznab API key from the Jackett dashboard into config.json if it wasn't updated automatically."
    )


if __name__ == "__main__":
    try:
        main()
    except SetupError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"[error] Command failed: {exc}", file=sys.stderr)
        sys.exit(exc.returncode)
