# Run: uv run --project signer --locked python tests/test.py

import base64
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import cryptography


root = Path(__file__).resolve().parents[1]
fixtures = root / "tests/test_cases"
output = root / "tests/results/U01_U14" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
output.mkdir(parents=True)
env = dict(os.environ, PYTHONPATH=str(root / "signer/src"), PYTHONDONTWRITEBYTECODE="1")
cli = [sys.executable, "-B", "-m", "signer.xaleidscopix"]


def run(*arguments, expected_code=0):
    arguments = [str(argument) for argument in arguments]
    result = subprocess.run(cli + arguments, capture_output=True, text=True, env=env)
    log.write(f"\nCOMMAND: xaleidscopix {' '.join(arguments)}\n")
    log.write(f"EXPECTED EXIT: {expected_code}\nACTUAL EXIT: {result.returncode}\n")
    log.write(f"STDOUT:\n{result.stdout}STDERR:\n{result.stderr}\n")
    log.flush()
    if result.returncode != expected_code:
        raise AssertionError(f"expected exit {expected_code}, got {result.returncode}: {result.stderr.strip()}; see {log.name}")
    return result.stdout


def check(label, artifact, bundle, store, expected_status, version="1.0.0"):
    code = 0 if expected_status == "OK" else 1
    text = run("verify", "--file", artifact, "--bundle", bundle, "--trust-store", store,
               "--package", "demo", "--version", version, "--json", expected_code=code)
    (artifact.parent / f"{label}.verification.json").write_text(text, encoding="utf-8")
    result = json.loads(text)
    if result["status"] != expected_status or result["valid"] is not (code == 0):
        raise AssertionError(f"{label}: expected {expected_status}, got {result}")
    message = f"PASS {label}: {expected_status}, exit {code}"
    print(message)
    log.write(f"EXPECTED STATUS: {expected_status}\n{message}\n")
    log.flush()


