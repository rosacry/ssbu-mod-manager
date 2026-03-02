# SSBU Online Desync Tracker

Created: 2026-02-26
Owner: chrig
Purpose: single source of truth for online compatibility/desync work, with clear done vs pending status.

## Status Legend
- `[x]` done
- `[ ]` pending
- `[~]` in progress
- `[!]` blocked or needs decision

## Current Snapshot
- `[x]` Existing compatibility checker located and reviewed.
- `[x]` Existing online guide text reviewed.
- `[x]` Existing emulator migration/network assumptions reviewed.
- `[x]` Chat claims from `oi` captured (including latest updates).
- `[x]` External research pass completed (primary sources + locked evidence tables).
- `[x]` Primary-source validation pass re-run and links refreshed.
- `[x]` Desync rule engine rewrite/hardening.
- `[x]` Mod list badge for desync risk states.
- `[x]` Automated tests for online compatibility/classification logic.
- `[x]` Strict audio sync UI control wired into generate/check flows.
- `[x]` Per-rule evidence URL output added to mod/plugin risk details.
- `[x]` Added emulator-pair matrix template and RTT benchmark protocol docs.
- `[x]` Added persisted emulator build + game version metadata inputs for compatibility codes.
- `[x]` Added game-version normalization/validation and inline metadata quality guidance.
- `[x]` Added CLI logging automation for emulator-pair/RTT empirical runs.
- `[x]` Completed strict environment policy mode (host-enforced metadata exactness checks).
- `[x]` Added `seed-defaults` flow for canonical emulator-pair matrix bootstrapping.
- `[x]` Added dedicated evidence-lock reference doc (`docs/online_evidence_lock.md`).
- `[x]` Re-rendered seeded emulator-pair report so canonical rows are visible.
- `[x]` Added matrix/RTT coverage summaries and pending-next command suggestions in empirical logging CLI.

## Conversation Claims Log (chrig <-> oi)

| ID | Claim | Source | Status vs Codebase | Verification State | Action |
|---|---|---|---|---|---|
| C01 | Port forwarding gives lowest ping; radmin vpn fallback if no port-forward. | oi | Not implemented in app logic. | Unverified in repo (network behavior outside app). | Research and document network topology guidance. |
| C02 | Skin-only mods do not desync if one side has them. | oi | Matches current checker policy. | Implemented policy. | Keep, verify with research evidence. |
| C03 | Gameplay/moveset/custom character logic mods must match or desync. | oi | Matches current checker policy. | Implemented policy. | Keep, improve per-mod labeling clarity. |
| C04 | Custom tracks/bgm mismatch desyncs. | oi | Conflicts with current checker policy (audio currently treated client-side safe). | Contradiction. | Research and decide final policy. |
| C05 | "wifi-unsafe mods" == desync-causing mods. | oi | Aligned in tool semantics (`desync_vulnerable`/`unknown_needs_review` for unsafe content). | Partially aligned (term is community shorthand; behavior is rule-driven). | Keep terminology mapping in guide text. |
| C06 | Different emulators can still connect. | oi | Now treated as incompatible by default in compatibility checks when emulator names differ. | Contradiction with locked policy unless specific pair/build is validated. | Build explicit tested emulator-pair matrix. |
| C07 | Public vs Unlisted room: public appears in browser, unlisted hidden. | oi | Aligned with locked evidence and guidance. | Verified by source-backed review. | Add concise wording in networking guide text. |
| C08 | "Public room in screenshot" is still host port-forward flow, not relay server. | oi | Aligned with locked evidence: listing flag controls discovery, room host endpoint handles play path. | Verified by source-backed review. | Keep clarified terminology in docs/UI copy. |
| C09 | Joining a middleman public server adds extra ping. | oi | Conditionally true by route/server location, not by listing flag alone. | Verified as conditional statement. | Keep path-based latency explanation in guide text. |

## Preliminary Assessment - "Part 2" Networking Discussion

Updated: 2026-02-26

1. "Different emulators can still connect" is currently treated as **untrusted**.
   - Evidence conflict:
     - yuzu LDN announcement explicitly says multiplayer between yuzu and other emulators is not supported.
     - current app docs/code assume separate emulator networks.
   - Status: `[!]` needs targeted verification for Eden-to-non-Eden/fork interoperability.

