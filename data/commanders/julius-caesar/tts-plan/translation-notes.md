# Julius Caesar — poznámky k překladu

Commander `rom_caesar` (frakce `rom_rome`, `vo_culture_roman`, Wwise actor `Commander_Caesar` = 4204137505, zobrazované jméno „Julius Caesar“). Platí jen pro 246 bezpečných commander-specific Media ID; žádná culture, unit ani global hláška. Žádné TTS, WEM ani poslech nebyly provedeny.

## Charakter

Charismatický, výjimečně sebejistý státník a vojevůdce: klidná velitelská samozřejmost v běžných rozkazech, ostrost v boji. Není to Scipiova strategická zdrženlivost, Germanikova přímočarost ani Leonidova tvrdost. Hlasový profil v `tools/tts/research_plan.py` (`julius-caesar`): rozkazy `CALM_COMMANDING [confident, commanding]`, frontend/citáty `COMPOSED [confident, authoritative]`, zastrašení `SUPERIOR [confident, restrained]`, výtky `MEASURED [calm, serious]`. `eleven_v3` plán navrhuje jen u 8 prokazatelně křičených výkonů; výchozí doporučení pro pilot je `eleven_v4`.

## Latina a citáty

| Original | Čeština | Rozhodnutí |
|---|---|---|
| Veni, vidi, vici. | Veni, vidi, vici. | v češtině se cituje latinsky; TTS vstup *Veny, vidy, vici.* (tvrdé n/d) |
| Alea iacta est. | Kostky jsou vrženy. | ustálený český ekvivalent; lokalizační text „Alia“ je překlep |
| Divide et impera! | Rozděl a panuj! | ustálený český ekvivalent |
| Divide and conquer! | Rozdělte je a porazte! | odlišeno od latinské varianty ve stejné schopnosti |
| Our allies fire upon us! Et tu? | Spojenci po nás pálí! I ty? | narážka na „I ty, Brute?“ |
| If you must break the law, do it to seize power! | Musíš-li porušit zákon, ať je to kvůli moci! | Suetoniův citát, zkráceno bez změny smyslu |
| Let us satisfy both nature and glory. | Učiňme zadost přírodě i slávě. | narážka na *satis diu vel naturae vixi vel gloriae* |

Alternativa pro pilot (bez změny canonical textu): *Alea iacta est.* lze ponechat latinsky, pokud by uživatel preferoval původní citát.

## Terminologie a rozhodnutí

- Převzato z canonical Scipio/Germanicus/Leonidas: *Zapřít!*, *Udržte linii!*, *Zapřáhnout!*, *Svižně!*, *Poklusem!*, *Kupředu!*, *Jako předtím!*, *křídlo*, *ježci*, *dehtové jámy*, *Nechte to Lue!*.
- *To arms! / Arm yourself!* ze stejné větve: **Do zbraně! / Ozbrojte se!**; *Fire*-větev **Mířit! Pal! / Pusťte! / Připravit! Palte!**.
- *Gaul* (Vercingetorix) → **Gal**; *Honos* (římský bůh cti) a *Minerva*, *Diana*, *Mars* beze změny.
- Vlastní jméno v textu zůstává *Caesar*; výslovnost [cézar] řeší jen TTS vstup.

## Krátké povely a WEM budget

Zbylých 8 HIGH Media ID má originál pod 6 500 B a 0,46–0,68 s; čeština je minimální (*Běžte!, Nikdy!, Bojujte!, Vpřed!, Svižně!, Krýt!, Rychle!*). Kompaktní úprava v tomto kroku: *Drop traps!* **Pokládejte pasti! → Položte pasti!** (1,55× délka, HIGH → MEDIUM). Volitelná alternativa, ne nutná: *As you were!* → *Pohov!*.

## Přepisy

11 sporných přepisů bylo vyřešeno lokální evidencí (alternativní medium.en/small.en analýza, sourozenecké hlášky stejné schopnosti, druhý `vo_actor`). Nejde o lidský poslech. Patří sem *Divide et impera!*, *Honor the gods!*, *A wasted charge!*, *Caesar needs you elsewhere!*, *Et tu?*, *Let Honos guide you…*, *Our men are cowards!* a *We have killed the Gaul!*. Detail je v [transcript-review-decisions.csv](transcript-review-decisions.csv) a ve sdíleném `transcript-corrections.json`.

## Schopnosti

DB `rom_caesar` má právě tři schopnosti (Veni, Vidi, Vici). Hlasové stavy: `vo_ua_Vidi`, `vo_ua_Vici` a nepojmenovaný `599090551` (*Divide and conquer!*, *Intercept their commands!*, odpovídá tichu/Silence). Přesné přiřazení on-screen jména ke stavu se netvrdí.

## Výslovnost

Navržené TTS vstupy jsou v [pronunciation-overrides.csv](pronunciation-overrides.csv) (Cézar, Germanykus, Boudyku, Ksantypos, Veny vidy vici). Fallback pro měkké *ni/di* (Miltiadés, Massinissa, Arminius, Leonidas, Diana) se použije jen podle pilotu.
