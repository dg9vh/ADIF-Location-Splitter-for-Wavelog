import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import adif_io
import requests
import os
import io
import configparser
from collections import defaultdict

# ----------------------------------------
# KLASSE: RESOLUTIONSDIALOG
# ----------------------------------------
class ResolutionDialog(simpledialog.Dialog):
    """
    Ein einfacher Dialog zur Auswahl einer Wavelog ID bei Mehrdeutigkeit.
    """
    def __init__(self, parent, callsign_grid, conflicting_stations):
        # conflicting_stations: Dict {id: profile_name}
        self.callsign_grid = callsign_grid
        self.conflicting_stations = conflicting_stations 
        self.selected_id = tk.StringVar(parent)
        self.result_id = None
        
        super().__init__(parent, title=f"Auflösung für {callsign_grid}")


    def body(self, master):
        tk.Label(master, text=f"Für {self.callsign_grid} existieren mehrere Profile. Wählen Sie die Ziel-ID:").pack(pady=5)
        
        # Radio Buttons für bestehende, in Konflikt stehende Stationen
        for id, name in self.conflicting_stations.items():
            tk.Radiobutton(master, 
                           text=f"ID {id} / Profil: '{name}'", 
                           variable=self.selected_id, 
                           value=f"ID_{id}").pack(anchor=tk.W)
            
        # Option für neue Station
        tk.Radiobutton(master, 
                       text="NEU anlegen (Exportiert als neue Datei)", 
                       variable=self.selected_id, 
                       value="NEU").pack(anchor=tk.W, pady=(10, 0))
                       
        # Standard-Auswahl: Erstes Element (zur Sicherheit)
        if self.conflicting_stations:
             first_id = list(self.conflicting_stations.keys())[0]
             self.selected_id.set(f"ID_{first_id}")
        else:
             self.selected_id.set("NEU")

        return master


    def apply(self):
        # Speichert die ausgewählte ID, wenn OK gedrückt wird
        self.result_id = self.selected_id.get()
        
# ----------------------------------------
# ENDE KLASSE RESOLUTIONSDIALOG
# ----------------------------------------


# ----------------------------------------
# KLASSE: DXCCSelectionComboboxDialog
# ----------------------------------------
class DXCCSelectionComboboxDialog(simpledialog.Dialog):
    """
    Ein Dialog mit einer scrollbaren Combobox zur Auswahl der DXCC-Region.
    """
    def __init__(self, parent, callsign_locator, dxcc_data, current_dxcc_id):
        # dxcc_data: Liste der Namen (sorted_names)
        self.callsign_locator = callsign_locator
        self.dxcc_data = dxcc_data # Liste der DXCC-Namen + ID
        self.current_dxcc_id = current_dxcc_id
        self.selected_dxcc_name = tk.StringVar(parent)
        self.result_id = None
        
        super().__init__(parent, title=f"DXCC-Auswahl für {callsign_locator}")

        
    def body(self, master):
        tk.Label(master, text=f"Wählen Sie die DXCC-Region für {self.callsign_locator}:").pack(pady=5)
        
        # 1. Combobox erstellen
        self.combo = ttk.Combobox(master, 
                                  textvariable=self.selected_dxcc_name, 
                                  values=self.dxcc_data, 
                                  state='readonly', 
                                  width=50)
        self.combo.pack(pady=10, fill='x', padx=20)
        
        # 2. Aktuellen Wert setzen
        # Wir müssen den Namen des aktuellen DXCC-ID finden, um ihn vorzuselektieren
        current_name = ""
        for name_id_str in self.dxcc_data:
            # Format: 'Deutschland (ID: 230)'
            if f"(ID: {self.current_dxcc_id})" in name_id_str:
                current_name = name_id_str
                break
        
        self.combo.set(current_name)
        self.combo.focus_set()

        return master


    def apply(self):
        # 1. Ausgewählten String (z.B. 'Germany (ID: 230)') auslesen
        selected_string = self.selected_dxcc_name.get()
        
        # 2. DXCC ID extrahieren: Suche nach der Zahl in den Klammern
        import re
        match = re.search(r'\(ID:\s*(\d+)\)', selected_string)
        
        if match:
            self.result_id = match.group(1)
        else:
            # Fallback, z.B. wenn "N/A (nicht definiert)" gewählt wird
            self.result_id = '0' 

# ----------------------------------------
# ENDE KLASSE DXCCSelectionComboboxDialog
# ----------------------------------------


