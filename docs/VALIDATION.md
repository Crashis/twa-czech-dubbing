# Validation record — 2026-10-16

Cleanup/restructuring was performed offline. No ElevenLabs requests, new speech generation, game/launcher runs, real-installation writes, Git initialization, commits or uploads were performed.

## Reproduction

The new manifest-driven builder consumed the canonical original local backup and the 305 canonical WEMs. The output was created outside the game and repository, then compared directly byte by byte against the final Batch 04 Complete PACK.

| Check | Result |
|---|---|
| Original SHA-256 | `d6ee7ec4c4422276d9caba7013f46662a980955c138be13f653b58992ad876ad` |
| Output / Batch 04 SHA-256 | `3405389faa3c5336e6635189e033e117144605356d9042a34f797b2c576df32b` |
| Byte-identical to Batch 04 | PASS |
| Size | 244 019 593 B |
| Entries | 16 545 |
| Full entry byte diff | 305 changed / 16 240 unchanged |
| Unexpected payload changes | 0 |
| RSA-2048 / SHA-256 | PASS |
| Header / dependencies / encrypted index / offsets / Appendix | PASS |
| Canonical final WEM SHA vs dataset and Batch 04 conversion report | 305 / 305 PASS |
| Shared replacements | 0 |
| Silent placeholders | 16 unchanged, excluded from 305 spoken rows |

Machine-readable builder evidence: [reproducibility.json](reproducibility.json). No complete PACK is distributed here.

## Audio

All 305 canonical WEMs were freshly checked with the new generic validator against the unchanged prepared PCM references from Batch 04. Each passed structural fingerprint, PCM16 and float32 decoding, sample-count/rate checks, clipping checks, correlation >0.95, SNR >15 dB and ww2ogg reconstruction/direct-decode comparison. See `data/commanders/hannibal/cleanup-audio-qa.json`.

On Media ID 1017480313, the refactored 24→32 kHz preparation also reproduced the historical prepared WAV byte for byte using NumPy 2.5.4. A fresh local encoder-only search selected quality 4.0 and reproduced the approved exact-size WEM byte for byte (`5c5392ab6adc1e2059f0d8e4cae65a1694be4aee6f891505c0f210555609e9ad`, 17 124 B). These were offline processing checks of existing speech, not TTS requests; the canonical replacement was not changed.

Historical full QA was retained separately in `audio-qa.json`. New decoded WAVs and intermediate checks live only in the private external archive. No fresh human listening is claimed. Batch 03 runtime success is user-reported; Batch 04 has no new runtime test.

## Installation and safety regressions

17 tests passed with `TWA_TEST_BASE_PACK` pointing at a private canonical backup. All four PowerShell files passed syntax parsing. The real PowerShell install, verify and restore wrappers, including `-WhatIf` and `-DryRun`, ran successfully against throwaway mock installations with spaces in their paths. They never targeted the real game.

Tests cover canonical data and fingerprints, silent-ID rejection, changed manifest hashes, FNV/wildcard analysis, ordinary Event/ActionPlay and standalone Sound retention, JUNK preservation, secret-report redaction, complete PACK reproduction, unknown/modded-base rejection, no overwrite/in-place writes, RSA tampering, process blocking, backup integrity, missing backup, dry-run, restore and a concurrent target change before installation. Invalid inputs and races preserve the current target and original backup.

## Repository checks

`python -B -m tools.validation.repository` performs a local exact-value scan using the private `.env` without printing its values, plus common token/private-key patterns. It also rejects original/complete assets and files exceeding 100 MiB. The final result and size inventory are recorded in `cleanup-after.md` and `docs/repository-audit.json`.

The scan is evidence for the local candidate set, not a claim to recognize every possible secret format. Original source history, build tools and third-party binaries remain preserved privately outside the repository.
