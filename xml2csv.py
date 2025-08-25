#!/usr/bin/env python3
"""
Converte file XML delle fatture gas in formato CSV usando solo librerie standard.
Versione: 0.1.4
Build: 20250825-1600
"""

import xml.etree.ElementTree as ET
import csv
import os
import glob
import sys
import argparse
from pathlib import Path
import datetime
import time


# Costanti globali
DEFAULT_OUTPUT_FOLDER = "xml2csv_output"

CSV_FIELDNAMES = [
    'nome_file', 'data_creazione', 'numero_sequenza',
    'mittente_ragione_sociale', 'mittente_partita_iva',
    'numero_fattura', 'data_emissione',
    'codice_pdr', 'remi_pool',
    'data_inizio', 'data_fine', 'tipo_movimento',
    'componente_tariffaria', 'quota', 'scaglione',
    'quantita', 'imponibile'
]

EMPTY_IMPORT_FIELDS = {
    'data_inizio': '', 'data_fine': '', 'tipo_movimento': '',
    'componente_tariffaria': '', 'quota': '', 'scaglione': '',
    'quantita': '', 'imponibile': ''
}

EMPTY_PDR_FIELDS = {
    'codice_pdr': '', 'remi_pool': '', **EMPTY_IMPORT_FIELDS
}


def filter_csv_rows(csv_rows, grep_filter):
    """Filtra le righe CSV in base ai criteri specificati"""
    if not grep_filter:
        return csv_rows
    
    # Divide i filtri per virgola (logica OR)
    filters = [f.strip() for f in grep_filter.split(',') if f.strip()]
    
    if not filters:
        return csv_rows
    
    filtered_rows = []
    
    for row in csv_rows:
        # Combina tutti i valori della riga in una stringa per la ricerca
        row_text = ' '.join(str(value) for value in row.values()).lower()
        
        # Applica logica OR: se almeno un filtro matcha, includi la riga
        for filter_term in filters:
            filter_term = filter_term.lower()
            if filter_term in row_text:
                filtered_rows.append(row)
                break  # Match trovato, passa alla riga successiva
    
    return filtered_rows


def get_current_timestamp(format_type='log'):
    """Genera timestamp nel formato richiesto"""
    now = datetime.datetime.now()
    if format_type == 'log':
        return now.strftime('%Y-%m-%d %H:%M:%S')
    elif format_type == 'filename':
        return now.strftime('%Y%m%d_%H%M%S')
    elif format_type == 'consolidated':
        return now.strftime('%Y%m%d-%H%M%S')
    return now


def is_valid_xml_file(file_path):
    """Verifica se il file è un XML valido"""
    return (file_path and file_path.lower().endswith('.xml') and
            os.path.isfile(file_path))


def find_xml_files(input_path, recursive=False):
    """Trova tutti i file XML nella cartella, opzionalmente in modo ricorsivo"""
    if recursive:
        # Ricerca ricorsiva usando **/*.xml
        xml_files = glob.glob(os.path.join(input_path, "**", "*.xml"), 
                             recursive=True)
    else:
        # Ricerca solo nella cartella principale
        xml_files = glob.glob(os.path.join(input_path, "*.xml"))
    
    return sorted(xml_files)


def get_text_safe(element, tag_name):
    if element is None:
        return ''
    found = element.find(tag_name)
    return found.text if found is not None else ''


