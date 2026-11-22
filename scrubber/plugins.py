"""Detector-plugin interface.

A *detector plugin* scores a (scrubbed) image file and returns a verdict:
flagged / clean / unknown. Plugins let you test outputs against the specific
detectors you care about — from our built-in metadata audit to external
command-line tools or HTTP services used in your lab.

Built-in plugins:
  - ``metadata``  wraps scrubber.detect — flagged if any provenance signal remains
  - ``watermark-declared`` — flagged only if a C2PA manifest declares a
    c2pa.watermarked.* action (i.e. generator asserts a latent watermark)
  - ``openai[:base_url]`` — POSTs the file to OpenAI's Content Provenance API
    (detects C2PA metadata + SynthID watermark). Requires ``OPENAI_API_KEY``.
  - ``stable-signature[:key]`` — decodes the Meta Stable Signature 48-bit
    invisible pixel watermark using the public HiDDeN extractor. Requires
    ``torch`` + ``torchvision`` (optional); p-value is the Binomial(48,0.5)
    tail. Forensic only when you supply the signing key.
  - ``shell:<cmd>`` — runs an external command; ``{path}`` is substituted with
    the image path. Verdict from exit code: 0 = clean, 1 = flagged, other =
    error/unknown. Optionally parses a JSON object on stdout with keys
    {"flagged": bool, "score": float, "details": str}.
  - ``http:<url>`` — POSTs the file as multipart field ``file``; expects JSON
    {"flagged": bool, ...}. Requires ``requests``. For lab endpoints only.

Configuration: a JSON file (default ``detectors.json`` next to the CLI, or
``--detectors-config``) can enable/disable plugins:

  {"plugins": ["metadata", "shell:/opt/lab/aidec --json {path}"]}
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .detect import detect

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "detectors.json"


@dataclass
class Verdict:
    plugin: str
    flagged: bool | None  # True=flagged, False=clean, None=unknown/error
    score: float | None = None
    details: str = ""
    error: str | None = None


class DetectorPlugin:
    name = "base"

    def check(self, path: Path) -> Verdict:  # pragma: no cover - interface
        raise NotImplementedError


class MetadataPlugin(DetectorPlugin):
    name = "metadata"

    def check(self, path: Path) -> Verdict:
        rep = detect(path)
        return Verdict(self.name, flagged=not rep.clean,
                       details="; ".join(rep.findings) or "no signals found")


class WatermarkDeclaredPlugin(DetectorPlugin):
    name = "watermark-declared"

    def check(self, path: Path) -> Verdict:
        rep = detect(path)
        return Verdict(self.name, flagged=rep.declared_watermark,
                       details="manifest declares c2pa.watermarked.*"
                               if rep.declared_watermark else
                               "no watermark declaration")


class ShellPlugin(DetectorPlugin):
    """Wrap an external detector binary/script."""

    def __init__(self, command: str, timeout: float = 120.0):
        self.command = command
        self.timeout = timeout
        self.name = f"shell:{command.split()[0]}"

    def check(self, path: Path) -> Verdict:
        cmd = [part.replace("{path}", str(path))
               for part in shlex.split(self.command)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Verdict(self.name, flagged=None, error=str(exc))

        out = proc.stdout.strip()
        if out.startswith("{"):
            try:
                payload = json.loads(out)
                return Verdict(self.name,
                               flagged=bool(payload.get("flagged")),
                               score=payload.get("score"),
                               details=str(payload.get("details", ""))[:500])
            except json.JSONDecodeError:
                pass
        if proc.returncode == 0:
            return Verdict(self.name, flagged=False,
                           details=out[:500] or "exit 0")
        if proc.returncode == 1:
            return Verdict(self.name, flagged=True,
                           details=out[:500] or proc.stderr[:500] or "exit 1")
        return Verdict(self.name, flagged=None,
                       error=f"exit {proc.returncode}: {proc.stderr[:300]}")


class HttpPlugin(DetectorPlugin):
    """POST the file to a lab HTTP endpoint; expects JSON {"flagged": ...}."""

    def __init__(self, url: str, timeout: float = 120.0):
        self.url = url
        self.timeout = timeout
        self.name = f"http:{url.split('/')[2] if '//' in url else url}"

    def check(self, path: Path) -> Verdict:
        try:
            import requests
        except ImportError:
            return Verdict(self.name, flagged=None,
                           error="requests not installed")
        try:
            with open(path, "rb") as fh:
                resp = requests.post(self.url, files={"file": fh},
                                     timeout=self.timeout)
            payload = resp.json()
            return Verdict(self.name,
                           flagged=bool(payload.get("flagged")),
                           score=payload.get("score"),
                           details=str(payload.get("details", ""))[:500])
        except Exception as exc:
            return Verdict(self.name, flagged=None, error=str(exc))


class OpenAIPlugin(DetectorPlugin):
    """Detect OpenAI provenance signals (C2PA metadata + SynthID watermark)
    via the Content Provenance API. Requires ``OPENAI_API_KEY``; override the
    endpoint with ``OPENAI_PROVENANCE_URL`` or ``openai:<base_url>``."""

    name = "openai"

    def __init__(self, base_url: str | None = None,
                 api_key: str | None = None, timeout: float = 120.0):
        self.base_url = (base_url
                         or os.environ.get("OPENAI_PROVENANCE_URL")
                         or "https://api.openai.com/v1")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.timeout = timeout

    def check(self, path: Path) -> Verdict:
        if not self.api_key:
            return Verdict(self.name, flagged=None,
                           error="OPENAI_API_KEY not set")
        try:
            import requests
        except ImportError:
            return Verdict(self.name, flagged=None,
                           error="requests not installed")
        url = self.base_url.rstrip("/") + "/content_provenance_checks"
        try:
            with open(path, "rb") as fh:
                resp = requests.post(
                    url, files={"file": (Path(path).name, fh)},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout)
            if resp.status_code >= 400:
                return Verdict(self.name, flagged=None,
                               error=f"HTTP {resp.status_code}: "
                                     f"{resp.text[:200]}")
            payload = resp.json()
        except Exception as exc:
            return Verdict(self.name, flagged=None, error=str(exc))
        flagged, details = _parse_openai_provenance(payload)
        return Verdict(self.name, flagged=flagged, details=details)


class StableSignaturePlugin(DetectorPlugin):
    """Decode the Meta Stable Signature 48-bit invisible watermark using the
    public HiDDeN extractor. Requires torch + torchvision (optional)."""

    name = "stable-signature"

    def __init__(self, key: str | None = None,
                 cache_dir: str | Path | None = None,
                 download: bool = True):
        self.key = key
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.download = download

    def check(self, path: Path) -> Verdict:
        from .watermark import decode_stable_signature
        try:
            res = decode_stable_signature(path, key=self.key,
                                          cache_dir=self.cache_dir,
                                          download=self.download)
        except Exception as exc:
            return Verdict(self.name, flagged=None, error=str(exc))
        if res.get("error"):
            return Verdict(self.name, flagged=None, error=res["error"])
        if self.key is None:
            return Verdict(self.name, flagged=None,
                           details="bits=" + res["extracted_bits"]
                                   + " (no key; supply a 48-bit key for a "
                                   "forensic verdict)")
        return Verdict(self.name, flagged=res["flagged"],
                       score=res.get("p_value"),
                       details=(f"{res['matching_bits']}/{res['nbits']} bits "
                                f"match, p={res['p_value']:.2e}"))


def _parse_openai_provenance(payload) -> tuple[bool, str]:
    """Flatten OpenAI's provenance response into (flagged, details)."""
    signals: list[str] = []
    flagged = False

    def walk(node) -> None:
        nonlocal flagged
        if isinstance(node, dict):
            typ = node.get("type")
            outcome = node.get("outcome")
            if outcome is not None:
                signals.append(f"{typ or 'signal'}:{outcome}")
                if str(outcome).lower() in ("detected", "present", "true"):
                    flagged = True
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    details = "; ".join(signals) if signals else json.dumps(payload)[:500]
    return flagged, details


