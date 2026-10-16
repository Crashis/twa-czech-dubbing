# Total War: Arena Czech Dubbing

Český dabing commanderů pro **Total War: Arena**. Hannibal má hotových **305 / 305 mluvených hlášek**. Všech 16 tichých placeholderů zůstává původních a žádné sdílené médium se nemění.

Repozitář obsahuje české náhrady, metadata a nástroje. Vyžaduje **vlastní existující instalaci podporované verze hry**. Původní herní PACKy, banky ani extrahované původní audio nejsou součástí projektu. Installer sestaví a aplikuje mod lokálně.

Batch 03 byl uživatelem úspěšně vyzkoušen ve hře. Complete / Batch 04 má úplnou offline validaci a reprodukovatelný výsledek; samostatný runtime test Batch 04 dosud neproběhl.

## Požadavky a podporovaná verze

Windows, Windows PowerShell 5.1 nebo PowerShell 7 a Python 3.11+. Pro instalaci není potřeba pip, ElevenLabs účet ani API klíč. Počítejte přibližně s 500 MB volného místa pro zálohu a pracovní PACK.

Podporu určuje přesný obsah `data/audio_cn.pack`, nikoli jen název vydání launcheru:

| Vlastnost | Podporovaný originál |
|---|---|
| SHA-256 | `d6ee7ec4c4422276d9caba7013f46662a980955c138be13f653b58992ad876ad` |
| Velikost | 244 019 593 B |
| Položky | 16 545 |
| Runtime slot | `audio_cn.pack` s očekávaným původním anglickým obsahem |

Jiný hash installer odmítne. Čínský soubor `.pack.orig` není automaticky podporovaný základ.

## Instalace

Stáhněte nebo naklonujte projekt mimo složku hry. V PowerShellu přejděte do jeho kořene a zavřete hru i launcher. Příklad cesty upravte podle své instalace; jde o složku obsahující `data`.

```powershell
.\scripts\install.ps1 -GamePath "D:\Games\TotalWar_Arena" -WhatIf
.\scripts\install.ps1 -GamePath "D:\Games\TotalWar_Arena"
.\scripts\verify.ps1 -GamePath "D:\Games\TotalWar_Arena"
```

Installer zkontroluje originál, uchová ověřenou zálohu, sestaví a ověří nový PACK a teprve potom vymění `data/audio_cn.pack`. Výsledný SHA-256 je `3405389faa3c5336e6635189e033e117144605356d9042a34f797b2c576df32b`.

Obnova originálu:

```powershell
.\scripts\restore.ps1 -GamePath "D:\Games\TotalWar_Arena"
```

Záloha zůstává v `<GamePath>/.twa-czech-dubbing/backups/audio_cn.original.pack`. Neodstraňujte ji před odinstalací. Příkazy samy hru ani launcher nespouštějí.

## Pokud něco nefunguje

- **Unsupported PACK SHA-256:** ověřte správnou instalaci a její původní soubory. Nepřejmenovávejte náhodný PACK na podporovaný a neupravujte očekávaný hash.
- **Game/launcher is running:** zavřete oba procesy a příkaz opakujte.
- **Python není nalezen:** nainstalujte Python 3.11+ a otevřete nový PowerShell; lze předat `-PythonExecutable` s cestou k interpretu.
- **PowerShell blokuje skript:** použijte postup v [uživatelském návodu](docs/USER_GUIDE.md). Neměňte globální bezpečnostní nastavení kvůli projektu.
- **Po spuštění launcheru znovu angličtina:** zavřete ho a spusťte `verify.ps1`. Launcher může soubory obnovit; konkrétní budoucí chování není zaručeno.

## Struktura a vývoj

```text
data/commanders/hannibal/   manifest, 305 hlášek, inventory a QA metadata
replacements/hannibal/wem/  305 finálních českých WEMů
scripts/                   install, verify, restore pro Windows
tools/                     obecný PACK, WEM, inventory, offline TTS planning
tests/                     ochranné a integrační testy
docs/                      uživatelský i technický postup
third_party/               licence převzaté logiky
```

[USER_GUIDE](docs/USER_GUIDE.md) · [DEVELOPMENT](docs/DEVELOPMENT.md) · [TECHNICAL_PIPELINE](docs/TECHNICAL_PIPELINE.md) · [ADDING_COMMANDER](docs/ADDING_COMMANDER.md) · [AGENTS](AGENTS.md)

Leonidas a Germanicus jsou možné další kroky; jejich dabing zatím nevznikl. Nástroje vybírají data parametrem `--commander` / `-Commander`. Každý další commander potřebuje vlastní schválený manifest a náhrady. Současné releasy se instalují jednotlivě; automatické kombinování commanderů není implementované.
