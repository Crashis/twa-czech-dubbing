# Vývoj a reprodukce

## Windows GUI a release 1.0.0

Koncový uživatel používá ZIP s EXE a externím `payload/`. Vývojář potřebuje 64bitový Windows Python s Tk. Ověřený build používá Python 3.13.5, PyInstaller 6.22.3 a přesné verze v `requirements-development.txt`. NumPy je jen pro vývoj zvuku; není v EXE.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-development.txt
.\.venv\Scripts\python.exe -B -m tools.installer.gui
.\scripts\build-release.ps1 -BasePack "D:\PrivateAssets\audio_cn.original.pack" -ReferencePack "D:\PrivateAssets\hannibal-complete.pack"
```

`-BasePack` je povinný soukromý canonical original mimo repozitář. `-ReferencePack` je volitelný byte comparison s dříve schváleným Complete PACKem; whole-PACK hash se kontroluje vždy. Oba vstupy se pouze čtou. Výstupy vzniknou v ignorovaném `release/`: složka `TWA-Czech-Dubbing-Hannibal-v1.0.0-win64`, ZIP a privátní build report s velikostmi, hashi a výsledky. Existující výstupy se nepřepisují; další build lze dát do nového `-OutputDirectory`.

Builder spustí celou unittest sadu včetně integrací, manifest/WEM validaci a audit secrets/assets/Markdown odkazů. Z čistého PyInstaller buildu vytvoří EXE dvakrát a vyžaduje identický hash. ZIP má stabilní pořadí, Unix permissions, timestamp a kompresi; dvě zabalení musí být identická. Používá `PYTHONHASHSEED=0`, `SOURCE_DATE_EPOCH=1792108800` a verzovaný [installer.spec](../scripts/installer.spec), bez UPX a výchozího UAC. Principy reprodukce: [PyInstaller dokumentace](https://pyinstaller.org/en/stable/advanced-topics.html#creating-a-reproducible-build).

Reprodukce je ověřená v témže Windows/Python/toolchain prostředí. Jiný Python, runtime DLL, zlib nebo PyInstaller mohou změnit EXE/ZIP. Build report uchovává verze. Byte-identický PACK na těchto nástrojích nezávisí.

Release se sestavuje z explicitního seznamu: EXE, BAT, readme, notices/licence, veřejný ověřovací klíč, manifest, voice-lines, nezávislá inventory a schválené české WEMy. CSV jsou runtime vstupy bezpečnostní kontroly. QA historie, source, tests, `.env`, originály a celé PACKy se nebalí. `SHA256SUMS.txt` pokrývá každý distribuovaný soubor kromě sebe. Audit prochází i rozbalený ZIP a dekomprimovaný obsah EXE.

Zmrazené EXE má vývojový přepínač `--self-test ORIGINAL.pack REPORT.json`. Vždy vytváří vlastní dočasnou mock instalaci: GUI callbacky, install, verify, already-installed a restore. Nepřijímá cílovou herní složku. Browse selection a modální výsledky jsou v této automatické části simulované; skutečné dialogy potřebují samostatný vizuální smoke test. Žádná část releasu nespouští hru ani TTS.

GUI backend je v `tools/installer/`, společný PACK builder v `tools/mod.py`. Data se při běhu EXE hledají pouze vedle EXE v `payload/`, nezávisle na pracovním adresáři. Záloha je v LocalAppData s ID odvozeným od normalizované herní cesty; OS lock brání dvěma souběžným transakcím. Sestavení probíhá v nové dočasné složce na stejném disku jako cíl, po úplné kontrole následuje `os.replace`. Při nedostatečném oprávnění GUI nabídne přesný postup Run as administrator; samo se neelevuje.

Pokročilé původní `scripts/install.ps1`, `verify.ps1`, `restore.ps1` nadále vyžadují Python. Jejich záloha je `<GamePath>/.twa-czech-dubbing/backups/audio_cn.original.pack`; není totožná s GUI LocalAppData zálohou. Používejte stejný frontend také pro obnovu. Wrappers jsou zdrojové vývojové nástroje, ne součást end-user ZIPu.

## Metadata a další commandery

Manifest schema 1 navíc definuje `id`, `display_name`, `spoken_count`, `replacement_count`, `replacement_directory`, `supported_base_pack_hash`, `required_runtime_pack` a `version`. Alias fields musí souhlasit se stávajícími base/runtime/count údaji. GUI commandery dynamicky objevuje přes `data/commanders/*/manifest.json`.

Pro budoucí kombinaci vytvořte `data/releases/<sorted-id>+<sorted-id>.json` s `commanders` (seřazený seznam) a `release` (`sha256`, `changed_entries`, `unchanged_entries`). Nejdříve samostatně schvalte a reprodukujte výsledný celý PACK. Merge dovolí stejný Media ID pouze při shodném payload hashi i původním path/offset/size/hash, kontroluje kompatibilní základy a tichá média. Každá komponenta stále prochází nezávislou inventory validací. Bez joint descriptoru se kombinace nesestaví. Dnešní release builder záměrně vyžaduje Hannibala; před rozšířením upravte název releasu, payload výběr a integrační corpus.

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

Instalace a builder nečtou `.env`. Soukromý `.env` může zůstat lokálně pro samostatný budoucí TTS vývoj; `.env.example` obsahuje pouze placeholder. Síťový ElevenLabs klient zde není. `tools.tts.plan` nic neodesílá. API klíč ani Bearer token nesmí být v reportu, CSV, logu nebo test fixture.

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
