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

The build report in ignored `release/` contains current test/build evidence, standalone EXE and ZIP reproduction, frozen GUI callback results, release inventory, sizes and hashes. Reports are generated per build and are not historical source files. The automated GUI smoke captures modal callbacks and simulates directory selection; it states that native-dialog visual review is separate. Real game/runtime checks remain outside this task.

`python -B -m tools.validation.repository` checks source candidates plus tracked files, prohibited assets, sizes, local Markdown links, personal Windows profile paths, obsolete reports, common secret patterns and private `.env` values without printing them. It reports `SECRET SCAN PASS` only when those checks find no secret. No scanner claims to recognize every possible secret format.
