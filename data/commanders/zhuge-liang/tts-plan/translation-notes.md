# Zhuge Liang — poznámky k překladu a otevřená rozhodnutí

Ruční poznámky k `translation-memory.tsv`. Generovaný přehled je v [translation-review.md](translation-review.md). Nejde o schválení hereckého výkonu, nikdo nahrávky neposlouchal a nebyl odeslán žádný TTS požadavek.

## Charakter a styl

Zhuge Liang zní jako klidný, přesný a kultivovaný stratég. Je autoritativní bez křiku a nikde není komický ani stylizovaný do pseudo-asijských frází. Běžné povely jsou krátké rozkazovací věty v množném čísle („Držte pozice.“, „Hlídejte křídla.“). Citáty a frontend jsou v uhlazenější češtině. Některé maximy jsou v jednotném čísle jako obecné rady: „Odpoutej se od emocí, jednej v klidu.“, „Mysli. Plánuj. Připrav se.“

Terminologie navazuje na existující paměti projektu: countermeasures → *nástrahy*, caltrops → *ježky*, stakes → *kůly*, siege weapons → *obléhací stroje*. Západní jména mají tvary z dřívějších pamětí (Kynané, Xanthippos, Miltiadés, Spartakus, Leonidas, vokativ Sullo).

## Rozhodnutí k potvrzení člověkem

1. **Čínská jména v české transkripci.** Ču-ke Liang, Cchao Cchao, Lü Pu, Čou Jü, Šu Chan. Je to standardní česká sinologická transkripce a český TTS hlas ji vysloví správně, kdežto pinyin „Zhuge“ by četl chybně. Alternativou je ponechat pinyin jako ve hře. Pilot menu obsahuje obě jmenné repliky (179263288, 343019290), výslovnost se tedy ověří hned.
2. **„Crouching tiger“.** Přezdívka postavy je „Ležící/Spící drak“, ale nahrávky 451405982 a 481242422 říkají akusticky prokazatelně *tiger*. „Tiger“ vyhrává nad „dragon“ o 35–48 log-prob u všech tří modelů i variant signálu. Překlad zůstává věrný nahrávce: „číhající tygr“. Pokud má přednost konzistence s přezdívkou (jiné repliky říkají „Spící drak“), lze použít „ležící drak“.
3. **Hlasová umírněnost: 0× eleven_v3.** Žádná originální replika není křičená. Žádná lokální Whisper hypotéza není celá velkými písmeny a žádná replika není výrazně hlasitější ani jasnější než Zhuge Liangův medián (±1,6 dB RMS, nikde +4 dB RMS a současně +4 dB v pásmu 2–5 kHz). „Charge.“ i „Fight!“ jsou tedy na v4 s `[urgent, commanding]`. Pokud by pilot ukázal, že bojové povely potřebují víc energie, změňte jednotlivé fráze v paměti (sloupce delivery). Pravidlo neměňte.
4. **Nové tagy `strategic`, `composed`.** V projektu zatím nebyly runtime ověřené. Používají se jen pro frontend a citáty. Pilot menu je proto celé obsahuje. Pokud je ElevenLabs nepřijme podle očekávání, nahraďte je ověřeným `[calm, commanding]`.
5. **Respektující rozloučení.** U smrti Liou Peje („Bravely fought, my lord.“) je `[solemn]`. U Kuan Jüa, Sun Žen, obecného velitele a Boudiky je `[calm, serious]` místo obecného `[confident, restrained]` pro reakce na smrt.

## Dříve otevřené přepisy (vyřešeno)

Obě repliky potvrdil majitel projektu (HUMAN_CONFIRMED, CONFIRMED):

- **32253270**: „Watch the wind, Zhou Yu!“ → „Sleduj vítr, Čou Jü!“. Krátká, vědoucí poznámka k rivalovi a spojenci Čou Jüovi. Tykání odpovídá přímému oslovení rovnocenného stratéga. Neurčený úsek z ASR („say euro“) bylo jméno Zhou Yu.
- **801277871**: „Your arrogance ends, Lu Bu!“ → „Tvá pýcha končí, Lü Pu!“. Za jméno se nic nedoplňuje.

Ostatní původně sporné repliky (jména, umírající repliky s nádechy, „Loose!“, „stakes“, „flanks“, „Back!“) jsou rozhodnuté lokálními důkazy. Podrobnosti jsou v `transcript-review-decisions.csv`.

## Hra a sdílené nahrávky

17 Zhuge Liangových commander-specific replik („Fight!“, „No mercy.“, „Quick, march.“, „Loose!“ aj.) hra používá i pod šesti jinými Media ID čínských jednotek (`vo_culture_China`, Male_1–3 a Female_1–3), se shodným PCM. Tato Media ID jsou sdílená, proto nejsou bezpečná a v plánu nejsou. Po vydání samotného Zhuge Lianga budou jednotky dál říkat stejnou anglickou větu stejným hlasem. Seznam je v `research/duplicate-groups.csv`.

## WEM rozpočet

19 Media ID má riziko HIGH. Z toho 18 kvůli velmi malému originálu (<6 500 B), což formulace neovlivní. Deset delších českých návrhů bylo zkráceno, aby délka odpovídala originálu (např. „Ready tar pits.“ → „Dehtové jámy.“). Řeč se nikdy nesmí zkracovat ani stretchovat kvůli velikosti.
