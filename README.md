# Total War: Arena Czech Dubbing

Český dabing pro **Total War: Arena**, Windows x64. Verze 1.5.0 obsahuje Hannibala (305 hlášek), Spartaka (304), Zhuge Lianga (293), Leonida (257), Scipia Africana (249), Germanica (234) a Julia Caesara (246). Samostatný volitelný modul **Univerzální hlášky** přidává 465 společných mužských i ženských hlášek jednotek. Celý výběr má 2 353 náhrad; tiché placeholdery zůstávají původní.

Potřebujete vlastní podporovanou instalaci hry a přibližně 750 MB volného místa pro zálohu a sestavení. Release obsahuje připravený installer a česká data. Python, Git, API klíč ani další nástroje nejsou k instalaci potřeba.

## Installation

1. Rozbalte celý Windows ZIP verze 1.5.0.
2. Spusťte `TWA-Czech-Dubbing-Installer.exe`.
3. Vyberte složku Total War: Arena a zaškrtněte požadované commandery a případně Univerzální hlášky.
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
| Scipio Africanus CZ | `dc68174cb3aae799113163bd1460d256ff9f7bd4d29ce72bab6fe9f382469f02` |
| Germanicus CZ | `b710d2c43aaf2136ec48eec357aa306c709f17ce46e9b8aa354c8d6057ae0626` |
| Julius Caesar CZ | `47624e843b05ad84f4abbf28deb6097b7627ec65e2692bf9ba43512bb7aabde6` |
| Všech sedm commanderů + Univerzální hlášky | `083a09ded4641b74fbc2f1a6e8bbda5aa346f8a4fbddb034f334ec4f9d0c702b` |

Podporovaný soubor má 244 019 593 B a 16 545 položek. Název launcheru ani jazyk v názvu souboru neurčuje kompatibilitu. Původní herní soubory nejsou součástí projektu ani releasu.

## Vývoj a pokročilé použití

Zdrojový repozitář obsahuje finální české WEMy, metadata, Python/PowerShell tooling, testy a release builder. GUI lze spustit přes `python -B -m tools.installer.gui` s Pythonem 3.11+ a Tk. Pokročilé PowerShell wrappery zůstávají v `scripts/`; jejich zálohy používají starší umístění uvnitř složky hry, popsané v [DEVELOPMENT](docs/DEVELOPMENT.md).

[DEVELOPMENT](docs/DEVELOPMENT.md) · [TECHNICAL_PIPELINE](docs/TECHNICAL_PIPELINE.md) · [ADDING_COMMANDER](docs/ADDING_COMMANDER.md) · [VALIDATION](docs/VALIDATION.md) · [AGENTS](AGENTS.md) · [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)

Dostupné moduly a jejich pořadí v installeru určují manifesty. Výběr má 255 neprázdných stavů: osm samostatných modulů a 247 kombinací s vlastním whole-PACK hashem v `data/releases/`. Metadata kombinací vznikají z canonical originálu dvěma nezávislými výpočty hashe; cílené skutečné PACK buildy ověřují nové samostatné commandery a plnou kombinaci. Release 1.5.0 čeká na manuální herní test; je lokální a nebyl publikován. Technické výsledky jsou v [DEVELOPMENT](docs/DEVELOPMENT.md).