def extract_data(root, xml_filename):
    testata = root.find('TestataFlusso')
    mittente = root.find('Mittente')
    fattura = root.find('Fattura')
    dettagli_pdr = root.find('DettagliPDR')
    
    common_data = {
        'nome_file': xml_filename,
        'data_creazione': get_text_safe(testata, 'DataCreazione'),
        'numero_sequenza': get_text_safe(testata, 'NumeroSequenza'),
        'mittente_ragione_sociale': get_text_safe(mittente, 'RagioneSociale'),
        'mittente_partita_iva': get_text_safe(mittente, 'PartitaIVA'),
        'numero_fattura': get_text_safe(fattura, 'Numero'),
        'data_emissione': get_text_safe(fattura, 'DataEmissione')
    }
    
    rows = []
    if dettagli_pdr is not None:
        for dettaglio in dettagli_pdr.findall('DettaglioPDR'):
            pdr_data = {
                'codice_pdr': get_text_safe(dettaglio, 'CodicePDR'),
                'remi_pool': get_text_safe(dettaglio, 'REMIPool')
            }
            
            importi = dettaglio.find('Importi')
            if importi is not None:
                for importo in importi.findall('Importo'):
                    row = {**common_data, **pdr_data}
                    row.update({
                        'data_inizio': get_text_safe(importo, 'DataInizio'),
                        'data_fine': get_text_safe(importo, 'DataFine'),
                        'tipo_movimento': get_text_safe(importo, 'TipoMovimento'),
                        'componente_tariffaria': get_text_safe(importo, 'ComponenteTariffaria'),
                        'quota': get_text_safe(importo, 'Quota'),
                        'scaglione': get_text_safe(importo, 'Scaglione'),
                        'quantita': get_text_safe(importo, 'Quantita'),
                        'imponibile': get_text_safe(importo, 'Imponibile')
                    })
                    rows.append(row)
            else:
                row = {**common_data, **pdr_data}
                row.update(EMPTY_IMPORT_FIELDS)
                rows.append(row)
    else:
        common_data.update(EMPTY_PDR_FIELDS)
        rows.append(common_data)
    
    return rows



def create_log_filename():
    return f"xml2csv_{get_current_timestamp('filename')}.log.csv"


def write_log_entry(log_file_path, file_xml, file_csv, job_ts,
                    conversion_time, confirmation, notes=''):
    log_exists = os.path.exists(log_file_path)
    
    with open(log_file_path, 'a', newline='', encoding='utf-8-sig') as logfile:
        fieldnames = ['file_xml', 'file_csv', 'job_ts',
                      'conversion_time', 'confirmation', 'notes']
        writer = csv.DictWriter(logfile, fieldnames=fieldnames, delimiter=';')
        
        if not log_exists:
            writer.writeheader()
        
        writer.writerow({
            'file_xml': file_xml,
            'file_csv': file_csv,
            'job_ts': job_ts,
            'conversion_time': f"{conversion_time:.3f}".replace('.', ','),
            'confirmation': confirmation,
            'notes': notes
        })


def process_single_xml_file(xml_file, csv_filename, log_file_path,
                            current_num=None, total_num=None,
                            grep_filter=None):
    """Processa un singolo file XML e restituisce le righe CSV"""
    xml_filename = os.path.basename(xml_file)
    file_start_time = time.time()
    file_job_ts = get_current_timestamp('log')
    
    try:
        if current_num and total_num:
            print(f"Processando {current_num}/{total_num}: {xml_filename}")
        else:
            print(f"Processando: {xml_filename}")
            
        tree = ET.parse(xml_file)
        root = tree.getroot()
        csv_rows = extract_data(root, xml_filename)
        
        # Applica filtro se specificato
        if grep_filter:
            original_count = len(csv_rows)
            csv_rows = filter_csv_rows(csv_rows, grep_filter)
            if current_num and total_num:
                print(f"  Filtrate: {len(csv_rows)}/{original_count} righe")
        
        file_conversion_time = time.time() - file_start_time
        write_log_entry(log_file_path, xml_filename, csv_filename,
                        file_job_ts, file_conversion_time, 1)
        
        return csv_rows, len(csv_rows)
        
    except Exception as e:
        file_conversion_time = time.time() - file_start_time
        error_msg = f"Errore in {xml_filename}: {str(e)}"
        print(f"ERRORE: {error_msg}")
        write_log_entry(log_file_path, xml_filename, csv_filename,
                        file_job_ts, file_conversion_time, 0, error_msg)
        return [], 0


def convert_xml_to_csv(xml_file_path, output_folder, log_file_path,
                       suppress_print=False, grep_filter=None):
    xml_filename = os.path.basename(xml_file_path)
    csv_filename = xml_filename.replace('.xml', '.csv')
    csv_path = os.path.join(output_folder, csv_filename)
    
    job_start_time = time.time()
    job_ts = get_current_timestamp('log')
    
    try:
        if not suppress_print:
            print(f"Convertendo: {xml_filename}")
        
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        csv_rows = extract_data(root, xml_filename)
        
        # Applica filtro se specificato
        if grep_filter:
            original_count = len(csv_rows)
            csv_rows = filter_csv_rows(csv_rows, grep_filter)
            if not suppress_print:
                print(f"  Filtrate: {len(csv_rows)}/{original_count} righe")
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDNAMES,
                                    delimiter=';', quoting=csv.QUOTE_NONE)
            writer.writeheader()
            writer.writerows(csv_rows)
        
        conversion_time = time.time() - job_start_time
        if not suppress_print:
            print(f"Creato: {csv_filename} ({conversion_time:.3f}s)")
        write_log_entry(log_file_path, xml_filename, csv_filename,
                        job_ts, conversion_time, 1)
        
    except Exception as e:
        conversion_time = time.time() - job_start_time
        error_msg = str(e)
        print(f"ERRORE nel convertire {xml_filename}: {error_msg}")
        write_log_entry(log_file_path, xml_filename, '',
                        job_ts, conversion_time, 0, error_msg)


