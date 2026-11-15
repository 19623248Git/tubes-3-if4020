# Benchmark 20261115-231014-503419

```
Date: 2026-11-15T23:10:14
CPU: AMD Ryzen 7 7735HS with Radeon Graphics (16 logical CPUs)
Memory: 15.2 GiB
OS: Windows-11-10.0.26300-SP0
Python: CPython 3.14.3 (D:\Kuliah\Sem_7\Crypto\tugas3\tubes-3-if4020\signer\.venv\Scripts\python.exe)
cryptography: 50.0.2, linked against OpenSSL 4.0.3 29 Sep 2026
Clock: time.perf_counter_ns (monotonic)
Runs per batch: 5 warm-up (discarded) + 30 measured; keygen: 10 key pairs per profile
Median: statistics.median. P95: nearest-rank, sorted samples, position ceil(0.95 * n) counting from 1.
Garbage collector paused during each timed batch.
Artifacts (random bytes, seed 20261116):
  artifact-1KiB.bin: 1024 bytes, sha256 5e53e035b76488d1033773460f2d71edb885096e96a23d87bc3cb473a055ddb7
  artifact-1MiB.bin: 1048576 bytes, sha256 a6311a8876c70bdc1598f84ce44f5f3e5939a0fa846aa4654da579876ededfb6
  artifact-32MiB.bin: 33554432 bytes, sha256 2794eaf023501da6ae4514a04cb0cd43c3c660da38bda0224d1e878d64ba9529
```

## Key generation

| Metric | Profile | n | Median (ms) | P95 (ms) |
|---|---|---|---|---|
| keygen | rsa-pss-sha256 | 10 | 87.6355 | 261.1723 |
| keygen | ecdsa-p256-sha256 | 10 | 0.0143 | 0.0208 |
| keygen | ed25519 | 10 | 0.0486 | 0.0640 |

## SHA-256 over artifact bytes

| Metric | Profile | Artifact | n | Median (ms) | P95 (ms) |
|---|---|---|---|---|---|
| hash | - | 1KiB | 30 | 0.0013 | 0.0015 |
| hash | - | 1MiB | 30 | 0.4986 | 0.8945 |
| hash | - | 32MiB | 30 | 15.5747 | 16.1001 |

## Sign / verify over manifest bytes

| Metric | Profile | Artifact | n | Median (ms) | P95 (ms) |
|---|---|---|---|---|---|
| sign | rsa-pss-sha256 | 1KiB | 30 | 1.4849 | 1.5347 |
| verify | rsa-pss-sha256 | 1KiB | 30 | 0.0427 | 0.0433 |
| sign | rsa-pss-sha256 | 1MiB | 30 | 1.4922 | 1.5293 |
| verify | rsa-pss-sha256 | 1MiB | 30 | 0.0426 | 0.0693 |
| sign | rsa-pss-sha256 | 32MiB | 30 | 1.5237 | 1.5893 |
| verify | rsa-pss-sha256 | 32MiB | 30 | 0.0427 | 0.0497 |
| sign | ecdsa-p256-sha256 | 1KiB | 30 | 0.0237 | 0.0295 |
| verify | ecdsa-p256-sha256 | 1KiB | 30 | 0.0576 | 0.0640 |
| sign | ecdsa-p256-sha256 | 1MiB | 30 | 0.0583 | 0.0728 |
| verify | ecdsa-p256-sha256 | 1MiB | 30 | 0.0874 | 0.0932 |
| sign | ecdsa-p256-sha256 | 32MiB | 30 | 0.0330 | 0.0358 |
| verify | ecdsa-p256-sha256 | 32MiB | 30 | 0.0807 | 0.0891 |
| sign | ed25519 | 1KiB | 30 | 0.0459 | 0.0684 |
| verify | ed25519 | 1KiB | 30 | 0.1349 | 0.1797 |
| sign | ed25519 | 1MiB | 30 | 0.0421 | 0.0427 |
| verify | ed25519 | 1MiB | 30 | 0.1268 | 0.1379 |
| sign | ed25519 | 32MiB | 30 | 0.0377 | 0.0566 |
| verify | ed25519 | 32MiB | 30 | 0.1185 | 0.1287 |

## End-to-end, in process (no interpreter start-up)

