# Cleanup final report ? 2026-10-16

## Before cleanup

Size: 10,466,078,170 B (10.466 GB; 9.747 GiB). Files: 146,866.
Full inventory, main directories and top 50: [cleanup-before.md](cleanup-before.md).

## After cleanup

Repository working directory size: 7,203,451 B (7.203 MB; 6.870 MiB).
Files: 357, including one private ignored `.env`.

## Archived outside repo

Archive: sibling `../twa-czech-dubbing-archive/`.
Total archive size: 10,855,953,198 B (10.856 GB).
Total archive files: 148,775.
Historical files moved: 10,466,078,100 B / 146,865 files.
Destination: `cleanup-2026-10-16/workspace/`, preserving original relative paths.
Private move ledger: `cleanup-2026-10-16/move-ledger.json`; every moved root size/count verified.
New validation artifacts are stored separately in `cleanup-2026-10-16/validation/`.

## Removed temporary/cache

0 B of the original workspace permanently removed. All historical caches were archived.
Disposable mock installations created by tests were automatically removed by the tests.

## Git candidate

Candidate size: 7,203,381 B. Candidate files: 356.
Largest file: `data/commanders/hannibal/media-inventory.csv` (1,248,500 B).
Files >50 MiB: 0. Files >100 MiB: 0.
No original PACKs, full modified PACKs, original/extracted audio, banks or third-party binaries remain.
The only local non-candidate file is `.env`, protected by `.gitignore`.

### Top 20 largest candidate files

| File | Bytes |
|---|---:|
| `data/commanders/hannibal/media-inventory.csv` | 1,248,500 |
| `data/commanders/hannibal/audio-qa.json` | 390,396 |
| `data/commanders/hannibal/cleanup-audio-qa.json` | 279,371 |
| `data/commanders/hannibal/manifest.json` | 98,648 |
| `data/commanders/hannibal/voice-lines.csv` | 90,756 |
| `replacements/hannibal/wem/42766015.wem` | 31,230 |
| `replacements/hannibal/wem/34089947.wem` | 29,449 |
| `replacements/hannibal/wem/583630936.wem` | 29,016 |
| `replacements/hannibal/wem/24232323.wem` | 27,868 |
| `replacements/hannibal/wem/125895013.wem` | 27,834 |
| `replacements/hannibal/wem/353101255.wem` | 27,286 |
| `replacements/hannibal/wem/1018750797.wem` | 26,831 |
| `replacements/hannibal/wem/804596030.wem` | 26,570 |
| `replacements/hannibal/wem/1011132554.wem` | 26,536 |
| `replacements/hannibal/wem/47522607.wem` | 26,160 |
| `replacements/hannibal/wem/17388554.wem` | 26,132 |
| `replacements/hannibal/wem/345866214.wem` | 25,533 |
| `replacements/hannibal/wem/1019790500.wem` | 25,385 |
| `replacements/hannibal/wem/925898466.wem` | 25,343 |
| `replacements/hannibal/wem/257704217.wem` | 25,310 |

## Hannibal

- Replacement WEMs: 305 (4,945,700 B), all SHA-matched to final Batch 04 dataset and conversion evidence.
- Metadata spoken rows: 305; independent inventory rows: 1,127.
- Shared replacements: 0. Silent placeholders: 16 unchanged and excluded.
- Reproducible PACK build: PASS, byte-identical to Complete / Batch 04.
- Final SHA-256: `3405389faa3c5336e6635189e033e117144605356d9042a34f797b2c576df32b`.
- RSA: PASS. Changed entries: 305. Unchanged entries: 16,240. Entry count: 16,545.
- Header, dependencies, encrypted index, all offsets/order and Appendix: unchanged.
- Generic fresh PCM16 / float32 / unchanged-reference fidelity / ww2ogg validation: 305 / 305 PASS.
- New prepare + encoder probe on existing Media ID 1017480313 reproduced approved WAV and WEM bytes.
- Runtime: Batch 03 user-confirmed; Batch 04 offline validated, no new game run.

## Documentation created

- `README.md`, `AGENTS.md`, `.env.example`, `.gitignore`, `THIRD_PARTY_NOTICES.md`.
- `docs/USER_GUIDE.md`, `docs/ADDING_COMMANDER.md`, `docs/TECHNICAL_PIPELINE.md`, `docs/DEVELOPMENT.md`.
- `docs/VALIDATION.md`, `docs/ARCHIVE.md`, `docs/reproducibility.json`, `docs/repository-audit.json`.
- `cleanup-before.md`, `cleanup-after.md`; RPFM MIT notice in `third_party/`.

## Reusable tooling

- `scripts/install.ps1`, `scripts/verify.ps1`, `scripts/restore.ps1` (shared `common.ps1`).
- `python -B -m tools.mod [--commander hannibal] validate|build|verify`.
- `tools.pack.inspect`: signed inventory and read-only extraction.
- `tools.inventory.banks`, `tools.inventory.voice_map`, `tools.inventory.names`: bank graph, references, FNV/decision-tree analysis.
- `tools.wem.prepare`, `tools.wem.encode`, `tools.wem.exact_size`, `tools.wem.fingerprint`, `tools.wem.audio`, `tools.wem.validate`.
- `tools.tts.plan`: offline request planning only, no network client.
- `tools.validation.repository`: candidate, asset, size and secret audit.

## Tests

17 / 17 passed with a private canonical original, including after historical sources were moved.
Real PowerShell wrappers exercised only on disposable mock installations; dry-run, backup,
install, verify, restore and error guards passed. All PowerShell/Python syntax and local doc links passed.

## Secret scan

SECRET SCAN PASS

## Ready for Git

YES ? local candidate set is ready for review and a subsequent Git step.
No Git initialization, commit, push or upload was performed.
No ElevenLabs request or new speech generation, real-game installation write, game run or launcher run was performed.
