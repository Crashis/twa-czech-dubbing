# Technická pipeline a ověřené invarianty

Tento dokument popisuje zkoumaný Arena corpus. Nejde o univerzální parser všech Total War PACKů. Stav releasu a hashe jsou v `data/commanders/hannibal/manifest.json`; nová reprodukce v [reproducibility.json](reproducibility.json).

## Arena PACK

Podporovaný audio PACK má PFH5 magic, 48bajtovou rozšířenou hlavičku a flags `0x181`: Release type 1, XOR index `0x80`, rozšíření `0x100`. Jeho payloady nejsou PACKem šifrované ani zarovnávané na 8 B. Komprese Wwise Vorbis uvnitř WEM je jiná vrstva.

| Část | Offset | Délka v bajtech |
|---|---:|---:|
| Hlavička | 0 | 48 |
| Seznam závislostí | 48 | 0 |
| Šifrovaný file index | 48 | 495 754 |
| Payloady | 495 802 | 243 523 535 |
| Appendix | 244 019 337 | 256 |

Celkem 244 019 593 B a 16 545 položek. File entry má velikost u32 a NUL-terminated cestu, případně 4bajtový timestamp při flagu `0x40`. Chybí compression bool z jiných PFH5 variant. Offsety payloadů vyplývají ze součtu délek v pořadí indexu; nejsou uložené jako samostatné absolutní offsety každé entry.

Dekódování velikosti pro položku `i` z `N`:

```text
remaining = N - 1 - i
size = encoded_u32 XOR 0xE10B73F4 XOR ((NOT remaining) AND 0xffffffff)
path[j] = encoded_byte[j] XOR KEY[j mod 64] XOR ((NOT size) AND 0xff)
```

Indexový XOR klíč je formátová konstanta v readeru, nikoli credential. Se změnou velikosti by se změnilo kódování celé cesty včetně terminátoru i následující payload offsety.

V hlavičce je počet entries na `0x10`, index size na `0x14`, délka Appendixu na `0x24` a jeho offset na `0x28`. Neinterpretovaná rozšířená pole se zachovávají. Parser kontroluje přesné spotřebování indexu, duplicity a bezpečnost interních cest, hranice payloadů, Appendix i konec souboru. Šifrované payloady a neznámé flags odmítá.

