# Hasdrubal — poznámky k překladu

Commander `car_hasdrubal` (frakce `rom_carthage`, `vo_culture_Carthaginian`, Wwise actor `Commander_Hasdrubal` = 501335812). Platí jen pro 318 bezpečných spoken commander-specific Media ID; 13 commander-specific tichých placeholderů (`NO_SILENT`) zůstává v inventuře bez textu a bez TTS. Žádná culture, unit ani global hláška. Žádné TTS, WEM ani poslech nebyly provedeny.

## Charakter

Zkušený kartaginský polní velitel a plátce žoldnéřů: přímočarý, energický, bojovný, sebevědomý, ale disciplinovaný (ne berserkr). Má být odlišitelný od Hannibalova strategického klidu. Hlasový profil v `tools/tts/research_plan.py` (`hasdrubal`): běžné rozkazy `FIELD_COMMAND [determined, commanding]`, přípravné povely `URGENT_COMMAND [urgent, commanding]`, frontend `CONFIDENT [confident, commanding]`, citáty `CONFIDENT [confident]`, odmítnutí `DISAPPOINTED [disappointed]` (jeho sarkastické *Really? / Was that it?*), zastrašování `THREATENING [threatening, confident]`. `eleven_v3` plán navrhuje jen u 10 výkonů s prokazatelně křičeným originálem; výchozí doporučení pro pilot je `eleven_v4`.

## Terminologie a rozhodnutí

- Hasdrubal sdílí s Hannibalem kartaginskou šablonu rozkazů (stejné stavy mají stejné věty, jiná nahrávka a jiná Media ID). 99 frází proto přebírá runtime-schválenou češtinu Hannibala (*Štíty vzhůru!, Připravit děla!, Spojenecké pasti nablízku!, Taste čepele!, Zbraně tasit!* …).
- Kompaktní odchylky od Hannibala kvůli WEM budgetu (originál krátký, Hannibalova věta o polovinu delší): *AS ONE!* **Společně!** (místo *Jako jeden muž!*; projektová varianta), *No mercy!* **Bez milosti!** (projektový standard), *KEEP FIRING!* **Střílejte dál!**, *Ready tar pits!* **Dehtové jámy!**, *Stay ready!* **Ve střehu!**; *Run Romans, run!* **Běžte, Římané, běžte!**.
- Úplatkářské schopnosti (Incite Defection, Double Pay) překládány jako obchodnické nabídky: *I have coin! Let's talk!* **Mám peníze! Promluvme si!**, *Would gold improve your skills?* **Bojovali byste za zlato lépe?**, *Kill them off or buy them out!* **Pobijeme je, nebo je koupíme!**
- Vlastní jména: Hasdrubal, Hannibal, Kartágo, Baal, Kynané, Alexandr, Miltiadés, Xanthippos, Spartakus, Teuta (pirátka), Massinissa, Arminius; vokativ *Scipione* (jako Hannibal).
- Kapitálky pro důraz (*It will be GLORIOUS!*, *And THAT is how it is done!*) se v canonical češtině nepřenášejí; důraz nese delivery.

## Přepisy

89 sporných nebo zjevně chybných ASR přepisů bylo rozhodnuto lokální evidencí: shoda modelů, alternativní medium.en/small.en analýza (0,5 s ticha, beam 10), forced-choice skórování smysluplných kandidátů, přesný druhý `vo_actor` u reakcí a hlavně identická věta ve stejném stavu Hannibalovy runtime-schválené šablony. Nejde o lidský poslech. Detail je v `transcript-review-decisions.csv` a ve sdíleném `transcript-corrections.json`. Nejtěsnější rozhodnutí: 474294373 *Up shields!* (všechny modely „Options!“; Hannibal má ve stejném stavu *Up shields!*) a 939435592/421376580 *The foe's base…* (modely „false/first base“).

Dva emote eventy (`Play_car_hasdrubal_emote_intimidate_listen___and_run`, `…_save_time_surrender_now`) nemají chat-tag řádek; jsou to druhé nahrávky replik s interpunkcí v klíči. Byly obnoveny přesnou FNV-1 shodou uvnitř vlastního emote poolu (podrobnosti ve `docs/VOICE_INVENTORY.md`).

## Krátké povely a WEM budget

Po kompaktních úpravách zůstávají HIGH jen 2 Media ID: *Really?* (2 nahrávky, 6,4 kB, 0,72 s) má už nejkratší přirozenou češtinu **Vážně?**. Riziko řeší až exact-size kódování, nikdy zkrácení řeči.

## Výslovnost

Navržené TTS vstupy jsou odděleně v [pronunciation-overrides.csv](pronunciation-overrides.csv): `PROPOSED_VERIFY_IN_PILOT` Cézar, Germanykus, Ksantypos; `FALLBACK_ONLY_IF_PILOT_PALATALIZES` Leonydovi, Miltyadés, Masynysu, Arminya. „Hasdrubal“, „Hannibal“, „Kartágo“, „Kynané“ a „Baal“ override nemají: Hannibalova runtime-schválená produkce je vyslovila správně z canonical textu.
