# Uživatelský návod

## Co potřebujete

Vlastní fungující instalaci Total War: Arena s přesným podporovaným souborem `audio_cn.pack`, Windows, PowerShell 5.1+ a Python 3.11+. Instalace modu nepoužívá ElevenLabs a nevytváří nový dabing. Internet po získání projektu a Pythonu není pro instalaci potřebný.

Rozbalte projekt do vlastní složky mimo herní `data`. V Průzkumníku v této složce otevřete PowerShell. Příkazy v návodu spouštějte z kořene projektu. Žádný příkaz nevyžaduje administrátora, pokud máte právo zapisovat do zvolené instalace. Je potřeba přibližně 500 MB navíc pro zálohu a sestavení.

`GamePath` je složka hry, která přímo obsahuje podsložku `data` a herní soubory. Pokud je PACK v `D:\Games\TotalWar_Arena\data\audio_cn.pack`, zadejte `D:\Games\TotalWar_Arena`, bez koncového `data`.

## Před instalací

Ukončete hru i launcher, včetně launcheru běžícího na pozadí. Installer je neukončuje násilně. Při nemožnosti ověřit procesy skončí bez instalace.

```powershell
python --version
.\scripts\verify.ps1 -GamePath "D:\Games\TotalWar_Arena"
.\scripts\install.ps1 -GamePath "D:\Games\TotalWar_Arena" -WhatIf
```

`verify` přečte soubory a zkontroluje RSA podpis, identitu PACKu a integritu českých náhrad v projektu. `kind: original` označuje podporovaný originál, `kind: modified` finální Hannibal CZ. Při jiném hashi skončí chybou. `-WhatIf` a `-DryRun` kontrolují předpoklady a vypíší plán; nevytvoří zálohu ani pracovní PACK a nemění hru. Plná kontrola sestavení se provede při skutečné instalaci.

Podporovaný originál má 244 019 593 B, 16 545 položek a SHA-256:

```text
d6ee7ec4c4422276d9caba7013f46662a980955c138be13f653b58992ad876ad
```

## Instalace a záloha

```powershell
.\scripts\install.ps1 -GamePath "D:\Games\TotalWar_Arena"
```

Installer nejprve ověří hash a podpis. Původní `audio_cn.pack` uloží do:

```text
<GamePath>/.twa-czech-dubbing/backups/audio_cn.original.pack
```

Existující zálohu nikdy nepřepíše; musí sama odpovídat podporovanému originálu. V pracovní složce `.twa-czech-dubbing/staging` sestaví novou kopii z této zálohy. Vloží přesně 305 českých zvuků, ověří všechny ostatní položky a výsledný hash, znovu zkontroluje procesy a původní stav cíle a poté vymění `data/audio_cn.pack`.

Mění se pouze obsah určených Hannibalových zvukových položek v tomto PACKu. Jejich délky se nemění. Index, hlavička, offsety a podpisový Appendix zůstávají shodné. Tiché placeholdery i sdílené hlášky zůstanou původní. `audio_en.pack`, banky, manifest launcheru a konfigurace jazyka se neupravují.

Kromě nového `audio_cn.pack` vznikne soukromá záloha a dočasná pracovní data v `.twa-czech-dubbing`. Zálohu ponechte. Při opakované instalaci platného modu a přítomnosti platné zálohy příkaz vrátí `ALREADY_INSTALLED`.

## Ověření výsledku

```powershell
.\scripts\verify.ps1 -GamePath "D:\Games\TotalWar_Arena"
```

Pro Hannibal CZ očekávejte `kind: modified`, `RSA: PASS`, 305 náhrad a hash:

```text
3405389faa3c5336e6635189e033e117144605356d9042a34f797b2c576df32b
```

Samostatné `verify` pozná finální release podle celého hashe a ověří také každou náhradu. Údaj 305 změněných položek je v tomto režimu svázaný se známým hashem releasu. Při sestavení probíhá skutečné porovnání všech 16 545 položek s originálem. Technický postup nabízí i samostatné ověření s `--base`.

Batch 04 je offline ověřený. Runtime test Batch 03 potvrdil uživatel; pro Batch 04 se netvrdí nový poslech ani nový test ve hře.

## Odinstalace / návrat k originálu

Zavřete hru i launcher a spusťte:

```powershell
.\scripts\restore.ps1 -GamePath "D:\Games\TotalWar_Arena" -WhatIf
.\scripts\restore.ps1 -GamePath "D:\Games\TotalWar_Arena"
.\scripts\verify.ps1 -GamePath "D:\Games\TotalWar_Arena"
```

Obnova ověří zálohu, připraví její kopii, ověří ji a obnoví `audio_cn.pack`. Záloha zůstává zachovaná. Chybějící nebo poškozená záloha znamená zastavení bez destruktivního kroku. Je-li ve hře už podporovaný originál, příkaz vrátí `ALREADY_ORIGINAL`.

Neznámý aktuální PACK se automaticky nepřepisuje ani při obnově: může patřit jiné verzi nebo jiné úpravě. Nejdříve vyřešte jeho původ. Projekt neumí stáhnout původní herní obsah.

## Běžné chyby

| Zpráva / situace | Postup |
|---|---|
| Missing `<GamePath>/data/audio_cn.pack` | Opravte `GamePath`; nemá končit `data`. |
| Unsupported PACK SHA-256 | Použijte vlastní podporovanou instalaci. Hash v manifestu nepřepisujte jako obcházení kontroly. |
| Game/launcher is running | Ukončete oba a zkontrolujte Správce úloh. |
| Cannot inspect processes | Ověřte dostupnost Windows PowerShellu/CIM a oprávnění. Kontrola se nesmí vypnout kvůli instalaci. |
| Replacement hash/size mismatch | Obnovte nepoškozené soubory projektu. |
| Original backup missing | Obnova se neprovede. Najděte vlastní ověřenou zálohu; nepoužívejte náhodný PACK. |
| Přítomný mod bez zálohy | Installer ho nechá na místě. Obnovte nejprve vlastní podporovaný originál. |
| Přístup odepřen / soubor používá jiný proces | Zavřete související programy a zkontrolujte práva. Zálohu nerušte. |
| Junctions/symlinks unsupported | Použijte běžnou složku hry; přesměrované adresáře jsou záměrně odmítnuté. |

Pokud PowerShell blokuje stažené skripty, po jejich kontrole lze povolit jen konkrétní spuštění:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -GamePath "D:\Games\TotalWar_Arena" -WhatIf
```

Tato volba nemění trvalou execution policy. Python mimo `PATH` lze předat například jako `-PythonExecutable "D:\Tools\Python\python.exe"`.

## Launcher a runtime slot

V ověřeném prostředí se pro funkční dabing používá `audio_cn.pack` s anglickým původním hlasovým obsahem. Název `cn` tedy sám neurčuje skutečný jazyk zvuků. Známý originál je rozpoznán hashem, nikoli příponou `.orig` nebo nastavením `EN`.

Předchozí experiment s úpravou `audio_en.pack` nepřinesl očekávaný runtime výsledek; následný provozní test přes CN slot byl úspěšný. Proto se mod aplikuje do `audio_cn.pack`. Z toho nevyplývá obecné tvrzení, že hra nikdy neotevře `audio_en.pack` ve všech distribucích.

Launcher může při opravě, aktualizaci nebo přepnutí jazyka hlasové soubory nahradit. Po podezřelé změně jej zavřete a spusťte `verify`. Je-li zpět přesný podporovaný originál, lze mod znovu nainstalovat. Je-li hash jiný, zastavte se; tento projekt jeho kompatibilitu neověřil.