2. Public vs Unlisted behavior appears consistent with `oi` on visibility semantics.
   - Eden host-room code path indicates Public triggers room announcement to a public lobby, and Unlisted is the non-public alternative.
   - Status: `[x]` preliminarily consistent for listing/visibility.

3. "Public room = always extra ping due to middleman" is **not yet proven as a universal rule**.
   - Current evidence suggests visibility/lobby announcement is separate from gameplay compatibility checks.
   - Latency impact likely depends on actual packet path (direct host route vs proxy/relay fallback), NAT/UPnP, and region.
   - Status: `[!]` needs source-backed network-path confirmation.

4. Same game version requirement is strongly indicated by emulator-side networking changes.
   - Eden commit history references multiplayer connection errors from different game versions.
   - Status: `[x]` likely true and should be enforced in compatibility guidance.

## Clarified Answer - Screenshot Room Flow (Create Room / Public / Unlisted)

Updated: 2026-02-26

### What the screenshot action does
- The `Create Room` dialog starts a room server on the host machine (`Host Room`).
- `Public` vs `Unlisted` controls public-lobby announcement/visibility, not whether the room exists.
- If `Public` is selected, the client attempts to register/announce to public lobby web service.
- If `Unlisted` is selected, no public lobby publication is attempted.

### Data path implications
- Players connect to the host room endpoint (host IP + port) when joining from lobby entries.
- Public lobby provides discovery/metadata; gameplay packets are handled by the room server.
- Therefore, switching only `Unlisted -> Public` should not inherently add a gameplay relay hop.

### Where extra latency can appear
- If you and your opponent play through a third-party dedicated room server that is geographically far,
  your packets can take longer routes through that room server.
- If one player hosts locally (their own machine), the route is usually shortest relative to that host's location.
- Listing the room publicly by itself is not the same as adding a separate relay for gameplay.

### Confidence
- `[x]` High confidence on Public/Unlisted = lobby publication semantics.
- `[~]` Medium confidence on "no extra ping from Public toggle alone" pending current-version live packet capture.
- `[ ]` Planned: verify on current Eden build with controlled RTT tests (public vs unlisted on same host/port).

## Final Evidence Table (Locked For Implementation)

Locked on: 2026-02-26  
Scope: network behavior + cross-emulator compatibility + desync-safe/desync-vulnerable classification for mods/plugins.

### 1) Public/Unlisted Latency Behavior

| Topic | Evidence | Decision | Confidence | Implementation Impact |
|---|---|---|---|---|
| Public vs Unlisted in host dialog | Eden host-room flow conditionally registers room metadata when announce flag is set (`announce_multiplayer_room`) and uses room web service registration. | Treat Public/Unlisted as discovery/listing visibility state, not a separate gameplay mode. | High | UI/docs should explain this as listing scope. |
| How joining works from browser | Eden multiplayer state opens selected room and connects using room host IP + port from room metadata. | Joining public-browser rooms still targets the room endpoint provided by host/server metadata. | High | Networking docs should state "browser is discovery + metadata". |
| Packet path in room | Eden room server forwards wifi packets to other members in room. yuzu multiplayer docs describe room as server used by clients to exchange data. | Room server is in packet path during room play; route quality depends on where room server lives. | High | Add latency guidance tied to server location. |
| Does Public toggle alone add ping? | No source indicates toggling listing alone inserts an extra gameplay relay layer; it changes discoverability/registration. | Do **not** claim Public always adds ping by itself. | Medium | Phrase as conditional: latency changes come from actual host/server route, not listing flag alone. |
| Why middleman can increase ping | switch-lan-play architecture explicitly shows clients traversing a shared server path over UDP. | Extra hop/longer geographic path can increase RTT. | High | Add "path model" explainer in Online Guide docs. |

### 2) Cross-Emulator Compatibility

| Topic | Evidence | Decision | Confidence | Implementation Impact |
|---|---|---|---|---|
| yuzu LDN cross-emulator support | yuzu LDN announcement states Local Wireless is supported only between yuzu instances and not between yuzu and other emulators. | Default policy: cross-emulator compatibility is **not guaranteed** and should be treated incompatible unless proven for a specific pair/build. | High | Make emulator mismatch blocking by default (not warning-only). |
| Same game version/update | yuzu progress report notes most games require players on same update version; room UI surfaces game version of peers. Eden commit history references fixes around joining with different game versions. | Treat game version/update mismatch as high-risk incompatibility. | High | Add game version field to compatibility code and enforce check. |
| Fork/family compatibility (Eden/yuzu descendants) | Evidence suggests common ancestry/protocol reuse but no universal guarantee matrix. | Allow "compatible fork" only if explicitly validated by source-backed matrix. | Medium | Maintain emulator-pair compatibility matrix in app docs, not assumptions. |

