# Alexander the Great — poznámky k překladu

Commander `gre_alexander` (frakce `rom_athens`, `vo_culture_greek`, Wwise actor `Commander_Alexander` = 1019910666; složka podle display name „Alexander the Great“). Platí jen pro 255 bezpečných commander-specific Media ID; žádná culture, unit ani global hláška. Žádné TTS, WEM ani poslech nebyly provedeny.

## Charakter

Mladý, mimořádně charismatický a naprosto sebevědomý vojevůdce, který strhává vojáky osobní autoritou; inspirativní spíš než přísný. Nesmí znít jako spartsky tvrdý Leonidas, athénský stratég Miltiades ani státnický Caesar. Hlasový profil v `tools/tts/research_plan.py` (`alexander-the-great`): běžné rozkazy `FIELD_COMMAND [confident, commanding]`, přípravné povely `URGENT_COMMAND [urgent, confident]`, frontend a citáty `PROUD [proud, confident]`, souhlas `ENCOURAGING [encouraging, confident]`, odmítnutí a zastrašování `SUPERIOR`. `eleven_v3` plán navrhuje jen u 8 výkonů s prokazatelně křičeným originálem; výchozí doporučení pro pilot je `eleven_v4`.

## Terminologie a rozhodnutí

- Řecká šablona rozkazů je sdílená s Leonidem, Miltiadem a Cynane (jiné nahrávky, jiná Media ID); terminologie převzata: *Pal! / Pusťte! / Vypustit!* (Fire/Release/Loose), *Zapřít!*, *Svižně!*, *Poklusem!*, *Zapřáhnout!*, *Jako předtím!*, *Do falangy!*, *ježci*, *křídlo*.
- Schopnosti: *Hammer* = **Bušte do nich! / Rozdrťte je! / Rozbijte je na kusy!**, *Anvil* = **Kovadlina! / Přikovejte je! / Držte je!**, *Wedge* = **Utvořit klín! / Do klínu! / Jízdo, klín!**
- Vlastní jména: Alexandr (Veliký, Makedonský), Diův syn (*I am the son of Zeus!* → **Jsem syn Diův!**), Barkas, Spartakus, Miltiadés, Xanthippos (*Smrt si našla Xanthippa!*), Germanicus (*Srazili jsme Germanika!*, jako Hannibal); *My half-sister is slain!* → **Moje nevlastní sestra padla!** (Kynané).
- *Charge!* → **Do útoku!** (Miltiadova volba), *Attack!* → **Útok!**; *Give them death!* → **Smrt jim!**; *Punch through them!* → kompaktní **Prorazte je!**

## Přepisy

58 sporných nebo zjevně chybných ASR přepisů bylo rozhodnuto lokální evidencí (shoda modelů, alternativní medium.en/small.en analýza s 0,5 s ticha a beam 10, forced-choice skórování smysluplných kandidátů, druhý `vo_actor`, řecká šablona stejného stavu). Nejde o lidský poslech. Nejvýznamnější strukturální rozhodnutí: *Form/Greeks/Into for likes!* = **phalanx** (Cynane má ve stejném stavu pike wall *Form Phalanx!* a *Greeks! Phalanx!*), *BUCKLE CALLS!* = *Battle calls!*, *TO THE FOUR!* = *To the fore!*, *HANVILLE!* = *Anvil!*

Dvě položky zůstávají **NEEDS_MANUAL_TRANSCRIPTION** a do plánu nevstupují: 305833039 (porážka, ASR „I can not many ass their feet!“) a 366092679 (stress, „Pull and torta!“). Doporučení a evidence jsou v `work/tts-preparation/alexander-the-great/manual-review.md`.

## Krátké povely a WEM budget

13 HIGH Media ID: 11 má originál pod 6 500 B a 0,56–0,67 s a česká varianta je už nejkratší přirozená (*Nikdy!, Krýt!, Zapřít!, Bojujte!, Běžte!, Rychle!, Tlačte!, Vstávat!, Vypustit!*). Zbylé dva jsou HIGH jen poměrem délek: *ANVIL!* **Kovadlina!** (název schopnosti) a *FOCUS FIRE* **Soustředit palbu!** (projektová terminologie; kratší přirozená varianta neexistuje). Riziko řeší až exact-size kódování, nikdy zkrácení řeči.

## Výslovnost

[pronunciation-overrides.csv](pronunciation-overrides.csv): `PROPOSED_VERIFY_IN_PILOT` Cézar, Ksantypa; `FALLBACK_ONLY_IF_PILOT_PALATALIZES` Leonydas, Miltyadés, Masynysa, Dyjův. „Alexandr“, „Makedonský“, „Kynané“ override nemají (Hannibalova runtime-schválená produkce *Alexandr je mrtev!*, *Kynané padla!*).
