"""Päivitysten allekirjoitus: vain julkaisijan avaimella allekirjoitettu paketti
kelpaa, ja manifesti sitoo tiedostonimen, version, tarkisteen ja koon."""
import copy
import io
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

import ordinate.core.release_signing as RS
import ordinate.core.updater as U
from ordinate.core.release_signing import VerificationError

URL = "https://example.invalid/download/v0.9.37/Ordinate-0.9.37.zip"


def _pem():
    return Ed25519PrivateKey.generate().private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())


@pytest.fixture
def key(monkeypatch):
    pem = _pem()
    monkeypatch.setattr(RS, "PUBLIC_KEYS", (RS.public_key_b64(pem),))
    return pem


def _manifest(**kw):
    m = {"file": "Ordinate-0.9.37.zip", "version": "0.9.37", "sha256": "a" * 64, "size": 1234}
    m.update(kw)
    return m


class _Resp(io.BytesIO):
    headers: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _serve(monkeypatch, doc):
    def fake(req, timeout=None):
        assert req.full_url == URL + ".sig.json"
        if doc is None:
            raise U.urllib.error.URLError("404")
        return _Resp(json.dumps(doc).encode())
    monkeypatch.setattr(U.urllib.request, "urlopen", fake)


def test_roundtrip(key):
    m = _manifest()
    assert RS.verify(RS.sign(m, key)) == m


def test_tampered_manifest_rejected(key):
    doc = RS.sign(_manifest(), key)
    doc["manifest"]["sha256"] = "b" * 64
    with pytest.raises(VerificationError):
        RS.verify(doc)


def test_foreign_key_rejected(key):
    with pytest.raises(VerificationError):
        RS.verify(RS.sign(_manifest(), _pem()))


def test_no_trusted_keys_rejects(monkeypatch):
    monkeypatch.setattr(RS, "PUBLIC_KEYS", ())
    with pytest.raises(VerificationError):
        RS.verify(RS.sign(_manifest(), _pem()))


def test_malformed_documents_rejected(key):
    good = RS.sign(_manifest(), key)
    for bad in (None, [], {"manifest": good["manifest"]}, {"signature": good["signature"]},
                {"manifest": good["manifest"], "signature": "%%%"}):
        with pytest.raises(VerificationError):
            RS.verify(bad)
    no_size = copy.deepcopy(good)
    del no_size["manifest"]["size"]
    with pytest.raises(VerificationError):
        RS.verify(no_size)


def test_shipped_key_is_a_valid_ed25519_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    assert RS.PUBLIC_KEYS
    for k in RS.PUBLIC_KEYS:
        Ed25519PublicKey.from_public_bytes(RS.base64.b64decode(k))


def test_fetch_manifest_accepts_matching_release(key, monkeypatch):
    _serve(monkeypatch, RS.sign(_manifest(), key))
    assert U.fetch_signed_manifest(URL, "0.9.37")["size"] == 1234


def test_fetch_manifest_rejects_old_package_under_new_version(key, monkeypatch):
    _serve(monkeypatch, RS.sign(_manifest(version="0.9.36"), key))
    with pytest.raises(VerificationError):
        U.fetch_signed_manifest(URL, "0.9.37")


def test_fetch_manifest_rejects_other_file(key, monkeypatch):
    _serve(monkeypatch, RS.sign(_manifest(file="Ordinate-Setup-0.9.37.exe"), key))
    with pytest.raises(VerificationError):
        U.fetch_signed_manifest(URL, "0.9.37")


def test_fetch_manifest_rejects_foreign_or_tampered_signature(key, monkeypatch):
    _serve(monkeypatch, RS.sign(_manifest(), _pem()))
    with pytest.raises(VerificationError):
        U.fetch_signed_manifest(URL, "0.9.37")
    doc = RS.sign(_manifest(), key)
    doc["manifest"]["sha256"] = "c" * 64
    _serve(monkeypatch, doc)
    with pytest.raises(VerificationError):
        U.fetch_signed_manifest(URL, "0.9.37")


def test_fetch_manifest_missing_signature_refuses(key, monkeypatch):
    _serve(monkeypatch, None)
    with pytest.raises(VerificationError):
        U.fetch_signed_manifest(URL, "0.9.37")


