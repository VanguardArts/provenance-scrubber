"""Deep provenance analyzer / viewer.

Parses and reports, in human- and machine-readable form, exactly what
provenance metadata is embedded in a file — so a user can see what was present
*before* excision and what remained *after*, with a diff as proof.

Covers:
  - C2PA Content Credentials: full JUMBF manifest store inside the PNG ``caBX``
    chunk or JPEG ``APP11`` segment. Extracts the claim (instance ID, claim
    generator, title), the actions assertion (each action, its software agent,
    digital source type, timestamp), the ingredient manifest(s), and the
    signature (signer identity, issuer, signing certificate validity, algorithm).
  - EXIF, XMP, and IPTC presence.

Note on signature: this reports the *embedded* signer identity and certificate
(what the manifest claims / who signed it). It does not perform cryptographic
signature validation against a trust list — use ``c2patool`` for that. It is
still a faithful "what was there / what is left" record, which is the point.
"""

from __future__ import annotations

import json
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import cbor2
except ImportError:  # pragma: no cover
    cbor2 = None

from .detect import PNG_SIGNATURE

# --------------------------------------------------------------------------
# JUMBF box parsing
# --------------------------------------------------------------------------

_C2PA_UUID = bytes.fromhex("00110010800000aa00389b71")


@dataclass
class _Box:
    tbox: bytes
    payload: bytes


def _parse_boxes(buf: bytes) -> list[_Box]:
    """Parse a flat sequence of ISO-BMFF-style boxes (JUMBF)."""
    out, n, o = [], len(buf), 0
    while o + 8 <= n:
        lbox = struct.unpack(">I", buf[o : o + 4])[0]
        tbox = buf[o + 4 : o + 8]
        hdr = 8
        if lbox == 1:
            lbox = struct.unpack(">Q", buf[o + 8 : o + 16])[0]
            hdr = 16
        elif lbox == 0:
            lbox = n - o
        out.append(_Box(tbox, buf[o + hdr : o + lbox]))
        o += lbox
    return out


def _parse_description(payload: bytes) -> tuple[str, str]:
    """Return (content_type, label) from a JUMBF description ('jumd') box.

    Layout (empirically verified against C2PA manifests):
        contentType (4 bytes)  e.g. 'cbor', 'c2cl', 'c2as', 'c2cs', 'c2ma'
        uuid         (12 bytes)  C2PA UUID 00110010800000aa00389b71 (or variant)
        toskip       (1 byte)   label prefix length to skip
        label        (null-terminated string)
    """
    ct = payload[:4].decode("latin1", "replace")
    label = ""
    rest = payload[17:]
    if rest:
        label = rest.split(b"\x00", 1)[0].decode("latin1", "replace")
    return ct, label


def _walk(buf: bytes) -> list[tuple[str, bytes]]:
    """Return [(content_type, payload)] for every cbor box, tracking the
    enclosing description-box content type."""
    results: list[tuple[str, bytes]] = []
    ctx = ""
    for box in _parse_boxes(buf):
        if box.tbox == b"jumd":
            ctx, _label = _parse_description(box.payload)
        elif box.tbox == b"jumb":
            results.extend(_walk(box.payload))
        elif box.tbox == b"cbor":
            results.append((ctx, box.payload))
    return results


# --------------------------------------------------------------------------
# X.509 (DER) helpers — extract identity from the signing certificate
# --------------------------------------------------------------------------

class _TLV:
    __slots__ = ("tag", "value", "size")

    def __init__(self, tag, value, size):
        self.tag, self.value, self.size = tag, value, size


def _read_tlv_at(data: bytes, off: int) -> _TLV:
    start = off
    tag = data[off]; off += 1
    length = data[off]; off += 1
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(data[off:off + n], "big")
        off += n
    return _TLV(tag, data[off:off + length], off + length - start)


def _der_children(data: bytes) -> list[_TLV]:
    children, off = [], 0
    while off < len(data):
        tlv = _read_tlv_at(data, off)
        children.append(tlv)
        off += tlv.size
    return children


def _name_to_cn(name_bytes: bytes) -> str:
    """Extract common name from a DER Name (SEQUENCE OF RDN)."""
    cn = ""
    for rdn in _der_children(name_bytes):   # each RDN is a SET
        for atv in _der_children(rdn.value):  # SET OF SEQUENCE{OID, value}
            parts = _der_children(atv.value)
            if len(parts) >= 2 and parts[0].value == bytes.fromhex("550403"):
                cn = _string_value(parts[1])
    return cn


