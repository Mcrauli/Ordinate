"""Luo julkaisujen Ed25519-allekirjoitusavain (kerran).

Aja:  .venv/Scripts/python scripts/new_signing_key.py
Avain tallennetaan %USERPROFILE%/.ordinate/release_ed25519.pem (EI repoon).
Tulostaa julkisen avaimen, joka lisätään src/ordinate/core/release_signing.py:n
PUBLIC_KEYS-listaan. Ottaa avaimesta varmuuskopion talteen erilleen koneesta:
jos se katoaa, asennetut kopiot eivät voi enää itsepäivittyä.
"""
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.release_signing import public_key_b64  # noqa: E402

path = Path.home() / ".ordinate" / "release_ed25519.pem"
if path.exists():
    print(f"Avain on jo olemassa: {path} — ei ylikirjoiteta.")
    print("Julkinen avain:", public_key_b64(path.read_bytes()))
    sys.exit(0)
path.parent.mkdir(parents=True, exist_ok=True)
pem = Ed25519PrivateKey.generate().private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
path.write_bytes(pem)
print(f"Yksityinen avain: {path}")
print("Julkinen avain (lisää PUBLIC_KEYS-listaan):", public_key_b64(pem))
