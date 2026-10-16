# Uživatelský návod

## Instalace

1. Stáhněte Windows release ZIP ze sekce Releases projektu.
2. Rozbalte **celý** ZIP do vlastní složky.
3. Dvakrát klikněte na `Install.bat` nebo `TWA-Czech-Dubbing-Installer.exe`.
4. Pomocí **Browse…** vyberte složku Total War: Arena. Installer může známou složku nabídnout automaticky.
5. Zavřete hru i launcher, vyberte Hannibala a klikněte na **Install Czech Dubbing**.
6. Po zprávě o úspěšné instalaci můžete spustit hru.

Žádná další konfigurace, Python, Git ani API účet nejsou potřeba. Po rozbalení funguje instalace offline. Potřebujete Windows x64, vlastní podporovanou hru a přibližně 750 MB volného místa; záloha a dočasný soubor mohou být na různých discích.

Vyberte složku obsahující `data`, například `D:\Games\TotalWar_Arena`. Pokud vyberete přímo `data`, installer umí rozpoznat jejího rodiče. Neprohledává celý disk.

## Ověření a opakovaná instalace

**Verify** nic ve hře nemění. Zkontroluje podporovanou verzi, integritu herního souboru i dodaných českých dat. Po instalaci zobrazí, že Hannibal CZ je správně nainstalovaný.

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