Layout byl porovnán s [tw_pack_lib parse.rs](https://github.com/TotalWar-Modding/tw_pack_lib/blob/7a9d2264e1b4ea0f35e9332d00dd9a870abdb65d/src/parse.rs), indexový XOR s [RPFM encryption](https://github.com/Frodo45127/rpfm/blob/cbc9626d098dc645f40ba950be2d90c60ea94805/rpfm_lib/src/encryption/mod.rs). Původní workflow mělo také druhý nezávisle napsaný read-only parser. Není tvrzeno spuštění upstream Rust parserů.

## RSA a exact-size replacement

256bajtový Appendix je RSA-2048 / PKCS#1 v1.5 / SHA-256 podpis **uložených šifrovaných bytes file indexu**. Veřejný ověřovací klíč byl identifikován v lokálním `game.dll` a ověřen proti podpisům corpus. Není k dispozici privátní klíč. `data/arena-index-public-key.json` uchovává pouze veřejný klíč a provenance; DER SHA-256 se kontroluje před použitím.

Ověřovač vypočte RSA operaci a porovná celý očekávaný PKCS#1 blok včetně SHA-256 DigestInfo. Nejde o kontrolu pouhé délky podpisu. Testy odmítají pozměněný index i podpis.

Změna velikosti WEM by změnila index a zneplatnila zachovaný podpis. Stejně velký payload lze v podporované variantě nahradit bez změny indexu. Podpis nekryje samotné payloady; jejich správnost proto kontrolujeme samostatnými SHA-256 a úplným porovnáním PACKu.

Builder vždy vychází z originálu `d6ee7e…76ad`. Před zápisem ověří manifest, metadata, scope, finální WEMy a původní PACK. Zkopíruje originál a zapíše pouze povolené rozsahy. Index vůbec nesestavuje. Po zápisu ověří:

- velikost, 16 545 entries a RSA;
- přesnou shodu hlavičky, závislostí, šifrovaného indexu a Appendixu;
- stejné pořadí, cesty, velikosti a offsety všech entries;
- hash každého vloženého WEM a celého PACKu;
- úplným byte diffem přesně povolenou množinu 305 změněných položek a 16 240 nezměněných.

Protože entries přesně pokrývají payload oblast a metadata i Appendix jsou shodné, nezbývají nezvalidované mezery mimo povolené rozsahy. Finální výstup má hash `3405389f…6df32b` a byl přímo porovnán bajt po bajtu s původním Complete PACKem Batch 04.

Samostatné `verify` bez originálu identifikuje pouze známé kompletní hashe a kontroluje náhrady, RSA a strukturální hashe. Pole `counts_basis` výslovně rozlišuje tento důkaz od plného entry diffu s `--base`.

## Wwise: od události k WEM

Relevantní banky: `frontend_vo.bnk`, `battle_vo_orders.bnk`, `battle_vo_announcer.bnk`, `battle_vo_conversational.bnk`, `battle_vo_emotes.bnk` a `battle_advice.bnk`. Ve zkoumaném EN corpus mají BKHD version 126 (raw `0x8000007e`) a English(UK) Language ID 550298558. CN-named bankové sloty měly také EN obsah. Tyto hodnoty se nesmí automaticky přenášet na jiné buildy.

Řetězec je `DialogueEvent → decision-tree branch → audioNodeId → container(s) → Sound → external sourceID / Media ID → WEM`. Object/Sound ID není totéž co Media ID. Object IDs je nutné rozlišovat podle banky. Kořenový key decision tree je sentinel, nikoli první game-sync argument. Target 0 je null branch, nikoli chybějící zvuk k doplnění.

U každé větve se uchovávají všechny game-sync podmínky, skupiny, váhy a pravděpodobnosti; u kontejnerů children, playlist a vlastnosti. Pro bezpečné vlastnictví média je nutné sesbírat reference napříč všemi relevantními bankami a kontexty. Reference na Hannibala sama nestačí. Inventory rozlišuje commander-specific, faction-shared, unit-shared a global-shared.

Hannibal inventory má 1 127 médií: 305 mluvených commander-specific, 16 tichých commander-specific a 806 sdílených. Releasová allowlist obsahuje pouze oněch 305. `media-inventory.csv` zachovává identifikátory bank/events/containers/sounds, podmínky, původní hashe a reference bez původního audia.

## WEM a příprava zvuku

Ověřený formát je little-endian RIFF/WAVE, Wwise Vorbis `0xffff`, `fmt` o 66 B, mono 32 000 Hz, embedded vorb metadata, stripped setup s externími 10bitovými aoTuV 6.03 codebook IDs, mod packets s 2bajtovou délkou bez granule field. Bloky jsou 256/2048 vzorků, subtype/channel config `0x4101`. Seek delty se kontrolují proti packet boundaries a počtu vzorků. Přesný původní Wwise SDK build ani encoder quality nebyly určeny.

Pro schválené TTS 24 kHz mono PCM16 byl použit 64tapový Lanczos sinc resampler 4/3. Odstraní se jen krajní ticho při prahu −48 dBFS s rezervou 20 ms před a 40 ms za řečí. Následuje 5ms fade a případné snížení gainu na špičku −4 dBFS. Nevkládá se time-stretch ani změna výšky a řeč se nezkracuje, aby se vešla do PACKu. Tento postup uchovává `tools.wem.prepare` s volitelným NumPy.

`wav2wem` převádí připravený PCM / Ogg do kompatibilního Wwise Vorbis. Nestačí přejmenovat běžný Ogg na WEM. Encoding je hledán v omezeném rozsahu quality, každý fitting kandidát se dekóduje a srovnává se **stejným neupraveným PCM reference**. Historické řešení používalo coarse 0,25 a fine 0,025 quality kroky, při těsném neúspěchu i lokální dohledání kolem nejlepšího téměř vyhovujícího kandidáta. Nízká propust a transient tuning byly volby encoderu, nikoli změna QC reference.

Použitý oggenc (aoTuV) při quality pod 0 na 32 kHz mono přepíná Vorbis bloky z 256/2048 na 512/4096. To už není ověřený Arena formát; `tools.wem.encode.search` s `wem_format` z manifestu takového kandidáta označí `FORMAT_MISMATCH` a nepovažuje ho za fit ani PASS. Plná QC (`tools.wem.validate`) formát porovnává s originálem znovu. Originální Arena WEMy byly zjevně kódované jiným (Wwise) encoderem s nižším bitrate při blocích 256/2048, proto u velmi malých budgetů nemusí existovat platná kombinace velikosti, formátu a QC.

Měření Zhuge Lianga ukázalo, že originální hlasové WEMy jsou úzkopásmové (bez energie nad asi 8 kHz) a kódované stejnou 35-codebookovou šablonou jako projektový encoder při quality 2. Byte budget originálu tedy odpovídá úzkopásmovému a řídčeji mluvenému obsahu, ne jinému kodéru. `tools.wem.prepare.band_limit_wav` (255 tapů, Kaiser, −6 dB na cutoffu, ~70 dB útlum o 0,3 kHz výš, nulová fáze, stejná délka) a `tools.wem.recovery` tento poznatek používají jen pro jinak blokované linky a vždy s dvojím auditem vůči produkční referenci i nezměněnému TTS.

Exact-size nástroj normalizuje přípustný terminal alignment a vloží před `data` RIFF `JUNK` s nulovými bytes. Dodatečná délka musí být 0 nebo sudá a alespoň 8 B. Aktualizuje RIFF length. `fmt`, `data` a všechny původní chunk bodies musí zůstat shodné. Nepoužívá náhodné bytes za koncem RIFF ani ořezávání řeči. Lichý terminální data chunk bez padding byte je v ověřené Arena/ww2ogg variantě přípustný.

Fingerprint validuje strukturu včetně stripped setup, packetů, seek tabulky a sample count. Full QC provádí PCM16 i float32 decode, kontrolu clippingu, přesného počtu vzorků, korelaci >0,95 a SNR >15 dB vůči připravenému reference. Rekonstrukce přes ww2ogg musí po opravě Ogg page granules/CRC souhlasit s přímým dekódem do jednoho PCM16 kroku. Oprava granules nemění codec packets. Padding se navíc ověřuje shodným dekódem raw a padded WEM.

`data/commanders/hannibal/audio-qa.json` uchovává validaci všech 305 finálních WEMů: PCM16/float32, korelaci a SNR vůči nezměněné referenci, ww2ogg a důkaz zachování PCM při paddingu. Nejde o nový lidský poslech.

## Runtime: rozsah důkazů

Pro tuto instalaci a úspěšný runtime test Batch 03 je používán CN-named slot `audio_cn.pack` s EN výchozím hlasovým obsahem. První statická diagnostika slotu byla pouze silná hypotéza; následný uživatelský runtime test je pozdější důkaz funkčního postupu. Přesná VFS precedence všech duplicitních packových cest není obecně dokázána. Nelze tvrdit, že `audio_en.pack` se nikdy nenačítá nebo že každý launcher funguje stejně.

Installer proto upravuje výhradně hashově podporovaný `audio_cn.pack`. Malý unsigned override PACK, jiné PACK typy/load order a obecná možnost obcházení podpisu nejsou ověřené a nejsou součástí řešení. Finální Batch 04 má offline validaci; nový runtime test se teprve může provést po samostatném svolení.