def _string_value(tlv: _TLV) -> str:
    if tlv.tag in (0x0C, 0x13, 0x16, 0x1E):  # UTF8Str/Printable/IA5/BMP
        return tlv.value.decode("utf-8", "replace")
    return tlv.value.decode("latin1", "replace")


def _cert_info(der: bytes) -> dict:
    """Extract subject CN, issuer CN, validity window from a DER certificate."""
    info = {"subject": "", "issuer": "", "not_before": "", "not_after": ""}
    try:
        outer = _read_tlv_at(der, 0)
        tbs = _der_children(outer.value)[0]
        fields = _der_children(tbs.value)
        # skip version [0], serial, signature
        # tbs fields: [0]=serial, [1]=signature alg, [2]=issuer, [3]=validity,
        #              [4]=subject (after an optional leading version [0])
        idx = 0
        if fields and fields[0].tag == 0xA0:
            idx = 1
        issuer = fields[idx + 2] if idx + 2 < len(fields) else None
        validity = fields[idx + 3] if idx + 3 < len(fields) else None
        subject = fields[idx + 4] if idx + 4 < len(fields) else None
        if issuer is not None:
            info["issuer"] = _name_to_cn(issuer.value)
        if validity is not None:
            times = _der_children(validity.value)
            if len(times) >= 2:
                info["not_before"] = _string_value(times[0])
                info["not_after"] = _string_value(times[1])
        if subject is not None:
            info["subject"] = _name_to_cn(subject.value)
    except Exception:
        pass
    return info


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------

@dataclass
class Action:
    action: str
    software_agent: str = ""
    digital_source_type: str = ""
    when: str = ""
    description: str = ""


@dataclass
class Manifest:
    instance_id: str = ""
    title: str = ""
    claim_generator: str = ""
    claim_generator_version: str = ""
    actions: list[Action] = field(default_factory=list)
    ingredients: list[str] = field(default_factory=list)
    assertions: list[str] = field(default_factory=list)
    signature_subject: str = ""
    signature_issuer: str = ""
    signature_not_before: str = ""
    signature_not_after: str = ""
    signature_alg: str = ""


@dataclass
class ProvenanceReport:
    path: str
    format: str = "unknown"
    has_manifest: bool = False
    manifests: list[Manifest] = field(default_factory=list)
    exif: dict = field(default_factory=dict)
    xmp: str = ""
    iptc_present: bool = False
    verification: dict | None = None  # optional cryptographic verify (c2pa-python)

    @property
    def summary_keys(self) -> list[str]:
        """Short labels describing what provenance is present."""
        keys = []
        if self.has_manifest:
            keys.append("C2PA manifest (Content Credentials)")
            gen = {m.claim_generator for m in self.manifests if m.claim_generator}
            if gen:
                keys.append("claim generator: " + ", ".join(sorted(gen)))
            acts = {a.action for m in self.manifests for a in m.actions}
            if acts:
                keys.append("actions: " + ", ".join(sorted(acts)))
            dst = {a.digital_source_type.split("/")[-1]
                   for m in self.manifests for a in m.actions if a.digital_source_type}
            if dst:
                keys.append("digital source type: " + ", ".join(sorted(dst)))
            wm = any(a.action.startswith("c2pa.watermarked")
                     for m in self.manifests for a in m.actions)
            if wm:
                keys.append("declares invisible pixel watermark "
                            "(c2pa.watermarked)")
            subs = {m.signature_subject for m in self.manifests if m.signature_subject}
            if subs:
                keys.append("signed by: " + ", ".join(sorted(subs)))
        if self.exif:
            keys.append(f"EXIF metadata ({len(self.exif)} field(s))")
        if self.xmp:
            keys.append("XMP metadata")
        if self.iptc_present:
            keys.append("IPTC metadata")
        return keys


def _parse_cose_signature(payload: bytes) -> tuple[str, str]:
    """Return (algorithm_name, cert_der) from a COSE_Sign1 cbor payload."""
    alg, der = "", ""
    if cbor2 is None:
        return alg, der
    try:
        obj = cbor2.loads(payload)
        # CBORTag(18) -> COSE_Sign1 = [protected, unprotected, payload, sig]
        if hasattr(obj, "tag") and obj.tag == 18 and len(obj.value) >= 4:
            protected = obj.value[0]
            prot = cbor2.loads(protected)
            if isinstance(prot, dict):
                for k, v in prot.items():
                    if k in (1, "alg"):
                        alg_map = {-7: "ES256", -35: "ES384", -36: "ES512",
                                    -37: "PS256", -259: "EdDSA"}
                        alg = alg_map.get(v, f"alg:{v}")
                    if k in (33, "x5chain", "C2PA_signature"):
                        certs = v if isinstance(v, list) else [v]
                        for c in certs:
                            if isinstance(c, bytes) and c.startswith(b"0\x82"):
                                der = c
                                break
    except Exception:
        pass
    return alg, der


