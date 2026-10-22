# Arminius — poznámky k překladu

Commander `bar_arminius` (frakce `rom_arverni`, `vo_culture_barbarian`, Wwise actor `Commander_Arminius` = 1378821244). Platí jen pro 231 bezpečných commander-specific Media ID (193 budoucích výkonů). Sdílené barbarské culture/unit větve (1 616 Media ID společných s Boudicou a Vercingetorigem, včetně unit acknowledgements) v bezpečné sadě nejsou. Žádné TTS, WEM ani poslech nebyly provedeny.

## Charakter

Schopný germánský vojevůdce: sebevědomý, přímý, energický a takticky uvažující (*Know your enemy!*, *Watch your step! These lands are trap-ridden!*), bojovný, ale ne bezhlavý. Odlišení od Germanica (disciplinovaný Říman) a Vercingetoriga (charismatický řečník) nese text i profil `arminius`: frontend `CONFIDENT [determined, commanding]`, rozkazy `FIELD_COMMAND [determined, commanding]`, souhlas `ENCOURAGING [encouraging, confident]`, odmítnutí `STERN [stern]`, vlastní smrt `SOLEMN [solemn]` (*Valkýry si pro mě přišly!*). `eleven_v3` jen u 8 výkonů s prokazatelně křičeným originálem.

## Terminologie a rozhodnutí

- Germánské reálie: **Wodan** (*Wodan nás chrání!*, *Rozpoutejte Wodanův hněv!*), **Thorova ruka!**, **Valkýry**, **Germánie**, *clans* = **kmeny**, *banner* = **korouhev**, battlecry **Modi!** (severský bůh bojové zuřivosti; lokalizovaný text emotu).
- Schopnosti: *Infiltration* **Nepozorovaně! / Poznejte nepřítele! / Mezi ně!**, *Momentum* **Dožeňte je! / Vpřed, kupředu! / Nezastavujte!**, *Frenzy* **Krev, krev, krev! / Zabijte je všechny!**
- *Stake wall, up!* → **Palisádu vztyčit!**; *Harass them!* → **Znepokojujte je!**; *As you were!* → **Jako předtím!** (projektová konvence).
- Jména: Kynané, Caesar(a), Massinissa, Miltiade (vokativ), Xanthippa, Alexandře, Icenové, Spartakus.

## Přepisy

42 sporných nebo zjevně chybných ASR přepisů bylo rozhodnuto lokální evidencí (shoda modelů, alternativní dekód, forced-choice, druhý `vo_actor`, chat-tag texty, sourozenci). Nejde o poslech. Příklady: *More day!* = lokalizované **Modi!**, *Moving on scene!* = *Moving unseen!* (Infiltration), *Foster!* = *Faster!*, *So I breathe this last* = *Sulla breathes his last!*, *Stagwol, up!* = *Stake wall, up!* (alternativní medium dekód).

Dvě Arminiovy nahrávky (619244861 *Death has come for the enemy commander!*, 834617163 *Enemies of Germania!*) mají přesně shodné PCM s jinými, advisor reference Media ID. Commander-only náhrada je bezpečná (jiná ID), advisor kopie zůstanou anglicky.

## Krátké povely a WEM budget

HIGH 4: *Eyes!* → **Sledujte!**, *Unite!* → **Spojte se!** (jen poměr délek), *Fight!* → **Bojujte!** (5,8 kB / 0,67 s), *DODGE!* → **Uhnout!** (6,3 kB / 0,64 s, zkráceno z *Uhýbejte!*).

## Výslovnost

[pronunciation-overrides.csv](pronunciation-overrides.csv) převzaté konvence: **Arminyus** jen jako `FALLBACK_ONLY_IF_PILOT_PALATALIZES` (pilotní karta *Arminius!* posílá canonical text), Germanykus, Cézara, Ksantypa (`PROPOSED_VERIFY_IN_PILOT`), Masynyssa, Miltyade a nově **Mody** pro *Modi!* (tvrdé d, jen fallback). Canonical český text se nemění.
