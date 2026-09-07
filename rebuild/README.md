# Clean rebuild workspace

This subtree is intentionally isolated from the legacy implementation while the new runtime contract is proven.

RC1 at `9976548` (host 0.2.0 / firmware 0.20.1) was approved by the owner on
7 September 2026.

- [Operator manual — all current features and instructions](docs/USER_MANUAL.md)
- [Daily startup and shutdown](docs/DAILY_USE.md)
- [Approved build and observed acceptance](docs/RC1_ACCEPTANCE.md)
- [Authoritative engineering handover](docs/KADENCE_HANDOVER.md)
- [Next-release proposal — awaiting owner approval](docs/NEXT_RELEASE_PROPOSAL.md)

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
