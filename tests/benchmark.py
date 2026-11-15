import argparse
import base64
import contextlib
import csv
import gc
import hashlib
import io
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "signer/src"))

import cryptography
from cryptography.hazmat.backends.openssl.backend import backend
from cryptography.hazmat.primitives import serialization
from signer.subcommands import keygen, trust
from signer.subcommands import sign as sign_cmd
from signer.subcommands import verify as verify_cmd
from signer.subcommands.common import PROFILES, fingerprint, serialize_manifest

GENERATORS = {
    "rsa-pss-sha256": keygen.generate_rsa_key,
    "ecdsa-p256-sha256": keygen.generate_ecdsa_key,
    "ed25519": keygen.generate_ed25519_key,
}
SIZES = {"1KiB": 1024, "1MiB": 1024**2, "32MiB": 32 * 1024**2}
QUICK_SIZES = {"1KiB": 1024, "64KiB": 64 * 1024, "1MiB": 1024**2}
SEED = 20261116
PACKAGE = "bench-app"
VERSION = "1.0.0"

parser = argparse.ArgumentParser(description="xaleidscopix performance benchmark")
parser.add_argument("--runs", type=int, default=30, help="measured runs per batch (spec minimum: 30)")
parser.add_argument("--warmup", type=int, default=5, help="discarded warm-up runs per batch (spec: 5)")
parser.add_argument("--keygen-runs", type=int, default=10, help="key pairs per profile (spec minimum: 5)")
parser.add_argument("--quick", action="store_true", help="tiny smoke run, results are not valid for the report")
options = parser.parse_args()
if options.quick:
    options.runs, options.warmup, options.keygen_runs = 3, 1, 2
    SIZES = QUICK_SIZES

stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
output = root / "tests/results/benchmark" / (stamp + ("-quick" if options.quick else ""))
output.mkdir(parents=True)

env = dict(os.environ, PYTHONPATH=str(root / "signer/src"), PYTHONDONTWRITEBYTECODE="1")
cli = [sys.executable, "-B", "-m", "signer.xaleidscopix"]

raw_rows = []  # (metric, profile, artifact, run, ns)
summary_rows = []  # dicts


# statistics


def p95(samples):
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def summarize(metric, profile, artifact, samples):
    for index, value in enumerate(samples, start=1):
        raw_rows.append((metric, profile, artifact, index, value))
    row = {
        "metric": metric,
        "profile": profile,
        "artifact": artifact,
        "n": len(samples),
        "median_ms": statistics.median(samples) / 1e6,
        "p95_ms": p95(samples) / 1e6,
        "min_ms": min(samples) / 1e6,
        "max_ms": max(samples) / 1e6,
    }
    summary_rows.append(row)
    print(f"  {metric:18} {profile:18} {artifact:6} median {row['median_ms']:10.4f} ms   p95 {row['p95_ms']:10.4f} ms")


def measure(operation, runs, warmup, before=None):
    """Time operation() `runs` times after `warmup` discarded calls.

    before() runs outside the timed region before every call (e.g. deleting the
    previous output file).
    """
    samples = []
    gc.collect()
    gc.disable()
    try:
        for index in range(warmup + runs):
            if before:
                before()
            start = time.perf_counter_ns()
            operation()
            elapsed = time.perf_counter_ns() - start
            if index >= warmup:
                samples.append(elapsed)
    finally:
        gc.enable()
    return samples


# ---------------------------------------------------------------- environment


def cpu_name():
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def total_memory_gib():
    if sys.platform == "win32":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return f"{status.ullTotalPhys / 1024**3:.1f} GiB"
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                return f"{int(line.split()[1]) / 1024**2:.1f} GiB"
    except OSError:
        pass
    return "unknown"


