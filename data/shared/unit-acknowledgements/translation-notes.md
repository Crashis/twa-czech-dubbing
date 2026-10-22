# Unit acknowledgements: translation notes

## BYTE_BUDGET_COMPACT_FALLBACK (user decision 2026-10-22)

Ten reachable Media IDs could not hold the canonical Czech line in their original WEM byte budget: after the
production read, one compact re-read (`[brisk, clipped]`) and every existing encoder, band-limit and tail-margin
stage, each fitting encoding failed the >15 dB SNR / >0.95 correlation QC (777700830 did not fit at all). For exactly
these IDs the user approved a shorter Czech line; every other Media ID of the same phrase keeps the canonical text.

| English (meaning kept as reference) | Canonical Czech | Byte-budget fallback | Media IDs |
|---|---|---|---|
| Eager! (male slots) | Nedočkaví! | Jdeme! | 19968683, 267652445, 491277144, 530655529, 574187646, 776746889, 786324883, 881916246 |
| Eager! (female slot) | Nedočkavé! | Jdeme! | 777700830 |
| Ready! | Připraveni! | Hotovi! | 971454932 |

The canonical plan (`plan.staged.json`, `media-map.staged.csv`) is unchanged; the per-ID decision lives in
`byte-budget-fallbacks.csv`, and the final `voice-lines.csv` keeps both texts (`czech`, `canonical_plan_czech`) with
`translation_status` `BYTE_BUDGET_COMPACT_FALLBACK`. *Jdeme!* is gender-neutral; *Hotovi!* is the male plural, used
only in a male slot.