def _extract_manifest_store(data: bytes) -> list[Manifest]:
    """Parse a C2PA JUMBF manifest store bytes into Manifest summaries."""
    manifests: list[Manifest] = []
    if cbor2 is None:
        return manifests

    def build_manifest(payload: bytes) -> Manifest:
        m = Manifest()
        for content_type, cbor_payload in _walk(payload):
            try:
                obj = cbor2.loads(cbor_payload)
            except Exception:
                continue
            if content_type == "c2cl":  # claim
                if isinstance(obj, dict):
                    m.instance_id = obj.get("instanceID", "")
                    m.title = obj.get("dc:title", "")
                    cg = obj.get("claim_generator_info") or {}
                    m.claim_generator = cg.get("name", "")
                    m.claim_generator_version = (
                        cg.get("version") or cg.get("org.contentauth.c2pa_rs", ""))
                    for a in obj.get("created_assertions") or []:
                        if isinstance(a, dict) and a.get("url"):
                            m.assertions.append(a["url"])
            elif content_type == "c2cs":  # signature
                alg, der = _parse_cose_signature(cbor_payload)
                m.signature_alg = alg
                if der:
                    ci = _cert_info(der)
                    m.signature_subject = ci["subject"]
                    m.signature_issuer = ci["issuer"]
                    m.signature_not_before = ci["not_before"]
                    m.signature_not_after = ci["not_after"]
            else:  # assertion store ('cbor' boxes hold the assertions)
                if isinstance(obj, dict) and "actions" in obj:
                    for a in obj["actions"] or []:
                        sa = a.get("softwareAgent") or {}
                        m.actions.append(Action(
                            action=a.get("action", ""),
                            software_agent=sa.get("name", ""),
                            digital_source_type=a.get("digitalSourceType", ""),
                            when=a.get("when", ""),
                            description=a.get("description", ""),
                        ))
                if isinstance(obj, dict) and "relationship" in obj:
                    m.ingredients.append(obj.get("dc:title", "ingredient"))
        return m

    def recurse(blob: bytes) -> None:
        for box in _parse_boxes(blob):
            if box.tbox != b"jumb":
                continue
            desc = _parse_boxes(box.payload)
            if desc and desc[0].tbox == b"jumd":
                ct, _label = _parse_description(desc[0].payload)
                if ct == "c2ma":
                    manifests.append(build_manifest(box.payload))
            recurse(box.payload)

    recurse(data)
    return manifests


def _load_c2pa_blob(path: Path) -> bytes:
    data = path.read_bytes()
    if data.startswith(PNG_SIGNATURE):
        off = 8
        while off + 8 <= len(data):
            length, ctype = struct.unpack(">I4s", data[off : off + 8])
            if ctype == b"caBX":
                return data[off + 8 : off + 8 + length]
            off += 12 + length
    elif data.startswith(b"\xff\xd8\xff"):
        off = 2
        while off + 4 <= len(data):
            if data[off] != 0xFF:
                break
            marker = data[off + 1]
            if marker == 0xDA or (0xD0 <= marker <= 0xD7) or marker in (0x01, 0xD8):
                off += 2
                continue
            length = struct.unpack(">H", data[off + 2 : off + 4])[0]
            body = data[off + 4 : off + 2 + length]
            if marker == 0xEB and (b"jumb" in body[:16] or b"c2pa" in body[:64]):
                return body
            off += 2 + length
    return b""


def _extract_exif_xmp(path: Path, data: bytes) -> tuple[dict, str, bool]:
    from PIL import Image
    import io

    exif, xmp, iptc = {}, "", False
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format in ("JPEG", "TIFF", "MPO"):
                raw = im.getexif()
                for tag_id, value in raw.items():
                    exif[str(tag_id)] = str(value) if not isinstance(value, bytes) \
                        else f"<{len(value)} bytes>"
                if im.format == "JPEG":
                    # IPTC lives in APP13; Pillow does not expose it directly,
                    # so fall back to a raw marker scan.
                    if b"Photoshop 3.0" in data or b"XML:com.adobe.xmp" in data:
                        pass
            x = im.getxmp()
            if x and "xmp" in x:
                xmp = x["xmp"]
            # raw IPTC presence
            if im.format == "JPEG":
                off = 2
                while off + 4 <= len(data):
                    if data[off] != 0xFF:
                        break
                    m = data[off + 1]
                    if m == 0xDA:
                        break
                    length = struct.unpack(">H", data[off + 2 : off + 4])[0]
                    if m == 0xED:
                        iptc = True
                    off += 2 + length
    except Exception:
        pass
    return exif, xmp, iptc


