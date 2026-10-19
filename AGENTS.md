# Agent instructions

## Project invariants

- Commander-only releases must never replace shared Media IDs or silent placeholders. Cross-check the independent inventory, not just the replacement manifest.
- Every WEM must be the exact original entry size. Preserve codec chunks during RIFF JUNK padding; never truncate speech or time-stretch to fit.
- Never rewrite PACK header, dependencies, encrypted index, offsets/order or Appendix. Validate RSA on input and output.
- Always build from the canonical original SHA-256. Never build a release incrementally from a modded PACK. Unknown base means STOP. The only exception is the installer's strictly additive transition from a verified known state when no original is available; its result must equal the target's validated whole-PACK SHA-256.
- Whenever a verified clean original is available (current PACK, valid backup or a byte-identical local game file), back it up and verify the copy before the first write. Never back up a modified or unknown PACK. A missing backup must not block an additive install; removal and Restore require an original source. Check game/launcher processes before backup and immediately before replacement. Never stop them automatically.
- Default work is offline. Actual game writes, game/launcher runs and paid API calls require explicit task authorization. Tests use their own mock installations.
- One TTS generation per approved performance. Regeneration needs separate authorization. Never log keys, tokens or credentials.
- Prefer manifest-driven reusable tools over commander-specific batch scripts. Preserve research knowledge before archiving working experiments.

## Repository structure

`data/commanders/<name>/`: schema-1 manifest, final voice-lines, independent media inventory and QA. `replacements/<name>/wem/`: approved Czech payloads only. `tools/`: PACK, WEM, inventory, offline TTS planning and audits. `scripts/`: Windows wrappers. `docs/`: user and development workflows. Historical assets live in a private external archive.

## Adding commander workflow

Read `docs/ADDING_COMMANDER.md` and `docs/TECHNICAL_PIPELINE.md`. Resolve DialogueEvents and ordinary Event/ActionPlay references, containers and Sounds across banks. Keep ownership, transcript and trigger confidence explicit. New data uses `<NAME>_SPECIFIC` and `safe_to_replace_for_<name>` inventory fields. The current CLI supports one commander release at a time; combining releases needs a separately validated joint manifest.

## Validation requirements

Run `python -B -m tools.mod --commander <name> validate`, relevant unit tests and `python -B -m tools.validation.repository`. For release, also use a private canonical original for full integration tests and generic build/reproduction. Verify every entry, exact changed set, zero unexpected differences, whole PACK SHA, RSA and protected bytes. Audio changes additionally need direct PCM16/float decode, unchanged-reference correlation >0.95, SNR >15 dB, no clipping, ww2ogg validation and appropriate listening/runtime review. Do not claim skipped checks or human listening as PASS.

## Secrets

`.env` stays private and ignored; `.env.example` is a placeholder only. Installer/build do not need API credentials. The audit reads local secret values without displaying them; reports may say `SECRET SCAN PASS`, never quote secrets. The PACK public verification key and format XOR constants are public format data.

## Installer and release invariants

- Never include original game assets, full PACKs, backups, secrets or development archives in releases. Use an explicit payload allowlist and scan the extracted bundle and embedded EXE archive.
- No TTS or paid API calls during installation or release build.
- Manifests drive available commanders. Overlapping Media IDs require identical replacement hashes and compatible original entry metadata; conflicts stop the build.
- Combined selections require a separately validated joint release manifest/hash. Release builds use only the canonical original; installer additive transitions must reproduce that validated hash exactly.
- Unknown game PACK hash is a hard stop. Never write to a live PACK until the complete offline candidate passes validation.
- Keep at most one verified canonical backup per game installation/profile, created before the first write whenever a clean source exists; never overwrite or reuse an invalid backup. Preserve valid backups outside the release. Check game/launcher processes before backup and immediately before atomic replacement.
- Build deterministically where possible. Pin dependencies, Python/tool versions, hash seed and timestamp; compare independent EXE builds and deterministic ZIPs. Do not claim cross-toolchain identity without evidence.
- Release tests use disposable mock game directories only. Never run or modify a real game to validate an installer without explicit task authorization.

## Git hygiene

Do not initialize Git, commit, push or upload unless requested. Keep outputs outside the repository or in ignored `work/`. Report file sizes and audit findings before publication. Keep third-party notices for reused logic; obtain tools separately.

## What must never be committed

Original/full modified PACKs, `.orig`, BNK banks, original/extracted WEMs, original localization assets, installation copies, backups, intermediate WAV/OGG/MP3, experimental encodes, model/tool caches, third-party binaries, toolchain/build trees, secrets and private logs. Final approved `replacements/<name>/wem/*.wem` are intentional Git candidates. Do not add a blanket `*.wem` ignore.