def test_download_rejects_hash_or_size_mismatch(tmp_path, monkeypatch):
    payload = b"x" * 1000
    monkeypatch.setattr(U.urllib.request, "urlopen", lambda req, timeout=None: _Resp(payload))
    good = U.hashlib.sha256(payload).hexdigest()
    U.download_asset(URL, tmp_path / "ok.zip", expected_sha256=good, expected_size=1000)
    assert (tmp_path / "ok.zip").read_bytes() == payload
    with pytest.raises(ValueError):
        U.download_asset(URL, tmp_path / "bad.zip", expected_sha256="0" * 64, expected_size=1000)
    with pytest.raises(ValueError):
        U.download_asset(URL, tmp_path / "bad2.zip", expected_sha256=good, expected_size=999)
    assert not (tmp_path / "bad.zip").exists() and not (tmp_path / "bad2.zip").exists()
    assert not list(tmp_path.glob("*.part"))


def test_env_disables_update_check_without_network(monkeypatch):
    monkeypatch.setenv("ORDINATE_DISABLE_UPDATES", "1")

    def no_network(*a, **k):
        raise AssertionError("verkkoon ei saa ottaa yhteyttä")
    monkeypatch.setattr(U, "_open_releases", no_network)
    assert U.updates_disabled()
    assert U.check_for_update(current_version="0.0.1") is None


def test_updates_enabled_by_default(monkeypatch):
    monkeypatch.delenv("ORDINATE_DISABLE_UPDATES", raising=False)

    class _NoKey:
        HKEY_LOCAL_MACHINE = 1
        HKEY_CURRENT_USER = 2

        @staticmethod
        def OpenKey(*a):
            raise OSError("ei avainta")
    monkeypatch.setitem(__import__("sys").modules, "winreg", _NoKey)
    assert U.updates_disabled() is None


def test_policy_registry_disables(monkeypatch):
    monkeypatch.delenv("ORDINATE_DISABLE_UPDATES", raising=False)
    monkeypatch.setattr(U.sys, "platform", "win32")
    seen = []

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Reg:
        HKEY_LOCAL_MACHINE = "HKLM"
        HKEY_CURRENT_USER = "HKCU"

        @staticmethod
        def OpenKey(hive, path):
            seen.append((hive, path))
            if hive == "HKCU":
                raise OSError
            return _Key()

        @staticmethod
        def QueryValueEx(key, name):
            assert name == "DisableUpdateCheck"
            return 1, 4
    monkeypatch.setitem(__import__("sys").modules, "winreg", _Reg)
    assert "HKLM" in U.updates_disabled()
    assert seen[0] == ("HKLM", r"SOFTWARE\Policies\Ordinate")


def test_selftest_passes():
    RS.selftest()


def test_verify_file_accepts_genuine_and_rejects_modified(key, tmp_path):
    f = tmp_path / "Ordinate-Setup-0.9.37.exe"
    f.write_bytes(b"installer-bytes")
    m = {"file": f.name, "version": "0.9.37", "sha256": U.hashlib.sha256(b"installer-bytes").hexdigest(),
         "size": len(b"installer-bytes")}
    (tmp_path / (f.name + ".sig.json")).write_text(json.dumps(RS.sign(m, key)), encoding="utf-8")
    assert RS.verify_file(f)["version"] == "0.9.37"
    f.write_bytes(b"installer-bytez")
    with pytest.raises(VerificationError):
        RS.verify_file(f)


def test_verify_file_requires_signature(key, tmp_path):
    f = tmp_path / "x.zip"
    f.write_bytes(b"1")
    with pytest.raises(VerificationError):
        RS.verify_file(f)


def test_cli_verify_reports(key, tmp_path):
    from click.testing import CliRunner
    from ordinate.cli import main
    f = tmp_path / "Ordinate-0.9.37.zip"
    f.write_bytes(b"zip")
    m = {"file": f.name, "version": "0.9.37", "sha256": U.hashlib.sha256(b"zip").hexdigest(), "size": 3}
    (tmp_path / (f.name + ".sig.json")).write_text(json.dumps(RS.sign(m, key)), encoding="utf-8")
    ok = CliRunner().invoke(main, ["verify", str(f)])
    assert ok.exit_code == 0 and "AITO" in ok.output
    f.write_bytes(b"zap")
    bad = CliRunner().invoke(main, ["verify", str(f)])
    assert bad.exit_code != 0
