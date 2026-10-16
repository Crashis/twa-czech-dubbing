# Private cleanup archive

Historical files were moved to the sibling directory `twa-czech-dubbing-archive`, under `cleanup-2026-10-16/workspace/`. Their original relative paths are preserved, including `backup/`, `analysis/`, `hannibal/production/batch-01` through `batch-04`, old `scripts/` and old `tools/`.

`cleanup-2026-10-16/move-ledger.json` records each moved root with its byte size and file count. `validation/` separately contains the rebuilt Complete PACK, fresh local decode checks and encoder/resampler probes. These are private artifacts and must never be copied wholesale into Git candidates.

Nothing from the original workspace was permanently deleted during this cleanup. Even cache and toolchain directories were archived to avoid losing uncertain historical data. Temporary mock installations created by the new tests were disposable generated files and were removed by those tests.

The canonical original for subsequent local reproduction is under `workspace/backup/cn-ingame-test/audio_cn.pack`; verify SHA-256 against the manifest before using it. The historical final comparison target is `workspace/hannibal/production/batch-04/audio_cn_hannibal_complete.pack`. Old scripts retain their original absolute paths and should be treated as research evidence until adapted, not as current entrypoints.

The live project contains the final WEMs, metadata, compact QA evidence, reusable tools and documentation needed without this archive. A new user supplies their own supported original from their own installation.
