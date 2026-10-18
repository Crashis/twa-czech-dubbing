# Uživatelský návod

## Instalace

1. Rozbalte **celý** Windows ZIP verze 1.2.0 do vlastní složky.
2. Dvakrát klikněte na `TWA-Czech-Dubbing-Installer.exe`.
3. Vyberte požadované commandery i složku Total War: Arena. Složku lze vybrat přes **Browse…**.
4. Zavřete hru i launcher a klikněte na **Install Czech Dubbing**.
5. Po zprávě o úspěšné instalaci spusťte hru.

Žádná další konfigurace, Python, Git ani API účet nejsou potřeba. Po rozbalení funguje instalace offline. Potřebujete Windows x64, vlastní podporovanou hru a přibližně 750 MB volného místa; záloha a dočasný soubor mohou být na různých discích.

Vyberte složku obsahující `data`, například `D:\Games\TotalWar_Arena`. Pokud vyberete přímo `data`, installer umí rozpoznat jejího rodiče. Neprohledává celý disk.

## Ověření a opakovaná instalace

**Verify** nic ve hře nemění. Zkontroluje podporovanou verzi, integritu herního souboru i dodaných českých dat. Po instalaci zobrazí správně nainstalovanou vybranou kombinaci.

Je-li stejný dabing už nainstalovaný, tlačítko ukazuje **Installed** a soubor se znovu nepřepisuje. **Restore Original** zůstává dostupné. Pokud launcher vrátí přesný podporovaný originál, můžete dabing znovu nainstalovat.

## Záloha a obnova

Originál se před první instalací zkopíruje a ověří do:

```text
%LOCALAPPDATA%\TWA-Czech-Dubbing\backup\<installation-id>\audio_cn.pack
```

Vedle něj je `audio_cn.json` s kontrolním otiskem, datem, cestou hry a verzí modu. Každá instalace má vlastní podsložku. Platná záloha se při opakované instalaci nepřepisuje. Rozbalený ZIP můžete po instalaci odstranit; zálohu ponechte.

Pro návrat k původním hlasům znovu rozbalte/spusťte installer, vyberte stejnou hru, zavřete hru i launcher a klikněte na **Restore Original**. Potvrďte obnovu. Záloha zůstane zachovaná.

Chybějící nebo poškozená záloha obnovu zastaví. Installer neumí původní herní data stáhnout. Používejte stejný účet Windows, pod kterým byla záloha vytvořena. Starší vývojové PowerShell skripty mají odlišné umístění zálohy; viz [DEVELOPMENT](DEVELOPMENT.md).

## Řešení chyb

| Zpráva / situace | Co udělat |
|---|---|
| Unsupported audio_cn.pack version | Tato verze není podporovaná. Herní audio se nezměnilo. Ověřte správnou instalaci; kontrolu verze neobcházejte. |
| Select the Total War: Arena folder… | Vyberte složku, která obsahuje `data/audio_cn.pack`. |
| Game or launcher is currently running | Zavřete hru i launcher včetně jeho běhu na pozadí a zkuste znovu. Installer procesy neukončuje. |
| Cannot inspect game/launcher processes | Zkontrolujte dostupnost Windows PowerShellu a oprávnění. Instalace bez této kontroly nepokračuje. |
| Original backup missing / could not be verified | Obnova se neprovede. Je nutná vlastní ověřená původní záloha. |
| Replacement hash/size mismatch | Znovu stáhněte a rozbalte celý nepoškozený release. |
| Write access denied | Zavřete installer, klikněte pravým na EXE a vyberte **Spustit jako správce**. Vyberte znovu hru. Použijte stejný účet Windows. |
| Game file changed during build | Soubor mezitím změnil jiný program. Zavřete launcher a spusťte Verify. |
| Junctions/symlinks are unsupported | Vyberte běžnou fyzickou složku hry bez přesměrování. |

Technický stav je vidět v okně. Stručné logy jsou v `%LOCALAPPDATA%\TWA-Czech-Dubbing\logs\`. Neobsahují API klíče ani prostředí procesu. Během instalace nebo obnovy počkejte na dokončení.

Pokud launcher opraví nebo aktualizuje hru, spusťte po jeho zavření **Verify**. Dabing používá podporovaný hlasový soubor `audio_cn.pack`, přestože jeho původní zvuky jsou anglické; nepřejmenovávejte jiné soubory podle jazyka.

## Výběr commanderů ve verzi 1.2.0

ZIP verze 1.2.0 nabízí Hannibala, Spartaka a Zhuge Lianga v libovolné kombinaci (jeden, dva nebo všichni tři). Při změně výběru ověřte aktuální stav tlačítkem **Verify** a klikněte na **Install Czech Dubbing**. Installer vždy použije ověřenou zálohu původního PACKu a sestaví celý nový výběr od začátku; přidání i odebrání commandera tak dává přesně vybranou sadu. **Restore Original** obnoví původní PACK. Finální artefakt je zatím lokální release candidate a nebyl publikován.
