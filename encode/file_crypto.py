#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
file_crypto.py

A tiny CLI tool to encrypt/decrypt text (or any bytes) files with a key.

Security notes:
- Prefer using a randomly generated key (Fernet key).
- If you only have a human password, this tool derives a Fernet key using PBKDF2(SHA-256).
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from dataclasses import dataclass
from typing import Optional


FILE_HEADER = b"ENCODE1\n"
KDF_NONE = "none"
KDF_PBKDF2_SHA256 = "pbkdf2-sha256"


@dataclass(frozen=True)
class Envelope:
    kdf: str
    salt_b64: str
    token_b64: str

    def to_bytes(self) -> bytes:
        # Simple line-based envelope for portability and easy inspection.
        lines = [
            FILE_HEADER.decode("utf-8").rstrip("\n"),
            f"kdf={self.kdf}",
            f"salt={self.salt_b64}",
            f"token={self.token_b64}",
            "",
        ]
        return ("\n".join(lines)).encode("utf-8")

    @staticmethod
    def from_bytes(data: bytes) -> "Envelope":
        if not data.startswith(FILE_HEADER):
            raise ValueError("Input is not an ENCODE1 envelope (bad header).")
        text = data.decode("utf-8", errors="strict")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip() != ""]
        if len(lines) < 4:
            raise ValueError("Malformed envelope (missing fields).")
        if lines[0] != FILE_HEADER.decode("utf-8").rstrip("\n"):
            raise ValueError("Malformed envelope (header mismatch).")

        def parse_kv(line: str) -> tuple[str, str]:
            if "=" not in line:
                raise ValueError(f"Malformed envelope line: {line!r}")
            k, v = line.split("=", 1)
            return k.strip(), v.strip()

        kv = dict(parse_kv(ln) for ln in lines[1:4])
        kdf = kv.get("kdf")
        salt_b64 = kv.get("salt", "")
        token_b64 = kv.get("token")
        if not kdf or not token_b64:
            raise ValueError("Malformed envelope (kdf/token missing).")
        return Envelope(kdf=kdf, salt_b64=salt_b64, token_b64=token_b64)


def _require_cryptography():
    try:
        from cryptography.fernet import Fernet  # noqa: F401
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency 'cryptography'. Install it via:\n"
            "  pip install -r requirements.txt"
        ) from e


def _read_secret_value(value_or_path: str) -> str:
    """
    Read a secret from either:
    - a direct string, or
    - a file path containing the secret (trimmed).
    """
    if os.path.exists(value_or_path) and os.path.isfile(value_or_path):
        return open(value_or_path, "r", encoding="utf-8").read().strip()
    return value_or_path.strip()


def _is_valid_fernet_key(key_bytes: bytes) -> bool:
    """
    Validate whether key_bytes is a Fernet key.
    """
    _require_cryptography()
    from cryptography.fernet import Fernet

    try:
        Fernet(key_bytes)
        return True
    except Exception:
        return False


def generate_key_b64() -> str:
    _require_cryptography()
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode("utf-8")


def _derive_fernet_key_from_password(password: str, salt: bytes, iterations: int = 390_000) -> bytes:
    """
    Derive 32-byte key via PBKDF2HMAC(SHA256), then urlsafe-base64 encode for Fernet.
    """
    _require_cryptography()
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    raw = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def _load_key_bytes(args: argparse.Namespace, *, for_encrypt: bool, envelope: Optional[Envelope] = None) -> tuple[bytes, str, str]:
    """
    Returns (fernet_key_bytes, kdf_name, salt_b64_string).
    - If --key is provided: KDF_NONE, no salt.
    - If --password is provided: PBKDF2-SHA256 with random salt (encrypt) or envelope salt (decrypt).
    """
    key = args.key
    password = args.password
    if bool(key) == bool(password):
        raise ValueError("Provide exactly one of --key or --password.")

    if key:
        # --key supports either:
        # - a Fernet key (recommended), or
        # - a human passphrase (auto-derived via PBKDF2, like --password).
        key_str = _read_secret_value(key)
        key_bytes = key_str.encode("utf-8")

        if for_encrypt:
            if _is_valid_fernet_key(key_bytes):
                return key_bytes, KDF_NONE, ""
            salt = os.urandom(16)
            salt_b64 = base64.urlsafe_b64encode(salt).decode("utf-8")
            return _derive_fernet_key_from_password(key_str, salt), KDF_PBKDF2_SHA256, salt_b64

        if envelope is None:
            raise ValueError("Internal error: envelope required for decrypt.")
        if envelope.kdf == KDF_NONE:
            if not _is_valid_fernet_key(key_bytes):
                raise ValueError("This file requires a Fernet key; generate one via: python file_crypto.py gen-key")
            return key_bytes, KDF_NONE, ""
        if envelope.kdf == KDF_PBKDF2_SHA256:
            if not envelope.salt_b64:
                raise ValueError("Envelope missing salt; cannot derive key from passphrase.")
            salt = base64.urlsafe_b64decode(envelope.salt_b64.encode("utf-8"))
            return _derive_fernet_key_from_password(key_str, salt), envelope.kdf, envelope.salt_b64
        raise ValueError(f"Unsupported envelope kdf: {envelope.kdf!r}")

    # password path support (optional convenience)
    password_str = _read_secret_value(password)

    if for_encrypt:
        salt = os.urandom(16)
        salt_b64 = base64.urlsafe_b64encode(salt).decode("utf-8")
        return _derive_fernet_key_from_password(password_str, salt), KDF_PBKDF2_SHA256, salt_b64

    if envelope is None:
        raise ValueError("Internal error: envelope required for decrypt with password.")
    if envelope.kdf != KDF_PBKDF2_SHA256:
        raise ValueError(f"Envelope KDF is {envelope.kdf!r}, but you provided --password.")
    if not envelope.salt_b64:
        raise ValueError("Envelope missing salt; cannot derive key from password.")
    salt = base64.urlsafe_b64decode(envelope.salt_b64.encode("utf-8"))
    return _derive_fernet_key_from_password(password_str, salt), envelope.kdf, envelope.salt_b64