| Metric | Profile | Artifact | n | Median (ms) | P95 (ms) |
|---|---|---|---|---|---|
| e2e_inproc_sign | rsa-pss-sha256 | 1KiB | 30 | 95.8166 | 96.8700 |
| e2e_inproc_verify | rsa-pss-sha256 | 1KiB | 30 | 0.4476 | 0.4863 |
| e2e_inproc_sign | rsa-pss-sha256 | 1MiB | 30 | 96.8425 | 101.6891 |
| e2e_inproc_verify | rsa-pss-sha256 | 1MiB | 30 | 0.9724 | 1.0573 |
| e2e_inproc_sign | rsa-pss-sha256 | 32MiB | 30 | 117.4634 | 139.4041 |
| e2e_inproc_verify | rsa-pss-sha256 | 32MiB | 30 | 21.4977 | 22.0150 |
| e2e_inproc_sign | ecdsa-p256-sha256 | 1KiB | 30 | 0.5975 | 0.7425 |
| e2e_inproc_verify | ecdsa-p256-sha256 | 1KiB | 30 | 0.4613 | 0.5098 |
| e2e_inproc_sign | ecdsa-p256-sha256 | 1MiB | 30 | 1.8262 | 1.9969 |
| e2e_inproc_verify | ecdsa-p256-sha256 | 1MiB | 30 | 1.4687 | 1.6130 |
| e2e_inproc_sign | ecdsa-p256-sha256 | 32MiB | 30 | 29.1653 | 31.3940 |
| e2e_inproc_verify | ecdsa-p256-sha256 | 32MiB | 30 | 29.4617 | 34.1719 |
| e2e_inproc_sign | ed25519 | 1KiB | 30 | 1.2120 | 1.3531 |
| e2e_inproc_verify | ed25519 | 1KiB | 30 | 0.8195 | 0.8938 |
| e2e_inproc_sign | ed25519 | 1MiB | 30 | 1.7566 | 1.8146 |
| e2e_inproc_verify | ed25519 | 1MiB | 30 | 1.4103 | 1.6204 |
| e2e_inproc_sign | ed25519 | 32MiB | 30 | 28.7034 | 31.5272 |
| e2e_inproc_verify | ed25519 | 32MiB | 30 | 28.5661 | 32.4035 |

## End-to-end, CLI as a new process

| Metric | Profile | Artifact | n | Median (ms) | P95 (ms) |
|---|---|---|---|---|---|
| e2e_cli_sign | rsa-pss-sha256 | 1KiB | 30 | 477.2620 | 532.0028 |
| e2e_cli_verify | rsa-pss-sha256 | 1KiB | 30 | 377.3150 | 419.1902 |
| e2e_cli_sign | rsa-pss-sha256 | 1MiB | 30 | 480.8764 | 534.4616 |
| e2e_cli_verify | rsa-pss-sha256 | 1MiB | 30 | 379.9733 | 413.5564 |
| e2e_cli_sign | rsa-pss-sha256 | 32MiB | 30 | 490.6116 | 513.1300 |
| e2e_cli_verify | rsa-pss-sha256 | 32MiB | 30 | 389.1054 | 411.9396 |
| e2e_cli_sign | ecdsa-p256-sha256 | 1KiB | 30 | 387.7505 | 426.5055 |
| e2e_cli_verify | ecdsa-p256-sha256 | 1KiB | 30 | 391.3023 | 475.7384 |
| e2e_cli_sign | ecdsa-p256-sha256 | 1MiB | 30 | 386.3130 | 413.6027 |
| e2e_cli_verify | ecdsa-p256-sha256 | 1MiB | 30 | 369.3963 | 496.5806 |
| e2e_cli_sign | ecdsa-p256-sha256 | 32MiB | 30 | 378.9031 | 404.0173 |
| e2e_cli_verify | ecdsa-p256-sha256 | 32MiB | 30 | 387.8165 | 424.0115 |
| e2e_cli_sign | ed25519 | 1KiB | 30 | 393.2025 | 476.9066 |
| e2e_cli_verify | ed25519 | 1KiB | 30 | 377.7850 | 454.9544 |
| e2e_cli_sign | ed25519 | 1MiB | 30 | 389.8540 | 427.4771 |
| e2e_cli_verify | ed25519 | 1MiB | 30 | 362.7541 | 392.5330 |
| e2e_cli_sign | ed25519 | 32MiB | 30 | 384.3172 | 438.9290 |
| e2e_cli_verify | ed25519 | 32MiB | 30 | 383.5750 | 419.3702 |

## Sizes (bytes)

| Profile | Artifact | Private key DER | Public key DER | Signature | Signature Base64 | Manifest | Bundle |
|---|---|---|---|---|---|---|---|
| rsa-pss-sha256 | 1KiB | 1793 | 422 | 384 | 512 | 305 | 1002 |
| rsa-pss-sha256 | 1MiB | 1793 | 422 | 384 | 512 | 308 | 1006 |
| rsa-pss-sha256 | 32MiB | 1793 | 422 | 384 | 512 | 310 | 1010 |
| ecdsa-p256-sha256 | 1KiB | 138 | 91 | 64 | 88 | 308 | 582 |
| ecdsa-p256-sha256 | 1MiB | 138 | 91 | 64 | 88 | 311 | 586 |
| ecdsa-p256-sha256 | 32MiB | 138 | 91 | 64 | 88 | 313 | 590 |
| ed25519 | 1KiB | 48 | 44 | 64 | 88 | 298 | 570 |
| ed25519 | 1MiB | 48 | 44 | 64 | 88 | 301 | 574 |
| ed25519 | 32MiB | 48 | 44 | 64 | 88 | 303 | 574 |
