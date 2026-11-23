"""Check a shared certificate package on its own, with only the issuer's public key.

    python verify_certificate_file.py demo_output/certificate_package.json

This is what a school can do offline. Open the JSON file, change any field (for example
absence_end), save it and run this again: the result changes from VALID to INVALID.
"""
import json
import sys

from verifiedfever import crypto

pkg = json.load(open(sys.argv[1]))
cert = dict(pkg["certificate"])
sig = cert.pop("issuer_sig", "")
cert.pop("student_name", None)
ok = crypto.verify(pkg["issuer_public_key"], cert, sig)
print("VALID: signed by the issuer and unchanged" if ok else "INVALID: the certificate was changed or not signed by this issuer")
print(f"  student {cert['student_id']}, absence {cert['absence_start']} to {cert['absence_end']}, status {cert['status']}, "
      f"approved by {cert['validated_by']}")
sys.exit(0 if ok else 1)
