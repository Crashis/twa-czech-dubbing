# Cross-commander voice inventory

Counts compare primary voice inventories, including relevant shared unit sets. Generic advisor/tutorial references are separate.

| Pair | Shared Media IDs | Shared IDs safe for either side | Status | IDs |
|---|---:|---:|---|---|
| spartacus / germanicus | 229 | 0 | SHARED_NOT_SAFE | 229 IDs; every row is listed in the CSV |
| spartacus / hannibal | 5 | 0 | SHARED_NOT_SAFE | 157787261, 200927609, 488303164, 614870085, 747064452 |
| spartacus / leonidas | 0 | 0 | NO_OVERLAP | none |
| spartacus / scipio-africanus | 229 | 0 | SHARED_NOT_SAFE | 229 IDs; every row is listed in the CSV |
| germanicus / hannibal | 5 | 0 | SHARED_NOT_SAFE | 157787261, 200927609, 488303164, 614870085, 747064452 |
| germanicus / leonidas | 0 | 0 | NO_OVERLAP | none |
| germanicus / scipio-africanus | 1625 | 0 | SHARED_NOT_SAFE | 1625 IDs; every row is listed in the CSV |

Safe-candidate Media ID conflicts: **0**. This does not create or approve a joint release manifest.

Media IDs classified differently by two inventories: **0**.

| Explicit speaker with shared ownership | Media ID | Other owners |
|---|---|---|
| spartacus | 157787261 | commander:Commander_Hannibal; commander:Commander_Massinissa; commander:Commander_Xanthippus; unit:0:Male_1; unit:3254117665:Male_1; wildcard:actor |
| spartacus | 200927609 | commander:Commander_Hannibal; commander:Commander_Massinissa; commander:Commander_Xanthippus; unit:0:Male_1; unit:3254117665:Male_1; wildcard:actor |
| spartacus | 488303164 | commander:Commander_Hannibal; commander:Commander_Massinissa; commander:Commander_Xanthippus; unit:0:Male_1; unit:3254117665:Male_1; wildcard:actor |
| spartacus | 614870085 | commander:Commander_Hannibal; commander:Commander_Massinissa; commander:Commander_Xanthippus; unit:0:Male_1; unit:3254117665:Male_1; wildcard:actor |
| spartacus | 747064452 | commander:Commander_Hannibal; commander:Commander_Massinissa; commander:Commander_Xanthippus; unit:0:Male_1; unit:3254117665:Male_1; wildcard:actor |

Overlaps with the reference inventories:

- spartacus / hannibal: 5 IDs; classifications: GLOBAL_SHARED; reference safe/replacement IDs affected: 0.
- spartacus / leonidas: 0 IDs; classifications: none; reference safe/replacement IDs affected: 0.
- spartacus / scipio-africanus: 229 IDs; classifications: GLOBAL_SHARED; reference safe/replacement IDs affected: 0.
- germanicus / hannibal: 5 IDs; classifications: GLOBAL_SHARED; reference safe/replacement IDs affected: 0.
- germanicus / leonidas: 0 IDs; classifications: none; reference safe/replacement IDs affected: 0.
- germanicus / scipio-africanus: 1625 IDs; classifications: CULTURE_SHARED, GLOBAL_SHARED, UNIT_TYPE_SHARED; reference safe/replacement IDs affected: 0.

Exact recording duplicate groups spanning primary commander inventories with different Media IDs: **1**.

Primary-to-generic-advisor duplicate groups: **8**. Advisor copies are catalogued alongside both research inventories but are not either commander speaking. The duplicate CSV explicitly distinguishes primary_inventories from advisor_reference_inventories.

Recording identity does not imply Media ID identity. Ownership and recording deduplication are separate.

Culture and unit sets can contain wider fallback reuse. Tone of voice and culture names alone never establish commander ownership.

- spartacus: 215 file-backed advisor/tutorial reference IDs, excluded from primary voice counts. External-source cookies are not missing WEMs.
- germanicus: 210 file-backed advisor/tutorial reference IDs, excluded from primary voice counts. External-source cookies are not missing WEMs.