def analyze(path: str | Path, verify: bool = False) -> ProvenanceReport:
    """Deep-parse a file's provenance. Set ``verify=True`` to also run
    cryptographic C2PA verification (requires the optional ``c2pa-python``
    package; otherwise the ``verification`` field reports "unavailable")."""
    path = Path(path)
    data = path.read_bytes()
    report = ProvenanceReport(path=str(path))
    report.format = path.suffix.lstrip(".").lower() or "unknown"

    blob = _load_c2pa_blob(path)
    if blob:
        manifests = _extract_manifest_store(blob)
        if manifests:
            report.has_manifest = True
            report.manifests = manifests

    report.exif, report.xmp, report.iptc_present = _extract_exif_xmp(path, data)

    if verify:
        try:
            from .verify import verify_c2pa
            report.verification = verify_c2pa(path)
        except Exception as exc:  # pragma: no cover - defensive
            report.verification = {"available": False, "status": "error",
                                   "error": str(exc)}
    return report


def to_dict(report: ProvenanceReport) -> dict:
    d = asdict(report)
    return d


def diff(before: ProvenanceReport, after: ProvenanceReport) -> dict:
    """Summarise what was removed and what remained, for proof."""
    before_keys = before.summary_keys
    after_keys = after.summary_keys
    return {
        "removed": [k for k in before_keys if k not in after_keys],
        "remained": [k for k in before_keys if k in after_keys],
        "added": [k for k in after_keys if k not in before_keys],
        "before_manifest_count": len(before.manifests),
        "after_manifest_count": len(after.manifests),
        "before_has_manifest": before.has_manifest,
        "after_has_manifest": after.has_manifest,
    }


def pretty(report: ProvenanceReport) -> str:
    lines = [f"Provenance report: {report.path}",
             f"  format: {report.format}"]
    if report.has_manifest:
        lines.append(f"  C2PA manifests: {len(report.manifests)}")
        for i, m in enumerate(report.manifests, 1):
            lines.append(f"  ── manifest {i} ──")
            if m.claim_generator:
                lines.append(f"     generator: {m.claim_generator} "
                             f"{m.claim_generator_version}".rstrip())
            if m.instance_id:
                lines.append(f"     instanceID: {m.instance_id}")
            if m.title:
                lines.append(f"     title: {m.title}")
            for a in m.actions:
                sa = f" by {a.software_agent}" if a.software_agent else ""
                dst = f" [{a.digital_source_type.split(chr(47))[-1]}]" \
                    if a.digital_source_type else ""
                lines.append(f"     action: {a.action}{sa}{dst}"
                             + (f" @ {a.when}" if a.when else ""))
            if m.signature_subject:
                lines.append(f"     signer: {m.signature_subject}")
            if m.signature_issuer:
                lines.append(f"     issuer: {m.signature_issuer}")
            if m.signature_not_before:
                lines.append(f"     cert valid: {m.signature_not_before} .. "
                             f"{m.signature_not_after}")
            if m.signature_alg:
                lines.append(f"     signature alg: {m.signature_alg}")
    else:
        lines.append("  C2PA manifests: none")
    if report.exif:
        lines.append(f"  EXIF: {len(report.exif)} field(s)")
    if report.xmp:
        lines.append(f"  XMP: present ({len(report.xmp)} chars)")
    if report.iptc_present:
        lines.append("  IPTC: present")
    if report.verification is not None:
        v = report.verification
        status = v.get("status", "?")
        line = f"  C2PA signature verification: {status}"
        if v.get("active_manifest"):
            line += f" ({v['active_manifest']})"
        if v.get("validation_codes"):
            line += " codes=" + ",".join(v["validation_codes"])
        if v.get("error"):
            line += f" [{v['error']}]"
        lines.append(line)
    if not report.has_manifest and not report.exif and not report.xmp \
            and not report.iptc_present:
        lines.append("  (no provenance metadata found)")
    return "\n".join(lines)


def dump_json(report: ProvenanceReport) -> str:
    return json.dumps(to_dict(report), indent=2, default=str)
