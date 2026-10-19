# Uživatelský návod

## Instalace

1. Rozbalte **celý** Windows ZIP verze 1.3.0 do vlastní složky.
2. Dvakrát klikněte na `TWA-Czech-Dubbing-Installer.exe`.
3. Vyberte složku Total War: Arena přes **Browse…**. Po ověření checkboxy ukážou skutečně nainstalované hlasy; u originálu budou všechny prázdné.
4. Zaškrtněte požadované commandery, zavřete hru i launcher a klikněte na **Install**.
5. Po zprávě o úspěšné instalaci spusťte hru.

Žádná další konfigurace, Python, Git ani API účet nejsou potřeba. Po rozbalení funguje instalace offline. Potřebujete Windows x64, vlastní podporovanou hru a přibližně 750 MB volného místa; záloha a dočasný soubor mohou být na různých discích.

Vyberte složku obsahující `data`, například `D:\Games\TotalWar_Arena`. Pokud vyberete přímo `data`, installer umí rozpoznat jejího rodiče. Neprohledává celý disk.

## Ověření a opakovaná instalace

Checkboxy určují čekající výběr. Jejich změna pouze aktivuje **Install**; instalace začne až kliknutím na toto tlačítko. Text **Pending** popisuje čekající změny, zatímco ověřený stav a status log stále odpovídají aktuálnímu PACKu. Odškrtnutí všech hlasů nic neobnovuje a **Install** zůstane vypnuté; pro obnovu použijte **Restore Original**.

**Verify** nic ve hře nemění. Zkontroluje podporovanou verzi, integritu herního souboru i dodaných českých dat. Checkboxy nastaví podle skutečně nainstalované kombinace, takže případný čekající výběr zahodí. Totéž se stane po úspěšné instalaci; po **Restore Original** budou všechny checkboxy prázdné.

Je-li stejný dabing už nainstalovaný, tlačítko ukazuje **Installed** a soubor se znovu nepřepisuje. **Restore Original** zůstává dostupné. Pokud launcher vrátí přesný podporovaný originál, můžete dabing znovu nainstalovat.

## Záloha a obnova

Installer si pro každou instalaci hry drží nejvýše jednu ověřenou kopii čistého originálu (244 019 593 bajtů, asi 233 MiB):

```text
%LOCALAPPDATA%\TWA-Czech-Dubbing\backup\<installation-id>\audio_cn.pack
```

Vedle něj je `audio_cn.json` s kontrolním otiskem, datem, cestou hry, zdrojem a verzí modu. Každá instalace má vlastní podsložku. Platná záloha se při opakované instalaci nepřepisuje. Rozbalený ZIP můžete po instalaci odstranit; zálohu ponechte.

Zálohu installer vytvoří automaticky před prvním zápisem, ale jen z prokazatelně čistého originálu: z aktuálního `data\audio_cn.pack`, pokud je originální, nebo z existujícího herního souboru `data\audio_en.pack` (případně `data\audio_cn.pack.orig`). Takový soubor se použije, jen když má přesně SHA-256 podporovaného originálu a projde kontrolou RSA i struktury. Launcher totiž do slotu `audio_cn.pack` kopíruje anglické audio. Tyto herní soubory installer pouze čte. Z již upraveného PACKu zálohu nikdy nevytvoří.

Pro návrat k původním hlasům znovu rozbalte/spusťte installer, vyberte stejnou hru, zavřete hru i launcher a klikněte na **Restore Original**. Potvrďte obnovu. Záloha zůstane zachovaná.

Bez dostupného originálu lze dabing dál **přidávat**. Z ověřeného známého stavu (například Hannibal) installer v dočasné kopii doplní jen nově vybrané commandery. Před zápisem vyžaduje přesný SHA-256 ověřené cílové kombinace, RSA a nulový rozdíl mimo přidané položky; Hannibal → Hannibal + Spartacus tak dá 609 náhrad a Hannibal + Spartacus + Zhuge Liang → všichni čtyři 1159. **Odebrání** nainstalovaného commandera a **Restore Original** ale potřebují původní data. Bez nich jsou vypnuté, GUI zobrazí „Original backup required to remove installed dubbing“ a hra se nezmění. Poškozenou zálohu installer nikdy nepoužije ani nepřepíše a zablokuje všechny zápisy; zkontrolujte ji nebo ji odstraňte ručně. Installer neumí původní herní data stáhnout. Používejte stejný účet Windows, pod kterým byla záloha vytvořena. Starší vývojové PowerShell skripty mají odlišné umístění zálohy; viz [DEVELOPMENT](DEVELOPMENT.md).

