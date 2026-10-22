# Xerxes — poznámky k překladu

Commander `per_xerxes` (frakce `rom_persia`, `vo_culture_Persian`, Wwise actor `Commander_Xerxes` = 2335687687). Platí jen pro 384 bezpečných commander-specific Media ID (317 budoucích výkonů). Žádné TTS, WEM ani poslech nebyly provedeny.

## Charakter

Originál hraje Xerxe jako královského, dominantního a sebevědomého vládce: klidná nadřazenost v běžných rozkazech, výsměch a hrozby v emotes (*Kneel, you dogs!*, *Sixty lashes!*), tvrdost v boji a zlost při neúspěchu (*Who is responsible for this defeat?*). Překlad drží vznešený, ale přirozený rejstřík bez archaismů a bez karikatury perského krále. Hlasový profil `xerxes` v `tools/tts/research_plan.py`: běžné rozkazy `AUTHORITATIVE [calm, authoritative]`, frontend `SUPERIOR [proud, authoritative]`, citáty `SUPERIOR [confident, restrained]`, zastrašování `THREATENING [threatening, confident]`, porážka `STERN [stern, serious]`. `eleven_v3` plán navrhuje jen u 9 výkonů s prokazatelně křičeným originálem; výchozí doporučení je `eleven_v4`.

Sebeodkazy jsou v mužském rodě (*Jsem spokojen.*, *Nejsem proslulý svou trpělivostí!*, *Musím snad všechno dělat sám?*). Rozkazy mají množné číslo vojska.

## Terminologie a rozhodnutí

- Velbloudí jednotky (camelry charge, camel dash, wild temper): *Velbloudi, do útoku!*, *Velbloudí výpad!*, *Rozběsněte velbloudy!*, *Velbloudi, běsněte!*
- Schopnosti: *Tremble Before Xerxes!* **Třeste se před Xerxem!**, *Tyrant's Lash* **Šedesát ran bičem! / Použijte bič! / Tvrději! Bojujte tvrději!**, *Invigorating Strike* **Kochám se jejich bolestí! / Ach, jak krásná smrt!**
- Obecný rozkazový skript je stejný jako u Boudicy, Kýra a Ambiorixe (sdílený text, různé nahrávky): překlady drží projektovou terminologii (*Taste čepele!*, *Svižně!*, *Poklusem!*, *Vypustit!*, *Pal!*, *Zapřít!*, *ježci*, *dehtové jámy*, *zátarasy*, *kůly*).
- *Hurl the naphtha!* → **Vrhejte zápalnou směs!** (české *nafta* dnes znamená motorovou naftu).
- Jména: Kýre (vokativ, jako v produkci Zhuge Lianga), Kynané, Caesar(a), Massinissa (*Massinissa už nedobojuje!* převzato z Hannibalovy produkce), Marathón, Spartakus, Scipio(nem).

## Přepisy

67 sporných nebo zjevně chybných ASR přepisů bylo rozhodnuto lokální evidencí, nikoli poslechem: alternativní medium/small dekód, forced-choice, druhý `vo_actor`, chat-tag texty a sourozenci stejného stavu, včetně stejného stavu u Kýra (`template-siblings-xabv`). Příklady: *Canvas/cameras* = *Camels*, *Touch them!* = *Dodge them!* (Kýros *DODGE THEM!*), *Peace!* = *Apace!*, *HOLD THE NAPTA / Harve naphtha* = *Hurl the naphtha!* (Kýros *Hurly-nuff-da!*), *BATTLE COURSE* = *Battle calls!*, *DAAAAAAMN!* = lokalizovaný beze-slovný pokřik *Yaaaah!* (česky **Jaaaa!**).

## Krátké povely a WEM budget

HIGH zůstávají jen 4 Media ID: *PUSH!* (6,2 kB / 0,66 s), *Onward!* (6,4 kB / 0,65 s) jsou krátké originály s minimální češtinou; *Obey me!* → **Poslouchejte!** (2×, 9,1 kB / 1,01 s) je HIGH jen poměrem délek při normální rychlosti řeči. *CAMEL DASH!* bylo zkráceno na **Velbloudí výpad!**

## Výslovnost

[pronunciation-overrides.csv](pronunciation-overrides.csv): nový návrh `PROPOSED_VERIFY_IN_PILOT` **Kserkses / Kserksem** (české čtení x = [ks]; ochrana proti poangličtěnému „Zerk-sees“) u *Xerxes Veliký!* a *Třeste se před Xerxem!*. Pilot u karty srovnává i canonical *Xerxes Veliký!*. Dále převzaté konvence: Germanykus, Cézara, Boudyka (`PROPOSED_VERIFY_IN_PILOT`), Leonydas, Masynyssa, Arminyus (`FALLBACK_ONLY_IF_PILOT_PALATALIZES`). Canonical český text se nemění; žádný návrh není APPROVED.
