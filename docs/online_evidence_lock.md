# SSBU Online Evidence Lock

Locked on: 2026-02-26  
Owner: chrig + Codex  
Purpose: audit-ready evidence table for online behavior and desync policy decisions.

## Scope
- Public/Unlisted latency behavior
- Cross-emulator compatibility
- Desync-safe vs desync-vulnerable mod/plugin categories

## Source Verification Status

| Source | Status | Notes |
|---|---|---|
| yuzu Multiplayer Guide | Verified | Confirms room-based server/client model, port-forward guidance, and public/private room behavior. |
| yuzu LDN release article | Verified | States yuzu LDN support is yuzu-to-yuzu only in that stack. |
| yuzu Progress Report (Sep 2022) | Verified | States most games only work when all players use the same game update version. |
| yuzu Game Modding Guide | Verified | Distinguishes ExeFS logic patches from RomFS asset replacements. |
| Skyline README | Verified | Explicitly describes runtime hooking and code patching plugin environment. |
| Smashline README | Verified | Identifies Smashline as code-mod tooling with required hook plugin dependency. |
| ARCropolis README | Verified | Describes framework/manager role for mods/plugins. |
| Ultimate Training Modpack README/FAQ | Verified | Declares training-mode-scoped behavior and online safety claim for transmitted data scope. |
| switch-lan-play README | Verified | Documents relay-server architecture path for LAN-over-internet packets. |
| ldn_mitm README | Verified | Describes UDP-based local-wireless emulation over network stack. |
| Eden source URLs in existing tracker | Partially verified | URLs are recorded but returned HTTP 403 from this environment on 2026-02-26; conclusions kept only where corroborated by other verified sources. |

## Locked Decisions (Implementation Policy)

### 1) Public/Unlisted and Latency
- `Public` and `Unlisted` are listing/discovery states, not separate gameplay sync engines.
- Public-room browsing and room announcement use web API metadata flow; gameplay data still traverses the room path.
- Extra ping is path-dependent (host/server location and routing), not caused by the `Public` toggle alone.

Confidence: High for semantics, Medium-High for latency interpretation without new packet capture.

### 2) Cross-Emulator Compatibility
- Default policy remains conservative: emulator mismatch is incompatible unless a specific pair/build has empirical PASS evidence.
- yuzu-sourced evidence is explicit that their LDN stack does not guarantee yuzu-to-other-emulator interoperability.
- Same game update/version remains a high-priority compatibility requirement.

Confidence: High for default-conservative policy, Medium for Eden-specific pair exceptions pending matrix runs.

### 3) Mod Categories and Desync Risk
- ExeFS logic/code patches: treat as `desync_vulnerable`.
- Gameplay parameter/script/stage logic files: treat as `desync_vulnerable` or `conditionally_shared` per rule.
- RomFS visual/UI/audio/text replacements: default `safe_client_only` unless strict mode elevates audio handling.
- Unknown file types/locations: `unknown_needs_review`.

Confidence: High for ExeFS/gameplay logic, Medium for universal audio safety.

### 4) Plugin Risk (explicitly researched)
- Plugin binaries are not automatically safe; behavior determines risk.
- Runtime hook/code-mod plugins are `desync_vulnerable` by default.
- Framework/utility plugins can be `safe_client_only` when behavior is non-gameplay.
- Scope-limited training-only behavior can be safe in principle, but this remains a policy claim with medium confidence.

Confidence: High that plugins can be desync-relevant; Medium for per-plugin safety unless empirically validated.

## Codebase Mapping
- Rule engine: `src/core/desync_classifier.py`
- Fingerprint/compare policy: `src/core/compat_checker.py`
- Mod badges/details UI: `src/ui/pages/mods_page.py`
- Plugin badges/details UI: `src/ui/pages/plugins_page.py`
- Online code generate/check UI policy toggles: `src/ui/pages/online_compat_page.py`
- Persistent metadata/policy settings: `src/models/settings.py`, `src/config.py`, `src/ui/pages/settings_page.py`

## Open Evidence Tasks
- Run controlled `Public` vs `Unlisted` RTT trials and log results in `docs/public_unlisted_rtt_results.md`.
- Run emulator pair matrix tests and promote seeded `UNVERIFIED` rows to `PASS`/`FAIL` in `docs/emulator_pair_matrix_results.md`.
- Increase confidence for audio/BGM policy with targeted SSBU emulator tests.

## Sources
- https://yuzu-mirror.github.io/help/feature/multiplayer/
- https://yuzu-mirror.github.io/entry/ldn-is-here/
- https://yuzu-mirror.github.io/entry/yuzu-progress-report-sep-2022/
- https://yuzu-mirror.github.io/help/feature/game-modding/
- https://github.com/skyline-dev/skyline
- https://github.com/blu-dev/smashline
- https://github.com/Raytwo/ARCropolis
- https://github.com/jugeeya/UltimateTrainingModpack
- https://github.com/spacemeowx2/ldn_mitm
- https://github.com/spacemeowx2/switch-lan-play
