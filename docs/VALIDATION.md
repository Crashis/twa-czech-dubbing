# Validation and evidence

## Approved Hannibal data

The 305 final Czech WEMs remain unchanged. The independent 1,127-row inventory permits only 305 spoken Hannibal-specific IDs; 16 silent placeholders and 806 shared media are excluded.

| PACK property | Expected |
|---|---|
| Canonical original SHA-256 | `d6ee7ec4c4422276d9caba7013f46662a980955c138be13f653b58992ad876ad` |
| Complete Czech SHA-256 | `3405389faa3c5336e6635189e033e117144605356d9042a34f797b2c576df32b` |
| Size / entries | 244 019 593 B / 16 545 |
| Changed / unchanged | 305 / 16 240 |
| Unexpected changes | 0 |
| RSA, header, dependencies, encrypted index, offsets/order, Appendix | PASS in the retained reproduction evidence |

[reproducibility.json](reproducibility.json) records the original generic builder reproduction, including byte identity with the approved Complete reference. No complete PACK is distributed.

`data/commanders/hannibal/audio-qa.json` retains per-WEM hashes and the established generic PCM16/float32 decode, correlation >0.95, unchanged-reference SNR >15 dB, no-clipping, ww2ogg and padding evidence. Repackaging this unchanged audio requires hash/fingerprint validation; it does not imply a new audio performance or listening review.

Runtime evidence has a meaningful limit: the user confirmed the earlier Batch 03 CN-slot runtime test. The final Complete (Batch 04) data have offline validation. No new human listening or game run is claimed by an installer build. This distinction is retained here and in the manifest rather than repeated in end-user installation steps.

## Current build gates

Run the commands in [DEVELOPMENT](DEVELOPMENT.md). Without a private canonical original the PACK integration tests are explicitly skipped. A release build requires that original and enables those tests; a skipped integration suite is not release evidence.

The installer tests cover supported original, unknown hash, already installed, missing file, replacement tampering, identical/conflicting overlaps, unapproved combinations, backup creation/integrity, exact build diff and RSA, mock install/verify/restore, process changes, concurrent target changes, operation locking and failed validation preserving the target.

`tests/test_installer_gui.py` uses real Tk widget commands through the worker and backend, with a private canonical original and disposable mock games. It checks zero PACK writes and zero backend calls for checkbox changes (including rapid clicks), startup without installation, separate pending/installed state, all seven selections and startup states, H remaining at 305 until an explicit all-three Install produces 902, all removals, Verify synchronization, Restore clearing checkboxes, failure preserving the previous verified state, disabled controls during operations and unsupported folders. The frozen self-test repeats the selection, startup, upgrade, removal and no-write scenarios. Full per-entry byte comparison against the original verifies the actual changed set and protected PACK metadata.

The build report in ignored `release/` contains current test/build evidence, standalone EXE and ZIP reproduction, frozen GUI callback results, release inventory, sizes and hashes. Reports are generated per build and are not historical source files. The automated GUI smoke captures modal callbacks and simulates directory selection; it states that native-dialog visual review is separate. Real game/runtime checks remain outside this task.

Install-button regressions use actual ttk state/configuration checks for a valid backup, a missing backup, an invalid backup and a proven canonical game file. Adding dubbing is always enabled when valid; removing installed dubbing is disabled with a pending warning when no original source exists; an invalid backup disables every write; Restore Original requires an original source. Source and frozen tests explicitly check H startup disabled, toggle S enabled with zero backend calls/writes, Install producing 609, toggle Z enabled with zero calls/writes, Install producing 902, and Verify/empty-selection states returning to disabled.

Backup-independent transitions are covered at backend and GUI level. With no backup and no other original source, H → H+S (609), H → H+S+Z (902), S → H+S, Z → S+Z and H → H+Z use the additive builder, never call Restore and never create a backup from a modified PACK. Removal (for example H+S+Z → S+Z) and Restore are refused with `ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL` / `ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE` and zero PACK writes. A clean original in a fresh profile auto-creates exactly one verified canonical backup before the first write. A canonical `data/audio_en.pack` is recovered read-only as the backup source; a same-sized modified or unrelated file is never accepted. An invalid backup is never used or replaced (`INVALID_BACKUP`), an unknown PACK is never patched or backed up (`UNKNOWN_PACK`), and a failed temporary candidate leaves the game untouched (`INSTALL_VALIDATION_FAILED`). `test_transition_matrix_with_and_without_backup` runs every known current state (original and all seven selections) against every target and Restore, once with a canonical backup and once without, and checks the whole-PACK SHA-256, RSA, 16,545 entries and zero differences outside the expected payloads against the canonical original. Set `TWA_TEST_MATRIX_REPORT` to write the resulting table as JSON.

`python -B -m tools.validation.repository` checks source candidates plus tracked files, prohibited assets, sizes, local Markdown links, personal Windows profile paths, obsolete reports, common secret patterns and private `.env` values without printing them. It reports `SECRET SCAN PASS` only when those checks find no secret. No scanner claims to recognize every possible secret format.