with (output / "results.txt").open("w", encoding="utf-8") as log:
    log.write(f"Python {platform.python_version()}, cryptography {cryptography.__version__}, {platform.platform()}\n")
    log.write("All generated private keys below are TEST-ONLY, not CI/service keys.\n")

    # U01: text, binary, and empty artifacts, for every required algorithm.
    for algorithm in ("rsa-pss-sha256", "ecdsa-p256-sha256", "ed25519"):
        folder = output / algorithm
        folder.mkdir(exist_ok=True)
        prefix = folder / "test-publisher"
        store = folder / "trust.json"
        store.unlink(missing_ok=True)
        run("keygen", "--algorithm", algorithm, "--out", prefix, "--overwrite")
        run("trust", "add", "--key", f"{prefix}.pub.pem", "--package", "demo", "--store", store)
        for name in ("test.txt", "sample.bin", "empty.bin"):
            artifact = folder / name
            artifact.write_bytes((fixtures / name).read_bytes())
            bundle = folder / f"{name}.bundle.json"
            bundle.unlink(missing_ok=True)
            run("sign", "--file", artifact, "--package", "demo", "--version", "1.0.0",
                "--key", f"{prefix}.key.pem", "--out", bundle)
            check(f"U01-{algorithm}-{name}", artifact, bundle, store, "OK")

    # U02/U03 reuse the valid Ed25519 binary release, with copies of the artifact.
    folder = output / "ed25519"
    bundle = folder / "sample.bin.bundle.json"
    store = folder / "trust.json"
    original = (fixtures / "sample.bin").read_bytes()
    variants = {
        "U02": bytes([original[0] ^ 1]) + original[1:],
        "U03-append": original + b"\x00",
        "U03-truncate": original[:-1],
    }
    assert len(variants["U02"]) == len(original) and variants["U02"] != original
    assert len(variants["U03-append"]) == len(original) + 1
    assert len(variants["U03-truncate"]) == len(original) - 1
    for label, data in variants.items():
        case = output / label
        case.mkdir(exist_ok=True)
        artifact = case / "sample.bin"
        artifact.write_bytes(data)
        check(label, artifact, bundle, store, "ARTIFACT_MISMATCH")

    # U04-U09: each case gets unchanged copies of the valid Ed25519 release.
    for label, status in (
        ("U04", "INVALID_SIGNATURE"),
        ("U05", "INVALID_SIGNATURE"),
        ("U06-empty", "KEY_NOT_TRUSTED"),
        ("U06-removed", "KEY_NOT_TRUSTED"),
        ("U07", "KEY_NOT_TRUSTED"),
        ("U08", "METADATA_MISMATCH"),
        ("U09", "METADATA_MISMATCH"),
    ):
        case = output / label
        case.mkdir(exist_ok=True)
        artifact = case / "sample.bin"
        artifact.write_bytes(original)
        case_bundle = case / "release.json"
        case_bundle.write_bytes(bundle.read_bytes())
        case_store = case / "trust.json"
        case_store.write_bytes(store.read_bytes())
        version = "1.0.0"

        if label == "U04":
            contents = json.loads(case_bundle.read_bytes())
            manifest = json.loads(base64.b64decode(contents["manifest_b64"]))
            manifest["version"] = "2.0.0"
            changed = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
            contents["manifest_b64"] = base64.b64encode(changed).decode("ascii")
            case_bundle.write_text(json.dumps(contents), encoding="utf-8")
        elif label == "U05":
            contents = json.loads(case_bundle.read_bytes())
            signature = base64.b64decode(contents["signature_b64"])
            changed = bytes([signature[0] ^ 1]) + signature[1:]
            contents["signature_b64"] = base64.b64encode(changed).decode("ascii")
            case_bundle.write_text(json.dumps(contents), encoding="utf-8")
        elif label == "U06-empty":
            contents = json.loads(case_store.read_bytes())
            contents["keys"] = []
            case_store.write_text(json.dumps(contents), encoding="utf-8")
        elif label == "U06-removed":
            contents = json.loads(case_store.read_bytes())
            keyid = contents["keys"][0]["keyid"]
            run("trust", "remove", "--keyid", keyid, "--store", case_store)
        elif label == "U07":
            contents = json.loads(case_store.read_bytes())
            contents["keys"][0]["packages"] = ["other-app"]
            case_store.write_text(json.dumps(contents), encoding="utf-8")
        elif label == "U08":
            version = "2.0.0"
        elif label == "U09":
            artifact = case / "renamed.bin"
            artifact.write_bytes(original)
            (case / "sample.bin").unlink()

        check(label, artifact, case_bundle, case_store, status, version=version)

    # U10: test malformed inputs separately
    for label in ("U10-duplicate-field", "U10-wrong-type", "U10-invalid-base64", "U10-oversized-manifest"):
        case = output / label
        case.mkdir()
        artifact = case / "sample.bin"
        artifact.write_bytes(original)
        case_store = case / "trust.json"
        case_store.write_bytes(store.read_bytes())
        contents = json.loads(bundle.read_bytes())
        manifest_bytes = base64.b64decode(contents["manifest_b64"])

        if label == "U10-duplicate-field":
            changed = manifest_bytes.replace(b'"version":', b'"version":"1.0.0","version":', 1)
            contents["manifest_b64"] = base64.b64encode(changed).decode("ascii")
        elif label == "U10-wrong-type":
            manifest = json.loads(manifest_bytes)
            manifest["artifact"]["size"] = str(manifest["artifact"]["size"])
            changed = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
            contents["manifest_b64"] = base64.b64encode(changed).decode("ascii")
        elif label == "U10-invalid-base64":
            contents["manifest_b64"] = "!" + contents["manifest_b64"][1:]
        elif label == "U10-oversized-manifest":
            changed = manifest_bytes + b" " * (16385 - len(manifest_bytes))
            assert len(changed) == 16385
            assert json.loads(changed) == json.loads(manifest_bytes)
            contents["manifest_b64"] = base64.b64encode(changed).decode("ascii")

        case_bundle = case / "release.json"
        data = json.dumps(contents).encode("utf-8")
        assert len(data) < 64 * 1024
        case_bundle.write_bytes(data)
        check(label, artifact, case_bundle, case_store, "FORMAT_ERROR")

    # U11-U13: unsupported profile, untrusted signer, and harmless bundle formatting.
    for label, status in (("U11", "UNSUPPORTED_ALGORITHM"),
                          ("U12", "KEY_NOT_TRUSTED"), ("U13", "OK")):
        case = output / label
        case.mkdir()
        artifact = case / "sample.bin"
        artifact.write_bytes(original)
        case_store = case / "trust.json"
        case_store.write_bytes(store.read_bytes())
        case_bundle = case / "release.json"
        contents = json.loads(bundle.read_bytes())

        if label == "U11":
            manifest = json.loads(base64.b64decode(contents["manifest_b64"]))
            manifest["algorithm"] = "unknown-profile"
            changed = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
            contents["manifest_b64"] = base64.b64encode(changed).decode("ascii")
            case_bundle.write_text(json.dumps(contents), encoding="utf-8")
        elif label == "U12":
            prefix = case / "other-publisher"
            run("keygen", "--algorithm", "ed25519", "--out", prefix)
            run("sign", "--file", artifact, "--package", "demo", "--version", "1.0.0",
                "--key", f"{prefix}.key.pem", "--out", case_bundle)
            signed = json.loads(case_bundle.read_bytes())
            manifest = json.loads(base64.b64decode(signed["manifest_b64"]))
            trusted = json.loads(case_store.read_bytes())["keys"]
            assert manifest["algorithm"] == "ed25519"
            assert all(entry["keyid"] != manifest["keyid"] for entry in trusted)
        elif label == "U13":
            reformatted = json.dumps(dict(reversed(list(contents.items()))), indent=4)
            assert json.loads(reformatted) == contents
            case_bundle.write_text(reformatted, encoding="utf-8")

        check(label, artifact, case_bundle, case_store, status)

    # U14: sign the same manifest twice with the same key, for every profile.
    for algorithm, explanation in (
        ("rsa-pss-sha256", "RSA-PSS uses a fresh random 32-byte salt; signatures normally differ."),
        ("ecdsa-p256-sha256", "This signer uses ECDSA with random nonces; signatures normally differ."),
        ("ed25519", "Ed25519 is deterministic; the same key and message produce identical signatures."),
    ):
        case = output / f"U14-{algorithm}"
        case.mkdir()
        artifact = case / "sample.bin"
        artifact.write_bytes(original)
        case_store = case / "trust.json"
        case_store.write_bytes((output / algorithm / "trust.json").read_bytes())
        key = output / algorithm / "test-publisher.key.pem"
        signed_bundles = []
        for number in (1, 2):
            case_bundle = case / f"release-{number}.json"
            run("sign", "--file", artifact, "--package", "demo", "--version", "1.0.0",
                "--key", key, "--out", case_bundle)
            check(f"U14-{algorithm}-{number}", artifact, case_bundle, case_store, "OK")
            signed_bundles.append(json.loads(case_bundle.read_bytes()))

        first, second = signed_bundles
        assert base64.b64decode(first["manifest_b64"]) == base64.b64decode(second["manifest_b64"])
        identical = base64.b64decode(first["signature_b64"]) == base64.b64decode(second["signature_b64"])
        assert identical == (algorithm == "ed25519"), f"unexpected signature comparison for {algorithm}"
        comparison = f"U14 {algorithm}: identical manifest bytes; signatures {'identical' if identical else 'different'}. {explanation}"
        (case / "comparison.txt").write_text(comparison + "\n", encoding="utf-8")
        print(comparison)
        log.write(comparison + "\n")

    log.write("\nAll 32 verification cases and 3 signature comparisons passed.\n")

print(f"All 32 verification cases and 3 signature comparisons passed. Results: {output / 'results.txt'}")
