#!/usr/bin/env python3
"""Offline Ed25519 certificate verifier. Requires only cryptography.

Usage: python verify.py certificate.json --trusted-public-key BASE64URL_KEY
A signature alone is not proof of organizer identity; compare the key with one
published through a trusted channel before trusting the issuer.
"""
import argparse
import base64
import binascii
import json
import sys
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _decode(value, length):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError('Invalid base64url field')
    if any(char not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for char in value):
        raise ValueError('Invalid base64url characters')
    try:
        raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    except (ValueError, binascii.Error) as exc:
        raise ValueError('Invalid base64url encoding') from exc
    if len(raw) != length or base64.urlsafe_b64encode(raw).rstrip(b'=').decode() != value:
        raise ValueError('Invalid base64url length or encoding')
    return raw


def verify(document, trusted_public_key=None):
    """Return (valid, explanation). Does not authenticate a self-asserted issuer."""
    if not isinstance(document, dict) or set(document) != {'payload', 'public_key', 'signature', 'algorithm'}:
        return False, 'Invalid certificate shape.'
    if document['algorithm'] != 'Ed25519' or not isinstance(document['payload'], dict):
        return False, 'Unsupported algorithm or payload.'
    try:
        public = _decode(document['public_key'], 32)
        signature = _decode(document['signature'], 64)
        signed = json.dumps(document['payload'], sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
        Ed25519PublicKey.from_public_bytes(public).verify(signature, signed)
        if trusted_public_key is not None and public != _decode(trusted_public_key, 32):
            return False, 'Signature valid, but the key does not match the trusted organizer key.'
    except (TypeError, ValueError, OverflowError, InvalidSignature, UnicodeError):
        return False, 'Invalid signature or malformed certificate.'
    if trusted_public_key is None:
        return True, 'Signature is internally valid. Issuer identity is NOT verified: compare the embedded public key with a trusted organizer key.'
    return True, 'Signature valid and public key matches the supplied trusted organizer key.'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('certificate', help='Path to the downloaded certificate JSON')
    parser.add_argument('--trusted-public-key', help='Base64url raw Ed25519 public key from a trusted organizer channel')
    args = parser.parse_args(argv)
    try:
        with open(args.certificate, 'rb') as source:
            body = source.read(16385)
        if len(body) > 16384:
            raise ValueError('Certificate exceeds 16 KiB')
        document = json.loads(body)
        valid, explanation = verify(document, args.trusted_public_key)
    except (OSError, ValueError, UnicodeError) as exc:
        valid, explanation = False, 'Cannot read certificate: ' + str(exc)
    print(('SIGNATURE VALID' if valid else 'INVALID') + ': ' + explanation)
    return 0 if valid else 1


if __name__ == '__main__':
    sys.exit(main())
