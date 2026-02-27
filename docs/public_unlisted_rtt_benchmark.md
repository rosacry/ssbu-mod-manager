# Public vs Unlisted RTT Benchmark Protocol

Updated: 2026-02-26  
Purpose: verify whether room visibility mode (`Public` vs `Unlisted`) changes latency when host and port are identical.

## Hypothesis
- `Public` vs `Unlisted` changes room discoverability, not gameplay packet topology by itself.
- Any RTT change should come from route/server placement differences, not the visibility flag alone.

## Controlled Setup
1. Same host machine, same room port, same internet route.
2. Same client peer location and network path.
3. Run two sessions back-to-back:
   - Session A: `Unlisted`
   - Session B: `Public`
4. Keep all other variables fixed:
   - emulator build/version
   - game update
   - mods/plugins

## Measurements
- Join success/failure
- Match start success/failure
- In-match average RTT or equivalent latency indicator (if available)
- Packet loss/disconnect events
- Subjective jitter notes

## Suggested Trial Count
- Minimum 5 runs per mode.
- Alternate order (`Public`, `Unlisted`, `Public`, ...) to reduce time-of-day routing bias.

## Result Table

| Date | Host Build | Client Build | Mode | Runs | Avg RTT | Disconnects | Notes |
|---|---|---|---|---|---|---|---|
| - | - | - | Unlisted | - | - | - | - |
| - | - | - | Public | - | - | - | - |

## Interpretation Guide
- If RTT deltas are within normal variance, treat `Public`/`Unlisted` as visibility-only.
- If `Public` is consistently higher under controlled conditions, capture packet-path evidence before policy changes.

## Source Context
- Eden host-room announcement/join flow and room forwarding logic:
  - https://git.eden-emu.dev/eden-emu/eden/src/commit/347348e4f4f31f3ed83cc65ca120a3be5f3eb45d/src/yuzu/multiplayer/host_room.cpp
  - https://git.eden-emu.dev/eden-emu/eden/src/commit/60f46f599f8cd0f4eb72db8da8f7c7a430f7e0b6/src/yuzu/multiplayer/multiplayer_state.cpp
  - https://git.eden-emu.dev/eden-emu/eden/src/commit/347348e4f4f31f3ed83cc65ca120a3be5f3eb45d/src/network/room.cpp

## Optional Logging CLI

You can record runs and regenerate machine-readable reports with:

```powershell
python scripts/online_validation_tool.py next
python scripts/online_validation_tool.py add-rtt --mode Public --runs 5 --avg-rtt-ms 42.5 --disconnects 0 --host-build v0.0.4-rc3 --client-build v0.0.4-rc3 --notes "stable"
python scripts/online_validation_tool.py render
python scripts/online_validation_tool.py status
```

Generated report path:
- `docs/public_unlisted_rtt_results.md`
