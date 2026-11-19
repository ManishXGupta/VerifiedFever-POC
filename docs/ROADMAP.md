# Roadmap

The proof of concept is deliberately small. Planned extensions, roughly in order:

## 1. Validation
- **Bench test** of the thermometer against a calibrated reference in a water bath (`experiments/bench_analysis.py`).
- **Usability study** with school nurses, parents and administrators (System Usability Scale plus task times), compared with the current doctor's-note process.
- **Pilot** with real longitudinal student readings, under IRB approval and parental consent, to confirm the personal-baseline gains seen in simulation.

## 2. Hardware
- Move signing from software into a **Bluetooth (BLE) thermometer** with a secure element, so the private key never leaves the device.
- Device attestation at enrollment (manufacturer certificate chain).
- Photo-of-display fallback for thermometers without connectivity, marked as lower assurance.

## 3. Product
- Mobile parent app and a school SIS integration (absence record created automatically on approval).
- W3C Verifiable Credential format for certificates, so they can be checked by any wallet or verifier.
- Configurable policies per school or district; Fahrenheit display.
- Audit log and role-based access for nurses, physicians and administrators.

## 4. Generalized proactive health monitoring (separate paper)
- Opt-in proactive temperature registration for any individual, not only students.
- Physician dashboard comparing many people's temperature trends over the same period.
- Cohort-level detection is in the POC (simulation); next: area-level aggregation across schools with privacy-preserving counts.

## Known limitations
- Cryptography proves that a reading came unaltered from an enrolled device. It does not prove that the probe was used correctly on the right child, or that it was not warmed.
- Fever-reducing medicine can mask a fever.
- Simulation results depend on the stated cohort assumptions.
