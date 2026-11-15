# Xaleidscopix Signer

Xaleidscopix is a command line tool for signing and verifying software releases, in the spirit of Sigstore Cosign blob signing and minisign. A publisher signs a release artifact with a private key, and the tool writes a bundle that holds a canonical JSON release manifest together with its signature. Anyone who has the publisher's public key in a local trust store can then check that the artifact is unchanged and that it was signed by a key trusted for that package.

Three signature profiles are supported: `rsa-pss-sha256`, `ecdsa-p256-sha256` and `ed25519`.

The tool is shipped as a container image on GitHub Container Registry and is used by a GitHub Actions pipeline that builds a release artifact, signs it, verifies it, and only deploys it once verification passes.

The artifact released by the pipeline is built from `app/`, a fork of [Zig](https://github.com/ziglang/zig) latest commit before migrating, with its upstream history squashed into a single commit, which explains the contributor count of this repository.

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

`ci/trust.json` is prepared manuially and committed to the repository. The pipeline only reads it, it is never generated or updated from a bundle.

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

ADD THIS LATER

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

### Algorithm profiles and library API

All three profiles use cryptography 50.0.2. Keys and RSA PSS salts come from the operating system's secure random source through the library. ECDSA uses random nonces.

| Profile | Key generation | Sign and verify | Signature bytes |
|---|---|---|---|
| `rsa-pss-sha256` | `rsa.generate_private_key(public_exponent=65537, key_size=3072)` | `padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)` with `hashes.SHA256()` | 384 bytes |
| `ecdsa-p256-sha256` | `ec.generate_private_key(ec.SECP256R1())` | `ec.ECDSA(hashes.SHA256())`, the DER signature is converted to raw `r‖s` with `decode_dss_signature` and back with `encode_dss_signature` | 64 bytes, `r‖s` |
| `ed25519` | `ed25519.Ed25519PrivateKey.generate()` | `sign(manifest)` and `verify(signature, manifest)`, pure Ed25519 | 64 bytes |

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