## Řešení chyb

| Zpráva / situace | Co udělat |
|---|---|
| Unsupported audio_cn.pack version | Tato verze není podporovaná. Herní audio se nezměnilo. Ověřte správnou instalaci; kontrolu verze neobcházejte. |
| Select the Total War: Arena folder… | Vyberte složku, která obsahuje `data/audio_cn.pack`. |
| Game or launcher is currently running | Zavřete hru i launcher včetně jeho běhu na pozadí a zkuste znovu. Installer procesy neukončuje. |
| Cannot inspect game/launcher processes | Zkontrolujte dostupnost Windows PowerShellu a oprávnění. Instalace bez této kontroly nepokračuje. |
| Original backup required to remove installed dubbing / Cannot remove … | Přidávat dabing lze dál. Pro odebrání je nutný ověřený originál (záloha nebo čistý `data\audio_en.pack`). Herní audio se nezměnilo. |
| Original game audio is not available. Restore cannot be performed safely. | Obnova bez ověřeného originálu se neprovede. Herní audio se nezměnilo. |
| The original game audio backup is invalid | Záloha je poškozená. Installer ji nepoužije ani nepřepíše a nic nezapíše. |
| Installation validation failed | Dočasná kopie neprošla kontrolou; hra se nezměnila. Znovu rozbalte celý release. |
| Replacement hash/size mismatch | Znovu stáhněte a rozbalte celý nepoškozený release. |
| Write access denied | Zavřete installer, klikněte pravým na EXE a vyberte **Spustit jako správce**. Vyberte znovu hru. Použijte stejný účet Windows. |
| Game file changed during build | Soubor mezitím změnil jiný program. Zavřete launcher a spusťte Verify. |
| Junctions/symlinks are unsupported | Vyberte běžnou fyzickou složku hry bez přesměrování. |

Technický stav je vidět v okně. Stručné logy jsou v `%LOCALAPPDATA%\TWA-Czech-Dubbing\logs\`. Neobsahují API klíče ani prostředí procesu. Během instalace nebo obnovy počkejte na dokončení.

Pokud launcher opraví nebo aktualizuje hru, spusťte po jeho zavření **Verify**. Dabing používá podporovaný hlasový soubor `audio_cn.pack`, přestože jeho původní zvuky jsou anglické; nepřejmenovávejte jiné soubory podle jazyka.

## Výběr commanderů ve verzi 1.3.0

ZIP verze 1.3.0 nabízí v tomto pořadí Hannibala (305 hlášek), Spartaka (304), Zhuge Lianga (293) a Leonida (257) v libovolné z 15 kombinací; všichni čtyři dohromady dají 1159 náhrad. Při změně výběru zaškrtněte commandery a klikněte na **Install**. Je-li k dispozici ověřený originál, installer sestaví celý nový výběr od začátku; přidání i odebrání commandera tak dává přesně vybranou sadu. Bez originálu je možné jen přidávání, jehož výsledek je bajtově shodný. **Restore Original** obnoví původní PACK, pokud installer má ověřený originál. Artefakt je zatím lokální release candidate a nebyl publikován.

**Upgrade z verze 1.2.0:** spusťte nový installer a vyberte stejnou hru. Po ověření budou zaškrtnutí Hannibal, Spartacus a Zhuge Liang, Leonidas zůstane prázdný. Zaškrtněte Leonida (nic se ještě nezapíše) a klikněte na **Install**. S ověřenou zálohou i bez ní vznikne stejný PACK se všemi čtyřmi commandery. Odebrání kteréhokoli commandera později vyžaduje ověřený originál.
