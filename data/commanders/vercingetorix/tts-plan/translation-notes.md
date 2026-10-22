# Vercingetorix — poznámky k překladu

Commander `bar_vercingetorix` (frakce `rom_arverni`, `vo_culture_barbarian`, Wwise actor `Commander_Vercingetorix` = 83219417). Platí jen pro 236 bezpečných commander-specific Media ID (196 budoucích výkonů). Sdílené galské/keltské/barbarské culture a unit větve v bezpečné sadě nejsou; pět ability Media ID sdílených s Boudicou (stav 3233209236) je `GLOBAL_SHARED`. Žádné TTS ani WEM nebyly provedeny; lidský poslech proběhl jen u 124609702.

## Charakter

Charismatický, hrdý a vzdorovitý galský vůdce, který burcuje (*Together we are stronger!*, *If we must die, die as Gauls!*, *Fight with home in heart, and blade in hand!*) a v boji je tvrdý (*Hack, slash!*, *Pound their skulls!*). Odlišení od Arminia (taktik), Leonida (spartská strohost) a Hasdrubala (polní velitel) nese profil `vercingetorix`: frontend `PROUD [proud, defiant]`, citáty `PROUD [proud, confident]`, rally povely `ENCOURAGING [encouraging, commanding]`, rozkazy `FIELD_COMMAND [confident, commanding]`, odmítnutí `DISAPPOINTED [disappointed]`. `eleven_v3` jen u 11 výkonů s prokazatelně křičeným originálem.

## Terminologie a rozhodnutí

- Galské reálie: **Galové / Galie**, **Arvernové** (*Náčelník Arvernů!*), bůh **Belenus**, *kinsmen* = **soukmenovci**, *brothers* = **bratři**.
- Karta *Vercingetorix, the Gaul!* → **Vercingetorix z Galie!**; *Slayer of Romans!* → **Zhouba Římanů!**; *If we must die, die as Gauls!* → **Když už zemřít, tak jako Galové!**
- Schopnosti: *Iron Discipline* **Bojujte se mnou! / Bojujte za mě! / Za mnou!**, *Scorched Earth* **Spalte všechno! / Zapalte to! / Spalte to všechno!**, *Defiance* **Budeme bojovat dál! / Smrt počká! / Ještě nekončíme!**
- *No flanks!* (stav ochrany křídla) → **Kryjte křídla!** (význam, ne doslovný překlad).

## Přepisy

80 sporných nebo zjevně chybných ASR přepisů bylo rozhodnuto lokální evidencí (Arminiův stav generic response řádek po řádku, druhý `vo_actor`, chat-tag texty, alternativní dekód, forced-choice). Nejde o poslech. Příklady: *There's Incatorix, the Ghoul* = *Vercingetorix, the Gaul!*, *CHIEF 10 OF THE ARVINI* = *Chieftain of the Arverni!*, *THE ENEMIES OF GO* = *The enemies of Gaul!*, *Bellanus* = *Belenus*, *CREAM PADAKA HAS BEEN KILLED* = *Queen Boudica has been killed!*, *Home to glory!* = *On to glory!*, *Let's book! More trash!* = *Less bulk! More slash!* (kontextová rekonstrukce).

124609702 (větev place tar, všechny modely *Take him out!*) majitel projektu 22. 10. 2026 ručně poslechl: **Take him out!** → **Vyřiďte ho!** (`HUMAN_CONFIRMED`). Zapojení pod větví dehtových jam je jen poznámka (context anomaly); skutečně namluvené audio má přednost. Manual review: 0.

## Krátké povely a WEM budget

17 HIGH: téměř všechny jsou velmi krátké originály (5–7 kB, 0,5–0,8 s) s minimální češtinou (*Pal!*, *Dost!*, *Běžte!*, *Rychle!*, *Držet!*, *Tlačte!*, *Vstávat!*, *Vstaňte!*, *Slaboši!*, *Bojujte!*, *Vypustit!*). Zkráceno: *Gut them!* **Vykuchat!** (2×), *Dodge!* **Uhnout!**. *Tar pit!* → *Dehtová jáma!* je HIGH jen poměrem délek.

## Výslovnost

Jméno **Vercingetorix** nemá žádný override: české čtení podle pravopisu ([vercingetoriks], c = [ts], bez di/ti/ni) odpovídá tradiční české výslovnosti a jméno se skloňuje (*Vercingetorixe*, *Vercingetorixi*), takže globální náhrada by byla chybná. Pilot ověřuje kartu *Vercingetorix z Galie!* a jednorázově ji srovnává s TTS-only zápisem *Vercingetoriks z Galie!*; teprve pokud poslech ukáže problém, vznikne phrase-specific řádek. [pronunciation-overrides.csv](pronunciation-overrides.csv) jinak přebírá konvence: Ksantypovu, Cézar, Germanykus, Boudyka (`PROPOSED_VERIFY_IN_PILOT`), Miltyadés, Masynyssu, Arminyus, Leonydas (`FALLBACK_ONLY_IF_PILOT_PALATALIZES`).
