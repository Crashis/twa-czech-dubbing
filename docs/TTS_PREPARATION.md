# Offline příprava textů pro další commandery

Leonidas a Scipio Africanus mají v `data/commanders/<id>/tts-plan/` české textové návrhy pro bezpečná commander-specific Media ID. Vstupem je nezávisle ověřená `research/voice-lines.csv`; do plánu nesmí proniknout culture, unit ani global shared hlas. `voice-lines-cz.csv` obsahuje jeden řádek pro každý bezpečný Media ID, `tts-plan.csv` jeden řádek pro každý odlišný plánovaný hlasový výkon. Obojí jsou textová metadata, nikoli pokyn k automatické placené generaci.

České návrhy jsou v `data/commanders/shared-research/commander-translation-memory.tsv`. Soubor pokrývá jen anglické fráze použité v bezpečných sadách. Generátor odmítne chybějící i nadbytečnou položku. Při změně anglického přepisu je nutné opravit překlad a znovu vytvořit oba plány:

```powershell
python -B -m tools.tts.research_plan --commander leonidas --commander scipio-africanus --translation-memory data/commanders/shared-research/commander-translation-memory.tsv
python -B -m tools.mod --commander leonidas validate
python -B -m tools.mod --commander scipio-africanus validate
python -B -m tools.validation.repository
```

`PREPARED` označuje český návrh nad angličtinou s úrovní CONFIRMED/HIGH; nejde o tvrzení, že člověk nahrávku poslechl nebo schválil herecký projev. `PROVISIONAL_ENGLISH` má český pracovní návrh, ale původní anglické slovo čeká na ověření. `NEEDS_MANUAL_TRANSCRIPTION` nemá použitelný anglický text ani český návrh. Požadované WAVy zůstávají mimo repository v soukromém `commander-research`; cesty jsou uvedeny v `research/manual-transcript-review.md` a `tts-plan/transcript-review-decisions.csv`.

Jeden budoucí výkon může pokrýt více Media IDs jen při shodném dekódovaném PCM, formátu, anglickém znění a českém návrhu. Jeden originální výkon může být ve Wwise použit jako emote i povel; plán sjednotí styl/model/tags pro celou takovou skupinu. Rozdílné WEM bajty nejsou překážkou pro společnou budoucí nahrávku, ale každé ID bude potřebovat samostatný přesně velký WEM a vlastní kontrolu. Skupiny nikdy nesdílejí výkon mezi dvěma novými commandery.

Routing podle ověřeného historického projektu: `eleven_v4` je výchozí. `eleven_v3` je návrh jen pro označený battlecry/warcry nebo krátký výrazný výkřik v příslušné schopnosti. Jde o doporučení, ne o ověření aktuální dostupnosti API. Tags mají jednu či dvě vlastnosti. `pilot-menu.csv` a `pilot-battle.csv` v research i tts-plan nyní obsahují angličtinu, češtinu, styl, model a tags; vybírají jen bezpečné texty s CONFIRMED/HIGH přepisem a doloženým triggerem.

`wem_budget_risk` je orientační triáž podle původních bajtů, trvání a délky české věty; přesné prahy jsou v `translation-review.md`. Není to úspěch ani neúspěch reálného kódování. Pro pozdější WEM se nesmí oříznout řeč, zkrátit čas strečinkem ani změnit originální velikost entry. Připravené plány nevytvářejí release manifest a nic nezapisují do hry.
