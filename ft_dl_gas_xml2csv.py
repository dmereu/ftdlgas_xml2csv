#!/usr/bin/env python3
"""
Converte file XML delle fatture gas in formato CSV usando solo librerie standard.
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
                            current_num=None, total_num=None):
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
                       suppress_print=False):
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


def convert_xml_to_csv_onefile(xml_files, output_folder, log_file_path):
    """Converte tutti file XML in un unico CSV con una sola intestazione"""
    
    csv_filename = f"xml_multi_{get_current_timestamp('consolidated')}.csv"
    csv_path = os.path.join(output_folder, csv_filename)
    
    job_start_time = time.time()
    total_rows = 0
    processed_files = 0
    
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDNAMES,
                                    delimiter=';', quoting=csv.QUOTE_NONE)
            writer.writeheader()
            
            for i, xml_file in enumerate(xml_files, 1):
                csv_rows, row_count = process_single_xml_file(
                    xml_file, csv_filename, log_file_path, i, len(xml_files))
                
                if csv_rows:  # Solo se il file è stato processato con successo
                    writer.writerows(csv_rows)
                    total_rows += row_count
                    processed_files += 1
        
        conversion_time = time.time() - job_start_time
        
        print(f"File consolidato creato: {csv_filename}")
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


def process_input(input_path, output_folder, onefile=False):
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_folder = os.path.join(script_dir, "xml2csv_logs")
    Path(log_folder).mkdir(parents=True, exist_ok=True)
    
    log_file_path = os.path.join(log_folder, create_log_filename())
    
    if os.path.isfile(input_path):
        if not is_valid_xml_file(input_path):
            print(f"ERRORE: {input_path} non è un file XML valido")
            return
        
        if onefile:
            convert_xml_to_csv_onefile([input_path], output_folder,
                                       log_file_path)
        else:
            convert_xml_to_csv(input_path, output_folder, log_file_path)
        
    elif os.path.isdir(input_path):
        xml_files = glob.glob(os.path.join(input_path, "*.xml"))
        
        if not xml_files:
            print(f"Nessun file XML trovato in: {input_path}")
            return
        
        print(f"Trovati {len(xml_files)} file XML da convertire")
        
        if onefile:
            convert_xml_to_csv_onefile(xml_files, output_folder, log_file_path)
        else:
            for i, xml_file in enumerate(xml_files, 1):
                print(f"Convertendo {i}/{len(xml_files)}: "
                      f"{os.path.basename(xml_file)}")
                convert_xml_to_csv(xml_file, output_folder, log_file_path,
                                   suppress_print=True)
    else:
        print(f"ERRORE: Il percorso {input_path} non esiste")
    
    print(f"Log creato: xml2csv_logs/{os.path.basename(log_file_path)}")


def main():
    parser = argparse.ArgumentParser(
        description='Converte file XML delle fatture gas in formato CSV',
        epilog="""
Esempi:
  python xml_to_csv_converter.py file.xml                     # Singolo file
  python xml_to_csv_converter.py file.xml -o output/          # Con output
  python xml_to_csv_converter.py -f cartella_xml/             # Cartella
  python xml_to_csv_converter.py -f cartella_xml/ -o output/  # Con output
  python xml_to_csv_converter.py -f cartella_xml/ -1          # Un solo file
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
        help='Cartella di output (default: stessa cartella dell\'input)'
    )
    
    parser.add_argument(
        '-1', '--onefile',
        action='store_true',
        help='Crea un unico file CSV consolidato con tutti i dati'
    )
    
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    args = parser.parse_args()
    
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
        if args.file_xml:
            output_folder = os.path.dirname(input_path)
        else:
            output_folder = input_path
    
    process_input(input_path, output_folder, args.onefile)
    print("Conversione completata!")


if __name__ == "__main__":
    main()