# ---------------------------------------------------------------- benchmark


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    runs, warmup = options.runs, options.warmup
    print(f"Writing results to {output}")

    with tempfile.TemporaryDirectory(prefix="xaleidscopix-bench-") as scratch:
        scratch = Path(scratch)

        # Artifacts: identical bytes for every profile, reproducible from SEED.
        artifacts = {}
        generator = random.Random(SEED)
        for label, size in SIZES.items():
            path = scratch / f"artifact-{label}.bin"
            path.write_bytes(generator.randbytes(size))
            artifacts[label] = path

        environment = [
            f"Date: {datetime.now().isoformat(timespec='seconds')}",
            f"CPU: {cpu_name()} ({os.cpu_count()} logical CPUs)",
            f"Memory: {total_memory_gib()}",
            f"OS: {platform.platform()}",
            f"Python: {platform.python_implementation()} {platform.python_version()} ({sys.executable})",
            f"cryptography: {cryptography.__version__}, linked against {backend.openssl_version_text()}",
            "Clock: time.perf_counter_ns (monotonic)",
            f"Runs per batch: {warmup} warm-up (discarded) + {runs} measured; keygen: {options.keygen_runs} key pairs per profile",
            "Median: statistics.median. P95: nearest-rank, sorted samples, position ceil(0.95 * n) counting from 1.",
            "Garbage collector paused during each timed batch.",
            f"Artifacts (random bytes, seed {SEED}):",
        ]
        for label, path in artifacts.items():
            environment.append(f"  {path.name}: {path.stat().st_size} bytes, sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}")
        if options.quick:
            environment.append("QUICK RUN: too few samples, NOT valid for the report.")
        (output / "environment.txt").write_text("\n".join(environment) + "\n", encoding="utf-8")
        print("\n".join(environment))

        # Hash: SHA-256 over artifact bytes already in memory (no file I/O).
        print("\nSHA-256 over artifact bytes")
        for label, path in artifacts.items():
            data = path.read_bytes()
            summarize("hash", "-", label, measure(lambda: hashlib.sha256(data).digest(), runs, warmup))

        size_rows = []
        for profile in PROFILES:
            print(f"\n{profile}")

            # Keygen, separate from sign/verify. One warm-up, then keygen_runs key pairs.
            generate = GENERATORS[profile]
            summarize("keygen", profile, "-", measure(generate, options.keygen_runs, 1))

            # Fixed key pair for the rest of this profile, saved as PEM files for the CLI runs.
            folder = scratch / profile
            folder.mkdir()
            private_key = generate()
            public_key = private_key.public_key()
            key_pem = folder / "publisher.key.pem"
            pub_pem = folder / "publisher.pub.pem"
            key_pem.write_bytes(keygen.private_key_pem(private_key))
            pub_pem.write_bytes(keygen.public_key_pem(public_key))
            store = folder / "trust.json"
            trust.add_key(str(pub_pem), PACKAGE, str(store))
            keyid = fingerprint(public_key)

            private_der = private_key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            public_der = public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)

            for label, artifact in artifacts.items():
                data = artifact.read_bytes()
                manifest = serialize_manifest(PACKAGE, VERSION, profile, keyid, artifact.name, len(data), hashlib.sha256(data).hexdigest())
                signature = sign_cmd.sign_manifest(private_key, profile, manifest)
                if not verify_cmd.verify_signature(public_key, profile, manifest, signature):
                    raise AssertionError(f"{profile} {label}: own signature does not verify")

                # Cryptographic operation over M only.
                summarize("sign", profile, label, measure(lambda: sign_cmd.sign_manifest(private_key, profile, manifest), runs, warmup))
                summarize(
                    "verify", profile, label, measure(lambda: verify_cmd.verify_signature(public_key, profile, manifest, signature), runs, warmup)
                )

                # End-to-end through the application.
                bundle = folder / f"{label}.bundle.json"

                def remove_bundle():
                    bundle.unlink(missing_ok=True)

                sign_args = SimpleNamespace(file=str(artifact), package=PACKAGE, version=VERSION, key=str(key_pem), out=str(bundle))
                verify_args = SimpleNamespace(
                    file=str(artifact), bundle=str(bundle), trust_store=str(store), package=PACKAGE, version=VERSION, json=True
                )

                def inproc(command, arguments):
                    def call():
                        with contextlib.redirect_stdout(io.StringIO()):
                            code = command.run(arguments)
                        if code != 0:
                            raise AssertionError(f"{command.__name__} exited {code}")

                    return call

                summarize("e2e_inproc_sign", profile, label, measure(inproc(sign_cmd, sign_args), runs, warmup, before=remove_bundle))
                summarize("e2e_inproc_verify", profile, label, measure(inproc(verify_cmd, verify_args), runs, warmup))

                sign_cli = cli + [
                    "sign",
                    "--file",
                    str(artifact),
                    "--package",
                    PACKAGE,
                    "--version",
                    VERSION,
                    "--key",
                    str(key_pem),
                    "--out",
                    str(bundle),
                ]
                verify_cli = cli + [
                    "verify",
                    "--file",
                    str(artifact),
                    "--bundle",
                    str(bundle),
                    "--trust-store",
                    str(store),
                    "--package",
                    PACKAGE,
                    "--version",
                    VERSION,
                    "--json",
                ]

                def process(command):
                    def call():
                        result = subprocess.run(command, capture_output=True, env=env)
                        if result.returncode != 0:
                            raise AssertionError(f"{command[4]} exited {result.returncode}: {result.stderr.decode()}")

                    return call

                summarize("e2e_cli_sign", profile, label, measure(process(sign_cli), runs, warmup, before=remove_bundle))
                summarize("e2e_cli_verify", profile, label, measure(process(verify_cli), runs, warmup))

                # Sizes in bytes (the last bundle written above is a normal, complete one).
                size_rows.append(
                    (
                        profile,
                        label,
                        len(private_der),
                        len(public_der),
                        len(signature),
                        len(base64.b64encode(signature)),
                        len(manifest),
                        bundle.stat().st_size,
                    )
                )

    # ---------------------------------------------------------------- write results
    write_csv(output / "raw.csv", ["metric", "profile", "artifact", "run", "ns"], raw_rows)
    columns = ["metric", "profile", "artifact", "n", "median_ms", "p95_ms", "min_ms", "max_ms"]
    write_csv(
        output / "summary.csv", columns, [[row[c] if not isinstance(row[c], float) else f"{row[c]:.6f}" for c in columns] for row in summary_rows]
    )
    size_header = ["profile", "artifact", "private_key_der", "public_key_der", "signature", "signature_b64", "manifest", "bundle"]
    write_csv(output / "sizes.csv", size_header, size_rows)

    lines = [f"# Benchmark {stamp}", "", "```", *environment, "```", ""]

    def table(title, metrics, include_artifact=True):
        lines.extend([f"## {title}", ""])
        head = "| Metric | Profile |" + (" Artifact |" if include_artifact else "") + " n | Median (ms) | P95 (ms) |"
        lines.extend([head, "|" + "---|" * (head.count("|") - 1)])
        for row in summary_rows:
            if row["metric"] in metrics:
                artifact = f" {row['artifact']} |" if include_artifact else ""
                lines.append(f"| {row['metric']} | {row['profile']} |{artifact} {row['n']} | {row['median_ms']:.4f} | {row['p95_ms']:.4f} |")
        lines.append("")

    table("Key generation", {"keygen"}, include_artifact=False)
    table("SHA-256 over artifact bytes", {"hash"})
    table("Sign / verify over manifest bytes", {"sign", "verify"})
    table("End-to-end, in process (no interpreter start-up)", {"e2e_inproc_sign", "e2e_inproc_verify"})
    table("End-to-end, CLI as a new process", {"e2e_cli_sign", "e2e_cli_verify"})

    lines.extend(
        [
            "## Sizes (bytes)",
            "",
            "| Profile | Artifact | Private key DER | Public key DER | Signature | Signature Base64 | Manifest | Bundle |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    lines.extend("| " + " | ".join(str(v) for v in row) + " |" for row in size_rows)
    lines.append("")
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nDone. Summary: {output / 'summary.md'}")


main()
