# Ověření výslovnosti bez obcházení production resolveru

`tools.tts.production --defer-pronunciation-review` ponechá nevyřešené výkony v ledgeru jako `deferred_pronunciation`; nikdy je neodešle. Ostatní používají běžný production resolver a obnovitelnou generaci. Canonical překlad, synthesis-only text a rozhodnutí o výslovnosti zůstávají oddělené.

Samostatný nástroj `tools.tts.verification` vybírá pouze skutečně blokované výkony z aktuálního plánu. Použije `Resolver.resolve(..., 'pilot')`, canonical delivery, přesný hlas a výhradně `eleven_v4`. Bez `--generate` provede jen preflight. Výstupy a `verification-state.json` patří do ignorovaného `work/`. Nástroj nic neschvaluje a odmítá opakovat dokončené či změněné requesty. Placenou generaci je nutné mít výslovně zadanou. Ukázky spouštějte po dokončení bulk generace, aby se nesčítaly souběžné požadavky na účet.

```powershell
python -B -m tools.tts.verification --commander <id> --routing work/tts-production/<id>/final-routing.csv --output work/tts-verification/<id> --voice-name "<exact voice name>" --voice-id <voice_id>
# Přidejte --generate pro schválenou generaci a --auto-retry-technical jen pro povolený jeden retry.
```

Po lidském rozhodnutí se zaznamená skutečné `APPROVED` nebo `REJECTED` v příslušném override CSV. Následný production resume může přes `--pilot-journal work/tts-verification/<id>/pilot-journal.json` znovu použít již zaplacené audio, pouze pokud přesně souhlasí hlas, model, canonical text, synthesis-only text i tags. Zamítnutý návrh s odlišným TTS vstupem nelze vydávat za použitelný production výkon. Změna již vygenerovaného vstupu vyžaduje samostatné povolení regenerace.

Pro neblokovanou část commandera podporují `tools.wem.production` a `tools.wem.recovery` volbu `--defer-pronunciation-review`. Celá nezávislá inventura a mapování se nejprve ověří. Z pracovního zpracování se vynechají pouze aktuálním resolverem blokované, nikdy neodeslané výkony. Jiný neúplný nebo stale stav způsobí chybu. Preflight označí takový výsledek jako `WORK_SUBSET` a vypíše plné počty i blokery. Promotion tuto volbu nemá a nadále vyžaduje kompletní plán. Pracovní subset není commander-only release ani joint descriptor.

Lidské schválení strategie není tvrzením, že byla slyšena každá nová generace. Pokud uživatel výslovně určí fallback při nejasném výsledku, zaznamenejte tento důvod. Při dokončení 1.5.0 zůstal pro Scipia 71920531 původní schválený TTS vstup `Publius Kornélius Scipio!`; nový pokus `Scípijo` nebyl vydáván za prokazatelně lepší. U 394797733, 70391879, 901080395 a 808002624 byl podle pokynu uživatele zamítnut `Germanykus` a produkce používá canonical `Germanicus`. Nepotřebné podmíněné fallbacky jsou `REJECTED`. Canonical překlady zůstaly beze změny.