def convert_xml_to_csv_onefile(xml_files, output_folder, log_file_path,
                               split_rows=None, grep_filter=None):
    """Converte tutti file XML in un unico CSV con una sola intestazione"""
    
    base_filename = f"xml_multi_{get_current_timestamp('consolidated')}"
    
    job_start_time = time.time()
    total_rows = 0
    processed_files = 0
    all_csv_rows = []
    total_filtered_rows = 0
    
    try:
        # Prima raccogliamo tutti i dati
        for i, xml_file in enumerate(xml_files, 1):
            csv_rows, row_count = process_single_xml_file(
                xml_file, f"{base_filename}.csv", log_file_path,
                i, len(xml_files), grep_filter)
            
            if csv_rows:  # Solo se il file è stato processato con successo
                all_csv_rows.extend(csv_rows)
                total_rows += row_count
                processed_files += 1
                if grep_filter:
                    total_filtered_rows += row_count
        
        # Ora scriviamo i file
        if split_rows and total_rows > split_rows:
            # Modalità split: crea più file
            file_count = 0
            row_start = 0
            
            while row_start < len(all_csv_rows):
                file_count += 1
                row_end = min(row_start + split_rows, len(all_csv_rows))
                chunk_rows = all_csv_rows[row_start:row_end]
                
                csv_filename = f"{base_filename}_{file_count:03d}.csv"
                csv_path = os.path.join(output_folder, csv_filename)
                
                with open(csv_path, 'w', newline='',
                          encoding='utf-8-sig') as csvfile:
                    writer = csv.DictWriter(csvfile,
                                            fieldnames=CSV_FIELDNAMES,
                                            delimiter=';',
                                            quoting=csv.QUOTE_NONE)
                    writer.writeheader()
                    writer.writerows(chunk_rows)
                
                print(f"Creato file {file_count}: {csv_filename} "
                      f"({len(chunk_rows)} righe)")
                
                row_start = row_end
            
            print(f"File diviso in {file_count} parti")
            
        else:
            # Modalità normale: un solo file
            csv_filename = f"{base_filename}.csv"
            csv_path = os.path.join(output_folder, csv_filename)
            
            with open(csv_path, 'w', newline='',
                      encoding='utf-8-sig') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDNAMES,
                                        delimiter=';',
                                        quoting=csv.QUOTE_NONE)
                writer.writeheader()
                writer.writerows(all_csv_rows)
            
            print(f"File consolidato creato: {csv_filename}")
        
        conversion_time = time.time() - job_start_time
        
        print(f"File processati: {processed_files}/{len(xml_files)}")
        print(f"Righe totali: {total_rows}")
        print(f"Tempo totale: {conversion_time:.3f}s")
        
    except Exception as e:
        conversion_time = time.time() - job_start_time
        error_msg = f"Errore nella creazione del file consolidato: {str(e)}"
        print(f"ERRORE: {error_msg}")
        job_ts = get_current_timestamp('log')
        write_log_entry(log_file_path, f"{len(xml_files)}_files", "",
                        job_ts, conversion_time, 0, error_msg)


