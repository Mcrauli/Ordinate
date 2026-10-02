"""Julkaisujen allekirjoitus: päivitys asennetaan vain julkaisijan avaimella.

SHA-256-tarkiste yksin ei suojaa väärennökseltä, koska se haetaan samasta
paikasta kuin itse paketti: joka voi vaihtaa paketin, voi vaihtaa tarkisteen.
Siksi jokaisesta päivityspaketista julkaistaan ``<paketti>.sig.json``:

    {"manifest": {"file": ..., "version": ..., "sha256": ..., "size": ...},
     "signature": "<base64 Ed25519>"}

Allekirjoitus lasketaan manifestin kanonisesta JSONista. Ohjelma tuntee vain
julkiset avaimet (``PUBLIC_KEYS``); yksityinen avain on julkaisijan koneella
repon ulkopuolella (``scripts/new_signing_key.py``). Manifesti sitoo
tiedostonimen JA version, joten vanhaa aidosti allekirjoitettua pakettia ei voi
tarjota uudemman version nimellä.

Avainten kierto: lisää uusi julkinen avain listaan yhdessä julkaisussa ennen
kuin vanhaa lakataan käyttämästä. Jos yksityinen avain katoaa, vanhat asennukset
eivät voi enää itsepäivittyä — ne on asennettava uudelleen asennusohjelmalla.
"""
from __future__ import annotations

import base64
import json

PUBLIC_KEYS: tuple[str, ...] = (
    "p19WqI5Zpi6wNC1QA9mbVncC8USDYE166sU8cSHubmQ=",
)


class VerificationError(Exception):
    """Päivityksen allekirjoitus tai manifesti ei kelpaa."""


def canonical(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def verify(doc: dict, *, keys: tuple[str, ...] | None = None) -> dict:
    """Palauta manifesti jos jokin luotetuista avaimista on sen allekirjoittanut."""
    from cryptography.exceptions import InvalidSignature  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: PLC0415

    keys = PUBLIC_KEYS if keys is None else keys
    if not keys:
        raise VerificationError("ohjelmassa ei ole yhtään luotettua julkaisuavainta")
    if not isinstance(doc, dict):
        raise VerificationError("allekirjoitustiedosto on väärää muotoa")
    manifest, sig_b64 = doc.get("manifest"), doc.get("signature")
    if not isinstance(manifest, dict) or not isinstance(sig_b64, str):
        raise VerificationError("allekirjoitustiedosto on väärää muotoa")
    for field, kind in (("file", str), ("version", str), ("sha256", str), ("size", int)):
        if not isinstance(manifest.get(field), kind):
            raise VerificationError(f"manifestista puuttuu kenttä {field}")
    try:
        signature = base64.b64decode(sig_b64, validate=True)
    except ValueError as exc:
        raise VerificationError("allekirjoitus ei ole base64-muotoa") from exc
    payload = canonical(manifest)
    for key in keys:
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(key)).verify(signature, payload)
            return manifest
        except InvalidSignature:
            continue
    raise VerificationError("allekirjoitus ei täsmää yhteenkään luotettuun avaimeen")


def sign(manifest: dict, private_key_pem: bytes) -> dict:
    """Allekirjoita manifesti (julkaisuskriptit, ei ohjelman ajossa)."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key  # noqa: PLC0415

    key = load_pem_private_key(private_key_pem, password=None)
    signature = key.sign(canonical(manifest))
    return {"manifest": manifest, "signature": base64.b64encode(signature).decode("ascii")}


def public_key_b64(private_key_pem: bytes) -> str:
    from cryptography.hazmat.primitives.serialization import (  # noqa: PLC0415
        Encoding, PublicFormat, load_pem_private_key,
    )

    key = load_pem_private_key(private_key_pem, password=None)
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


_RFC8032_PUBLIC = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
_RFC8032_SIGNATURE = ("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555"
                      "fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")


def selftest() -> None:
    """Varmista RFC 8032:n testivektorilla, että tarkistus toimii tässä asennuksessa.

    Nostaa poikkeuksen jos kryptokirjasto puuttuu paketista tai hylkää aidon
    allekirjoituksen tai hyväksyy muokatun.
    """
    from cryptography.exceptions import InvalidSignature  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: PLC0415

    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(_RFC8032_PUBLIC))
    sig = bytes.fromhex(_RFC8032_SIGNATURE)
    key.verify(sig, b"")
    try:
        key.verify(sig, b"x")
    except InvalidSignature:
        return
    raise VerificationError("tarkistus hyväksyi muokatun viestin")


def verify_file(path) -> dict:
    """Tarkista ladattu tiedosto viereistä ``<tiedosto>.sig.json``:ia vasten."""
    import hashlib  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    path = Path(path)
    sig = path.with_name(path.name + ".sig.json")
    if not sig.exists():
        raise VerificationError(f"allekirjoitustiedostoa ei löydy: {sig.name}")
    manifest = verify(json.loads(sig.read_text(encoding="utf-8")))
    if manifest["file"] != path.name:
        raise VerificationError(f"allekirjoitus koskee tiedostoa {manifest['file']}")
    if path.stat().st_size != manifest["size"]:
        raise VerificationError("tiedoston koko ei täsmää allekirjoitukseen")
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != manifest["sha256"].lower():
        raise VerificationError("tiedoston SHA-256 ei täsmää allekirjoitukseen")
    return manifest
