keygen: 

- add public key to trust.json
- add private key to gh secrets

This command will generate keypairs for all of the algorithms while also storing the public key in trust.json
```
mkdir -p ../keys
for a in ed25519 ecdsa-p256-sha256 rsa-pss-sha256; do
  uv run xaleidscopix keygen --algorithm "$a" --out "../keys/$a"
  uv run xaleidscopix trust add --key "../keys/$a.pub.pem" --package zig-fork-app --store ../ci/trust.json
done
```