def process_input(input_path, output_folder, onefile=False, split_rows=None,
                  grep_filter=None, recursive=False):
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_folder = os.path.join(script_dir, "xml2csv_logs")
    Path(log_folder).mkdir(parents=True, exist_ok=True)
    
    log_file_path = os.path.join(log_folder, create_log_filename())
    
    if grep_filter:
        print(f"Filtro attivo: '{grep_filter}'")
    
    if os.path.isfile(input_path):
        if not is_valid_xml_file(input_path):
            print(f"ERRORE: {input_path} non è un file XML valido")
            return
        
        if onefile:
            convert_xml_to_csv_onefile([input_path], output_folder,
                                       log_file_path, split_rows, grep_filter)
        else:
            convert_xml_to_csv(input_path, output_folder, log_file_path,
                               suppress_print=False, grep_filter=grep_filter)
        
    elif os.path.isdir(input_path):
        xml_files = find_xml_files(input_path, recursive)
        
        if not xml_files:
            search_type = "ricorsivamente" if recursive else ""
            print(f"Nessun file XML trovato {search_type} in: {input_path}")
            return
        
        search_info = " (ricerca ricorsiva)" if recursive else ""
        print(f"Trovati {len(xml_files)} file XML da convertire{search_info}")
        
        if onefile:
            convert_xml_to_csv_onefile(xml_files, output_folder, log_file_path,
                                       split_rows, grep_filter)
        else:
            for i, xml_file in enumerate(xml_files, 1):
                print(f"Convertendo {i}/{len(xml_files)}: "
                      f"{os.path.basename(xml_file)}")
                convert_xml_to_csv(xml_file, output_folder, log_file_path,
                                   suppress_print=True,
                                   grep_filter=grep_filter)
    else:
        print(f"ERRORE: Il percorso {input_path} non esiste")
    
    print(f"Log creato: xml2csv_logs/{os.path.basename(log_file_path)}")


def main():
    parser = argparse.ArgumentParser(
        description='Converte file XML delle fatture gas in formato CSV',
        epilog="""
Esempi:
  python xml2csv.py file.xml                               # Singolo file
  python xml2csv.py file.xml -o output/                    # Con output
  python xml2csv.py -f cartella_xml/                       # Cartella
  python xml2csv.py -f cartella_xml/ -o output/            # Con output
  python xml2csv.py -f cartella_xml/ -r                    # Ricerca ricorsiva
  python xml2csv.py -f cartella_xml/ -1                    # Un solo file
  python xml2csv.py -f cartella_xml/ -1 -s 100000          # Split
  python xml2csv.py -f cartella_xml/ -g "TAU1"             # Filtra TAU1
  python xml2csv.py -f cartella_xml/ -g "TAU1,TAU2" -r     # OR logic + ricorsivo
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    
    group.add_argument(
        'file_xml',
        nargs='?',
        help='File XML singolo da convertire'
    )
    
    group.add_argument(
        '-f', '--folder',
        dest='folder_path',
        help='Cartella contenente file XML da convertire'
    )
    
    parser.add_argument(
        '-o', '--output',
        dest='output_folder',
        help=f'Cartella di output (default: {DEFAULT_OUTPUT_FOLDER})'
    )
    
    parser.add_argument(
        '-1', '--onefile',
        action='store_true',
        help='Crea un unico file CSV consolidato con tutti i dati'
    )
    
    parser.add_argument(
        '-s', '--split-csv',
        type=int,
        dest='split_rows',
        metavar='RIGHE',
        help='Divide il file consolidato in chunk di RIGHE righe '
             '(default: 500000, usa solo con --onefile)'
    )
    
    parser.add_argument(
        '-g', '--grep',
        dest='grep_filter',
        metavar='FILTRO',
        help='Filtra le righe che contengono FILTRO (case-insensitive). '
             'Usa virgole per filtri multipli (OR): "testo1,testo2"'
    )
    
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Cerca file XML ricorsivamente nelle sottocartelle'
    )
    
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    args = parser.parse_args()
    
    # Validazione: split-csv richiede onefile
    if args.split_rows and not args.onefile:
        print("ERRORE: L'opzione --split-csv può essere usata solo "
              "con --onefile")
        return
    
    # Se onefile è specificato senza split-csv, usa default 500000
    if args.onefile and args.split_rows is None:
        args.split_rows = 500000
    
    if args.file_xml:
        input_path = args.file_xml
        if not is_valid_xml_file(input_path):
            print(f"ERRORE: {input_path} non è un file XML valido "
                  f"o non esiste")
            return
    elif args.folder_path:
        input_path = args.folder_path
        if not os.path.isdir(input_path):
            print(f"ERRORE: La cartella {input_path} non esiste")
            return
    else:
        parser.print_help()
        return
    
    if args.output_folder:
        output_folder = args.output_folder
    else:
        # Usa sempre la cartella di default per l'output
        output_folder = DEFAULT_OUTPUT_FOLDER
    
    process_input(input_path, output_folder, args.onefile, args.split_rows,
                  args.grep_filter, args.recursive)
    print("Conversione completata!")


if __name__ == "__main__":
    main()
