# Cynane — poznámky k překladu

Commanderka `gre_cynane` (frakce `rom_athens`, `vo_culture_greek`, Wwise actor `Commander_Cynane` = 4288538180, DB typ `archer`). Hlasové větvení je stejné jako u mužských commanderů: rozhoduje jen `vo_actor`; ženské řecké větve (`Female_*` unit voices) jsou sdílené unit/culture sady a v bezpečné sadě nejsou. Platí jen pro 241 bezpečných commander-specific Media ID. Žádné TTS, WEM ani poslech nebyly provedeny.

## Charakter

Silná, autoritativní a bojově zkušená makedonská princezna a velitelka armády; rozhodná, disciplinovaná, bez karikatury „ženského hlasu“ a bez slangu. Hlasový profil v `tools/tts/research_plan.py` (`cynane`): běžné rozkazy a přípravné povely `FIELD_COMMAND [firm, commanding]`, frontend a citáty `AUTHORITATIVE [confident, authoritative]`, souhlas `CONFIDENT [confident]`, odmítnutí `STERN [stern]`. `eleven_v3` plán navrhuje jen u 5 výkonů s prokazatelně křičeným originálem; výchozí doporučení pro pilot je `eleven_v4`.

## Rod

Všechny sebeodkazy jsou v ženském rodě: *I am proud!* **Jsem hrdá!**, *I am disappointed!* **Jsem zklamaná!** (2 výkony), *I stand ready!* **Jsem připravena!**, *Chosen of Artemis!* **Artemidina vyvolená!**. Rodově neutrální: *Stojím při vás!*, *Musím bojovat!*, *Smrt si mě našla!*, *Ustupte se mnou!*, *Chci vidět!*. Rozkazy a oslovení jednotek zůstávají v rodě posluchačů (*muži*, *Zklamali jste mě!*). *My brother has fallen!* → **Můj bratr padl!** (Alexandr). *She can take it!* (o stroji) → **Ten to vydrží!**

## Terminologie a rozhodnutí

- Řecká šablona sdílená s Leonidem, Miltiadem a Alexandrem: *Pal! / Vypustit!*, *Krýt!*, *Svižně!*, *Poklusem!*, *Do falangy / Utvořte falangu!*, *ježci*, *dehtové jámy*, *křídlo*.
- Schopnosti: *Barrage* **Příval střel! / Ostřelujte je! / Zatemněte nebe!**, *Hunt* **Ulovte je! / Jsou to kořist! / Artemido, pomoz nám!**, *Rapid Advance* **Rychlý postup! / Bez oddechu! / Kupředu!**
- Jména: Kynané, Alexandr, Athéna, Artemida, Makedonie / Makedonci, Barkas, Miltiadés, Xanthippos, Spartakus, Vercingetorix.
- *Nock and fire!* → **Založit a pal!** (nock = založit šíp, projektová konvence).

## Přepisy

54 sporných nebo zjevně chybných ASR přepisů bylo rozhodnuto lokální evidencí (shoda modelů, alternativní analýza, forced-choice, druhý `vo_actor`, vlastní emote/chat-tag texty a řecká šablona). Nejde o lidský poslech. Příklady: *BLACK IN THE SKIES!* = *Blacken the skies!* (její battlecry emote), *THEY ALL PRAY!* = *They are prey!* (Hunt), *Tabato!* = *To battle!*, *Fail ya!* = *Failure!* (event `…_negative_failure`), *Barrows!* = *Barrage!*

Jedna položka zůstává **NEEDS_MANUAL_TRANSCRIPTION** a do plánu nevstupuje: 667922401 (dismantle artillery, všechny modely „Hot down!“). Doporučení je v `work/tts-preparation/cynane/manual-review.md`.

## Krátké povely a WEM budget

Kompaktní úpravy (jednoznačně lepší kratší znění): *Take no hits!* **Žádné zásahy!** (místo *Nenechte se zasáhnout!*), *No rest!* **Bez oddechu!** (místo *Žádný odpočinek!*), *Bombard them!* **Ostřelujte je!** (místo *Zasypte je střelami!*). Zbylé 4 HIGH (*Dost!* 5,3 kB / 0,50 s; *Vykopejte dehtové jámy!*, *Soustřeďte palbu!*, *Příval střel!*) jsou buď minimální, nebo HIGH jen poměrem délek při nízké rychlosti řeči.

## Výslovnost

[pronunciation-overrides.csv](pronunciation-overrides.csv): `PROPOSED_VERIFY_IN_PILOT` Cézara, Germanykus, Ksantypos; `FALLBACK_ONLY_IF_PILOT_PALATALIZES` Leonydas, Miltyadés, Arminyus, Artemydo/Artemydina. Vlastní jméno: canonical česká podoba je **Kynané** (řec. Κυνάνη), stejně ve všech plánech i v Hannibalově produkci (*Kynané padla!*), a nemění se. Pilotní replika 1003404855 *Cynane!* → *Kynané!* má phrase řádek `PROPOSED_VERIFY_IN_PILOT` s kandidátem B **Kínané!**, který resolver pošle v pilotu. Pilotní plán k ní přidává srovnání A **Kynané!** (canonical) a C **Kinané!** (jen TTS pravopis se stejnou českou výslovností, proti poangličtění „Kai-“). Rozhodne poslech: `REJECTED` = zůstane A, `APPROVED` = B, pro C se přepíše `tts_text_override`. Ostatní výskyty jména (Hasdrubal, Germanicus, Julius Caesar, Scipio; produkce Hannibal, Leonidas, Spartacus, Zhuge Liang) zatím žádné pravidlo nemají; rozhodnutí se do nich případně přenese až po pilotu.
