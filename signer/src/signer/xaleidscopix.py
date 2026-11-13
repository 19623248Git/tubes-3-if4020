import argparse
from importlib.metadata import PackageNotFoundError, version as package_version

from signer.subcommands import keygen

prog = "xaleidscopix"
package = "signer"
profil = ("rsa-pss-sha256", "ecdsa-p256-sha256", "ed25519")

def program_version() -> str:
    try:
        return package_version(package)
    except PackageNotFoundError:
        return "unknown"


def call_keygen(args):
    raise SystemExit(keygen.run(args))

def call_sign(args):
    print("calling sign")

def call_verify(args):
    print("calling verify")

def call_trust_add(args):
    print("calling trust add")

def call_trust_list(args):
    print("calling trust list")

def call_trust_remove(args):
    print("calling trust remove")

def main():
    
    parser = argparse.ArgumentParser(prog=prog, description="software release signer and verifier")
    parser.add_argument("--version", action="version", version=f"%(prog)s {program_version()}")
    
    subcommands = parser.add_subparsers(dest="subcommands", required=True, metavar="<subcommands>")

    keygen = subcommands.add_parser("keygen", help="generate key pair")
    keygen.add_argument("--algorithm", required=True, choices=profil, metavar="<profil>")
    keygen.add_argument("--out", required=True, metavar="<prefix>", help="writes <prefix>.key.pem and <prefix>.pub.pem")
    keygen.add_argument("--overwrite", action="store_true", help="overwrite existing private key")
    keygen.set_defaults(func=call_keygen)

    sign = subcommands.add_parser("sign", help="sign artifact and outputs bundle")
    sign.add_argument("--file", required=True, metavar="<path>")
    sign.add_argument("--package", required=True, metavar="<nama>")
    sign.add_argument("--version", required=True, metavar="<versi>", help="release version (not the program version)")
    sign.add_argument("--key", required=True, metavar="<private.pem>")
    sign.add_argument("--out", required=True, metavar="<bundle.json>")
    sign.set_defaults(func=call_sign)

    verify = subcommands.add_parser("verify", help="verify artifact against bundle and local custom trust store")
    verify.add_argument("--file", required=True, metavar="<path>")
    verify.add_argument("--bundle", required=True, metavar="<bundle.json>")
    verify.add_argument("--trust-store", required=True, metavar="<trust.json>")
    verify.add_argument("--package", required=True, metavar="<nama>")
    verify.add_argument("--version", required=True, metavar="<version>",help="expected release version")
    verify.add_argument("--json", action="store_true", help="print the result as JSON")
    verify.set_defaults(func=call_verify)

    trust = subcommands.add_parser("trust", help="manage local trust store")
    trust_actions = trust.add_subparsers(dest="trust_command", required=True, metavar="<action>")

    trust_add = trust_actions.add_parser("add", help="add public key")
    trust_add.add_argument("--key", required=True, metavar="<public_pem>")
    trust_add.add_argument("--package", required=True, metavar="<name>")
    trust_add.add_argument("--store", required=True, metavar="<trust.json>")
    trust_add.set_defaults(func=call_trust_add)

    trust_list = trust_actions.add_parser("list", help="list trusted keys")
    trust_list.add_argument("--store", required=True, metavar="<trust.json>")
    trust_list.set_defaults(func=call_trust_list)

    trust_remove = trust_actions.add_parser("remove", help="remove key")
    trust_remove.add_argument("--keyid", required=True, metavar="<fingerprint>")
    trust_remove.add_argument("--store", required=True, metavar="<trust.json>")
    trust_remove.set_defaults(func=call_trust_remove)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()


