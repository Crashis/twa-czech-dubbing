# Total War: Arena Czech Dubbing

Český dabing pro **Total War: Arena**, Windows x64. Verze 1.3.0 obsahuje Hannibala (305 hlášek), Spartaka (304), Zhuge Lianga (293) a Leonida (257) v libovolné kombinaci; všichni čtyři dohromady mají 1159 hlášek. Všech 16 Hannibalových tichých placeholderů zůstává původních; sdílené hlášky se nemění.

Potřebujete vlastní podporovanou instalaci hry a přibližně 750 MB volného místa pro zálohu a sestavení. Release obsahuje připravený installer a česká data. Python, Git, API klíč ani další nástroje nejsou k instalaci potřeba.

## Installation

1. Rozbalte celý Windows ZIP verze 1.3.0.
2. Spusťte `TWA-Czech-Dubbing-Installer.exe`.
3. Vyberte složku Total War: Arena a zaškrtněte commandery.
4. Zavřete hru i launcher a klikněte na **Install**.
5. Po dokončení spusťte hru.

**Verify** zkontroluje instalaci, **Restore Original** obnoví původní audio. Záloha zůstává v `%LOCALAPPDATA%\TWA-Czech-Dubbing\backup\<installation-id>\audio_cn.pack`, nezávisle na staženém ZIPu. Podrobnosti a řešení chyb: [uživatelský návod](docs/USER_GUIDE.md).

Installer nejprve ověří podporovanou verzi, česká data a dostupnost ověřeného originálu. Nový soubor sestaví a celý ověří dočasně, teprve potom jej atomicky nainstaluje. Neznámou verzi hry odmítne. Bez zálohy lze dabing jen přidávat; odebrání a obnova vyžadují ověřený originál. Upgrade z verze 1.2.0 (Hannibal + Spartacus + Zhuge Liang) na všechny čtyři commandery proto funguje i bez zálohy: stačí zaškrtnout Leonida a kliknout na **Install**.

## Podporovaná verze

| Soubor | SHA-256 |
|---|---|
| Původní `data/audio_cn.pack` | `d6ee7ec4c4422276d9caba7013f46662a980955c138be13f653b58992ad876ad` |
| Hannibal CZ | `3405389faa3c5336e6635189e033e117144605356d9042a34f797b2c576df32b` |
| Spartacus CZ | `743b7e5677796d306b715857742dd900341e9ad4484c48f315f2a3e6c719cf35` |
| Zhuge Liang CZ | `9afa0f8b7b0cb24564c54c6c6aa2f7c577a53f32db41a50125ab3fe1ef15ecf6` |
| Leonidas CZ | `f121b2c73ea25015e4ade07637d50365e0e9d4cde9ce0e2ce174cf407e51a041` |
| Všichni čtyři CZ | `1d5401f6ec6d92dc7eecf240a45151c00bb8ed593a83175426a347ead7e23324` |

Podporovaný soubor má 244 019 593 B a 16 545 položek. Název launcheru ani jazyk v názvu souboru neurčuje kompatibilitu. Původní herní soubory nejsou součástí projektu ani releasu.

## Vývoj a pokročilé použití

Zdrojový repozitář obsahuje finální české WEMy, metadata, Python/PowerShell tooling, testy a release builder. GUI lze spustit přes `python -B -m tools.installer.gui` s Pythonem 3.11+ a Tk. Pokročilé PowerShell wrappery zůstávají v `scripts/`; jejich zálohy používají starší umístění uvnitř složky hry, popsané v [DEVELOPMENT](docs/DEVELOPMENT.md).

[DEVELOPMENT](docs/DEVELOPMENT.md) · [TECHNICAL_PIPELINE](docs/TECHNICAL_PIPELINE.md) · [ADDING_COMMANDER](docs/ADDING_COMMANDER.md) · [VALIDATION](docs/VALIDATION.md) · [AGENTS](AGENTS.md) · [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)

Dostupné commandery a jejich pořadí v installeru určují manifesty. Každá z 15 kombinací má samostatně ověřený hash výsledného PACKu v `data/releases/`. Hannibal, Spartacus a Zhuge Liang prošli podle potvrzení uživatele testem ve hře; Leonidas na lidský test ve hře teprve čeká. Artefakt v1.3.0 je zatím lokální release candidate; nebyl publikován. Technické výsledky jsou v [DEVELOPMENT](docs/DEVELOPMENT.md).