### 3) Desync-Safe vs Desync-Vulnerable Mod Categories

| Category | Evidence | Decision | Confidence | Implementation Impact |
|---|---|---|---|---|
| Pure visual/UI replacement (skins, portraits, textures, UI assets) | Training Modpack FAQ explains online safety as tied to whether gameplay-relevant transmitted data changes; community Wi-Fi-safe labeling commonly used for cosmetic mods. | Classify as `safe_client_only` by default. | Medium | Mark as safe unless conflicting gameplay indicators are present. |
| Gameplay logic changes (fighter params, scripts, stage collision/layout, ExeFS gameplay patches) | Skyline describes runtime hooking/code patching environment; Smashline explicitly targets code mods with hook plugin dependency. | Classify as `desync_vulnerable` and require both players to match. | High | Mandatory match in compatibility checks + mod badges. |
| Audio/music/BGM-only mods | Evidence is mixed: many communities treat as Wi-Fi-safe, but direct official emulator/game docs do not provide a definitive blanket rule for all BGM setups. | Temporarily classify as `safe_client_only` with caution note and optional strict mode. | Medium-Low | Add "Strict Audio Sync" toggle for users/events that require conservative matching. |
| Unknown file types / mixed-content mods | Deterministic safety cannot be guaranteed without file-level classification. | Classify as `unknown_needs_review` (conservative warning). | High | Badge and explanation panel must show exact triggering files. |

### 4) Plugins vs Mods (User Question)

Question: "Is desync risk mostly mods and not plugins?"  
Locked answer: **No. Plugins can be just as desync-relevant as mods depending on behavior.**

| Plugin Type | Evidence | Decision | Confidence | Implementation Impact |
|---|---|---|---|---|
| Framework/loader plugins | ARCropolis is a mod/plugin framework; API exists for plugin developers. | Loader/framework plugins are not automatically desync-causing by themselves. | Medium | Keep allowlist/known-safe handling but do not blanket-trust unknowns. |
| Runtime hook/code-mod plugins | Skyline is for runtime hooking/code patching; Smashline is explicitly for code mods and uses hook plugins. | Treat gameplay hook plugins as `desync_vulnerable` by default. | High | Include plugin fingerprint + per-plugin risk badges. |
| Scope-limited plugins (example: training-mode only behavior) | Training Modpack FAQ claims online-safe behavior because feature scope does not affect transmitted online data. | Scope-limited plugins can be safe; safety must be behavior-based, not file-extension-based alone. | Medium | Add plugin rule metadata and evidence/reason output in checker UI. |

## Locked Policy Decisions (v1)

1. Emulator mismatch result severity: **incompatible** by default.
2. Game update/version mismatch: **incompatible** by default.
3. Public vs Unlisted: treat as **listing visibility**, not automatic latency mode change.
4. Latency messaging: explain route-based impact (host/server location and hops), not just room visibility.
5. Mods and plugins both participate in desync risk classification.
6. Unknown/unclassified content defaults to conservative warning (`unknown_needs_review`), not silent pass.
7. Audio/BGM policy starts as safe-with-caution + optional strict mode until stronger evidence is collected.

## Additional Work Added From This Research

- `[ ]` Build emulator pair matrix with explicit tested outcomes:
  - Eden<->Eden
  - Eden<->yuzu-family forks
  - Eden<->Ryujinx
- `[x]` Add optional "Tournament Strict Mode":
  - enforce emulator + game version exactness
  - optionally enforce audio/BGM parity
- `[x]` Add plugin risk reasoning output parallel to mod reasoning output.
- `[x]` Add "evidence URL" field to internal rules for auditability.

## Primary Sources Used For Locked Table

