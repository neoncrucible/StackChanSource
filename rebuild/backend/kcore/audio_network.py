"""Local audio endpoint selection and explicit Windows access checks.

An assigned address and an allow rule are configuration evidence, never proof
that the robot reached the listener. Only authenticated media/device ACKs do that.
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys


SCRIPT = Path(__file__).with_name("audio_network.ps1")


class AudioAddressUnavailable(RuntimeError):
    pass


def address_is_local(address):
    try:
        parsed = ipaddress.IPv4Address(address)
        if parsed.is_unspecified or parsed.is_multicast or parsed.is_link_local:
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind((str(parsed), 0))
        return True
    except (OSError, ValueError):
        return False


def select_address(default, interfaces, ssid):
    """Prefer the configured Wi-Fi, then a physical default-route interface.

    Camera USB links and VPN interfaces must not win because they happen to be
    first in an address list. An explicit user/environment choice bypasses this.
    """
    candidates = [row for row in interfaces if row.get("physical") is True
                  and row.get("gateway") is True and address_is_local(row.get("address", ""))]
    wifi = [row for row in candidates if row.get("network") == ssid and ssid]
    pool = wifi or candidates
    if len(pool) == 1:
        return pool[0]["address"]
    if any(row["address"] == default for row in pool):
        return default
    return default


async def _powershell(mode, timeout=15):
    if sys.platform != "win32":
        return {"interfaces": [], "firewall": "unsupported", "rules": []}
    if not SCRIPT.is_file():
        raise RuntimeError("Audio network helper is missing. Reinstall the complete package.")
    encoded = base64.b64encode(str(Path(sys.executable).resolve()).encode("utf-8")).decode("ascii")
    program = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) /
                  "System32/WindowsPowerShell/v1.0/powershell.exe")
    process = await asyncio.create_subprocess_exec(program, "-NoLogo", "-NoProfile",
        "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
        "-Mode", mode, "-ProgramBase64", encoded,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        creationflags=0x08000000)
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout)
        if process.returncode != 0:
            raise RuntimeError("Windows did not complete the audio access change. Check the administrator prompt or network policy.")
        if mode == "Request":
            return {}
        if len(stdout) > 65536:
            raise RuntimeError("Windows network report exceeded its limit.")
        result = json.loads(stdout.decode("utf-8-sig"))
        if not isinstance(result, dict) or not isinstance(result.get("interfaces"), list):
            raise RuntimeError("Windows network report was incomplete.")
        return result
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def inspect_windows():
    try:
        return await _powershell("Inspect")
    except (OSError, RuntimeError, ValueError, TimeoutError):
        return {"interfaces": [], "firewall": "unknown", "rules": []}


async def allow_windows_audio():
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        raise RuntimeError("Use Allow Robot Audio in the installed Windows application.")
    await _powershell("Request", timeout=90)


def _port_matches(ports, port):
    if ports in {"*", "", None}:
        return True
    for part in str(ports).split(","):
        low, _, high = part.partition("-")
        try:
            if int(low) <= port <= int(high or low):
                return True
        except ValueError:
            continue
    return False


def network_report(snapshot, host, port, *, automatic, listening):
    rows = [row for row in snapshot.get("interfaces", []) if isinstance(row, dict)]
    selected = next((row for row in rows if row.get("address") == host), {})
    profile = selected.get("profile", "unknown")
    if profile not in {"private", "public", "domain"}:
        profile = "unknown"
    mask = {"private": 2, "public": 4, "domain": 1}.get(profile, 0)
    relevant = [rule for rule in snapshot.get("rules", []) if isinstance(rule, dict)
                and type(rule.get("profiles")) is int and rule["profiles"] & mask
                and _port_matches(rule.get("ports"), port)]
    allowed = any(rule.get("action") == "allow" and rule.get("application") is True
                  for rule in relevant)
    blocked = any(rule.get("action") == "block" for rule in relevant)
    assigned = address_is_local(host)
    firewall = snapshot.get("firewall", "unknown")
    state = ("address_not_local" if not assigned else "not_listening" if not listening
             else "block_rule" if blocked else "public_network" if profile == "public"
             else "allow_rule_present" if allowed else "no_allow_rule"
             if firewall == "checked" and profile in {"private", "domain"} else "unknown")
    messages = {
        "address_not_local": "The selected PC address is no longer assigned here. Stop the server, select Auto-detect or the current PC LAN address, then start again.",
        "not_listening": "The audio listener is stopped. Start the server before testing robot audio.",
        "block_rule": "Windows has a matching inbound block rule. Open Windows Firewall and review the Kadence rule; an allow rule cannot override an explicit block.",
        "public_network": "Windows labels this connection Public. If this is your trusted home network, change its Windows network profile to Private, then select Allow Robot Audio.",
        "allow_rule_present": "An app-specific Windows allow rule is present. Run Test Audio Link to check the connection from the robot.",
        "no_allow_rule": "No matching app-specific allow rule was found for this version. Select Allow Robot Audio, approve the Windows prompt, then Test Audio Link.",
        "unknown": "Windows access could not be fully checked. Test Audio Link checks the actual robot connection. If it fails, check the PC address, firewall and guest-network isolation.",
    }
    return {"state": state, "profile": profile, "automatic": bool(automatic),
            "assigned": assigned, "listening": bool(listening), "allow_rule": allowed,
            "block_rule": blocked, "interfaces": len(rows), "host": host, "port": port,
            "message": messages[state]}


def diagnostic(data):
    result = {}
    if data.get("state") in {"address_not_local", "not_listening", "block_rule", "public_network",
                             "allow_rule_present", "no_allow_rule", "unknown"}:
        result["state"] = data["state"]
    if data.get("profile") in {"private", "public", "domain", "unknown"}:
        result["profile"] = data["profile"]
    for key in ("automatic", "assigned", "listening", "allow_rule", "block_rule"):
        if type(data.get(key)) is bool:
            result[key] = data[key]
    if type(data.get("interfaces")) is int and 0 <= data["interfaces"] <= 64:
        result["interfaces"] = data["interfaces"]
    return result