# ----------------------------------------
# KLASSE: ADIFSplitterApp
# ----------------------------------------
class ADIFSplitterApp:
    
    def __init__(self, master):
        self.master = master
        master.title("ADIF Location Splitter für Wavelog by DG9VH (C) 2025")

        # Konfigurationsvariablen
        self.CONFIG_FILE = 'config.ini'
        self.wavelog_url = ""
        self.wavelog_token = ""
        self.dxcc_csv_path = ""
        
        self.loaded_qso_list = []
        self.location_data = {}
        self.checkbox_status = {}
        self.wavelog_locations = None

        # Zuerst Konfiguration laden, um den gespeicherten DXCC-Pfad zu bekommen
        self.load_config() 

        # --- DXCC / Zonen LOOKUP DATA (aus CSV geladen) ---
        self.dxcc_id_to_name = {}
        self.dxcc_name_to_id = {}
        self.dxcc_combo_list = []
        
        # Sicherstellen, dass der Default-Wert existiert
        self.dxcc_id_to_name['0'] = 'N/A (nicht definiert)'
        self.dxcc_name_to_id['N/A (nicht definiert)'] = '0'
        


        # CQ und ITU Zonen als Listen von Strings
        self.cq_zones = [str(i) for i in range(1, 41)]
        self.itu_zones = [str(i) for i in range(1, 91)]

        # 1. Menü erstellen
        self.create_menu()
        
        # 2. UI-Elemente
        
        # Frame für die Hauptinhalte
        main_frame = tk.Frame(master)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Status-Textfeld
        status_label = tk.Label(main_frame, text="Status-Protokoll:")
        status_label.pack(anchor='w')
        self.status_text = tk.Text(main_frame, height=8, width=70, state=tk.DISABLED)
        self.status_text.pack(fill='x')
        
        # Jetzt die DXCC-Daten laden (nutzt den gerade geladenen Pfad)
        self.load_dxcc_data(initial_load=True) 
        
        # Ergebnistabelle (Treeview)
        table_label = tk.Label(main_frame, text="Standort-Ergebnisse:")
        table_label.pack(anchor='w', pady=(10, 5))
        
        self.create_results_table(main_frame)
        
        # Konfiguration laden
        self.load_config()
        
        # Initialmeldung
        self.log_message("Programm gestartet. Konfiguration geladen.")


    # ----------------------------------------
    # Abschnitt: Konfigurations-Methoden (Unverändert)
    # ----------------------------------------
    def load_config(self):
        """Läd die Konfiguration aus der Datei."""
        config = configparser.ConfigParser()
        # Versuche, die Datei zu lesen (Unterdrücken von Fehlern, falls Datei fehlt)
        config.read(self.CONFIG_FILE) 

        if config.has_section('Wavelog'):
            self.wavelog_url = config.get('Wavelog', 'url', fallback="")
            self.wavelog_token = config.get('Wavelog', 'token', fallback="")
        
        if config.has_section('DXCC'):
            self.dxcc_csv_path = config.get('DXCC', 'csv_path', fallback="")

        # Prüfe, ob Wavelog URL am Ende ein Slash hat
        if self.wavelog_url and not self.wavelog_url.endswith('/'):
            self.wavelog_url += '/'


    def save_config(self):
        """Speichert die Konfiguration in der Datei."""
        config = configparser.ConfigParser()
        
        config['Wavelog'] = {
            'url': self.wavelog_url,
            'token': self.wavelog_token
        }
        
        # NEU: Speichere DXCC CSV Pfad
        config['DXCC'] = {
            'csv_path': self.dxcc_csv_path
        }

        try:
            with open(self.CONFIG_FILE, 'w') as configfile:
                config.write(configfile)
        except Exception as e:
            self.log_message(f"FEHLER beim Speichern der Konfigurationsdatei: {e}")


    def configure_wavelog(self):
        """Öffnet Dialoge zur Eingabe der API-Zugangsdaten und korrigiert die URL."""
        
        # 1. URL abfragen
        url = simpledialog.askstring("Wavelog Konfiguration", 
                                    "Wavelog Basis-URL (z.B. https://example.com/):",
                                    initialvalue=self.wavelog_url)
        
        if url is not None:
            # --- URL-KORREKTUR-LOGIK ---
            url = url.strip()
            if not url.startswith('http'):
                url = 'https://' + url
            url = url.rstrip('/')
            if not url.endswith('/api'):
                url = url + '/api'  
            # --- Ende URL-KORREKTUR-LOGIK ---

            token = simpledialog.askstring("Wavelog Konfiguration", "Wavelog API Token:",
                                            initialvalue=self.wavelog_token, show='*')
            
            if token is not None:
                self.wavelog_url = url
                self.wavelog_token = token
                self.save_config()
                messagebox.showinfo("Erfolg", "API-Daten gespeichert und URL korrigiert zu:\n" + self.wavelog_url)


    def load_dxcc_data(self, initial_load=False):
        """
        Läd die DXCC-Daten aus einer CSV-Datei. 
        Verwendet gespeicherten Pfad bei initial_load oder fragt den Benutzer bei manuellem Aufruf.
        """
        file_path = None
        default_path = 'dxcc_data.csv'
        
        if initial_load:
            # 1. Versuch: Gespeicherter Pfad aus config.ini
            if self.dxcc_csv_path and os.path.exists(self.dxcc_csv_path):
                file_path = self.dxcc_csv_path
                self.log_message(f"Versuche, DXCC-Daten aus Konfigurationspfad zu laden: '{file_path}'...")
            # 2. Versuch: Standard-Pfad im aktuellen Verzeichnis
            elif os.path.exists(default_path):
                file_path = default_path
                self.log_message(f"Versuche, DXCC-Daten aus Standardpfad zu laden: '{file_path}'...")
            else:
                # Still beim Start, keine Aufforderung
                self.log_message("Kein gespeicherter DXCC-Pfad gefunden und 'dxcc_data.csv' fehlt.")
                return 
        else:
            # Manuelles Laden (durch Menü-Klick)
            file_path = filedialog.askopenfilename(
                title="Wählen Sie die DXCC CSV-Datei",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )
            if not file_path:
                self.log_message("Ladevorgang für DXCC-Daten abgebrochen.")
                return

        if not file_path:
            return

        try:
            # Leere die bestehenden Listen, behalte aber den Default-Wert '0'
            self.dxcc_id_to_name = {'0': 'N/A (nicht definiert)'}
            self.dxcc_name_to_id = {'N/A (nicht definiert)': '0'}
            self.dxcc_combo_list = []
            
            loaded_count = 0
            
            with open(file_path, 'r', encoding='utf-8') as f:
                # Wir gehen davon aus, dass die erste Zeile der Header ist
                next(f)
                
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                        
                    # Versuch, mit Komma zu trennen. Wenn das fehlschlägt, versuchen wir Semikolon
                    if ',' in line:
                        separator = ','
                    elif ';' in line:
                        separator = ';'
                    else:
                        self.log_message(f"WARNUNG: Zeile ohne gültiges Trennzeichen übersprungen: {line[:20]}...")
                        continue
                        
                    parts = [p.strip() for p in line.split(separator, 1)]

                    if len(parts) == 2 and parts[0].isdigit():
                        dxcc_id = parts[0]
                        name = parts[1].replace('"', '').strip() # Entferne Anführungszeichen, falls vorhanden
                        
                        if dxcc_id in self.dxcc_id_to_name:
                             # Überspringen von Duplikaten, um '0' (N/A) nicht zu überschreiben
                             continue
                             
                        self.dxcc_id_to_name[dxcc_id] = name
                        self.dxcc_name_to_id[name] = dxcc_id
                        loaded_count += 1
                    else:
                        self.log_message(f"WARNUNG: Ungültiges Datenformat in Zeile: {line[:20]}...")

            # 3. Aktualisiere die Combobox-Liste aus den neu geladenen Daten
            self.dxcc_combo_list = sorted([
                f"{name} (ID: {dxcc_id})" 
                for dxcc_id, name in self.dxcc_id_to_name.items()
            ], key=lambda x: (x != "N/A (ID: 0)", x)) 
            # Sortiert N/A an den Anfang
            
            self.log_message(f"DXCC-Daten erfolgreich geladen. {loaded_count} Einträge verarbeitet.")
            if not initial_load:
                messagebox.showinfo("Erfolg", f"{loaded_count} DXCC-Einträge erfolgreich geladen.")

        except Exception as e:
            error_message = f"FEHLER beim Lesen der DXCC-CSV-Datei: {e}"
            self.log_message(error_message)
            if not initial_load:
                messagebox.showerror("Fehler", error_message)


    # ----------------------------------------
    # Abschnitt: GUI-Methoden
    # ----------------------------------------
    def log_message(self, message):
        """Hilfsfunktion zur Anzeige von Statusmeldungen im Textfeld."""
        self.status_text.config(state=tk.NORMAL)
        self.status_text.insert(tk.END, f"{message}\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)


    def create_menu(self):
        """Erstellt die Menüleiste. (Unverändert)"""
        menubar = tk.Menu(self.master)
        
        # Datei-Menü
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="ADIF-Datei auswählen...", command=self.load_adif_file)
        filemenu.add_command(label="Verarbeitung starten (Checken)", command=self.start_processing)
        filemenu.add_command(label="Markierte Stationen in Wavelog anlegen", command=self.create_new_wavelog_locations)
        filemenu.add_separator()
        filemenu.add_command(label="ADIF-Dateien exportieren (nach ID)", command=self.export_adif_files)
        filemenu.add_separator()
        filemenu.add_command(label="Beenden", command=self.master.quit)
        menubar.add_cascade(label="Datei", menu=filemenu)
        
        # Konfigurations-Menü
        configmenu = tk.Menu(menubar, tearoff=0)
        configmenu.add_command(label="Wavelog API konfigurieren", command=self.configure_wavelog)
        configmenu.add_command(label="DXCC-Liste importieren...", command=lambda: self.load_dxcc_data(initial_load=False))
        menubar.add_cascade(label="Konfiguration", menu=configmenu)
        
        self.master.config(menu=menubar)


    def create_results_table(self, parent_frame):
        """Erstellt das Treeview-Widget mit zusätzlichen Spalten für DXCC, CQ, ITU. (Unverändert)"""
        
        columns = ("#", "Call", "Locator", "QSOs", "Profilname", "DXCC", "CQ", "ITU", "Status", "Wavelog ID")
        self.tree = ttk.Treeview(parent_frame, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.tree.heading(col, text=col)
        
        # Spaltenbreiten setzen (angepasst)
        self.tree.column("#", width=40, anchor='center')
        self.tree.heading("#", text="Neu?")
        self.tree.column("Call", width=80, anchor='center')
        self.tree.column("Locator", width=80, anchor='center')
        self.tree.column("QSOs", width=50, anchor='center')
        self.tree.column("Profilname", width=150, anchor='w') 
        self.tree.column("DXCC", width=50, anchor='center')
        self.tree.column("CQ", width=40, anchor='center')
        self.tree.column("ITU", width=40, anchor='center')
        self.tree.column("Status", width=120, anchor='w')
        self.tree.column("Wavelog ID", width=80, anchor='center')
        
        vsb = ttk.Scrollbar(parent_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        
        vsb.pack(side='right', fill='y')
        self.tree.pack(side="left", fill="both", expand=True)

        # Bindungen hinzufügen
        self.tree.bind('<Button-1>', self.on_item_click)
        self.tree.bind('<Double-1>', self.on_item_double_click)


    def on_item_click(self, event):
        """Behandelt Klicks (Checkbox und Mehrdeutigkeits-Auflösung). (Indexe angepasst)"""
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            return
            
        item_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        
        if not item_id:
             return
             
        current_values = list(self.tree.item(item_id, 'values'))
        
        if column_id == '#1': # Index 0
            
            # Checkbox nur toggeln, wenn es keine UNZUGEOORDNETEN Daten oder unaufgelöste Konflikte sind
            if current_values[8] in ["Unvollständige Daten", "MEHRDEUTIG (Klick zur Auflösung)"]: # Status Index 8
                 self.log_message("HINWEIS: Dieser Eintrag kann nicht zur Neuanlage markiert werden.")
                 return "break"
                 
            current_value = current_values[0]
            new_value = "" if current_value == "X" else "X"
            
            current_values[0] = new_value
            
            self.tree.item(item_id, values=tuple(current_values))
            self.checkbox_status[item_id] = (new_value == "X")
            
            return "break" 
        
        # NEUE LOGIK: Wenn der Nutzer auf die Status-Spalte klickt und diese 'MEHRDEUTIG' ist (Index 8)
        elif column_id == '#9' and current_values[8].startswith("MEHRDEUTIG"):
             self.resolve_ambiguity(item_id, current_values)
             return "break"


    def resolve_ambiguity(self, item_id, current_values):
        """Öffnet den Dialog zur Auflösung der Mehrdeutigkeit und aktualisiert die Tabelle. (Indexe angepasst)"""
        
        call = current_values[1]
        locator = current_values[2]
        location_key = f"{call}|{locator}"
        
        conflicting_stations = self.location_data[location_key].get('conflicting_stations', {})

        dialog = ResolutionDialog(self.master, location_key, conflicting_stations)
        
        if dialog.result_id:
            resolved_id = dialog.result_id
            
            new_values = list(current_values)
            
            if resolved_id == "NEU":
                new_values[9] = "NEU" # Wavelog ID (Index 9)
                new_values[8] = "NEU (Anlegen)" # Status (Index 8)
                new_values[0] = "X" # Checkbox setzen (Index 0)
                self.log_message(f"Mehrdeutigkeit für {location_key} als NEUE Station markiert.")
            else:
                new_id = resolved_id.split('_')[1]
                
                new_profile_name = conflicting_stations.get(new_id, new_values[4])
                
                new_values[9] = new_id # Wavelog ID
                new_values[4] = new_profile_name # Profilname
                new_values[8] = f"Zugewiesen: ID {new_id}" # Status
                new_values[0] = "" # Checkbox entfernen, da existierende ID
                self.log_message(f"Mehrdeutigkeit für {location_key} auf ID {new_id} ({new_profile_name}) aufgelöst.")
            
            self.tree.item(item_id, values=tuple(new_values))
            self.location_data[location_key]['wavelog_id'] = new_values[9]
            self.location_data[location_key]['is_new'] = (new_values[9] == "NEU")


    def on_item_double_click(self, event):
        """Erlaubt das Editieren des Profilnamens, CQ und ITU (Entry) und DXCC (Dialog)."""
        
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
            
        column_id = self.tree.identify_column(event.x)
        column_index = int(column_id.replace('#', '')) - 1
        
        column_name = self.tree.heading(column_id)['text']
        editable_columns = ["Profilname", "DXCC", "CQ", "ITU"]
        
        if column_name not in editable_columns:
            return 
            
        # Prüfe, ob die Zeile unvollständige Daten hat oder MEHRDEUTIG ist (Status Index 8)
        current_values = self.tree.item(item_id, 'values')
        if current_values[8] in ["Unvollständige Daten", "MEHRDEUTIG (Klick zur Auflösung)"]:
             self.log_message("HINWEIS: Dieses Feld kann für Standorte mit unvollständigen Daten oder unaufgelöster Mehrdeutigkeit nicht editiert werden.")
             return
            
        original_value = current_values[column_index]
        
        # Position des Widgets (nur noch für Entry benötigt)
        x, y, width, height = self.tree.bbox(item_id, column_id)

        if column_name == "DXCC":
            # --- LOGIK FÜR DXCC (COMBOBOX-DIALOG) ---
            
            call = current_values[1]
            locator = current_values[2]
            location_key = f"{call}|{locator}"
            
            # 1. Dialog starten
            dialog = DXCCSelectionComboboxDialog(
                self.master, 
                location_key, 
                self.dxcc_combo_list, # Liste der vorformatierten Namen + IDs
                original_value        # Original DXCC ID
            )
            
            # 2. Ergebnis verarbeiten
            new_value = dialog.result_id
            
            if new_value and new_value != original_value:
                
                selected_name = self.dxcc_id_to_name.get(new_value, 'Unbekannt')
                
                # 3. Treeview aktualisieren (Index 5 ist DXCC ID)
                new_values = list(current_values)
                new_values[5] = new_value 
                self.tree.item(item_id, values=tuple(new_values))
                
                # 4. Interne Daten aktualisieren
                if location_key in self.location_data:
                    self.location_data[location_key]['dxcc'] = new_value
                
                self.log_message(f"DXCC für {call}@{locator} auf '{selected_name}' (ID: {new_value}) geändert.")
                
        else:
            # --- BESTEHENDE LOGIK FÜR ENTRY (Profilname, CQ, ITU) ---
            
            entry_edit = ttk.Entry(self.tree, width=len(original_value) + 5)
            entry_edit.insert(0, original_value)
            entry_edit.select_range(0, tk.END)
            entry_edit.focus()
            
            entry_edit.place(x=x, y=y, width=width, height=height)

            def on_edit_finished(event=None):
                new_value = entry_edit.get().strip()
                entry_edit.destroy()
                
                # Spezielle Validierung für CQ, ITU
                if column_name in ["CQ", "ITU"]:
                    if not new_value.isdigit() or new_value == "":
                        messagebox.showwarning("Fehler", f"Bitte geben Sie für {column_name} nur eine Zahl ein (0 für N/A).")
                        new_value = original_value
                    elif column_name == "CQ" and new_value not in self.cq_zones:
                        self.log_message(f"WARNUNG: CQ-Zone {new_value} außerhalb des üblichen Bereichs (1-40).")
                    elif column_name == "ITU" and new_value not in self.itu_zones:
                        self.log_message(f"WARNUNG: ITU-Zone {new_value} außerhalb des üblichen Bereichs (1-90).")
                
                
                if new_value != original_value:
                    new_values = list(current_values)
                    new_values[column_index] = new_value
                    self.tree.item(item_id, values=tuple(new_values))
                    
                    # Interne Datenstruktur aktualisieren
                    location_key = f"{new_values[1]}|{new_values[2]}"
                    if location_key in self.location_data:
                        if column_name == "CQ":
                            self.location_data[location_key]['cqz'] = new_value
                        elif column_name == "ITU":
                            self.location_data[location_key]['ituz'] = new_value

                    self.log_message(f"{column_name} für {new_values[1]}@{new_values[2]} auf '{new_value}' geändert.")


            entry_edit.bind('<Return>', on_edit_finished)
            entry_edit.bind('<FocusOut>', on_edit_finished)
            
    
    def load_adif_file(self):
        """Öffnet einen Dialog zur Auswahl der ADIF-Datei. (Re-inserted)"""
        file_path = filedialog.askopenfilename(
            defaultextension=".adi",
            filetypes=[ 
                ("ADIF alternative", "*.adi"),
                ("ADIF files", "*.adif"),
                ("All files", "*.*")
            ]
        )
        
        if file_path:
            self.log_message(f"Datei ausgewählt: {os.path.basename(file_path)}")
            self.loaded_qso_list = []
            self.tree.delete(*self.tree.get_children())
            self.location_data = {}
            
            try:
                # adif_io.read_from_file gibt eine Liste von QSOs und ein Header-Dictionary zurück.
                self.loaded_qso_list, _ = adif_io.read_from_file(file_path)
                self.log_message(f"Erfolgreich {len(self.loaded_qso_list)} QSOs eingelesen und gespeichert.")
            except Exception as e:
                error_message = f"Fehler beim Lesen der ADIF-Datei: {e}"
                self.log_message(error_message)
                messagebox.showerror("Fehler", error_message)
        else:
            self.log_message("Dateiauswahl abgebrochen.")


    def start_processing(self):
        """Startet den gesamten Prozess. (Re-inserted)"""
        if not self.loaded_qso_list:
            messagebox.showwarning("Achtung", "Bitte zuerst eine ADIF-Datei laden.")
            return

        if not self.wavelog_url or not self.wavelog_token:
            messagebox.showwarning("Achtung", "Bitte zuerst die Wavelog API konfigurieren.")
            return

        self.fetch_all_wavelog_locations()
        
        if self.wavelog_locations is not None:
             self.group_and_process_qsos(self.loaded_qso_list)
        else:
             self.log_message("FEHLER: Konnte Wavelog-Daten nicht laden. Verarbeitung abgebrochen.")

    
    def fetch_all_wavelog_locations(self):
        """Ruft alle Stationsprofile von Wavelog ab. (Ihre Korrektur beibehalten: station_info)"""
        self.log_message("\n-> Lade alle existierenden Wavelog Stationsprofile...")
        
        base_url = self.wavelog_url.rstrip('/') 
        base_host = base_url.split('/api')[0] 
        # ENDPUNKT KORREKTUR: 'station_info' anstelle von 'station_profile'
        search_url = f"{base_host}/index.php/api/station_info/{self.wavelog_token}"
        
        headers = {'Content-Type': 'application/json'}
        
        try:
            response = requests.get(search_url, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()
            
            # PRÜFUNG KORREKTUR: Prüft direkt auf Liste
            if isinstance(data, list):
                self.wavelog_locations = data
                self.log_message(f"-> {len(data)} Stationsprofile erfolgreich geladen.")
                return True
            else:
                self.log_message("FEHLER: API gab keine erwartete Liste von Standorten zurück.")
                return False

        except requests.exceptions.HTTPError as errh:
            status_code = errh.response.status_code
            self.log_message(f"-> HTTP-FEHLER ({status_code}) beim Laden der Profile: {errh}")
        except requests.exceptions.RequestException as err:
            self.log_message(f"-> Allgemeiner Fehler beim Laden der Profile: {err}")
            
        self.wavelog_locations = None
        return False


    def group_and_process_qsos(self, qso_list):
        """
        Gruppiert QSOs, prüft Wavelog und liest DXCC, CQ und ITU Zonen aus. (Indexe angepasst)
        """
        self.log_message("\n--- Starte Analyse und Gruppierung der Standorte ---\n")
        
        self.tree.delete(*self.tree.get_children())
        self.location_data = {}
        
        grouped_qsos = defaultdict(list)
        
        CALL_FIELD = 'STATION_CALLSIGN'
        LOCATOR_FIELD = 'MY_GRIDSQUARE'
        DXCC_FIELD = 'MY_DXCC' 
        CQZ_FIELD = 'MY_CQ_ZONE'
        ITUZ_FIELD = 'MY_ITU_ZONE'
        
        # 1. Gruppierung der QSOs
        unassigned_count = 0
        for qso in qso_list:
            call = qso.get(CALL_FIELD, '').upper()
            locator = qso.get(LOCATOR_FIELD, '').upper()
            
            if call and locator:
                location_key = f"{call}|{locator}"
            else:
                location_key = "UNZUGEOORDNET|FEHLT"
                unassigned_count += 1
                
            grouped_qsos[location_key].append(qso)
            
        self.log_message(f"Gesamtanzahl eindeutiger Standorte gefunden: {len(grouped_qsos) - (1 if unassigned_count > 0 else 0)}")
        if unassigned_count > 0:
             self.log_message(f"WARNUNG: {unassigned_count} QSOs fehlen wichtige Felder.")

        # 2. Anzeige in der Tabelle und API-Prüfung
        for location_key, qsos in grouped_qsos.items():
            
            first_qso = qsos[0]
            
            # Extrahiere und bereinige die neuen Felder
            qso_dxcc = first_qso.get(DXCC_FIELD, '0').strip()
            qso_cq = first_qso.get(CQZ_FIELD, '0').strip()
            qso_itu = first_qso.get(ITUZ_FIELD, '0').strip()
            
            if not qso_dxcc.isdigit() or qso_dxcc == "": qso_dxcc = "0"
            if not qso_cq.isdigit() or qso_cq == "": qso_cq = "0"
            if not qso_itu.isdigit() or qso_itu == "": qso_itu = "0"
            
            
            if location_key == "UNZUGEOORDNET|FEHLT":
                call, locator = "N/A", "N/A"
                is_found_on_api, wavelog_id, profile_name_db, conflicts = False, "N/A", "UNZUGEOORDNET", None
                status_text = "Unvollständige Daten"
                checkbox_value = ""
                profile_name_db = "UNZUGEOORDNET"
            else:
                call, locator = location_key.split('|')
                is_found_on_api, wavelog_id, profile_name_db, conflicts = self.check_wavelog_api_local(call, locator)
                
                if conflicts:
                    status_text = "MEHRDEUTIG (Klick zur Auflösung)"
                    wavelog_id = "KONFLIKT"
                    checkbox_value = ""
                    profile_name_db = ", ".join(conflicts.values())
                elif is_found_on_api:
                    status_text = "Gefunden" 
                    checkbox_value = ""
                else:
                    status_text = "NEU (Anlegen)"
                    checkbox_value = "X"
                    wavelog_id = "NEU"


            # Daten in der Tabelle anzeigen (mit Indexen 0-9)
            item_id = self.tree.insert('', tk.END, values=(
                checkbox_value,  # 0
                call,            # 1
                locator,         # 2
                len(qsos),       # 3
                profile_name_db, # 4 (Profilname/Konfliktliste)
                qso_dxcc,        # 5 (DXCC)
                qso_cq,          # 6 (CQ)
                qso_itu,         # 7 (ITU)
                status_text,     # 8 (Status)
                wavelog_id       # 9 (Wavelog ID)
            ))
            
            self.checkbox_status[item_id] = (checkbox_value == "X")
            
            # Speichere die QSOs und optionalen Felder intern
            self.location_data[location_key] = {
                'call': call,
                'locator': locator,
                'qsos': qsos,
                'wavelog_id': wavelog_id,
                'is_new': (wavelog_id == "NEU"),
                'tree_item_id': item_id,
                'conflicting_stations': conflicts,
                'dxcc': qso_dxcc,
                'cqz': qso_cq,
                'ituz': qso_itu
            }

        self.log_message("Tabelle mit Standorten befüllt.")


    def check_wavelog_api_local(self, callsign, gridsquare):
        """Prüft lokal auf Stationen. (Unverändert)"""
        if not self.wavelog_locations:
            self.log_message("WARNUNG: Lokale Stationsliste ist leer. Überspringe Check.")
            return False, "N/A", "N/A", None

        search_call = callsign.upper()
        search_locator = gridsquare.upper()

        found_matches = {}

        for station in self.wavelog_locations:
            station_call = station.get('station_callsign', '').upper()
            station_locator = station.get('station_gridsquare', '').upper()
            station_profile_name = station.get('station_profile_name', 'Unbekanntes Profil')
            
            if station_call == search_call and station_locator == search_locator:
                station_id = station.get('station_id')
                if station_id:
                    found_matches[str(station_id)] = station_profile_name
                    
        
        count = len(found_matches)
        
        if count == 0:
            return False, "N/A", "N/A", None
        elif count == 1:
            station_id, station_name = list(found_matches.items())[0]
            self.log_message(f"  -> {callsign}@{gridsquare} GEFUNDEN (ID: {station_id}, Profil: {station_name})")
            return True, station_id, station_name, None
        else:
            self.log_message(f"  -> {callsign}@{gridsquare} MEHRDEUTIG! ({count} Profile gefunden)")
            first_id, first_name = list(found_matches.items())[0]
            return True, first_id, first_name, found_matches


    # ----------------------------------------
    # Abschnitt: Weitere Methoden (Unverändert)
    # ----------------------------------------
    def create_new_wavelog_locations(self):
        """
        Sendet POST-Requests zur Erstellung von Stationsprofilen, inkl. DXCC, CQ, ITU. 
        """
        
        if not self.wavelog_url or not self.wavelog_token:
            self.log_message("FEHLER: Wavelog API URL oder Token fehlt. Kann keine Stationen anlegen.")
            return

        # Endpunkt-Korrekur beibehalten
        base_url = self.wavelog_url.rstrip('/') 
        base_host = base_url.split('/api')[0] 
        post_url = f"{base_host}/index.php/api/create_station/{self.wavelog_token}" 
        
        headers = { 'Content-Type': 'application/json' }
        
        items_to_create = []
        
        # 2. Sammle alle zu erstellenden Einträge aus der Tabelle (Index 0: Checkbox, Index 8: Status)
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, 'values')
            
            if values and values[0] == "X" and values[8] not in ["Unvollständige Daten", "MEHRDEUTIG (Klick zur Auflösung)"]: 
                
                data = {
                    'callsign': values[1],
                    'locator': values[2],
                    'profile_name': values[4], 
                    'station_dxcc': values[5],   # Index 5
                    'station_cq': values[6],     # Index 6
                    'station_itu': values[7],    # Index 7
                    'item_id': item_id,
                    'created_successfully': False
                }
                items_to_create.append(data)
                
                new_values = list(values)
                new_values[8] = "Wird erstellt..." # Status (Index 8)
                self.tree.item(item_id, values=tuple(new_values))
            
            elif values and values[8].startswith("MEHRDEUTIG"):
                 self.log_message(f"WARNUNG: Kann Station {values[1]}@{values[2]} nicht anlegen, Mehrdeutigkeit muss zuerst aufgelöst werden.")


        if not items_to_create:
            self.log_message("\nKeine Stationen zum Anlegen markiert.")
            return

        self.log_message(f"\nStarte Erstellung von {len(items_to_create)} neuen Stationsprofilen...")
        
        successfully_created_items = [] 

        # 3. Führe den POST-Request für jeden Eintrag aus
        for item in items_to_create:
            call = item['callsign']
            locator = item['locator']
            profile_name = item['profile_name']
            item_id = item['item_id']
            dxcc = item['station_dxcc']
            cq = item['station_cq']
            itu = item['station_itu']
            
            # Payload mit den neuen Feldern
            payload = [{
                "station_callsign": call,
                "station_gridsquare": locator,
                "station_profile_name": profile_name,
                "station_dxcc": dxcc,
                "station_cq": cq,
                "station_itu": itu
            }]
            
            new_id = "FEHLER"
            status_text = "FEHLER (unbek.)"
            
            try:
                self.log_message(f"  -> POST-Request zum Anlegen für {call}@{locator} (DXCC: {dxcc}, CQ: {cq}, ITU: {itu})...")
                
                response = requests.post(post_url, json=payload, headers=headers, timeout=10)
                response.raise_for_status()

                api_response = response.json() 
                
                if api_response.get('status') == 'success' and 'imported' in api_response.get('message', ''):
                    status_text = "Angelegt (ID wird gesucht)"
                    item['created_successfully'] = True 
                    successfully_created_items.append(item)
                    self.log_message(f"  -> ERFOLG: Station {call}@{locator} angelegt. Suche ID...")
                else:
                    status_text = "FEHLER (kein Erfolg i. Status)"
                    self.log_message(f"  -> FEHLER: POST OK, aber Status nicht 'success'. Response: {api_response}")
                    
            except requests.exceptions.HTTPError as errh:
                status_code = errh.response.status_code
                response_text = errh.response.text.strip()
                status_text = f"HTTP-FEHLER {status_code}"
                self.log_message(f"  -> HTTP-FEHLER ({status_code}) bei Erstellung: {response_text}")
                
            except requests.exceptions.RequestException as err:
                status_text = "VERBINDUNGSFEHLER"
                self.log_message(f"  -> Allgemeiner Fehler bei Erstellung: {err}")
            
            # Aktualisiere Zeile mit Zwischenstatus
            current_values = self.tree.item(item_id, 'values')
            new_values = list(current_values)
            new_values[8] = status_text # Status (Index 8)
            new_values[0] = "" if item['created_successfully'] else "X" 
            self.tree.item(item_id, values=tuple(new_values))

        # 4. Nach der Erstellung alle Profile neu laden und ID suchen
        if successfully_created_items:
            self.log_message("\n--- Starte Suche nach neu erstellten Stations-IDs ---")
            
            self.fetch_all_wavelog_locations() 
            
            for item in successfully_created_items:
                call = item['callsign']
                locator = item['locator']
                profile_name = item['profile_name']
                item_id = item['item_id']
                
                found_id = "NICHT GEFUNDEN"
                
                if self.wavelog_locations:
                    for station in self.wavelog_locations:
                        db_call = station.get('station_callsign', '').upper()
                        db_locator = station.get('station_gridsquare', '').upper()
                        db_name = station.get('station_profile_name', '')
                        
                        if db_call == call.upper() and \
                           db_locator.startswith(locator.upper()[:4]) and \
                           db_name == profile_name:
                            
                            found_id = station.get('station_id', "ID FEHLT")
                            break

                # 5. Finales Update der Zeile
                current_values = self.tree.item(item_id, 'values')
                new_values = list(current_values)
                
                if found_id not in ["NICHT GEFUNDEN", "ID FEHLT"]:
                    final_status = f"ID {found_id} gefunden"
                    self.log_message(f"  -> ID gefunden für {call}@{locator}: {found_id}")
                    # Interne Daten aktualisieren für den Export
                    self.location_data[f"{call}|{locator}"]['wavelog_id'] = str(found_id)
                    self.location_data[f"{call}|{locator}"]['is_new'] = False
                else:
                    final_status = "Anlage OK, ID unklar"
                    found_id = "UNKLARE ID"
                    self.log_message(f"  -> FEHLER: ID konnte nach Neuladen nicht eindeutig gefunden werden.")
                
                new_values[8] = final_status # Status (Index 8)
                new_values[9] = str(found_id) # Wavelog ID (Index 9)
                self.tree.item(item_id, values=tuple(new_values))

        self.log_message("\nAnlegeprozess abgeschlossen.")


    def export_adif_files(self):
        """
        Exportiert die eingelesenen QSOs in separate ADIF-Dateien. 
        """
        if not self.location_data:
            messagebox.showwarning("Export Fehler", "Bitte zuerst eine ADIF-Datei laden und die Verarbeitung starten.")
            return

        export_dir = filedialog.askdirectory(title="Wählen Sie das Exportverzeichnis")
        if not export_dir:
            self.log_message("Export abgebrochen.")
            return
            
        self.log_message(f"\nGewähltes Exportverzeichnis: {export_dir}")

        try:
            os.makedirs(export_dir, exist_ok=True)
            self.log_message(f"Exportverzeichnis erfolgreich erstellt/geprüft.")
        except OSError as e:
            self.log_message(f"SCHWERER FEHLER: Das Exportverzeichnis '{export_dir}' konnte nicht erstellt werden: {e}")
            messagebox.showerror("Export Fehler", "Das Exportverzeichnis konnte nicht erstellt werden. Siehe Status-Protokoll.")
            return
            
        self.log_message("\n--- Starte ADIF-Export nach Wavelog ID ---")
        
        qsos_by_export_key = defaultdict(list)
        
        for location_key, data in self.location_data.items():
            
            wavelog_id = data.get('wavelog_id')
            qsos = data.get('qsos')
            
            item_id = data.get('tree_item_id')
            try:
                profile_name = self.tree.item(item_id, 'values')[4] 
                status_text = self.tree.item(item_id, 'values')[8] # Index 8
            except:
                profile_name = data.get('call', 'NA')
                status_text = "Unbekannt"
            
            
            if status_text.startswith('MEHRDEUTIG'):
                 self.log_message(f"  -> EXPORT ABGEBROCHEN: Standort {location_key} ist mehrdeutig und muss zuerst aufgelöst werden.")
                 continue
            
            
            if location_key == "UNZUGEOORDNET|FEHLT":
                export_key_raw = "UNZUGEOORDNET"
            elif wavelog_id == "NEU":
                export_key_raw = f"NEU_{profile_name}_{data['call']}_{data['locator']}"
            elif wavelog_id and wavelog_id not in ["N/A", "FEHLER", "UNKLARE ID", "KONFLIKT"]:
                export_key_raw = f"ID_{wavelog_id}_{profile_name}_{data['locator']}"
            else:
                export_key_raw = f"KEINE_ID_{profile_name}_{data['call']}_{data['locator']}"
            
            export_key = self.sanitize_filename(export_key_raw)
                
            qsos_by_export_key[export_key].extend(qsos)

        # 2. Schreibe die Dateien (MANUELLE ADIF-GENERIERUNG, Unverändert)
        exported_files_count = 0
        
        def format_adif_field(key, value):
            if value is None or str(value).strip() == "":
                return ""
            content = str(value).strip().upper()
            return f"<{key}:{len(content)}>{content} "

        for export_key, qso_list in qsos_by_export_key.items():
            
            filename = os.path.join(export_dir, f"{export_key}.adi") 
            adif_text = ""
            
            try:
                self.log_message(f"  -> VERSUCHE ZU SCHREIBEN (Manuell): {filename}")
                
                adif_text += "ADIF-EXPORTIERT MIT WAVELOGSTATIONCREATOR\r\n"
                adif_text += f"<PROGRAMID:{len('WavelogStationCreator')}>WavelogStationCreator "
                adif_text += f"<PROGRAMVERSION:{len('1.0')}>1.0\r\n\r\n"
                
                for qso in qso_list:
                    qso['OPERATOR'] = qso.get('STATION_CALLSIGN', '').split('|')[0]
                       
                    qso_record = ""
                    sorted_keys = sorted(qso.keys())

                    for key in sorted_keys:
                        qso_record += format_adif_field(key, qso[key])

                    adif_text += qso_record + "<EOR>\r\n"
                
                adif_text += "<EOT>\r\n"
                
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(adif_text)
                
                self.log_message(f"  -> ERFOLG: {len(qso_list)} QSOs geschrieben in: {os.path.basename(filename)}")
                exported_files_count += 1
                
            except Exception as e:
                self.log_message(f"  -> FEHLER beim manuellen Schreiben von {os.path.basename(filename)}: {e}")

        self.log_message(f"\nADIF-Export abgeschlossen. {exported_files_count} Dateien erstellt.")
        messagebox.showinfo("Export Fertig", f"Der Export ist abgeschlossen. {exported_files_count} Dateien wurden im Verzeichnis '{export_dir}' erstellt.")


    def sanitize_filename(self, text):
        """Ersetzt Leerzeichen und entfernt alle ungültigen Zeichen für Dateinamen. (Unverändert)"""
        text = text.replace(' ', '_')
        sanitized_text = ''.join(c for c in text if c.isalnum() or c in ('_', '-'))
        return sanitized_text
# ----------------------------------------
# ENDE KLASSE: ADIFSplitterApp
# ----------------------------------------


# --- Hauptprogramm ---
if __name__ == "__main__":
    root = tk.Tk()
    app = ADIFSplitterApp(root)
    root.mainloop()
