# Vývoj a reprodukce

## Windows GUI a release 1.2.0

Koncový uživatel používá ZIP s EXE a externím `payload/`. Vývojář potřebuje 64bitový Windows Python s Tk. Ověřený build používá Python 3.13.5, PyInstaller 6.22.3 a přesné verze v `requirements-development.txt`. NumPy je jen pro vývoj zvuku; není v EXE.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-development.txt
.\.venv\Scripts\python.exe -B -m tools.installer.gui
.\scripts\build-release.ps1 -BasePack "D:\PrivateAssets\audio_cn.original.pack" -ReferencePack "D:\PrivateAssets\hannibal-complete.pack"
```

`-BasePack` je povinný soukromý canonical original mimo repozitář. `-ReferencePack` je volitelný byte comparison s dříve schváleným Complete PACKem; whole-PACK hash se kontroluje vždy. Oba vstupy se pouze čtou. Výstupy vzniknou v ignorovaném `release/`: složka `TWA-Czech-Dubbing-v1.2.0-win64`, ZIP a privátní build report s velikostmi, hashi a výsledky. Existující výstupy se nepřepisují; další build lze dát do nového `-OutputDirectory`.

Builder spustí celou unittest sadu včetně integrací, manifest/WEM validaci a audit secrets/assets/Markdown odkazů. Z čistého PyInstaller buildu vytvoří EXE dvakrát a vyžaduje identický hash. ZIP má stabilní pořadí, Unix permissions, timestamp a kompresi; dvě zabalení musí být identická. Používá `PYTHONHASHSEED=0`, `SOURCE_DATE_EPOCH=1792281600` a verzovaný [installer.spec](../scripts/installer.spec), bez UPX a výchozího UAC. Principy reprodukce: [PyInstaller dokumentace](https://pyinstaller.org/en/stable/advanced-topics.html#creating-a-reproducible-build).

Reprodukce je ověřená v témže Windows/Python/toolchain prostředí. Jiný Python, runtime DLL, zlib nebo PyInstaller mohou změnit EXE/ZIP. Build report uchovává verze. Byte-identický PACK na těchto nástrojích nezávisí.

Release se sestavuje z explicitního seznamu: EXE, readme, notices/licence, veřejný ověřovací klíč, manifesty, společné deskriptory, voice-lines, nezávislé inventory a schválené české WEMy. CSV jsou runtime vstupy bezpečnostní kontroly. QA historie, source, tests, `.env`, originály a celé PACKy se nebalí. `SHA256SUMS.txt` pokrývá každý distribuovaný soubor kromě sebe. Audit prochází i rozbalený ZIP a dekomprimovaný obsah EXE. Rozbalený EXE se testuje bez BAT v cestě s mezerami při jiném pracovním adresáři.

Zmrazené EXE má vývojový přepínač `--self-test ORIGINAL.pack REPORT.json`. Vždy vytváří vlastní dočasnou mock instalaci; nepřijímá cílovou herní složku. `tools.installer.smoke.MockGUI` používá skutečné `ttk.Checkbutton.invoke()` a `Button.invoke()`, worker, frontu událostí a backend. Počítá volání inspect/install/build/additive build/backup/restore a atomické zápisy PACKu. Kontroluje i SHA-256, modification time, nezměněné zálohy/logy a čeká déle než původní 700ms debounce. Matice všech sedmi výběrů, restartů, H → all, odebrání každého commandera, rychlé klikání, prázdný výběr, Verify a Restore procházejí skutečným PACK diffem vůči canonical originálu. Detekce složky je omezená na mock; odpovědi dialogů jsou simulované. Nativní dialogy nejsou vizuálně ověřené. Žádná část releasu nespouští hru ani TTS.

GUI odděluje `available_commanders`, `installed_commanders` a `pending_commanders`. `selection_changed()` pouze přečte checkboxy a přepočítá ovládání; neplánuje backend práci. Jen `folder_changed()` naplánuje read-only inspect. Explicitní Install pořídí snapshot aktuálních widgetů, uzamkne ovládání a po zápisu vyžaduje shodu ověřeného PACK hashe a commander setu se snapshotem. Install, Verify a Restore synchronizují checkboxy až z ověřeného výsledku. Chyba nepromuje pending výběr do installed stavu a vyžaduje nové Verify před dalším Install.

`refresh_install_button_state()` je jediné místo, které určuje text a dostupnost Install. Přes společné `controls()` se volá po změně checkboxu/složky i po dokončení nebo chybě operace. Aktivuje neprázdnou, validovanou pending kombinaci odlišnou od installed stavu, pokud je složka ověřená a GUI není busy. Chybějící záloha nikdy neblokuje přidání. Odebrání nainstalovaného commandera je vypnuté se stručným varováním, pokud inspect nenašel původní zdroj; neplatná záloha vypne každý zápis. Restore Original je aktivní jen se zdrojem originálu. GUI state testy pokrývají zálohu platnou, chybějící, neplatnou i původní herní soubor; source i frozen smoke ověřují H → 609 → 902 bez zálohy, bezpečné odmítnutí odebrání/Restore bez zápisu a automatickou zálohu.

### Přechodový model installeru

Každý Install/Restore nejdřív ověří aktuální `audio_cn.pack`. Povolený je jen canonical original nebo některý ze sedmi známých validovaných stavů; neznámý PACK skončí `UNKNOWN_PACK` bez zápisu a nikdy se z něj nestane záloha. Zdroj originálu se hledá v tomto pořadí: platná záloha profilu, aktuální čistý PACK, explicitně pojmenovaný `data/audio_en.pack` nebo `data/audio_cn.pack.orig`. Herní soubor se pouze čte a použije se jen při přesném SHA-256 canonical originálu, RSA a struktuře. Launcher kopíruje EN audio do CN slotu, proto je `audio_en.pack` v ověřené instalaci bajtově shodný s originálem.

S originálem platí preferovaný deterministický model `canonical original + vybrané náhrady = cílový PACK`. Chybí-li záloha, vytvoří se z ověřeného zdroje atomicky před prvním zápisem a kopie se znovu ověří. Bez originálu je dovolený jen aditivní přechod (`installed_commanders ⊆ selected_commanders`): `mod.build_additive` zkopíruje ověřený současný PACK do TEMP a zapíše pouze přidané payloady. Výsledek musí mít přesný whole-PACK SHA-256 validovaného cílového deskriptoru a projít RSA, kontrolou 16 545 entries, nezměněných header/index/Appendix a offsetů, diffem bez změn mimo přidané payloady a hashem každé cílové náhrady. Je proto bajtově shodný s canonical buildem. Release builder dál používá výhradně `mod.build` z canonical originálu. Odebrání bez originálu končí `ORIGINAL_SOURCE_REQUIRED_FOR_REMOVAL`, Restore `ORIGINAL_SOURCE_REQUIRED_FOR_RESTORE`, poškozená záloha `INVALID_BACKUP` (nikdy se nepřepíše) a chyba dočasné kopie `INSTALL_VALIDATION_FAILED`, vždy bez zápisu do hry.

Úspornější záloha jen původních bytů nahrazených položek by měla 14 335 023 bajtů pro současných 902 položek místo 244 019 593. Pokrývala by ale jen commandery známé v době zálohy, proto zůstává jedna úplná ověřená kopie PACKu.

GUI backend je v `tools/installer/`, společný PACK builder v `tools/mod.py`. Data se při běhu EXE hledají pouze vedle EXE v `payload/`, nezávisle na pracovním adresáři. Záloha je v LocalAppData s ID odvozeným od normalizované herní cesty; OS lock brání dvěma souběžným transakcím. Sestavení probíhá v nové dočasné složce na stejném disku jako cíl, po úplné kontrole následuje `os.replace`. Při nedostatečném oprávnění GUI nabídne přesný postup Run as administrator; samo se neelevuje.

Pokročilé původní `scripts/install.ps1`, `verify.ps1`, `restore.ps1` nadále vyžadují Python. Jejich záloha je `<GamePath>/.twa-czech-dubbing/backups/audio_cn.original.pack`; není totožná s GUI LocalAppData zálohou. Používejte stejný frontend také pro obnovu. Wrappers jsou zdrojové vývojové nástroje, ne součást end-user ZIPu.

## Metadata a další commandery

Manifest schema 1 navíc definuje `id`, `display_name`, `spoken_count`, `replacement_count`, `replacement_directory`, `supported_base_pack_hash`, `required_runtime_pack` a `version`. Alias fields musí souhlasit se stávajícími base/runtime/count údaji. GUI commandery dynamicky objevuje přes `data/commanders/*/manifest.json`.

Pro budoucí kombinaci vytvořte `data/releases/<sorted-id>+<sorted-id>.json` s `commanders` (seřazený seznam) a `release` (`sha256`, `changed_entries`, `unchanged_entries`). Nejdříve samostatně schvalte a reprodukujte výsledný celý PACK. Merge dovolí stejný Media ID pouze při shodném payload hashi i původním path/offset/size/hash, kontroluje kompatibilní základy a tichá média. Každá komponenta stále prochází nezávislou inventory validací. Bez joint descriptoru se kombinace nesestaví. Dnešní release builder záměrně vyžaduje Hannibala, Spartaka a Zhuge Lianga; před rozšířením upravte název releasu, payload výběr a integrační corpus.

Finální voice-lines a inventory uchovávají provenance, triggery a confidence. `audio-qa.json` spojuje decode evidence s padding/ww2ogg kontrolami. Původní PACKy, WAV reference, experimenty a move ledger zůstávají v soukromém archivu mimo projekt; umístění se předává jako vstup, nikdy se nezapisuje do veřejného source. Staré skripty s absolutními cestami jsou jen výzkumné podklady. Archiv se do releasu nekopíruje.

## Základní prostředí

Python **3.11+**; cleanup byl ověřen na Pythonu 3.13.5. Instalace, restore, verify, PACK build, fingerprinty a hlavní testy používají standardní knihovnu. `requirements.txt` proto nemá pip dependencies. PowerShell entrypointy používají Windows PowerShell 5.1+ / PowerShell 7; procesy se kontrolují přes místní `powershell.exe` a `Get-CimInstance Win32_Process` s fail-closed chováním.

Volitelný vývoj zvuku má `requirements-development.txt` s NumPy 2.5.4, verzí z původního pracovního prostředí a ověřeného resampler testu. Do vlastní `.venv` jej lze instalovat:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-development.txt
```

FFmpeg není pro instalaci ani současnou 24→32 kHz přípravu potřebný. Pro budoucí jiné vstupní formáty ho lze použít jako samostatnou, znovu validovanou převodní cestu; zde se netvrdí ověřená verze ani bitová shoda takové alternativy.

## Externí vývojové nástroje

Binárky, jejich zdrojové checkouty, model caches a toolchainy patří do `work/`, vlastní ignorované složky nebo mimo projekt. Nejsou součástí Git kandidátů. Odkazy a hashe níže pocházejí ze zaznamenané provenance použitých nástrojů; nejde o doporučení automaticky aktualizovat na latest.

| Nástroj | Historicky použitá verze / zdroj |
|---|---|
| wav2wem | [pas2k/wav2wem](https://github.com/pas2k/wav2wem), commit `38e916953bec63862b13b449d780d1303a1bf29c` |
| Go | 1.27.2 pro původní Windows build; `go.mod` tohoto wav2wem uvádí minimálně 1.23.3 |
| Embedded encoder | OggEnc 2.88, libvorbis 1.3.7, aoTuV b6.03 Lancer Mod |
| ww2ogg | [release 0.24](https://github.com/hcs64/ww2ogg/releases/tag/0.24); source commit `14ed9b0dd62e815a38702b5f03c57006cbe2501b` |
| vgmstream | [release r2117](https://github.com/vgmstream/vgmstream/releases/tag/r2117), Windows x64 |
| wwiser | [v20260808](https://github.com/bnnm/wwiser/releases/tag/v20260808); strukturální XML dump bank |

Původní Windows download SHA-256:

```text
Go 1.27.2 ZIP: 1314008898bd40df77af4b014f777f08873dbdfbcd3d92308728ee03304fe04f
ww2ogg 0.24 ZIP: cb90dbcc45160e0c435a4d83f59f678337c069e5551618e6b1c46254e7aef59f
vgmstream r2117 ZIP: 6c4a8a3813864fefed081bbd337dbc0ad93bf88e0b92f5db98d7ab258b22dc6c
wwiser.pyz: f4ba1368895adab285f27fa37b142e5da805bcc6fb77e8daba282dac65d89411
aoTuV603 codebooks: 00a93eab267d281401b1efd54e888a2e183299b9e6c446c48d09f701a89d9d27
```

Použijte upstream release / zdroj a ověřte stažený hash pomocí `Get-FileHash`. K vytvoření wav2wem lze do prázdné ignorované pracovní složky stáhnout uvedený commit, zkontrolovat HEAD a spustit:

```powershell
# Ve vlastním checkoutu připnutého wav2wem, s odpovídajícím Go v PATH:
go test ./...
go build -trimpath -buildvcs=false -o ..\wav2wem.exe ./cmd/wav2wem
```

Původní build měl `CGO_ENABLED=0`, `GOTOOLCHAIN=local`, `GOENV=off` a vypnuté telemetry; používal lokální GOCACHE/GOPATH/temp. Při změně nástrojů znovu ověřte corpus. wav2wem v tomto commitu obsahuje vlastní embedded encoder a codebooks; samostatný oggenc pro quality search je jeho `assets/oggenc2.exe`. Licence a převzatá logika jsou uvedené v [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md). Další binárky se bez přezkoumání licence do repozitáře nepřidávají.

## Konfigurace a secrets

Instalace a builder nečtou `.env`. Soukromý `.env` používá pouze samostatný produkční TTS klient `tools.tts.production`, případně klient čte `ELEVENLABS_API_KEY` z prostředí. `.env.example` obsahuje pouze placeholder. `tools.tts.plan` nic neodesílá. Produkční klient vyžaduje výslovně schválenou placenou úlohu a zapisuje jen do ignorovaného `work/`; API klíč ani Bearer token nesmí být v reportu, CSV, logu nebo test fixture.

`TWA_TEST_BASE_PACK` zapíná volitelné integrační testy s vlastní původní zálohou. `TWA_TEST_OUTPUT_ROOT` volitelně určí existující složku pro jejich dočasné kopie. Testy vlastní dočasné soubory po sobě odstraní. Nepředávejte jim herní `data` jako pracovní výstup.

## Validace a PACK build bez instalace

Z kořene projektu, s výstupem mimo instalaci hry:

```powershell
python -B -m tools.mod --commander hannibal validate
python -B -m tools.mod --commander hannibal build --base "D:\PrivateAssets\audio_cn.original.pack" --output "D:\ModBuild\hannibal.pack" --report "D:\ModBuild\validation.json"
python -B -m tools.mod --commander hannibal verify --pack "D:\ModBuild\hannibal.pack" --base "D:\PrivateAssets\audio_cn.original.pack"
python -B -m tools.validation.repository
```

PACK output, `.partial` a report musí být nové cesty. Builder nedovoluje overwrite, in-place patch ani použití modifikovaného PACKu jako základu. Ověřuje celý finální hash z manifestu. Obsahuje pouze payload writer; změna signed indexu není implementovaná.

Aktuální WEMy zůstávají přesně schválenými soubory Batch 04. Pro jejich reprodukci do PACKu nepotřebujete původní TTS WAVy ani encoder. Výroba nového audia je samostatná vývojová pipeline.

## Vývoj zvuku a inventory

```powershell
python -B -m tools.pack.inspect "D:\PrivateAssets\audio_cn.original.pack" --output work\pack-index.json
python -B -m tools.inventory.banks --xml work\banks.xml --output work\graph.json
python -B -m tools.inventory.voice_map --graph work\graph.json --output work\references.json
python -B -m tools.wem.fingerprint work\123.wem work\123-fingerprint.json
python -B -m tools.wem.prepare work\123-tts.wav work\123-game.wav
python -B -m tools.wem.exact_size work\123-raw.wem work\123-exact.wem --size 17124
```

Čísla jsou příklady; velikost vždy pochází z konkrétní originální entry. Pracovní složku vytvořte před použitím. Preparation vyžaduje NumPy a vstup 24 kHz mono PCM16. Standardní ostatní příkazy ho nepotřebují.

Příklad řízené offline encode search a následné plné validace:

```powershell
python -B -m tools.wem.encode --source work\123-game.wav --output work\123.wem --size 17124 --media-id 123 --oggenc "D:\Tools\wav2wem\assets\oggenc2.exe" --wav2wem "D:\Tools\wav2wem.exe" --vgmstream "D:\Tools\vgmstream-cli.exe" --work work\123-search
python -B -m tools.wem.validate --wem work\123.wem --reference work\123-game.wav --original work\123-original.wem --vgmstream "D:\Tools\vgmstream-cli.exe" --ww2ogg "D:\Tools\ww2ogg.exe" --codebooks "D:\Tools\packed_codebooks_aoTuV_603.bin" --work work\123-validation
```

Encode search používá původně ověřený Windows oggenc s desetinnou čárkou; pro jiný locale je explicitní `--decimal-separator .`. Každý kandidát má unikátní cestu. `--advanced-option lowpass_frequency=11` či jiné profily vyžadují review. Encoder může výstup označit pouze `ENCODED_REQUIRES_FULL_VALIDATION`; před kanonizací následuje full QC, raw-vs-padded PCM porovnání a poslech. `tools.wem.audio REFERENCE.wav DECODED.wav` kontroluje PCM16 fidelity. Nová data přísluší do manifestu až po schválení.

## Testy

```powershell
python -B -m unittest discover -s tests -v
# Volitelně plné testy s původní soukromou zálohou:
$env:TWA_TEST_BASE_PACK = "D:\PrivateAssets\audio_cn.original.pack"
python -B -m unittest discover -s tests -v
```

Bez proměnné se integrační část označí skipped; neoznačujte takový běh jako plnou PACK validaci. Integrační testy vytvářejí vlastní mock game složky, provádějí skutečné install/verify/restore wrappery pouze nad nimi a po sobě je odstraní. Nikdy nesmí cílit na skutečnou instalaci. Procesové blokování je navíc testované simulovaným běžícím procesem.

Regrese zahrnují exact-size JUNK, změněný manifest, tiché IDs, neznámý základ, odmítnutí incremental buildu a overwrite, RSA tampering, zálohu, chybějící zálohu, dry-run a restore. Čerstvé testy a audio QA při cleanupu jsou shrnuté ve [VALIDATION](VALIDATION.md).

## Spartacus a vývojový mezistupeň 1.1.0

Schválených 259 MP3 výkonů se offline páruje s 304 bezpečnými Media IDs přes `generation-state.json`, `final-routing.csv` a `tts-plan.csv`. `tools.wem.production` ověří checksumy a canonical PACK, dekóduje MP3 44,1 kHz přes miniaudio na 24 kHz mono PCM16 a použije Hannibalovu 24→32 kHz přípravu. Připnuté knihovny pro tuto vývojovou fázi jsou v `requirements-audio-production.txt`. Neprovádí se API volání ani nová TTS generace.

Každé Media ID má vlastní original byte budget. `tools.wem.encode` hledá fitting quality, případně omezené jemné kroky; vybrané WEMy se validují přímým PCM16/float dekódem, korelací, SNR, ww2ogg a raw-vs-JUNK dekódem. Provenance a výsledky všech 304 jsou v `data/commanders/spartacus/audio-qa.json`. U `225505249` se odstranilo dalších 20 ms koncového ticha, řeč zůstala zachována; použil se encoder-only lowpass 8,1 kHz. Další napjaté rozpočty používají encoder-only lowpass podle jednotlivých ignorovaných `work/spartacus-production/encode-reports/`. `194179632` má ve finálním WEM délku přibližně 1,99× originálu. Uživatel později potvrdil úspěšný test Spartaka ve hře; úplný samostatný poslech každého finálního WEMu není doložen.

`tools.wem.promote` vytvoří produkční schema-1 metadata až po úplném audio QC a porovnání všech PACK entries proti canonical originálu. `tools.installer.joint` vytváří samostatný hash kombinace. Installer sestavuje výběr z ověřeného canonical originálu, pokud je dostupný; bez něj smí jen aditivně doplnit ověřený známý stav na přesný validovaný hash cílové kombinace. Zná původní stav, všechny samostatné i kombinované stavy. Lokální build přes `scripts/build-release.ps1 -BasePack <soukromý-canonical-PACK>` testuje jen dočasné mock instalace, balí explicitní allowlist a skenuje ZIP i embedded EXE. Skutečnou hru nespouští ani nemění.

## Zhuge Liang a příprava verze 1.2.0

Finální hlas `ZhugeLiang_CZ_v2` a `eleven_v4` pokrývají všech 292 unikátních výkonů pro 293 bezpečných Media IDs (4 znovu použité pilotní výstupy, 288 nových; audit history bez neshod). Stejná příprava jako u Spartaka vytvořila 292 kanonických 32 kHz WAV. Standardní a fallback encoding dal 224 WEMů s plnou exact-size QC; 69 Media IDs zůstalo blokovaných.

Analýza originálních WEMů těchto 69 ID ukázala, že encoder není příčinou: projektový oggenc/wav2wem zakóduje dekódovaný originál při quality 2 do jeho budgetu u 68/69 ID. Všechny originály mají stejný 35-codebookový setup a jsou úzkopásmové (nad 8 kHz asi −80 dB, šířka −40 dB nejvýše 7,8 kHz). TTS má nad 8 kHz o 61 dB víc energie a 1,6× (skupina A 2,3×) víc aktivní řeči. `tools.wem.recovery` proto zkouší od nejmírnějšího lineárně-fázový band-limit referenčního WAV (10 → 7 kHz; pod 7 kHz jen pro linky s užším originálem), poté mírný −3 dB šelf nad 6,5 kHz a 20 ms koncovou rezervu, každý s nezměněným Arena searchem. Přijme jen kandidáta, který projde standardní QC vůči band-limited referenci i auditem vůči nezměněnému TTS (full-band korelace >0,95, SNR >15 dB v zachovaném pásmu, žádný výpadek řeči, žádná přidaná energie ve stabilní řeči, nejvýše jeden přechodový rámec jako ve schválené sadě Spartaka, zachovaná šířka pásma). Obnovilo 43 ID; 26 zůstalo blokovaných. Pro ně `tools.tts.regenerate` se stejným hlasem a modelem vygeneroval kompaktnější přednes změnou delivery tagů (22 obnoveno; u 996690592 i lidsky schválená synthesis-only varianta „Útok.“). Request-level `voice_settings.speed` model `eleven_v4` ignoruje (history ukládá jen `stability`), tempo nezměnil. Poslední čtyři povely dostaly lidsky schválené kratší canonical překlady (`translation-notes.md`): 138096276 „Držte!“, 197890216 „Štíty!“, 894824780 „Smrt shůry!“, 996690592 „Vpřed!“; plán byl přegenerován `tools.tts.research_plan` a změnil jen tyto čtyři řádky. Celkem 55 cílených requestů, 706 credits. Produkční ledger `generation-state.json` zůstává zmrazený; `accepted-state.json` je jeho kopie s aktuálními hashi plánu/routingu a 26 přijatými kompaktními zdroji. Staging 293 WEMů (224 standardních, 43 band-limit recovery, 26 kompaktních) prošel nezávislou plnou re-validací a auditem vůči nezměněnému TTS; `tools.wem.promote` vytvořil schema-1 manifest a `replacements/zhuge-liang/` (293/293). Tři obnovy s 7 kHz cutoffem (24917836, 500434611, 836554480; přes 99,9 % energie originálu, asi 0,6–0,75 kHz pod jeho −40 dB hranou) jsou lidsky schválená výjimka zapsaná v `audio-qa.json` i `wem-recovery/approved-exceptions.json`. Joint descriptory H+Z (598), S+Z (597) a H+S+Z (902) byly sestaveny z canonical originálu a byte-identicky zreprodukovány. Uživatel později potvrdil úspěšný test Zhuge Lianga ve hře; úplný samostatný poslech každého finálního WEMu není doložen.

`tools.resources.VERSION` je `1.2.0`. Release builder vyžaduje přesně Hannibala, Spartaka a Zhuge Lianga a každou jejich kombinaci se samostatným descriptorem v `data/releases/`; jinak se fail-closed odmítne spustit. `tools.installer.joint --commanders a,b` vytvoří descriptor pro libovolnou podmnožinu, aniž by měnil existující `hannibal+spartacus.json`. Installer testy a GUI smoke odvozují matici instalace, upgradu, odebrání, verify a restore z objevených production manifestů. Uživatel potvrdil úspěšný test všech tří commanderů ve hře; finální 1.2.0 artefakt je zatím pouze lokální release candidate.
