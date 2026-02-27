# Emulator Pair Compatibility Matrix (Evidence + Test Log)

Updated: 2026-02-26  
Purpose: lock source-backed and test-backed outcomes for cross-emulator online compatibility.

## Status Key
- `PASS` = tested and confirmed compatible for room join + gameplay
- `FAIL` = tested and confirmed incompatible
- `UNVERIFIED` = no controlled test run yet

## Test Protocol
1. Use identical game update and DLC on both sides.
2. Use identical mod/plugin set for baseline run.
3. Validate:
   - room discovery/join
   - match start success
   - 3-5 minute stable gameplay without disconnect
4. Record exact emulator name + build/version + date.

## Matrix

| Pair A | Pair B | Result | Last Tested | Build A | Build B | Notes |
|---|---|---|---|---|---|---|
| Eden | Eden | UNVERIFIED | - | - | - | Baseline expected to pass; pending controlled run. |
| Eden | Ryujinx | UNVERIFIED | - | - | - | Policy default is incompatible until validated. |
| Eden | Yuzu-family fork | UNVERIFIED | - | - | - | Validate per specific fork + build pair. |
| Ryujinx | Ryujinx | UNVERIFIED | - | - | - | Add same-version baseline test. |
| Yuzu-family fork | Same fork | UNVERIFIED | - | - | - | Add same-fork baseline test. |

## Evidence Notes
- yuzu LDN announcement states no general cross-emulator support guarantee:
  - https://yuzu-mirror.github.io/entry/ldn-is-here/
- yuzu multiplayer and version constraints:
  - https://yuzu-mirror.github.io/help/feature/multiplayer/
  - https://yuzu-mirror.github.io/entry/yuzu-progress-report-sep-2022/

Use this file to promote `UNVERIFIED` entries to `PASS`/`FAIL` with concrete builds and dates.

## Optional Logging CLI

You can record runs and regenerate machine-readable reports with:

```powershell
python scripts/online_validation_tool.py seed-defaults
python scripts/online_validation_tool.py next
python scripts/online_validation_tool.py add-matrix --pair-a Eden --pair-b Ryujinx --result FAIL --build-a v0.0.4-rc3 --build-b 1.2.3 --notes "join failed"
python scripts/online_validation_tool.py render
python scripts/online_validation_tool.py status
```

Generated report path:
- `docs/emulator_pair_matrix_results.md`