def load_plugins(config_path: str | Path | None = None,
                 specs: list[str] | None = None) -> list[DetectorPlugin]:
    """Build plugin instances from explicit specs or a JSON config file.

    Spec strings: "metadata" | "watermark-declared" | "openai[:url]" |
    "stable-signature[:key]" | "shell:<cmd>" | "http:<url>"
    """
    if specs is None:
        cfg = Path(config_path) if config_path else DEFAULT_CONFIG
        if cfg.exists():
            specs = json.loads(cfg.read_text()).get("plugins", [])
        else:
            specs = ["metadata"]
    plugins: list[DetectorPlugin] = []
    for spec in specs:
        if spec == "metadata":
            plugins.append(MetadataPlugin())
        elif spec == "watermark-declared":
            plugins.append(WatermarkDeclaredPlugin())
        elif spec.startswith("shell:"):
            plugins.append(ShellPlugin(spec[len("shell:"):]))
        elif spec == "openai":
            plugins.append(OpenAIPlugin())
        elif spec.startswith("openai:"):
            plugins.append(OpenAIPlugin(base_url=spec[len("openai:"):]))
        elif spec == "stable-signature":
            plugins.append(StableSignaturePlugin())
        elif spec.startswith("stable-signature:"):
            plugins.append(StableSignaturePlugin(
                key=spec[len("stable-signature:"):]))
        elif spec.startswith("http:"):
            plugins.append(HttpPlugin(spec[len("http:"):]))
        else:
            raise ValueError(f"unknown plugin spec: {spec!r}")
    return plugins


def run_detectors(path: str | Path,
                  plugins: list[DetectorPlugin]) -> list[Verdict]:
    path = Path(path)
    return [p.check(path) for p in plugins]
