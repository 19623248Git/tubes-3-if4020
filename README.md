# Xaleidscopix Signer

Xaleidscopix is a command line tool for signing and verifying software releases, in the spirit of Sigstore Cosign blob signing and minisign. A publisher signs a release artifact with a private key, and the tool writes a bundle that holds a canonical JSON release manifest together with its signature. Anyone who has the publisher's public key in a local trust store can then check that the artifact is unchanged and that it was signed by a key trusted for that package.

Three signature profiles are supported: `rsa-pss-sha256`, `ecdsa-p256-sha256` and `ed25519`.

The tool is shipped as a container image on GitHub Container Registry and is used by a GitHub Actions pipeline that builds a release artifact, signs it, verifies it, and only deploys it once verification passes.

The artifact released by the pipeline is built from `app/`, a fork of [Zig](https://github.com/ziglang/zig) latest commit before migrating, with its upstream history squashed into a single commit, which explains the contributor count of this repository.

## Releases

| Program version | Repository tag | Commit | Image tag | Image digest |
|---|---|---|---|---|
| 0.1.0 | `v0.1.0` | `f345aa3` | `ghcr.io/19623248git/tubes-3-if4020:v0.1.0` | `sha256:332d9c180eeef05ac739c75d44bf5abc4579f0aeb6dd50df5732754f3f5fab0e` |

The image is public at [ghcr.io/19623248git/tubes-3-if4020](https://github.com/19623248Git/tubes-3-if4020/pkgs/container/tubes-3-if4020). A release image is built by `push_image.yaml` from the commit its repository tag points to, and `ci/push_image.sh` refuses to build it unless the tag matches the version in `signer/pyproject.toml`. Workflows pin the image by digest, so the digest decides which image runs, while trust in the publisher's keys still comes only from the trust store.

## Repository layout

```
app/                  # zig fork for artifact
signer/               # xaleidscopix source, pyproject.toml, uv.lock, Dockerfile
ci/                   # pipeline scripts and CI trust store
ci/c0x_scenario/      # scripts and trust stores for CI test scenarios
.github/workflows/    # github action scripts
```

## Tech stack

| Part | Technology |
|---|---|
| Language | Python 3.14 |
| Project and dependency manager | uv 0.11.32 in the image |
| Cryptography | cryptography 50.0.2 |
| CLI | argparse |
| Container | Docker with multi-stage Dockerfile |
| Registry | GitHub Container Registry, `ghcr.io` |
| CI/CD | GitHub Actions with sh scripts |


## Dependencies

The signer has a single direct runtime dependency, cryptography 50.0.2, which handles key generation, signing, verification, SHA-256, and PEM and DER key encoding. cryptography in turn pulls in cffi 2.1.1 and pycparser 3.12, and all three are pinned in `signer/uv.lock`. Everything else, including argparse and the strict JSON parsing, comes from the Python standard library.

The image is built with uv 0.11.32 on top of `python:3.14-slim-trixie`, so every dependency already lives inside the image. A CI/CD runner only needs Docker and the usual shell tools such as `zip` and `sha256sum`.

## Running on a CI/CD runner

### The image

| Item | Value |
|---|---|
| Image | `ghcr.io/19623248git/tubes-3-if4020` |
| Tag | `v0.1.0` |
| Pinned reference | `ghcr.io/19623248git/tubes-3-if4020@sha256:332d9c180eeef05ac739c75d44bf5abc4579f0aeb6dd50df5732754f3f5fab0e` |
| Platform | `linux/amd64` |

The image is public, so it can be pulled without logging in. Workflows always pin it by digest, never by tag alone.

```bash
IMAGE=ghcr.io/19623248git/tubes-3-if4020@sha256:332d9c180eeef05ac739c75d44bf5abc4579f0aeb6dd50df5732754f3f5fab0e
docker pull "$IMAGE"
docker run --rm "$IMAGE" --version
```

The container runs the CLI directly, so everything after the image name is passed to the signer:

```bash
docker run --rm <image> <subcommand> ...
```

### Signing and verifying with docker run

Inputs are bind mounted read only, outputs go to a mounted folder on the runner, the container runs as the runner's UID and GID, and it has no network access.

```bash
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/dist:/input:ro" \
  -v "$PWD/out:/output" \
  -v "$KEY_FILE:/run/signing.key.pem:ro" \
  "$IMAGE" sign --file /input/app.zip \
  --package zig-fork-app --version 0.1.0 \
  --key /run/signing.key.pem --out /output/rilis.json

docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/dist:/input:ro" \
  -v "$PWD/out:/bundle:ro" \
  -v "$PWD/ci:/trust:ro" \
  "$IMAGE" verify --file /input/app.zip --bundle /bundle/rilis.json \
  --trust-store /trust/trust.json \
  --package zig-fork-app --version 0.1.0 --json \
  > out/verification.json
```

### Pipeline scripts

The workflows do not call `docker run` directly, they call the scripts in `ci/`, which are configured through environment variables.

| Script | What it does | Variables |
|---|---|---|
| `ci/build.sh` | zips `app/` into `dist/app.zip` and prints its SHA-256 | none |
| `ci/sign.sh` | signs the artifact inside the container and writes the bundle | `IMAGE`, `PACKAGE`, `VERSION` required, `SIGNING_KEY_PEM` or `SIGNING_KEY_FILE`, `ARTIFACT` default `dist/app.zip`, `OUT_DIR` default `out`, `BUNDLE_NAME` default `rilis.json` |
| `ci/verify.sh` | verifies inside the container, writes the JSON result and exits with the program's exit code | `IMAGE`, `PACKAGE`, `VERSION` required, `ARTIFACT` default `dist/app.zip`, `BUNDLE` default `out/rilis.json`, `TRUST_STORE` default `ci/trust.json`, `RESULT` default `out/verification.json` |
| `ci/deploy.sh` | simulated deployment, writes `out/deployed.marker` with the artifact name, SHA-256, commit and time | `ARTIFACT` default `dist/app.zip`, `OUT_DIR` default `out` |

### Private keys

Private keys live only in GitHub Actions secrets:

| Secret | Profile |
|---|---|
| `SIGNING_KEY_ED25519` | `ed25519` |
| `SIGNING_KEY_ECDSA_P256` | `ecdsa-p256-sha256` |
| `SIGNING_KEY_RSA_PSS` | `rsa-pss-sha256` |

`ci/sign.sh` receives the secret as `SIGNING_KEY_PEM`, writes it to a temporary file that only the runner user can read, mounts that file read only into the container, and deletes it when the script exits. The key is never printed, never stored in the image, and never part of an uploaded artifact.

### Trust store

`ci/trust.json` is prepared manually and committed to the repository. The pipeline only reads it, it is never generated or updated from a bundle.

### One time key setup

Generate a key pair for each profile, add the public keys to `ci/trust.json`, then store the private keys as secrets. The `keys/` folder is ignored by git.

```bash
cd signer
mkdir -p ../keys
for a in ed25519 ecdsa-p256-sha256 rsa-pss-sha256; do
  uv run xaleidscopix keygen --algorithm "$a" --out "../keys/$a"
  uv run xaleidscopix trust add --key "../keys/$a.pub.pem" --package zig-fork-app --store ../ci/trust.json
done
cd ..
gh secret set SIGNING_KEY_ED25519    < keys/ed25519.key.pem
gh secret set SIGNING_KEY_ECDSA_P256 < keys/ecdsa-p256-sha256.key.pem
gh secret set SIGNING_KEY_RSA_PSS    < keys/rsa-pss-sha256.key.pem
```

Without `gh`, add the secrets in Settings -> Secrets and variables -> Actions.

### Workflows

| Workflow | Runs on | What it does |
|---|---|---|
| `push_image.yaml` | push to `master` that changes `signer/`, or a `v*` tag | builds the image from `signer/Dockerfile`, pushes it to GHCR as `sha-<short commit>` for `master` or as the tag name for a release, and prints the pinned reference in the run summary |
| `ci_app.yaml` | push to `master` that changes `app/` or `ci/` outside `ci/c0x_scenario/`, or a manual run | the release pipeline: build, then sign, verify and deploy for each of the three profiles. Deploy only starts after verify succeeds |
| `c0x_scenario.yaml` | push to `master` that changes `app/` or `ci/`, or a manual run | the C02 to C05 integration scenarios |

## Usage

The examples run from source with `uv run xaleidscopix`, from inside the `signer/` folder. With the image, the same arguments follow `docker run --rm <image>` instead.

### Help and version

```bash
uv run xaleidscopix --help
uv run xaleidscopix keygen --help
uv run xaleidscopix --version
```

```
xaleidscopix 0.1.0
```

### keygen

```bash
uv run xaleidscopix keygen --algorithm ed25519 --out keys/ed25519
```

Writes `keys/ed25519.key.pem`, readable only by the owner, and `keys/ed25519.pub.pem`, then prints the key fingerprint, which is the keyid. `--algorithm` accepts `ed25519`, `ecdsa-p256-sha256` or `rsa-pss-sha256`.

An existing private key is never replaced silently:

```
error: output keys/ed25519.key.pem already exists; use --overwrite explicitly
```

To replace it on purpose, add `--overwrite`:

```bash
uv run xaleidscopix keygen --algorithm ed25519 --out keys/ed25519 --overwrite
```

### trust add, trust list, trust remove

```bash
uv run xaleidscopix trust add --key keys/ed25519.pub.pem --package zig-fork-app --store trust.json
```

Creates `trust.json` if it does not exist. Adding the same key again for the same package changes nothing, adding it for another package extends its package list.

```bash
uv run xaleidscopix trust list --store trust.json
```

```bash
uv run xaleidscopix trust remove --keyid EXAMPLE_HERE --store trust.json
```

Removing a keyid that is not in the store fails with exit code 2.

### sign

```bash
uv run xaleidscopix sign --file dist/app.zip --package zig-fork-app --version 0.1.0 \
  --key keys/ed25519.key.pem --out out/rilis.json
```

The profile is taken from the private key. The bundle is never written over an existing file:

```
error: output out/rilis.json already exists; remove it or choose another --out
```

### verify

```bash
uv run xaleidscopix verify --file dist/app.zip --bundle out/rilis.json \
  --trust-store trust.json --package zig-fork-app --version 0.1.0
```

```
OK: signature and artifact are valid
```

With `--json`:

```json
{"valid": true, "status": "OK", "message": "signature and artifact are valid", "algorithm": "ed25519", "keyid": "KEY_ID", "package": "zig-fork-app", "version": "0.1.0"}
```

### Running the tests

#### U01 to U14

`tests/test.py` runs the minimum scenarios from Table 2.11 through the CLI. Each profile first gets a test-only key pair from `keygen`, a trust store from `trust add` for the package `demo`, and signed releases of the three files in `tests/test_cases`: `test.txt` (text), `sample.bin` (1 KiB binary) and `empty.bin` (0 bytes). U01 and U14 run for all three profiles. U02 to U13 start from the valid Ed25519 release of `sample.bin` and change one thing each, which the spec allows since they are not specific to one algorithm.

| Scenario | What is changed | Expected status | Exit |
|---|---|---|---|
| U01 | nothing: text, binary and empty files signed and verified with matching key and metadata, all three profiles | `OK` | 0 |
| U02 | the first byte of the artifact is flipped, size and name unchanged | `ARTIFACT_MISMATCH` | 1 |
| U03 | one byte appended to the artifact, and separately one byte removed | `ARTIFACT_MISMATCH` | 1 |
| U04 | `version` in the manifest changed to `2.0.0`, still canonically serialized, old signature kept | `INVALID_SIGNATURE` | 1 |
| U05 | one bit of the signature flipped, same length, valid Base64 | `INVALID_SIGNATURE` | 1 |
| U06 | the trust store emptied, and separately the publisher key removed with `trust remove` | `KEY_NOT_TRUSTED` | 1 |
| U07 | the publisher key is only allowed for `other-app` | `KEY_NOT_TRUSTED` | 1 |
| U08 | valid bundle, but verify expects version `2.0.0` | `METADATA_MISMATCH` | 1 |
| U09 | the artifact file renamed to `renamed.bin`, contents unchanged | `METADATA_MISMATCH` | 1 |
| U10 | each tested separately: a duplicate `version` field, `artifact.size` as a string, an invalid Base64 character, a manifest of 16385 bytes | `FORMAT_ERROR` | 1 |
| U11 | `algorithm` set to `unknown-profile` | `UNSUPPORTED_ALGORITHM` | 1 |
| U12 | signed with another Ed25519 key whose keyid is correct but which is not in the trust store | `KEY_NOT_TRUSTED` | 1 |
| U13 | bundle fields reordered and indented, both Base64 strings unchanged | `OK` | 0 |
| U14 | the same manifest signed twice with the same key, all three profiles; both bundles verified and the signatures compared | `OK` | 0 |

U14 result: RSA-PSS and ECDSA give two different signatures because every signature uses a fresh random 32-byte salt or random nonce, while Ed25519 gives two identical signatures because it is deterministic. Each comparison is saved as `comparison.txt`.

Run it from the repository root:

```bash
uv run --project signer --locked python tests/test.py
```

The script stops at the first command whose exit code or status differs from the expected one. Each run writes to `tests/results/U01_U14/<timestamp>/`: the keys, artifacts, bundles and trust stores of every case, the `verify --json` output of each case as `<case>.verification.json`, and a full command log with expected and actual exit codes in `results.txt`. The committed run, `20261115-223118-786842`, passed all 32 verification cases and the 3 signature comparisons. All private keys there are test-only.

#### C01 to C05

| Scenario | Workflow and job | Expected result |
|---|---|---|
| C01, all three profiles | `ci_app.yaml` | verify exits 0 with `OK`, deploy writes `out/deployed.marker` |
| C02, one byte changed after signing | `c0x_scenario.yaml`, job `c02` | exit 1, `ARTIFACT_MISMATCH`, no marker |
| C03, empty trust store | `c0x_scenario.yaml`, job `c03_empty` | exit 1, `KEY_NOT_TRUSTED`, no marker |
| C03, key only allowed for another package | `c0x_scenario.yaml`, job `c03_other_package` | exit 1, `KEY_NOT_TRUSTED`, no marker |
| C03 extra, trusted keyid with a different public key | `c0x_scenario.yaml`, job `c03_swapped_key` | exit 1, `FORMAT_ERROR`, no marker |
| C04, artifact file missing | `c0x_scenario.yaml`, job `c04` | exit 2, `INPUT_ERROR`, no marker |
| C05, runner UID and GID, no TTY, `--network none` | `c0x_scenario.yaml`, job `c05` | verify exits 0, the bundle is owned by the runner user |

To rerun them, open the Actions tab, pick `ci app` or `c0x scenarios`, and press Run workflow, or use the GitHub CLI:

```bash
gh workflow run ci_app.yaml
gh workflow run c0x_scenario.yaml
```

#### Interoperability

`tests/interop.py` checks every profile against OpenSSL, an independent implementation, in both directions:

| Direction | What happens | Expected result |
|---|---|---|
| A, xaleidscopix to OpenSSL | xaleidscopix runs keygen and sign; OpenSSL re-exports the public key, recomputes the keyid and artifact SHA-256, checks the key parameters and verifies the signature | OpenSSL verifies the signature; a manifest with one changed byte fails |
| B, OpenSSL to xaleidscopix | OpenSSL generates the key pair and signs a manifest built by the script; xaleidscopix runs trust add and verify | `trust add` prints the same keyid, verify gives `OK`; one flipped signature bit gives `INVALID_SIGNATURE` |
| C, OpenSSL key, xaleidscopix sign | xaleidscopix signs with an OpenSSL-generated key, OpenSSL verifies | OpenSSL verifies the signature |

Directions A and B use `test.txt`, `sample.bin` and `empty.bin` from `tests/test_cases`, which gives 27 checks in total. For ECDSA the script converts between the bundle's `r || s` and the ASN.1 DER form OpenSSL uses, with its own small DER encoder and decoder rather than the library under test.

OpenSSL commands used per profile:

| Profile | Key generation | Sign / verify |
|---|---|---|
| `rsa-pss-sha256` | `genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -pkeyopt rsa_keygen_pubexp:65537` | `dgst -sha256 -sigopt rsa_padding_mode:pss -sigopt rsa_pss_saltlen:32 -sigopt rsa_mgf1_md:sha256` |
| `ecdsa-p256-sha256` | `genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -pkeyopt ec_param_enc:named_curve` | `dgst -sha256`, signature converted between DER and `r \|\| s` |
| `ed25519` | `genpkey -algorithm ED25519` | `pkeyutl -rawin` (pure Ed25519, no pre-hash) |

The RSA key is generated with `-algorithm RSA`, not `RSA-PSS`, so its SPKI uses the `rsaEncryption` OID that Table 2.5 requires.

Run it from the repository root. It needs `openssl` on `PATH`, or `OPENSSL=/path/to/openssl`:

```bash
uv run --project signer --locked python tests/interop.py
```

Each run writes its keys, bundles, manifests, verification results and a full command log to `tests/results/interop/<timestamp>/results.txt`. All private keys there are test-only.

#### Performance

`tests/benchmark.py` measures every profile on the same three artifacts, 1 KiB, 1 MiB and 32 MiB of random bytes generated from a fixed seed:

| Metric | What is timed |
|---|---|
| `keygen` | generating one key pair, 10 key pairs per profile, separate from sign and verify |
| `hash` | SHA-256 over the artifact bytes already in memory, no file I/O |
| `sign`, `verify` | the signature operation over the manifest bytes only, including the algorithm's internal hash; no I/O and no artifact hashing |
| `e2e_inproc_sign`, `e2e_inproc_verify` | the full `sign` and `verify` commands called inside one Python process: reading files, hashing the artifact, parsing, writing the bundle or printing the result |
| `e2e_cli_sign`, `e2e_cli_verify` | the same commands as a new `xaleidscopix` process, so Python interpreter start-up is included |
| sizes | private key (PKCS8 DER, unencrypted), public key (SPKI DER), signature before and after Base64, manifest and bundle, in bytes |

Every timed batch runs 5 warm-up iterations that are thrown away, then 30 measured ones, timed with `time.perf_counter_ns`, a monotonic clock. The garbage collector is paused inside each batch. The median comes from `statistics.median`, and P95 uses the nearest-rank method: sort the samples and take position `ceil(0.95 * n)` counting from 1, which is the 29th of 30.

Run it from the repository root:

```bash
uv run --project signer --locked python tests/benchmark.py
```

`--runs`, `--warmup` and `--keygen-runs` change the counts, and `--quick` does a tiny smoke run whose numbers are not meant for the report. Each run writes to `tests/results/benchmark/<timestamp>/`:

| File | Contents |
|---|---|
| `environment.txt` | CPU, memory, OS, Python and library versions, the OpenSSL version `cryptography` is linked against, the method, and the SHA-256 of each generated artifact |
| `summary.md`, `summary.csv` | median, P95, min and max per metric, profile and artifact |
| `sizes.csv` | key, signature, manifest and bundle sizes |
| `raw.csv` | every individual sample in nanoseconds |

The artifacts are written to a temporary folder and deleted afterwards because the 32 MiB file is too large to commit; the fixed seed recreates the same bytes on every run.

## File formats

### Release manifest

| Field | Type | Rule |
|---|---|---|
| `schema` | string | always `minisign-manifest/v1` |
| `package` | string | `[a-z0-9][a-z0-9._-]{0,63}` |
| `version` | string | `[A-Za-z0-9][A-Za-z0-9._+-]{0,63}` |
| `algorithm` | string | one of the three profiles |
| `keyid` | string | 64 lowercase hex characters |
| `artifact.name` | string | file name without folders, `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` |
| `artifact.size` | integer | size in bytes, 0 to 9007199254740991 |
| `artifact.sha256` | string | SHA-256 of the artifact bytes, 64 lowercase hex characters |

```json
{
  "schema": "minisign-manifest/v1",
  "package": "zig-fork-app",
  "version": "0.1.0",
  "algorithm": "ed25519",
  "keyid": "KEY_ID",
  "artifact": {
    "name": "app.zip",
    "size": 0,
    "sha256": "SHA256"
  }
}
```

### Bundle

| Field | Type | Rule |
|---|---|---|
| `schema` | string | always `minisign-bundle/v1` |
| `manifest_b64` | string | the manifest bytes in standard Base64, RFC 4648, with padding |
| `signature_b64` | string | the signature bytes in standard Base64, RFC 4648, with padding |

```json
{
  "schema": "minisign-bundle/v1",
  "manifest_b64": "EXAMPLE_HERE",
  "signature_b64": "EXAMPLE_HERE"
}
```

### Key files

| Part | Format |
|---|---|
| Private key | PKCS8 PEM, label `PRIVATE KEY`, unencrypted |
| Public key | SubjectPublicKeyInfo PEM, label `PUBLIC KEY` |
| keyid | `hex_lower(SHA256(DER_SPKI))`, where `DER_SPKI` is the public key exported again as DER |

### Trust store

| Field | Type | Rule |
|---|---|---|
| `schema` | string | always `minisign-trust/v1` |
| `keys` | array | may be empty, each keyid appears once |
| `keys[].keyid` | string | fingerprint of `public_key_pem` |
| `keys[].algorithm` | string | profile, must match the key type and parameters |
| `keys[].public_key_pem` | string | the SPKI PEM text itself, not a path |
| `keys[].packages` | array of strings | packages this key may sign, not empty, no duplicates, no wildcards |

```json
{
  "schema": "minisign-trust/v1",
  "keys": [
    {
      "keyid": "KEY_ID",
      "algorithm": "ed25519",
      "public_key_pem": "-----BEGIN PUBLIC KEY-----\nPUBLIC_KEY\n-----END PUBLIC KEY-----\n",
      "packages": ["zig-fork-app"]
    }
  ]
}
```

## Cryptography library

All three signature profiles are implemented with [cryptography](https://cryptography.io/en/latest/) 50.0.2, pinned in `signer/uv.lock`. SHA-256 for artifacts and keyids comes from [hashlib](https://docs.python.org/3/library/hashlib.html) in the Python standard library. The manifest, bundle and trust store handling, the input checks, and the signing and verification flow are written in this repository, not handed off to another signing tool.

### Parameters

| Profile | Key | Signature scheme | Hash |
|---|---|---|---|
| `rsa-pss-sha256` | RSA, 3072 bit modulus, public exponent 65537 | PSS padding, MGF1 with SHA-256, 32 byte salt | SHA-256 |
| `ecdsa-p256-sha256` | ECDSA on P-256, also called secp256r1 | ECDSA with a random nonce, signature stored as raw `r‖s`, each 32 bytes big endian | SHA-256 |
| `ed25519` | Ed25519, RFC 8032 | pure Ed25519, no prehash | SHA-512 inside Ed25519 |

Key generation, PSS salts and ECDSA nonces use the secure random generator inside the library, which is seeded by the operating system, and no fixed seed is ever used. Because of the random salt and nonce, signing the same manifest twice gives two different RSA PSS or ECDSA signatures, while Ed25519 is deterministic and gives the same signature both times.

### Library API per profile

| Profile | Key generation | Sign and verify | Signature bytes |
|---|---|---|---|
| `rsa-pss-sha256` | `rsa.generate_private_key(public_exponent=65537, key_size=3072)` | `padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)` with `hashes.SHA256()` | 384 bytes |
| `ecdsa-p256-sha256` | `ec.generate_private_key(ec.SECP256R1())` | `ec.ECDSA(hashes.SHA256())`, the DER signature is converted to raw `r‖s` with `decode_dss_signature` and back with `encode_dss_signature` | 64 bytes, `r‖s` |
| `ed25519` | `ed25519.Ed25519PrivateKey.generate()` | `sign(manifest)` and `verify(signature, manifest)`, pure Ed25519 | 64 bytes |

### Other library calls

| Task | Call |
|---|---|
| Write a private key | `private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())` |
| Write a public key | `public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)` |
| Read a private key | `serialization.load_pem_private_key(data, password=None)` |
| Read a public key from the trust store | strict Base64 decode of the PEM body, then `serialization.load_der_public_key(der)` |
| keyid | `public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)`, then `hashlib.sha256(der).hexdigest()` |
| Artifact hash | `hashlib.file_digest(file, "sha256")` |
| Profile check | `key_size` and `public_numbers().e` for RSA, `curve` being `ec.SECP256R1` for ECDSA, the key type for Ed25519 |
| Rejected signature | `cryptography.exceptions.InvalidSignature` |

### Documentation

- [cryptography](https://cryptography.io/en/latest/)
- [RSA](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/)
- [Elliptic curve](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ec/)
- [Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/)
- [Key serialization](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/serialization/)
- [Asymmetric utilities](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/utils/)
- [Exceptions](https://cryptography.io/en/latest/exceptions/)
- [Python hashlib](https://docs.python.org/3/library/hashlib.html)

## Running outside a CI/CD runner

### From source with uv

```bash
cd signer
uv sync
uv run xaleidscopix --help
uv run xaleidscopix keygen --algorithm ed25519 --out ../keys/ed25519
```

### With the image on your own machine

```bash
IMAGE=ghcr.io/19623248git/tubes-3-if4020@sha256:332d9c180eeef05ac739c75d44bf5abc4579f0aeb6dd50df5732754f3f5fab0e
mkdir -p keys
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/keys:/keys" \
  "$IMAGE" keygen --algorithm ed25519 --out /keys/ed25519
```

### The pipeline scripts on your own machine

The same scripts the workflows use can run locally with a key file instead of a secret. `ci/trust.json` only trusts the CI keys, so a local key needs its own trust store.

```bash
export IMAGE=ghcr.io/19623248git/tubes-3-if4020@sha256:332d9c180eeef05ac739c75d44bf5abc4579f0aeb6dd50df5732754f3f5fab0e
export PACKAGE=zig-fork-app VERSION=0.1.0
bash ci/build.sh
SIGNING_KEY_FILE=keys/ed25519.key.pem bash ci/sign.sh
TRUST_STORE=keys/trust.json bash ci/verify.sh
bash ci/deploy.sh
```