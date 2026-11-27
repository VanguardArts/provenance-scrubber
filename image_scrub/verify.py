"""Optional cryptographic C2PA verification via the official ``c2pa-python``
bindings (the Content Authenticity Initiative's open-source library).

The built-in analyzer reads the *embedded* manifest — signer identity, issuer,
certificate validity window, algorithm — but deliberately does not validate the
signature chain. This module performs real verification (signature + data-hash
+ trust) when ``c2pa-python`` is installed, and reports a compact, serialisable
summary: overall status plus the per-entry validation results.

If ``c2pa-python`` is not installed the result is ``{"status": "unavailable"}``
rather than an error, so the analyzer and viewer keep working everywhere.
"""

from __future__ import annotations

import json
from pathlib import Path


def _collect_validation(node) -> list[dict]:
    """Walk the manifest-store JSON and collect every ``validation_status``."""
    out: list[dict] = []
    if isinstance(node, dict):
        for key, val in node.items():
            if key == "validation_status" and isinstance(val, list):
                for entry in val:
                    if isinstance(entry, dict):
                        out.append(entry)
            else:
                out.extend(_collect_validation(val))
    elif isinstance(node, list):
        for entry in node:
            out.extend(_collect_validation(entry))
    return out


def _active_summary(store: dict) -> str:
    """Short identity string for the active manifest (generator / title)."""
    active = store.get("active_manifest", "")
    manifests = store.get("manifests") or {}
    if isinstance(manifests, dict):
        m = manifests.get(active)
        if isinstance(m, dict):
            parts = [str(m[k]) for k in ("claim_generator", "title")
                     if m.get(k)]
            return " | ".join(parts) or str(active)
    return str(active or "")


def verify_c2pa(path: str | Path) -> dict:
    """Verify a file's C2PA manifest store. Returns a JSON-safe dict.

    ``status`` is one of: ``unavailable`` (library missing), ``error``,
    ``unsigned`` (no manifest store), ``valid``, ``invalid``, or
    ``present`` (manifest exists but exposes no validation status).
    """
    try:
        import c2pa  # type: ignore
    except ImportError:
        return {"available": False, "status": "unavailable",
                "error": "c2pa-python not installed (pip install c2pa-python)"}

    try:
        with c2pa.Reader(str(path)) as reader:  # type: ignore
            raw = reader.detailed_json()
    except Exception as exc:  # pragma: no cover - depends on c2pa internals
        return {"available": True, "status": "error", "error": str(exc)}

    try:
        store = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        store = {}

    entries = _collect_validation(store)
    active = _active_summary(store)

    if entries:
        ok = all(bool(e.get("success")) for e in entries)
        status = "valid" if ok else "invalid"
    elif store.get("active_manifest") or store.get("manifests"):
        status = "present"
    else:
        status = "unsigned"

    failures = [e for e in entries if e.get("success") is False]
    codes = sorted({str(e.get("code")) for e in entries if e.get("code")})
    return {
        "available": True,
        "status": status,
        "active_manifest": active,
        "validation_entries": len(entries),
        "validation_codes": codes,
        "failure_count": len(failures),
        "failures": failures[:10],
    }