- yuzu multiplayer guide: https://yuzu-mirror.github.io/help/feature/multiplayer/
- yuzu game modding guide: https://yuzu-mirror.github.io/help/feature/game-modding/
- yuzu LDN announcement: https://yuzu-mirror.github.io/entry/ldn-is-here/
- yuzu progress report (Sep 2022): https://yuzu-mirror.github.io/entry/yuzu-progress-report-sep-2022/
- Eden host room source (`announce_multiplayer_room` flow): https://git.eden-emu.dev/eden-emu/eden/src/commit/347348e4f4f31f3ed83cc65ca120a3be5f3eb45d/src/yuzu/multiplayer/host_room.cpp
- Eden room join path (room metadata -> connect ip/port): https://git.eden-emu.dev/eden-emu/eden/src/commit/60f46f599f8cd0f4eb72db8da8f7c7a430f7e0b6/src/yuzu/multiplayer/multiplayer_state.cpp
- Eden room packet forwarding logic: https://git.eden-emu.dev/eden-emu/eden/src/commit/347348e4f4f31f3ed83cc65ca120a3be5f3eb45d/src/network/room.cpp
- Eden commit note on game version room-join behavior: https://git.eden-emu.dev/eden-emu/eden/commit/839e1faf491776f4e2348c46773c248644e260ba?files=src%2Fnetwork
- ldn_mitm README: https://github.com/spacemeowx2/ldn_mitm
- switch-lan-play README (server path diagram): https://github.com/spacemeowx2/switch-lan-play
- Skyline README (runtime hooking/code patching): https://github.com/skyline-dev/skyline
- ARCropolis README: https://github.com/Raytwo/ARCropolis
- Smashline README: https://github.com/blu-dev/smashline
- UltimateTrainingModpack README/FAQ: https://github.com/jugeeya/UltimateTrainingModpack

Note (2026-02-26 verification pass): Eden source-host URLs above returned HTTP 403 from this runner. Locked conclusions were kept only where corroborated by currently reachable primary sources.

## Execution Quality Commitments

Added per user request (2026-02-26):
- `[x]` Maintain this tracker as the canonical, continuously updated task ledger.
- `[x]` Record every new claim/update before implementation changes.
- `[x]` Research-first workflow for policy decisions (with primary-source citations).
- `[x]` No implementation phase marked complete without tests and tracker updates.
- `[x]` Explicitly call out uncertainty instead of assuming behavior.

## Codebase Findings (updated 2026-02-26)

### Implemented now
- Compatibility fingerprint generation/comparison exists:
  - `src/core/compat_checker.py`
  - `src/ui/pages/online_compat_page.py`
- Online guide page already explains gameplay vs client-side categories.
- Emulator migration page already states separate emulator networks and includes migration tooling.

### Known gaps and risks
1. Emulator-pair compatibility matrix is not yet validated end-to-end (Eden<->Ryujinx, Eden<->forks, etc.).
   - Impact: policy is conservative by default; exceptions are not auto-whitelisted yet.

2. Audio/BGM strict policy remains unresolved.
   - Strict-audio classification is implemented and exposed in the Online Compatibility UI, but final default policy confidence is still medium-low.
   - Impact: policy remains configurable, but source confidence for universal audio parity requirements is still not locked as high.

3. Emulator/game version metadata is currently manual input.
   - Impact: checks are now enforceable, but accuracy depends on users entering correct build/update values.
   - Mitigation implemented: format validation + game-version normalization in Settings.

## Work Backlog

## Phase 0 - Tracking
- `[x]` Create this tracker file.
- `[x]` Record all current conversation updates.
- `[x]` Keep this file updated after each implementation step.

## Phase 1 - Research (must complete before policy lock)
- `[ ]` Build source-backed matrix for emulator cross-compatibility (Eden, Ryujinx, Yuzu-family forks). (partially complete; policy locked, matrix expansion pending)
- `[x]` Verify room topology terms:
  - public listed room
  - unlisted room
  - dedicated/public relay server
  - direct host (port-forwarded)
- `[x]` Verify whether "wifi-unsafe" is equivalent to "desync-causing" for SSBU mod categories. (mapped as near-equivalent terminology; behavior-based caveat retained)
- `[ ]` Verify custom audio/BGM desync behavior for emulator online use cases. (still mixed evidence)
- `[x]` Produce citations and final policy decisions.

## Phase 2 - Core Rule Engine (desync vulnerability detection)
- `[x]` Implement centralized desync classification module for mods/plugins.
- `[x]` Add per-mod risk level and machine-readable reasons:
  - safe_client_only
  - conditionally_shared
  - desync_vulnerable
  - unknown_needs_review
- `[x]` Classify from file tree with deterministic rule evidence per mod.
- `[x]` Add robust fallback for unknown files (conservative handling + explicit reason text).

