# Miltiades — poznámky k překladu

Commander `gre_miltiades` (frakce `rom_athens`, `vo_culture_greek`, Wwise actor `Commander_Miltiades` = 1016622620). Platí jen pro 255 bezpečných commander-specific Media ID; žádná culture, unit ani global hláška. Žádné TTS, WEM ani poslech nebyly provedeny.

## Charakter

Athénský stratég od Marathónu: rozhodný, sebevědomý, bojovný, ale disciplinovaný. Úsporné krátké rozkazy bez spartské tvrdosti Leonidase. Hlasový profil v `tools/tts/research_plan.py` (`miltiades`): běžné rozkazy `FIELD_COMMAND [confident, commanding]`, frontend/citáty `STRATEGIC [confident, authoritative]`, odmítnutí `STERN [stern]`. `eleven_v3` plán navrhuje jen u 10 výkonů, kde je originál prokazatelně křičený (Whisper velkými písmeny); výchozí doporučení pro pilot je `eleven_v4`.

## Terminologie a rozhodnutí

- Převzato z canonical Leonidas/Scipio/Germanicus: *Zapřít!*, *Ustupte!*, *Zapřáhnout!*, *Svižně!*, *Poklusem!*, *Kupředu!*, *Jako předtím!*, *křídlo*, *ježci*, *Do zbraně!*, *Bez milosti!*.
- *Elected General!* → **Zvolený stratég!** (Miltiadés byl volený athénský stratég); *Phalanx formation!* → **Do falangy!**.
- Řecká božstva v českých tvarech: Arés (*Se silou Área!*), Zeus, Hádés, Artemis/Artemidy, Lovkyně (Artemis) velkým písmenem.
- Vlastní jména podle projektu: Miltiadés, Xanthippos, Kynané, Spartakus; latinská jména Germanicus, Arminius, Massinissa beze změny.
- *Fire! / Release! / Loose!* ze stejné větve odlišeny: **Pal! / Pusťte! / Vypustit!**.
- *Will you not let me be Nemesis?* chápáno jako oslovení bohyně odplaty: **Nenecháš mě na pokoji, Nemesis?**

## Krátké povely a WEM budget

Zbylých 12 HIGH Media ID (11 výkonů) má originál pod 6 500 B a 0,50–0,72 s; česká varianta je už jedno- až dvouslabičná (*Běžte!, Postup!, Pusťte!, Vpřed!, Pochod!, Rychle!, Kupředu!, Uhněte!, Krýt!, Pal!, Sevřete je!*). Kratší přirozená čeština neexistuje; riziko řeší až exact-size kódování, nikdy zkrácení řeči.

Kompaktní úpravy provedené v tomto kroku (jednoznačně lepší kratší znění):

| English | Původní návrh | Finální | Důvod |
|---|---|---|---|
| MOVE! MOVE! | Pohněte se! Pohněte! | Rychle! Rychle! | 1,82× délka angličtiny, HIGH → MEDIUM |
| FOCUS | Soustřeďte se! | Pozor! | 2,8× délka; v kontextu úhybu (*ON YOUR TOES!*) znamená „pozor“ |
| Dodge them! | Uhýbejte! | Uhněte! | kratší, přirozený povel |

Volitelná alternativa, ne nutná: *As you were!* → *Pohov!* místo canonical *Jako předtím!* (MEDIUM). Ponecháno kvůli shodě s Leonidasem.

## Přepisy

11 sporných přepisů bylo vyřešeno lokální evidencí (alternativní medium.en/small.en analýza s 0,5 s ticha a beam 10, sourozenecké hlášky stejné větve, druhý `vo_actor`). Nejde o lidský poslech. Detail je v [transcript-review-decisions.csv](transcript-review-decisions.csv) a ve sdíleném `transcript-corrections.json`. Nejtěsnější rozhodnutí: 293222453 *Release!* (medium.en ×2 a řecká šablona Fire!/Loose!/RELEASE! u Leonidase; base/small slyší „Ready“).

## Výslovnost

Navržené TTS vstupy jsou odděleně v [pronunciation-overrides.csv](pronunciation-overrides.csv). Canonical český text se nemění. `PROPOSED_VERIFY_IN_PILOT` se ověří v pilotu (Cézar, Germanykus, Boudyka, Ksantypos). `FALLBACK_ONLY_IF_PILOT_PALATALIZES` platí jen tehdy, když hlas vysloví *Miltiadés, Massinissa, Arminius, Artemidy* měkce.
