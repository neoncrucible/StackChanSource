# Branch audit — 7 September 2026

All 18 remote branches were fetched before candidate work. The authoritative
starting point was `70e7d80baa81ef3b280e96e0f3de25e0c52618ed` on
`kadence/rebuild-kade`. No historical branch was merged into the rebuild.

| Branch | Head | Engineering disposition |
|---|---|---|
| beta/project-kadence | 908455e | Preserve lessons about I2C error containment and single service ownership. |
| docs-dev | ad47f0b | Upstream documentation only. |
| feature/alpha1-startup-foundation | 47062b9 | Preserve the correction of the ReadMove deadlock and factory pitch convention. |
| feature/kade-eye-smoke-test | 0241902 | Historical asset provenance; no hardware owner or asset import reused. |
| feature/kade-eye-v0.1 | 36e2521 | Historical packaging reference; old combined image is incompatible with this partition layout. |
| feature/kade-firmware-bootstrap | 7f76862 | Preserve explicit IDF environment initialization. |
| feature/optic-eye-checkpoint-0727 | 0a1ef73 | Preserve flash manifest subdirectories and the Xtensa type compatibility lesson. |
| feature/servo-yaw-checkpoint | c0ed6aa | Preserve factory motor update semantics; do not create a second executor. |
| feature/voice-checkpoint-1 | 77c8dd6 | Preserve single response service ownership and accepted volume. |
| firmware-dev | da156e1 | Upstream baseline; no cross-generation runtime merge. |
| ios-dev | 4f87087 | Separate mobile application; not the device/host authority. |
| kadence/rebuild-kade | 70e7d80 | Authoritative Phase A physical sign-off and current architecture. |
| kadence/2.0-alpha-1 | 2d9ca4d | Frozen older transport; retain rollback provenance, not its flash offsets. |
| kadence/2.0-alpha-2 | c74d894 | Reuse strict schema validator ancestry; preserve bounded completed-turn history, exact authority gate, and location disambiguation lessons. |
| kadence/2.0-alpha-3 | b6cf6e2 | Retain bounded reasoning/output and provider independence; no legacy runtime patching. |
| main | 3b98900 | Historical checkpoint base; not a release target for this work. |
| remote-dev | f71b5cc | Separate upstream remote client; no merge needed. |
| server-dev | d990e6d | Separate upstream service architecture; not the current RuntimeBody boundary. |

The old M5 boundary passed physical validation, but its Gemini-specific recursive
function adapter hit `thought_signature` and schema-dialect failures. RC1 keeps
the current stream adapter and uses a bounded provider-neutral JSON proposal.
Only the host registry can execute it; model text cannot authorize a write.

`tool_bridge.py` adapts the schema validation from the Alpha 2
`kadence_tools.py` at `c74d894`, adding execution deadlines, cancellation,
bounded JSON input/output, immutable registration copies and write denial.
The previous transport patchers and generic plugin executors are not imported.

The existing CI workflow still selected archived CP10–19 entries and flattened
artifact paths. RC1 replaces those obsolete entry selectors with the current
CP23/A3/A4 contracts, behavioral host tests, native renderer checks and an actual
ESP-IDF build. Historical gates remain in the repository as diagnostic history.
