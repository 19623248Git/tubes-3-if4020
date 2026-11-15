#Run: uv run --project signer --locked python tests/test_u01_u03.py

import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import cryptography


root = Path(__file__).resolve().parents[1]
fixtures = root / "tests/test_cases"
output = root / "tests/results/U01_U03"
output.mkdir(parents=True, exist_ok=True)
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
        raise AssertionError(f"expected exit {expected_code}, got {result.returncode}; see {log.name}")
    return result.stdout


def check(label, artifact, bundle, store, expected_status):
    code = 0 if expected_status == "OK" else 1
    text = run("verify", "--file", artifact, "--bundle", bundle, "--trust-store", store,
               "--package", "demo", "--version", "1.0.0", "--json", expected_code=code)
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

    log.write("\nAll 12 verification cases passed.\n")

print(f"All 12 cases passed. Results: {output / 'results.txt'}")
