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
                row.update({
                    'data_inizio': '', 'data_fine': '', 'tipo_movimento': '',
                    'componente_tariffaria': '', 'quota': '', 'scaglione': '',
                    'quantita': '', 'imponibile': ''
                })
                rows.append(row)
    else:
        common_data.update({
            'codice_pdr': '', 'remi_pool': '', 'data_inizio': '', 'data_fine': '',
            'tipo_movimento': '', 'componente_tariffaria': '', 'quota': '',
            'scaglione': '', 'quantita': '', 'imponibile': ''
        })
        rows.append(common_data)
    
    return rows


def create_log_filename():
    timestamp = datetime.datetime.now()
    return f"xml2csv_{timestamp.strftime('%Y%m%d_%H%M%S')}.log.csv"


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
def convert_xml_to_csv(xml_file_path, output_folder, log_file_path):
    xml_filename = os.path.basename(xml_file_path)
    csv_filename = xml_filename.replace('.xml', '.csv')
    csv_path = os.path.join(output_folder, csv_filename)
    
    job_start_time = time.time()
    job_ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        print(f"Convertendo: {xml_filename}")
        
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        
        csv_rows = extract_data(root, xml_filename)
        
        fieldnames = [
            'nome_file', 'data_creazione', 'numero_sequenza',
            'mittente_ragione_sociale', 'mittente_partita_iva',
            'numero_fattura', 'data_emissione',
            'codice_pdr', 'remi_pool',
            'data_inizio', 'data_fine', 'tipo_movimento',
            'componente_tariffaria', 'quota', 'scaglione',
            'quantita', 'imponibile'
        ]
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames,
                                    delimiter=';', quoting=csv.QUOTE_NONE)
            writer.writeheader()
            writer.writerows(csv_rows)
        
        conversion_time = time.time() - job_start_time
        print(f"Creato: {csv_filename} ({conversion_time:.3f}s)")
        write_log_entry(log_file_path, xml_filename, csv_filename,
                        job_ts, conversion_time, 1)
        
    except Exception as e:
        conversion_time = time.time() - job_start_time
        error_msg = str(e)
        print(f"ERRORE nel convertire {xml_filename}: {error_msg}")
        write_log_entry(log_file_path, xml_filename, '',
                        job_ts, conversion_time, 0, error_msg)


def process_input(input_path, output_folder):
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_folder = os.path.join(script_dir, "xml2csv_logs")
    Path(log_folder).mkdir(parents=True, exist_ok=True)
    
    log_file_path = os.path.join(log_folder, create_log_filename())
    
    if os.path.isfile(input_path):
        if not input_path.lower().endswith('.xml'):
            print(f"ERRORE: {input_path} non è un file XML")
            return
        convert_xml_to_csv(input_path, output_folder, log_file_path)
        
    elif os.path.isdir(input_path):
        xml_files = glob.glob(os.path.join(input_path, "*.xml"))
        
        if not xml_files:
            print(f"Nessun file XML trovato in: {input_path}")
            return
        
        print(f"Trovati {len(xml_files)} file XML da convertire")
        
        for xml_file in xml_files:
            convert_xml_to_csv(xml_file, output_folder, log_file_path)
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
    
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    args = parser.parse_args()
    
    if args.file_xml:
        input_path = args.file_xml
        if not input_path.lower().endswith('.xml'):
            print(f"ERRORE: {input_path} non è un file XML")
            return
        if not os.path.isfile(input_path):
            print(f"ERRORE: Il file {input_path} non esiste")
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
    
    process_input(input_path, output_folder)
    print("Conversione completata!")


if __name__ == "__main__":
    main()