def encrypt_file(in_path: str, out_path: str, args: argparse.Namespace) -> None:
    _require_cryptography()
    from cryptography.fernet import Fernet

    plaintext = open(in_path, "rb").read()
    key_bytes, kdf, salt_b64 = _load_key_bytes(args, for_encrypt=True)
    f = Fernet(key_bytes)
    token = f.encrypt(plaintext)  # bytes (urlsafe base64 token)
    env = Envelope(kdf=kdf, salt_b64=salt_b64, token_b64=token.decode("utf-8"))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "wb") as fw:
        fw.write(env.to_bytes())


def decrypt_file(in_path: str, out_path: str, args: argparse.Namespace) -> None:
    _require_cryptography()
    from cryptography.fernet import Fernet, InvalidToken

    data = open(in_path, "rb").read()
    env = Envelope.from_bytes(data)

    # If envelope has KDF_NONE, the user must supply --key
    if env.kdf == KDF_NONE:
        if not args.key or args.password:
            raise ValueError("This file was encrypted with --key; decrypt with --key (not --password).")
        key_bytes, _, _ = _load_key_bytes(args, for_encrypt=False, envelope=env)
    elif env.kdf == KDF_PBKDF2_SHA256:
        if not (args.password or args.key) or (args.password and args.key):
            raise ValueError("This file was encrypted with PBKDF2; decrypt with exactly one of --password or --key (passphrase).")
        key_bytes, _, _ = _load_key_bytes(args, for_encrypt=False, envelope=env)
    else:
        raise ValueError(f"Unsupported envelope kdf: {env.kdf!r}")

    f = Fernet(key_bytes)
    try:
        plaintext = f.decrypt(env.token_b64.encode("utf-8"))
    except InvalidToken as e:
        raise ValueError("Decrypt failed: wrong key/password or file was modified.") from e

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "wb") as fw:
        fw.write(plaintext)


def _default_out_path(in_path: str, mode: str) -> str:
    if mode == "encrypt":
        return in_path + ".enc"
    if mode == "decrypt":
        if in_path.endswith(".enc"):
            return in_path[: -len(".enc")] + ".dec"
        return in_path + ".dec"
    raise ValueError(f"Unknown mode: {mode!r}")


def compare_files(path_a: str, path_b: str, *, chunk_size: int = 1024 * 1024) -> bool:
    """
    Compare two files byte-by-byte.

    Returns True if identical, False otherwise.
    """
    if os.path.abspath(path_a) == os.path.abspath(path_b):
        return True

    stat_a = os.stat(path_a)
    stat_b = os.stat(path_b)
    if stat_a.st_size != stat_b.st_size:
        return False

    with open(path_a, "rb") as fa, open(path_b, "rb") as fb:
        while True:
            ba = fa.read(chunk_size)
            bb = fb.read(chunk_size)
            if ba != bb:
                return False
            if not ba:
                return True


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="file_crypto.py",
        description="Encrypt/decrypt a file using a key (Fernet) or a password-derived key (PBKDF2).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("gen-key", help="Generate a Fernet key and print it (or save to a file).")
    p_gen.add_argument("--out", help="Write key to file instead of stdout.")

    p_enc = sub.add_parser("encrypt", help="Encrypt a file into an ENCODE1 envelope.")
    p_enc.add_argument("--in", dest="in_path", required=True, help="Input file path (plaintext).")
    p_enc.add_argument("--out", dest="out_path", help="Output file path. Default: <in>.enc")
    p_enc.add_argument("--key", help="Fernet key string OR path to a file containing the key.")
    p_enc.add_argument("--password", help="Password string OR path to a file containing password.")

    p_dec = sub.add_parser("decrypt", help="Decrypt an ENCODE1 envelope file back to plaintext.")
    p_dec.add_argument("--in", dest="in_path", required=True, help="Input file path (.enc envelope).")
    p_dec.add_argument("--out", dest="out_path", help="Output file path. Default: <in>.dec")
    p_dec.add_argument("--key", help="Fernet key string OR path to a file containing the key.")
    p_dec.add_argument("--password", help="Password string OR path to a file containing password.")

    p_cmp = sub.add_parser("compare", help="Compare whether two files have identical content.")
    p_cmp.add_argument("file1", help="First file path.")
    p_cmp.add_argument("file2", help="Second file path.")

    return p


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.cmd == "gen-key":
            key = generate_key_b64()
            if args.out:
                os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
                with open(args.out, "w", encoding="utf-8", newline="\n") as fw:
                    fw.write(key + "\n")
            else:
                sys.stdout.write(key + "\n")
            return 0

        if args.cmd == "compare":
            same = compare_files(args.file1, args.file2)
            if same:
                sys.stdout.write("SAME\n")
                return 0
            sys.stdout.write("DIFF\n")
            # Note: use a dedicated exit code so it won't be confused with "ERROR" (which is 1).
            return 3

        if args.cmd in ("encrypt", "decrypt"):
            out_path = args.out_path or _default_out_path(args.in_path, args.cmd)
            if args.cmd == "encrypt":
                encrypt_file(args.in_path, out_path, args)
            else:
                decrypt_file(args.in_path, out_path, args)
            return 0

        parser.error(f"Unknown command: {args.cmd}")
        return 2
    except Exception as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


