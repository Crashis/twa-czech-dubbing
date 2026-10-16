# Total War: Arena Czech Dubbing

Český dabing pro **Total War: Arena**, Windows x64. **Hannibal: 305 / 305 mluvených hlášek.** Všech 16 tichých placeholderů zůstává původních; sdílené hlášky se nemění.

Potřebujete vlastní podporovanou instalaci hry a přibližně 750 MB volného místa pro zálohu a sestavení. Release obsahuje připravený installer a česká data. Python, Git, API klíč ani další nástroje nejsou k instalaci potřeba.

## Installation

1. Stáhněte nejnovější Windows ZIP ze sekce **Releases** tohoto projektu.
2. Rozbalte celý ZIP.
3. Spusťte `Install.bat` nebo `TWA-Czech-Dubbing-Installer.exe`.
4. Vyberte složku Total War: Arena a zavřete hru i launcher.
5. Klikněte na **Install Czech Dubbing**. Po dokončení můžete spustit hru.

**Verify** zkontroluje instalaci, **Restore Original** obnoví původní audio. Záloha zůstává v `%LOCALAPPDATA%\TWA-Czech-Dubbing\backup\<installation-id>\audio_cn.pack`, nezávisle na staženém ZIPu. Podrobnosti a řešení chyb: [uživatelský návod](docs/USER_GUIDE.md).

Installer nejprve ověří podporovanou verzi, česká data a zálohu. Nový soubor sestaví a celý ověří dočasně, teprve potom jej atomicky nainstaluje. Neznámou verzi hry odmítne.

## Podporovaná verze

| Soubor | SHA-256 |
|---|---|
| Původní `data/audio_cn.pack` | `d6ee7ec4c4422276d9caba7013f46662a980955c138be13f653b58992ad876ad` |
| Hannibal CZ 1.0.0 | `3405389faa3c5336e6635189e033e117144605356d9042a34f797b2c576df32b` |

Podporovaný soubor má 244 019 593 B a 16 545 položek. Název launcheru ani jazyk v názvu souboru neurčuje kompatibilitu. Původní herní soubory nejsou součástí projektu ani releasu.

## Vývoj a pokročilé použití

Zdrojový repozitář obsahuje finální české WEMy, metadata, Python/PowerShell tooling, testy a release builder. GUI lze spustit přes `python -B -m tools.installer.gui` s Pythonem 3.11+ a Tk. Pokročilé PowerShell wrappery zůstávají v `scripts/`; jejich zálohy používají starší umístění uvnitř složky hry, popsané v [DEVELOPMENT](docs/DEVELOPMENT.md).

[DEVELOPMENT](docs/DEVELOPMENT.md) · [TECHNICAL_PIPELINE](docs/TECHNICAL_PIPELINE.md) · [ADDING_COMMANDER](docs/ADDING_COMMANDER.md) · [VALIDATION](docs/VALIDATION.md) · [AGENTS](AGENTS.md) · [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)

Dostupné commandery určuje manifest. Dnes release obsahuje Hannibala; další hlasová data zatím nejsou připravena. Budoucí kombinace vyžadují kontrolu konfliktů a samostatně ověřený společný release hash.
