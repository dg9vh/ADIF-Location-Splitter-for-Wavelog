# 🚀 ADIF Location Splitter & Wavelog Station Creator

Dieses Python-Tool wurde entwickelt, um die **Verwaltung von Amateurfunk-Standorten** in großen ADIF-Logs zu optimieren und den Prozess der **Erstellung neuer Stationen in Wavelog** zu automatisieren.

Es löst das Problem, bei dem viele QSOs unter derselben *Hauptrufzeichen-Locator-Kombination* (z.B. DG9VH/P @ JO44) neue Einträge in der Logbuch-Software erfordern.

---

## 🎯 Hauptfunktionalität

| Feature                        | Beschreibung                                                                                                                                                                                      |
|:------------------------------ |:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ADIF-Analyse & Gruppierung** | Liest eine ADIF-Datei und gruppiert alle QSOs automatisch nach der Kombination aus **`CALLSIGN`** und **`GRIDSQUARE`**.                                                                           |
| **Wavelog-Abgleich**           | Ruft die vorhandenen Stationen aus Wavelog (über API) ab, um festzustellen, ob die gefundenen Standortkombinationen bereits existieren (Matching anhand von Rufzeichen und Locator).              |
| **Interaktive Tabelle**        | Zeigt alle erkannten, potenziell neuen Standorte in einer editierbaren Tabelle an. Hier können Sie Profilnamen, **DXCC-Zonen**, CQ/ITU-Zonen und den Erstellungsstatus festlegen.                 |
| **DXCC-Datenpflege**           | Ermöglicht die manuelle Korrektur von **DXCC-IDs** über einen stabilen Dialog, der auf einer **importierbaren CSV-DXCC-Liste** basiert. Der Pfad zur Liste wird in der Konfiguration gespeichert. |
| **API-Automatisierung**        | **Erstellt neue Stationen in Wavelog** (z.B. DG9VH/P-JN49) vollautomatisch über die Wavelog-API unter Verwendung des konfigurierten API-Tokens.                                                   |
| **ADIF-Export**                | Exportiert die ursprünglichen QSOs, gruppiert nach der zugewiesenen Profil-ID, in separate ADIF-Dateien.                                                                                          |

---

## ⚙️ Technologie & Anforderungen

* **Sprache:** Python
* **GUI:** `tkinter` / `ttk` (Standardbibliothek)
* **Backend:** Eine installierte **Wavelog**-Instanz mit aktivierter und konfigurierter API.

### Python-Abhängigkeiten

Das Programm benötigt die folgenden externen Bibliotheken. Installieren Sie diese, falls noch nicht geschehen:
```pip install requests adif-io```

## 💾 Setup & Erste Schritte

1. Konfiguration (config.ini)
   Erstellen Sie eine Datei namens config.ini im Programmverzeichnis und füllen Sie diese mit Ihren Wavelog-Zugangsdaten.

```
[Wavelog]
url = [https://ihre.wavelog.de/](https://ihre.wavelog.de/)
token = IHR_WAWELOG_API_TOKEN

[DXCC]
csv_path = 
(Der csv_path wird automatisch nach dem ersten erfolgreichen Import gespeichert.)
```

2. DXCC-Daten (Optional)
   Um eine vollständige DXCC-Auswahl in der Tabelle zu haben:

Erstellen Sie eine Datei namens dxcc_data.csv im Programmverzeichnis.

Das Format muss ID,Name sein (z.B. 230,Germany).

Alternativ nutzen Sie das Menü Konfiguration -> DXCC-Liste importieren..., um die Datei zu laden.

3. Programmstart
   Starten Sie das Skript und laden Sie Ihre ADIF-Log-Datei über das Menü Datei -> ADIF-Datei auswählen....

```python main.py```

