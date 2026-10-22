# Boudica — poznámky k překladu

Commanderka `bar_boudica` (frakce `rom_arverni`, `vo_culture_barbarian`, Wwise actor `Commander_Boudica` = 3051967427; řádek `arena_commanders_tables` nese i samostatnou hodnotu `bar_boudicca`). Platí jen pro 293 bezpečných commander-specific Media ID (256 budoucích výkonů). Hlasové větvení je stejné jako u mužských commanderů: rozhoduje jen `vo_actor`. Ženské barbarské větve (`Female_*` unit voices, culture sady a unit acknowledgements) jsou sdílené a v bezpečné sadě nejsou; žádný ženský unit hlas nebyl zaměněn za Boudicu. Žádné TTS, WEM ani poslech nebyly provedeny.

Pět Media ID ability stavu 3233209236 (35020084, 39879063, 157192972, 190412426, 232920240) je v Wwise zapojeno pod klíčem Boudicy i Vercingetoriga. Jsou `GLOBAL_SHARED` a pro oba nebezpečné.

## Charakter

Autoritativní, bojovná a vzdorovitá královna Icenů, která burcuje svůj lid (*Who's with me?!*, *I fight to defend the weak!*, *We will never bow to tyrants!*). Bez stereotypního nebo afektovaného „ženského“ podání. Profil `boudica`: frontend `DEFIANT [defiant, authoritative]`, citáty `DEFIANT [defiant, proud]`, přípravné/rally povely `ENCOURAGING [encouraging, commanding]`, rozkazy `FIELD_COMMAND [firm, commanding]`, odmítnutí `STERN [stern]`. `eleven_v3` jen u 12 výkonů s prokazatelně křičeným originálem.

## Rod (Gender-sensitive translations checked: PASS)

Všechny repliky, kde Boudica mluví o sobě, jsou buď v ženském rodě: **Andrastina vyvolená!**, **Boudica! Královna bojovnice!**, **Pravá královna Icenů!**; nebo rodově neutrální: *Nedám se porazit!*, *Odcházím ke svým předkům!*, *Pomstím se!*, *Budu bojovat do posledního dechu!*, *Bojuji na obranu slabých!* (záměrně bez příčestí „abych chránila“), *Můj lid mě potřebuje!*, *Vítězství je mé!*, *Má pomsta je téměř dokonána!*. Rozkazy a oslovení se řídí adresátem (*Buďte silní!*, *Nebojte se, muži!*, *Zklamali jste mě!*, *Vstaňte, soukmenovci!*), první osoba množného čísla za celé vojsko je v obvyklém mužském životném tvaru (*Zabili jsme…*, *Vedli jsme si dobře!*).

## Terminologie a rozhodnutí

- Keltské reálie: **Icenové / Icenů**, bohyně **Andrasta** (*Andrastina vyvolená!*), **Epona** (*Epona nám přeje!*), battlecry **Icenové!** (lokalizovaný text emotu *Iceni!*), *kinsmen* = **soukmenovci**.
- Obecný rozkazový skript je stejný jako u Xerxe, Kýra a Ambiorixe; terminologie odpovídá projektu.
- Schopnosti: *Fury* **Pusťte jim krev! / Rozsekejte je! / Zabijte je všechny!**, *Rebellion* **Přidejte se ke mně! / Bojujte za svobodu! / Kdo je se mnou?!**. Třetí DB schopnost *Vanguard* nemá pod jejím klíčem vlastní hlasovou větev.
- *Germanicus, the Roman Beast* → **Germanicus, římská bestie, je mrtev!** (shoda rodu u přísudku).

## Přepisy

72 sporných nebo zjevně chybných ASR přepisů bylo rozhodnuto lokální evidencí (sdílený skript Xerxe/Kýra/Ambiorixe, druhý `vo_actor`, chat-tag texty, alternativní dekód, forced-choice). Nejde o poslech. Příklady: *I say nay!* = lokalizované **Iceni!**, *I like traps* = *Allied traps*, *This man told the artillery!* = *Dismantle the artillery!*, *Cravings!* = *Cravens!*, *There, come on to Husband Slane!* = *Their commander has been slain!*

## Krátké povely a WEM budget

HIGH 4: *Gut them!* → **Vykuchejte je!** (2×, jen poměr délek při 9,8 znaku/s), *QUICKLY!* → **Rychle!** (6,3 kB) a *Run!* → **Běžte!** (4,8 kB / 0,51 s). Zkráceno: *Bleed them!* **Ať krvácí!**, *Ready tar pits!* **Jámy připravit!**

## Výslovnost

[pronunciation-overrides.csv](pronunciation-overrides.csv): převzatý návrh **Boudyka** (`PROPOSED_VERIFY_IN_PILOT`) u *Boudica! Královna bojovnice!*; pilot srovnává i canonical *Boudica!*. Dále Germanykus, Cézar, Ksantypos (`PROPOSED_VERIFY_IN_PILOT`), Arminyus, Miltyadés a nově **Numydský** (tvrdé d, jen fallback). Canonical český text (*Boudica*, *Boudicu*, *Boudiko* v ostatních plánech) se nemění; žádný návrh není APPROVED.
