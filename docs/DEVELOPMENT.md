# Vývoj a reprodukce

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

## Releasová data a historické podklady

`voice-lines.csv` zachovává všech 305 finálních vět, překlady, triggery, confidence, source batch, model/delivery a final WEM hashes. `media-inventory.csv` poskytuje nezávislou scope/silent allowlist. `audio-qa.json` je redukovaná historická Batch 04 QC evidence; `cleanup-audio-qa.json` nová full decode kontrola. Manifest drží očekávané originální a releasové hashe.

Historické Batch 01–04 scripts, pokusy, WAVy, originály a podrobné logy jsou přesunuté mimo repozitář. Soukromý archiv uchovává původní relativní strukturu v `cleanup-2026-10-16/workspace/` a move ledger. Staré scripts jsou historické důkazy s původními absolutními cestami; nespouštějte je naslepo po přesunu. Reusable část je nyní v `tools/` a technické poznatky v tomto projektu. Git kandidáti se z archivu nesestavují.
