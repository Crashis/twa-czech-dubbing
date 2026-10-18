# Total War: Arena Czech Dubbing

Český dabing pro **Total War: Arena**, Windows x64. Verze 1.2.0 obsahuje Hannibala (305 hlášek), Spartaka (304) a Zhuge Lianga (293) v libovolné kombinaci. Všech 16 Hannibalových tichých placeholderů zůstává původních; sdílené hlášky se nemění.

Potřebujete vlastní podporovanou instalaci hry a přibližně 750 MB volného místa pro zálohu a sestavení. Release obsahuje připravený installer a česká data. Python, Git, API klíč ani další nástroje nejsou k instalaci potřeba.

## Installation

1. Rozbalte celý Windows ZIP verze 1.2.0.
2. Spusťte `TWA-Czech-Dubbing-Installer.exe`.
3. Vyberte commandery a složku Total War: Arena.
4. Zavřete hru i launcher a klikněte na **Install Czech Dubbing**.
5. Po dokončení spusťte hru.

**Verify** zkontroluje instalaci, **Restore Original** obnoví původní audio. Záloha zůstává v `%LOCALAPPDATA%\TWA-Czech-Dubbing\backup\<installation-id>\audio_cn.pack`, nezávisle na staženém ZIPu. Podrobnosti a řešení chyb: [uživatelský návod](docs/USER_GUIDE.md).

Installer nejprve ověří podporovanou verzi, česká data a zálohu. Nový soubor sestaví a celý ověří dočasně, teprve potom jej atomicky nainstaluje. Neznámou verzi hry odmítne.

## Podporovaná verze

| Soubor | SHA-256 |
|---|---|
| Původní `data/audio_cn.pack` | `d6ee7ec4c4422276d9caba7013f46662a980955c138be13f653b58992ad876ad` |
| Hannibal CZ | `3405389faa3c5336e6635189e033e117144605356d9042a34f797b2c576df32b` |
| Spartacus CZ | `743b7e5677796d306b715857742dd900341e9ad4484c48f315f2a3e6c719cf35` |
| Zhuge Liang CZ | `9afa0f8b7b0cb24564c54c6c6aa2f7c577a53f32db41a50125ab3fe1ef15ecf6` |

Podporovaný soubor má 244 019 593 B a 16 545 položek. Název launcheru ani jazyk v názvu souboru neurčuje kompatibilitu. Původní herní soubory nejsou součástí projektu ani releasu.

## Vývoj a pokročilé použití

Zdrojový repozitář obsahuje finální české WEMy, metadata, Python/PowerShell tooling, testy a release builder. GUI lze spustit přes `python -B -m tools.installer.gui` s Pythonem 3.11+ a Tk. Pokročilé PowerShell wrappery zůstávají v `scripts/`; jejich zálohy používají starší umístění uvnitř složky hry, popsané v [DEVELOPMENT](docs/DEVELOPMENT.md).

[DEVELOPMENT](docs/DEVELOPMENT.md) · [TECHNICAL_PIPELINE](docs/TECHNICAL_PIPELINE.md) · [ADDING_COMMANDER](docs/ADDING_COMMANDER.md) · [VALIDATION](docs/VALIDATION.md) · [AGENTS](AGENTS.md) · [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)

Dostupné commandery určuje manifest. Každá kombinace má samostatně ověřený hash výsledného PACKu. Hannibal, Spartacus a Zhuge Liang prošli podle potvrzení uživatele testem ve hře. Finální artefakt v1.2.0 je zatím lokální release candidate; nebyl publikován. Technické výsledky jsou v [DEVELOPMENT](docs/DEVELOPMENT.md).
