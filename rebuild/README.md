# Clean rebuild workspace

This subtree is intentionally isolated from the legacy implementation while the new runtime contract is proven.

## Rules

- Hardware is an endpoint, not the cognitive host.
- Core runtime must remain provider-agnostic.
- Optional integrations must fail independently.
- Device/runtime messages are versioned and validated.
- Presentation and identity are data-driven and kept out of the transport core.
- Every milestone must have a host-side diagnostic before hardware flashing.

## First host check

```powershell
py -3.12 .\rebuild\tools\doctor.py
```
