# Cloud Mod Failure Handoff

## Goal

Fix Cloud skin mods for Smash Ultimate on Yuzu so they load into actual matches instead of hanging on the black loading screen.

The user specifically wants:

- `mihawk over cloud` to work
- `Super Sonic Over Cloud` to work
- `Cloud Shadow` would be nice, but the user already said it can be sacrificed if needed

Late-session user observation that materially changes the likely failure mode:

- even default, non-custom Cloud costumes may now also hang on match load
- the user suspects one active Cloud mod is poisoning the entire fighter, not just its own costume slot

The user is frustrated because multiple prior passes fixed other mod issues but did **not** fix Cloud.

## Repo / App State

- Repo: `C:\github\ssbu-mod-manager`
- Current committed app version: `1.4.18`
- Current commit: `93dba72`
- Release: `https://github.com/rosacry/ssbu-mod-manager/releases/tag/v1.4.18`

Relevant code files:

- `C:\github\ssbu-mod-manager\src\core\content_importer.py`
- `C:\github\ssbu-mod-manager\src\core\mod_manager.py`
- `C:\github\ssbu-mod-manager\src\core\runtime_repair.py`
- `C:\github\ssbu-mod-manager\src\ui\pages\mods_page.py`
- `C:\github\ssbu-mod-manager\tests\test_content_importer.py`
- `C:\github\ssbu-mod-manager\tests\test_runtime_repair.py`

## User Environment

- Yuzu version shown in screenshots/logs: `yuzu 1734`
- Firmware: `21.0.0-5.0`
- GPU: NVIDIA
- OS: Windows 11

Critical paths:

- Live Yuzu root: `C:\Users\10ros\AppData\Roaming\yuzu`
- Live Smash mods: `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods`
- Live disabled mods: `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\disabled_mods`
- Live Skyline plugins: `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\atmosphere\contents\01006A800016E000\romfs\skyline\plugins`
- Live Yuzu custom Smash profile: `C:\Users\10ros\AppData\Roaming\yuzu\config\custom\01006A800016E000.ini`
- Live Yuzu log: `C:\Users\10ros\AppData\Roaming\yuzu\log\yuzu_log.txt`
- Downloaded source archives: `C:\Users\10ros\OneDrive\Documents\switch\new mods`

## Current Active Cloud State

At the time the main Cloud investigation started, only these Cloud mods were active:

- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\mihawk over cloud`
- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\Super Sonic Over Cloud`

At that point, Cloud-related disabled mods were:

- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\disabled_mods\Cloud Shadow`
- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\disabled_mods\Crimson Trails for Cloud`

Later, at the user's request, these Cloud-based skins were restored from `disabled_mods` back into `mods`:

- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\Cloud Shadow`
- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\Corin Wickes`
- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\crossworlds_miku`
- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\S Hawk`

`Crimson Trails for Cloud` was intentionally left disabled because the user explicitly said they do not want it if it is incompatible.

Active Skyline plugins are intentionally minimal:

- `libarcropolis.nro`
- `libone_slot_eff.nro`

No other active mod currently writes Cloud paths. This was checked by scanning the active mods folder for:

- `fighter/cloud/...`
- `effect/fighter/cloud/...`
- `sound/bank/fighter_voice/vc_cloud_*`
- `ui/replace/chara/...cloud_..`

Result: only `mihawk over cloud` and `Super Sonic Over Cloud` matched.

After the user's restore request, the active Cloud-writing mods became:

- `Cloud Shadow`
- `Corin Wickes`
- `crossworlds_miku`
- `mihawk over cloud`
- `S Hawk`
- `Super Sonic Over Cloud`

## Current Repro

Repro is still valid after the latest runtime reset:

1. Launch Smash in Yuzu.
2. Pick Cloud with `Super Sonic Over Cloud`.
3. Proceed into a match.
4. Game hangs forever on the black loading screen with the Smash logo in the lower-right.

The user also separately tested `mihawk over cloud` and reported the same infinite load behavior.

Additional user report after that:

- even default/non-custom Cloud costumes also seem to hang
- this suggests at least one active Cloud mod may be breaking Cloud globally

## What Has Already Been Fixed Successfully

These are **not** the current issue anymore:

- Sonic slot conflicts
- Sonic voice/effect slot handling
- Hyper Sonic effects not loading
- 8-player CSS portrait breakage for other characters
- broad support-pack overlap handling
- bogus Wi-Fi safety false positives
- several bad `config.json` / `config.txt` mod-manifest problems