## Phase 3 - Fingerprint/Comparison Hardening
- `[x]` Fix gameplay hash keying to avoid cross-mod path overwrite collisions.
- `[x]` Decide and implement emulator mismatch policy (warning vs incompatible).
- `[x]` Add emulator build/version fields to code format (with versioned schema migration).
- `[x]` Reconcile plugin optional/gameplay lists with known plugin catalog.

## Phase 4 - UI Integration
- `[x]` Add "Desync Vulnerable" (or equivalent) badge to each mod entry in Mods page.
- `[x]` Add details access for why a mod/plugin was flagged (context menu copy action).
- `[x]` Keep Online Guide analysis and actual checker engine fully aligned.

## Phase 5 - Tests
- `[x]` Add unit tests for file classification rules.
- `[x]` Add unit tests for plugin classification rules.
- `[x]` Add unit tests for fingerprint generation collisions and compare behavior.
- `[x]` Add schema/version tests for compatibility code encode/decode.

## Decisions Needed
- `[!]` Final policy for custom audio/BGM mismatches (safe vs desync risk).
- `[x]` Final policy for emulator mismatch result severity. (locked v1: incompatible by default)
- `[x]` Final naming for user-facing badge text. (current UI uses DESYNC/CONDITIONAL/SAFE/REVIEW)

## Next Action Queue
1. Execute and lock the emulator-pair matrix with real outcomes:
   - Template: `docs/emulator_pair_matrix.md`
   - Logging/report CLI: `python scripts/online_validation_tool.py add-matrix ...`
2. Execute controlled public vs unlisted RTT benchmark and record measured results:
   - Protocol: `docs/public_unlisted_rtt_benchmark.md`
   - Logging/report CLI: `python scripts/online_validation_tool.py add-rtt ...`
3. Revisit unresolved policy only: custom audio/BGM strictness confidence upgrade.

## Change Log
- 2026-02-26: Initial tracker created with codebase findings, conversation claims, contradictions, and phased backlog.
- 2026-02-26: Added preliminary assessment for networking "part 2" claims (cross-emulator, public/unlisted, latency path, game version implications).
- 2026-02-26: Added concrete screenshot room-flow interpretation, latency path notes, confidence levels, and execution quality commitments.
- 2026-02-26: Completed full research pass and locked final evidence tables (networking, cross-emulator compatibility, mod/plugin desync classification) with primary-source references.
- 2026-02-26: Implemented centralized desync classifier and integrated mod/plugin risk metadata + UI badges/details.
- 2026-02-26: Hardened compatibility checker (v3 schema, environment mismatch handling, duplicate-path collision fix, v2 decode compatibility).
- 2026-02-26: Added automated tests for classifier and checker (`tests/test_desync_classifier.py`, `tests/test_compat_checker.py`) and validated full suite pass.
- 2026-02-26: Updated Online Compatibility and Migration page wording to align with locked cross-emulator policy language.
- 2026-02-26: Revalidated key external sources for public/unlisted semantics, cross-emulator policy, and plugin/mod behavior references.
- 2026-02-26: Added Strict Audio Sync UI toggle persistence and host-policy-aware compatibility checking.
- 2026-02-26: Added source URLs to runtime classifier outputs (`RiskReason.evidence_url`, plugin evidence links) and surfaced them in copied risk details.
- 2026-02-26: Added execution templates for remaining empirical work (`docs/emulator_pair_matrix.md`, `docs/public_unlisted_rtt_benchmark.md`).
- 2026-02-26: Added settings-backed emulator/game version metadata fields and wired them into compatibility code generation/checking.
- 2026-02-26: Added metadata input quality controls (game-version normalization/validation + Online checker guidance when metadata is missing).
- 2026-02-26: Added `scripts/online_validation_tool.py` and JSON-backed report generation for empirical matrix/RTT runs.
- 2026-02-26: Added strict environment policy toggle and schema support (`strict_environment_match`) for host-enforced metadata parity checks.
- 2026-02-26: Added `seed-defaults` command to bootstrap canonical UNVERIFIED matrix entries.
- 2026-02-26: Added `docs/online_evidence_lock.md` with refreshed source-verification status and locked policy mapping.
- 2026-02-26: Re-rendered `docs/emulator_pair_matrix_results.md`; seeded canonical matrix rows are now visible.
- 2026-02-26: Added matrix/RTT aggregate summaries (`matrix_coverage_summary`, `rtt_mode_summary`) and CLI `next` workflow guidance for pending evidence runs.
