keygen: 

- add public key to trust.json
- add private key to gh secrets

This command will generate keypairs for all of the algorithms while also storing the public key in trust.json

```bash
cd signer
mkdir -p ../keys
for a in ed25519 ecdsa-p256-sha256 rsa-pss-sha256; do
  uv run xaleidscopix keygen --algorithm "$a" --out "../keys/$a"
  uv run xaleidscopix trust add --key "../keys/$a.pub.pem" --package zig-fork-app --store ../ci/trust.json
done
```

This command will add the private key to github action secrets, you can do this manually in github if `gh` is not setup

```bash
gh secret set SIGNING_KEY_ED25519    < keys/ed25519.key.pem
gh secret set SIGNING_KEY_ECDSA_P256 < keys/ecdsa-p256-sha256.key.pem
gh secret set SIGNING_KEY_RSA_PSS    < keys/rsa-pss-sha256.key.pem
```