The remaining major unresolved problem is Cloud.

## Important Proven Facts

### 1. This is not caused by a hidden active Cloud overlap in the mods folder

Scans of active mods showed only:

- `mihawk over cloud`
- `Super Sonic Over Cloud`

No third active mod is still writing Cloud files.

### 2. This is not caused by `Crimson Trails for Cloud` deleting a Cloud sword/model pack

This theory was specifically checked because the user suspected it.

What was verified:

- Saved conflict snapshot:
  `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\_import_backups\manual_repair_20260301\arcropolis_conflicts_20260301.json`
  only shows overlaps between `Crimson Trails for Cloud` and `Super Sonic Over Cloud` under:
  - `effect/fighter/cloud/ef_cloud.eff`
  - `effect/fighter/cloud/trail/tex_cloud_sword*.nutexb`

- Disabled Crimson pack is still intact:
  `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\disabled_mods\Crimson Trails for Cloud`

- The original downloaded Cloud archives were inspected with 7-Zip. Results:

  - `mihawk_over_cloud.rar`
    contains only:
    - `fighter/cloud/model/body/c00/...`
    - `ui/...`
    and does **not** contain `fighter/cloud/model/fusionsword/...`

  - `super_sonic_over_cloud_20.rar`
    contains:
    - `fighter/cloud/model/body/c00/...`
    - `effect/fighter/cloud/...`
    - `sound/bank/fighter_voice/vc_cloud_c00.nus3audio`
    - `ui/...`
    and does **not** contain `fighter/cloud/model/fusionsword/...`

  - `cloud_shadow.rar`
    is the only downloaded Cloud archive that actually contains:
    - `fighter/cloud/model/fusionsword/c03/def_cloud_004_col.nutexb`

Conclusion:

- `Crimson Trails for Cloud` did **not** remove an original sword-model pack from `mihawk` or `Super Sonic Over Cloud`
- those two source archives never shipped such files in the first place

### 3. Separate Yuzu `load/01006A800016E000` mod layering is not the cause

Checked:

- `C:\Users\10ros\AppData\Roaming\yuzu\load\01006A800016E000`

It exists, but it was effectively empty for this issue. No stale extra Smash mod payload was found there.

### 4. There are no stray `data.arc` / `.nrr` leftovers under the Yuzu path

Searches were run for:

- `data.arc`
- `*.nrr`

Nothing relevant was found under the Yuzu data root.

### 5. ARCropolis log output is not helping right now

`arcropolis/logs` is effectively empty even when its config includes a `Debug` logging level in one workspace. No useful mod-path failure log was captured there.

## Source Archive Contents

### `mihawk_over_cloud.rar`

Observed source content:

- `fighter/cloud/model/body/c00/`
  - `def_cloud_001_col.nutexb`
  - `def_cloud_002_col.nutexb`
  - `model.nuhlpb`
  - `model.numatb`
  - `model.numdlb`
  - `model.numshb`
  - `model.numshexb`
  - `model.nusktb`
- `ui/replace/chara/chara_0..6`
- archive listing did **not** show `chara_7`
- no `config.json`
- no `effect`
- no `sound`
- no `fusionsword`

Installed live copy currently has `chara_0..7`, so one of the app’s portrait-repair passes backfilled the missing `chara_7`.

### `super_sonic_over_cloud_20.rar`

Observed source content:

- `effect/fighter/cloud/ef_cloud.eff`
- `effect/fighter/cloud/trail/tex_cloud_sword*.nutexb`
- `fighter/cloud/model/body/c00/...`
- `sound/bank/fighter_voice/vc_cloud_c00.nus3audio`
- `ui/replace/chara/chara_1`
- `ui/replace/chara/chara_2`
- `ui/replace/chara/chara_3`
- `ui/replace/chara/chara_4`
- no `chara_0`, `chara_5`, `chara_6`, `chara_7` in the original archive
- no `fighter/cloud/model/fusionsword/...`

Installed live copy currently has:

- `effect/fighter/cloud/...`
- `fighter/cloud/model/body/c06/...`
- `sound/bank/fighter_voice/vc_cloud_c06.nus3audio`
- `ui/replace/chara/chara_0`
- `ui/replace/chara/chara_1`
- `ui/replace/chara/chara_2`
- `ui/replace/chara/chara_3`
- `ui/replace/chara/chara_4`
- `ui/replace/chara/chara_6`
- `ui/replace/chara/chara_7`
- still **missing `chara_5`**

Installed manifest:

- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\Super Sonic Over Cloud\config.json`

Current contents:

```json
{
    "new-dir-files": {
        "fighter/cloud/c06": [
            "effect/fighter/cloud/ef_cloud.eff",
            "effect/fighter/cloud/trail/tex_cloud_sword1.nutexb",
            "effect/fighter/cloud/trail/tex_cloud_sword1_blue.nutexb",
            "effect/fighter/cloud/trail/tex_cloud_sword1_purple.nutexb",
            "effect/fighter/cloud/trail/tex_cloud_sword1_red.nutexb",
            "effect/fighter/cloud/trail/tex_cloud_sword1_yellow.nutexb",
            "effect/fighter/cloud/trail/tex_cloud_sword2.nutexb",
            "effect/fighter/cloud/trail/tex_cloud_sword3.nutexb",
            "effect/fighter/cloud/trail/tex_cloud_sword4.nutexb"
        ]
    }
}
```

Notable detail:

- this manifest enumerates the effect files only
- it does **not** enumerate the fighter body files

### `cloud_shadow.rar`

Observed source content:

- partial `fighter/cloud/model/body/c03/...`
- one `fighter/cloud/model/fusionsword/c03/def_cloud_004_col.nutexb`
- partial UI set
- this pack was already considered suspicious/incomplete and was disabled intentionally

## Live File Content Observations

### `mihawk over cloud`

String scraping of key model files produced:

- `model.numatb` contains:
  - `def_cloud_001_col`
  - `def_cloud_002_col`
- `model.numshb` contains:
  - `H_Exo_SwordRhand`
- `model.numdlb` did not surface obvious ASCII references

### `Super Sonic Over Cloud`

String scraping of key model files produced:

- `model.numdlb` contains:
  - `bastar_sword_L_VIS_O_OBJShape`
  - `bastar_sword_R_VIS_O_OBJShape`
  - `def_cloud_004`
- `model.numatb` contains:
  - `def_cloud_001_col`
  - `def_cloud_002_col`
  - `def_cloud_003_col`
  - `def_cloud_004`
  - `def_cloud_004_col`
  - `def_cloud_004_nor`
  - `def_cloud_004_prm`
- `model.numshb` contains:
  - `bastar_sword_L_VIS_O_OBJShape`
  - `bastar_sword_R_VIS_O_OBJShape`

This is why Cloud weapon support kept looking suspicious: the body model clearly references sword-related objects and `def_cloud_004*`, but the pack still does not ship a `fusionsword` directory.

That said, this still has **not** been proven to be the full root cause.

## Current Log Evidence

Fresh post-test log:

- `C:\Users\10ros\AppData\Roaming\yuzu\log\yuzu_log.txt`

Important lines:

- repeated Vulkan/texture assertions beginning around line `3302`
- many repeated:
  - `texture format=0 srgb=false components={0 0 0 0}`
  - `Invalid MSAA mode=15`
- eventual forced termination at line `5248`:
  - `Force stopping EmuThread`

These assertions occur during the attempted match load for the Cloud pack.

This is the strongest concrete signal currently available.

It points toward a bad loaded graphics payload or malformed asset path, not just a generic ARCropolis deadlock.

## Critical New Observation About Yuzu Profile Repair

I added a Yuzu runtime repair flow in the app and also applied it live.

Backup path:

- `C:\Users\10ros\AppData\Roaming\yuzu\_ssbumm_runtime_backups\20260301_185034`

That backup contains:

- the previous Smash custom profile
- the previous Smash shader cache

However, after the user reran Yuzu and tested again, the live custom Smash profile was **not** still in the exact stable form I wrote.

Current file:

- `C:\Users\10ros\AppData\Roaming\yuzu\config\custom\01006A800016E000.ini`

Current contents now include:

- `use_asynchronous_shaders=false`
- `async_presentation=false`
- `enable_compute_pipelines=false`
- lots of `use_global=true`

This means one of these is true:

1. Yuzu rewrote the per-game profile on launch
2. another config path or Yuzu behavior overrode the intended stable values
3. the runtime repair baseline did not actually stick through a real run

This matters because the log’s `Invalid MSAA mode=15` / texture assertions are still heavily renderer-side.

## What Has Already Been Changed In Code

### Import / repair hardening

The app already contains a lot of import/repair logic added during this session, including:

- slot-aware skin import
- voice/effect/camera retargeting
- support-pack overlap pruning
- manifest synthesis / normalization
- portrait repair for missing `chara_0..4`
- partial fighter bundle quarantine
- Cloud-specific missing-weapon-support quarantine

Relevant file:

- `C:\github\ssbu-mod-manager\src\core\content_importer.py`

### Yuzu runtime repair

Added in:

- `C:\github\ssbu-mod-manager\src\core\runtime_repair.py`

This currently:

- locates Yuzu root from mods path
- backs up the Smash-specific custom INI
- rewrites a minimal per-game profile
- moves Smash shader cache out
- clears ARCropolis `conflicts.json` and `mod_cache`
- removes plugin junk like `.DS_Store`

Wired into:

- `C:\github\ssbu-mod-manager\src\core\mod_manager.py`
- `C:\github\ssbu-mod-manager\src\ui\pages\mods_page.py`

### Tests

Relevant tests added/adjusted:

- `C:\github\ssbu-mod-manager\tests\test_content_importer.py`
- `C:\github\ssbu-mod-manager\tests\test_runtime_repair.py`

Current test status when last run:

- `118 passed`

## Theories That Were Explored And Should Not Be Repeated Blindly

### Theory: Crimson Trails broke Cloud by removing sword assets

Status: disproven locally.

Reason:

- the two relevant source archives never had those sword-model assets to begin with

### Theory: hidden extra Cloud overlap from another active mod

Status: disproven locally.

Reason:

- active mods were scanned and only two active Cloud mods remained

### Theory: separate Yuzu `load/` directory is shadowing extra mods

Status: disproven locally.

Reason:

- checked and effectively empty for this issue

### Theory: it was only stale shader cache / stale per-game Yuzu profile

Status: not enough by itself.

Reason:

- cache/profile reset was applied
- `Super Sonic Over Cloud` still hangs

## Best Current Leads

These are the best remaining leads from the evidence.

### Lead 1: malformed or incompatible texture payload in the Cloud pack

Reason:

- fresh logs still show repeated:
  - `texture format=0 srgb=false components={0 0 0 0}`
  - `Invalid MSAA mode=15`
- these happen during match load for the Cloud pack
- `Super Sonic Over Cloud` carries effect and body textures that may be malformed for Yuzu

Specific suspicious files:

- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\Super Sonic Over Cloud\fighter\cloud\model\body\c06\def_cloud_004_col.nutexb`
- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\Super Sonic Over Cloud\fighter\cloud\model\body\c06\def_cloud_004_nor.nutexb`
- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\Super Sonic Over Cloud\fighter\cloud\model\body\c06\def_cloud_004_prm.nutexb`
- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\Super Sonic Over Cloud\effect\fighter\cloud\trail\tex_cloud_sword1.nutexb`

### Lead 2: Cloud pack still needs stronger weapon-support handling or a different manifest shape

Reason:

- body files clearly reference sword-related objects
- source archives still do not ship `fusionsword`
- current `config.json` only enumerates effect files, not fighter files
- this may still be a Cloud-specific ARCropolis/Yuzu expectation mismatch
- if the user's late observation is correct, the failure may be fighter-global rather than slot-local, which makes support/config poisoning a stronger candidate than a simple single-slot asset miss

### Lead 3: missing `chara_5` may still matter

Reason:

- `Super Sonic Over Cloud` still lacks `ui/replace/chara/chara_5/chara_5_cloud_06.bntx`
- earlier broad portrait repair was rolled back because generating advanced UI sizes blindly caused regressions
- it is possible `chara_5` specifically matters for an in-match/vs/load path for Cloud and should be repaired differently than the abandoned blanket `chara_5..7` synthesis

### Lead 4: Yuzu per-game profile is getting rewritten back to unsafe/problematic values

Reason:

- runtime repair wrote stable values
- after the user ran Yuzu again, the current custom INI had:
  - `use_asynchronous_shaders=false`
  - `async_presentation=false`
  - `enable_compute_pipelines=false`
- the latest failing log still showed renderer assertions

This may not be the whole cause, but it is still suspicious.

## Recommended Next Debug Steps

These are the next steps I would recommend to another model/agent.

### 1. Isolate `Super Sonic Over Cloud` down to subcomponents, not just whole-mod on/off

Make temporary variants of the installed mod and test:

- body only
- body + UI only
- body + voice only
- body + effect only
- effect only

Reason:

- current evidence suggests the failure is likely in a specific asset class, not necessarily the whole pack
- because default Cloud may also be broken, this needs to be combined with a whole-fighter isolation pass rather than only costume-slot testing

### 1a. Do a fighter-global isolation pass

Recommended sequence:

- disable all Cloud-related mods
- verify whether completely default Cloud loads into a match
- then re-enable Cloud mods one at a time:
  - `mihawk over cloud`
  - `Super Sonic Over Cloud`
  - `Cloud Shadow`
  - `Corin Wickes`
  - `crossworlds_miku`
  - `S Hawk`

Reason:

- the user's latest report implies one active Cloud mod may corrupt the fighter globally, including default costumes

### 2. Specifically test whether the effect textures are the renderer trigger

The repeated `texture format=0` / `Invalid MSAA mode=15` assertions make the effect textures a real suspect.

Start with:

- keep `fighter/cloud/model/body/c06/...`
- disable/remove only:
  - `effect/fighter/cloud/ef_cloud.eff`
  - `effect/fighter/cloud/trail/*.nutexb`

If that loads, the problem is probably in the effect payload rather than the body skin.

### 3. Specifically test whether `def_cloud_004*` body textures are the renderer trigger

Temporarily remove only:

- `def_cloud_004_col.nutexb`
- `def_cloud_004_nor.nutexb`
- `def_cloud_004_prm.nutexb`

Reason:

- those are the body textures most closely tied to the sword/object references in the model files

### 4. Recheck whether `chara_5` is required for Cloud

Do not blindly restore the old broken global `chara_5..7` cloning logic.

Instead:

- test a targeted repair for `chara_5` only on Cloud packs
- if doing so, make it explicit and narrow

### 5. Verify whether the per-game Yuzu profile is being rewritten externally

The runtime repair did not persist in practice.

Need to determine:

- whether Yuzu itself rewrote the file
- whether global settings are overriding it
- whether the app should repair the profile differently

### 6. If possible, use an external SSBU asset tool to validate the suspicious Cloud `.nutexb` files

I did not have a local tool in this repo that could properly validate or decode `.nutexb`.

This is probably the single most useful external validation step now.

## Important Communication Notes For The Next AI

- Do **not** assume the Cloud issue is already explained by missing `fusionsword`. That was a plausible theory, but it is not fully proven.
- Do **not** assume Crimson Trails removed original sword assets. That was checked and disproven.
- Do **not** assume the runtime repair solved the Yuzu side. It helped narrow things, but the profile appears to have drifted again.
- The freshest hard evidence is the renderer assertions in `yuzu_log.txt`, not ARCropolis logs.

## Most Relevant Paths To Inspect First

### Live Cloud mods

- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\mihawk over cloud`
- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\mods\Super Sonic Over Cloud`

### Disabled Cloud mods

- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\disabled_mods\Cloud Shadow`
- `C:\Users\10ros\AppData\Roaming\yuzu\sdmc\ultimate\disabled_mods\Crimson Trails for Cloud`

### Source archives

- `C:\Users\10ros\OneDrive\Documents\switch\new mods\mihawk_over_cloud.rar`
- `C:\Users\10ros\OneDrive\Documents\switch\new mods\super_sonic_over_cloud_20.rar`
- `C:\Users\10ros\OneDrive\Documents\switch\new mods\cloud_shadow.rar`

### Logs / config

- `C:\Users\10ros\AppData\Roaming\yuzu\log\yuzu_log.txt`
- `C:\Users\10ros\AppData\Roaming\yuzu\config\custom\01006A800016E000.ini`
- `C:\Users\10ros\AppData\Roaming\yuzu\_ssbumm_runtime_backups\20260301_185034`

### Repo code

- `C:\github\ssbu-mod-manager\src\core\content_importer.py`
- `C:\github\ssbu-mod-manager\src\core\runtime_repair.py`
- `C:\github\ssbu-mod-manager\tests\test_content_importer.py`
- `C:\github\ssbu-mod-manager\tests\test_runtime_repair.py`

## Bottom Line

The remaining Cloud problem is real and unresolved.

What is known with high confidence:

- only two active Cloud mods remain
- Crimson Trails is not the thing that removed some hidden original sword asset
- Yuzu still hits repeated texture/MSAA assertions during Cloud match load
- `Super Sonic Over Cloud` still hangs even after cache/profile reset
- the app has already been heavily hardened around import/manifests/support packs, so this is no longer a simple overlap/manifest mistake

If another model picks this up, the shortest path is probably:

1. validate the suspicious Cloud textures/effects as actual assets
2. split-test `Super Sonic Over Cloud` by component class
3. verify why the Yuzu per-game profile drifted back after runtime repair
