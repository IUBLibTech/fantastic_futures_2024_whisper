#!/usr/bin/env python3

import argparse
import jiwer
from pathlib import Path
import logging
import re
import json
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.styles import Font, Alignment
import yaml
import string
from utils import human_time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", default=False, action="store_true", help="Turn on debugging")
    parser.add_argument("threeplay", type=Path, help="3play json directory")
    parser.add_argument("workdir", type=Path, help="Root of the media files")
    parser.add_argument("output", type=Path, help="Excel Output File")
    
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s [%(process)d:%(filename)s:%(lineno)d] [%(levelname)s] %(message)s")
    workdir: Path = args.workdir
    threeplay: Path = args.threeplay


    # Load all of the generated transcripts into a standard format.
    transcripts = []
    for d in workdir.glob('*'):
        transcripts.extend(load_transcripts(d, threeplay))
        

    # Start generating the excel workbook
    workbook = Workbook()
    del(workbook['Sheet']) 

    variations = ['Whisper Model', 'Audio Filter', 'Previous Text']

    # Generate the details for every permutation compared to our control (3play)        
    for title, txscripts in sorted(group_by(transcripts, 'title').items()):
        snum = 1
        for file, fxscripts in group_by(txscripts, 'base_filename').items():            
            sheet_title = normalize_sheet_title(title) + f"_{snum}"            
            sheet: Worksheet = workbook.create_sheet(sheet_title)
            data = []            
            for model in ('small', 'medium', 'large-v2', 'large-v3'):
                for audio_filter in ('X', 'A', 'B'):
                    for previous_text in ('T', 'F'):
                        variant = [model, audio_filter, previous_text]
                        xscripts = search_transcripts(fxscripts, search_key := {'whisper_model': model,
                                                                                'audio_filter': audio_filter,
                                                                                'previous_text': previous_text})
                        if len(xscripts) != 1:
                            logging.warning(f"Skipping {search_key}: not found in {len(fxscripts)}")                            
                            data.append({'variant': variant,
                                         'base': None,
                                         'comp': None})
                            continue
                        else:
                            # note the worksheet this transcript resides on.
                            xscripts[0]['worksheet'] = sheet_title
                            data.append({'variant': variant,
                                         'processing_ratio': xscripts[0]['whisper_processing_duration'] / xscripts[0]['truncated_duration'],
                                         'base': normalize_transcript_text(xscripts[0]['3play_transcript']),
                                         'comp': normalize_transcript_text(xscripts[0]['whisper_transcript'])})
            populate_sheet(sheet, f"{title} {file} ({human_time(fxscripts[0]['truncated_duration'])})", variations, data)
            snum += 1
 
    # Aggregate everything
    sheet: Worksheet = workbook.create_sheet("Average", 0)
    all_worksheets = list(set([x["worksheet"] for x in transcripts]))    
    data = []
    for model in ('small', 'medium', 'large-v2', 'large-v3'):
        for audio_filter in ('X', 'A', 'B'):
            for previous_text in ('T', 'F'):
                variant = [model, audio_filter, previous_text]
                data.append({'variant': variant,
                             'sheets': all_worksheets})
    aggregate_sheet(sheet, f"Average across everything", variations, data)

    # Aggregate(s) by Physical Media Type
    # physical_format
    for pf, pxscripts in sorted(group_by(transcripts, 'physical_format').items()):
        sheet: Worksheet = workbook.create_sheet(normalize_sheet_title(f"Physical Format {pf}"), 1)
        sheets = list(set([x["worksheet"] for x in pxscripts]))
        data = []
        for model in ('small', 'medium', 'large-v2', 'large-v3'):
            for audio_filter in ('X', 'A', 'B'):
                for previous_text in ('T', 'F'):
                    variant = [model, audio_filter, previous_text]
                    data.append({'variant': variant,
                                 'sheets': sheets})
        aggregate_sheet(sheet, f"Average across physical format {pf}", variations, data)

    # Aggregate(s) by Content Type
    for pf, pxscripts in sorted(group_by(transcripts, 'content_type').items()):
        sheet: Worksheet = workbook.create_sheet(normalize_sheet_title(f"Content Type {pf}"), 1)
        sheets = list(set([x["worksheet"] for x in pxscripts]))
        data = []
        for model in ('small', 'medium', 'large-v2', 'large-v3'):
            for audio_filter in ('X', 'A', 'B'):
                for previous_text in ('T', 'F'):
                    variant = [model, audio_filter, previous_text]
                    data.append({'variant': variant,
                                 'sheets': sheets})
        aggregate_sheet(sheet, f"Average across content type {pf}", variations, data)



    workbook.save(args.output)
    
 
def group_by(transcripts: list[dict], field: str) -> dict[str, list[dict]]:
    """Return a dict of lists grouped by the given field"""
    results = {}
    for i in transcripts:
        k = i.get(field, None)
        if k not in results:
            results[k] = []
        results[k].append(i)
    return results


def search_transcripts(transcripts: list[dict], query: dict) -> list[dict]:
    """Search the transcripts for the specific query fields"""
    results = list(transcripts)
    for k, v in query.items():
        results = [x for x in results if x.get(k, None) == v]
    return results



def populate_sheet(sheet: Worksheet, title: str, vtitle: list[str], todo: list[dict]):
    """Populate the spreadsheet based on the todo list"""
    stat_headers = {'Word Error Rate': 'wer',
                    'Word Information Lost': 'wil',
                    'Word Information Preserved': 'wip',
                    'Match Error Rate': 'mer'}

    edit_headers = {'Hits': 'hit',
                    'Inserts': 'ins',
                    'Deletes': 'del',
                    'Substitutions': 'sub'}

    sheet.cell(1, 2, title).font = Font(bold=True, name="Arial", sz=14)

    data_font = Font(name="Arial", sz=10)
    edit_font = Font(name="Courier", sz=8)
    vtitle_font = Font(name="Arial", sz=10, bold=True)

    # populate the column 1 headers...
    sheet.column_dimensions['A'].width = 27
    row = 2
    for x in vtitle:
        sheet.cell(row, 1, x).font = data_font    
        row += 1
    row += 1
    
    # processing ratio
    sheet.cell(row, 1, "Processing Ratio").font = data_font
    row += 2

    for x in stat_headers:
        sheet.cell(row, 1, x).font = data_font
        row += 1
    row += 1
    for x in edit_headers:
        sheet.cell(row, 1, x).font = data_font
        row += 1
    sheet.cell(row + 1, 1, 'Edits').font = data_font


    # Walk through the todo...
    col = 2
    for this in todo:
        row = 2
        sheet.column_dimensions[chr(64 + col)].width = 75
        # print the variant headers
        for x in this['variant']:
            sheet.cell(row, col, x).font = vtitle_font
            row += 1
        row += 1
        if this['base'] is None:
            col += 1
            continue

        sheet.cell(row, col, this['processing_ratio']).number_format = "0.00%"
        row += 2

        o = jiwer.process_words(this['base'], this['comp'])
        vis, stats = generate_visualization(o, differences=True)
        for k in stat_headers.values():
            sheet.cell(row, col, getattr(o, k)).number_format = "0.00%"
            row += 1
        row += 1
        for k in edit_headers.values():
            sheet.cell(row, col, stats[k])
            row += 1
        row += 1
        for edit in vis:
            c = sheet.cell(row, col)
            c.font = edit_font
            #c.alignment = Alignment(wrapText=True, vertical="top")        
            c.value = edit
            row += 1
        col += 1


def aggregate_sheet(sheet: Worksheet, title: str, vtitle: list[str], todo: list[dict]):
    """Populate the spreadsheet based on the todo list"""
    stat_headers = {'Word Error Rate': 'wer',
                    'Word Information Lost': 'wil',
                    'Word Information Preserved': 'wip',
                    'Match Error Rate': 'mer'}

    sheet.cell(1, 2, title).font = Font(bold=True, name="Arial", sz=14)

    data_font = Font(name="Arial", sz=10)
    edit_font = Font(name="Courier", sz=8)
    vtitle_font = Font(name="Arial", sz=10, bold=True)

    # populate the column 1 headers...
    sheet.column_dimensions['A'].width = 27
    row = 2
    for x in vtitle:
        sheet.cell(row, 1, x).font = data_font    
        row += 1
    row += 1
    
    # processing ratio
    sheet.cell(row, 1, "Processing Ratio").font = data_font
    row += 2

    for x in stat_headers:
        sheet.cell(row, 1, x).font = data_font
        row += 1

    # Walk through the todo...
    col = 2
    for this in todo:
        row = 2
        sheet.column_dimensions[chr(64 + col)].width = 10
        # print the variant headers
        for x in this['variant']:
            sheet.cell(row, col, x).font = vtitle_font
            row += 1
        row += 1

        # processing ratio
        cell = sheet.cell(row, col)
        formula = f"=AVERAGE(" + ",".join([f"{x}!{cell.coordinate}" for x in this['sheets']]) + ")"
        sheet[cell.coordinate] = formula        
        cell.number_format = "0.00%"
        row += 2

        for k in stat_headers.values():
            cell = sheet.cell(row, col)
            formula = f"=AVERAGE(" + ",".join([f"{x}!{cell.coordinate}" for x in this['sheets']]) + ")"
            sheet[cell.coordinate] = formula        
            cell.number_format = "0.00%"
            row += 1

        col += 1


def load_transcripts(asset: Path, threeplay: Path) ->list[dict]:
    """Load all of the transcript data for a single asset and return
       them, along with a permutation tuple"""

    transcripts = []
    if not (asset / "metadata.yaml").exists():
        logging.warning(f"Skipping {asset.name} because there's no metadata.yaml")
        return transcripts

    # load the base metadata
    with open(asset / "metadata.yaml") as f:
        base_meta = yaml.safe_load(f)

    # we're going to assume that every media file in this asset has been
    # normalized, so we'll use that as the basis for gathering the 
    # transcripts    
    for nfile in asset.glob("*.normalization.yaml"):
        base_filename = nfile.name
        # remove all of the suffixes.
        for s in reversed(nfile.suffixes):
            base_filename = base_filename[0:-len(s)]

        # It's great that we're normalized, but without a 3play transcript
        # this is for nothing.  Let's get it if it exists, otherwise move
        # to the next one.
        if not (threeplay / f"{base_filename}.json").exists():
            logging.warning(f"Skipping {asset.name}/{base_filename} since there isn't a corresponding 3play transcript")
            continue
        # load threeplay
        threeplay_transcript = load_3play_json(threeplay / f"{base_filename}.json")

        # load the normalization
        with open(nfile) as f:
            normalization_meta = yaml.safe_load(f)

        # get the transcript data for each whisper transcript variation
        for tfile in asset.glob(f"{base_filename}.whisper.*.json"):            
            whisper_transcript = load_whisper_json(tfile)
            
            # now that we've collected everything, add it to the list of transcripts
            data = {
                'title': base_meta['title'],
                'physical_format': base_meta['physical format'],
                'content_type': base_meta['content type'],
                'base_filename': base_filename,
                'whisper_model': whisper_transcript['model'],
                'previous_text': whisper_transcript['previous_text'],
                'audio_filter': whisper_transcript['audio_filter'],
                'original_duration': normalization_meta['original_duration'],
                'truncated_duration': normalization_meta['truncated_duration'],
                'whisper_processing_duration': whisper_transcript['runtime'],
                'whisper_transcript': whisper_transcript['text'],
                '3play_transcript': threeplay_transcript
            }
            transcripts.append(data)
    return transcripts


def load_3play_json(file: Path):
    """Load the 3play json file and convert it to plain text without
       audio descriptions or diarization"""
    # 'words' is a list of tuples where I'm assuming the first value is a
    # timestamp of some sort and the 2nd is the word at that timestamp.
    # 'paragraphs' is a list of timestamps where each paragraph starts.
    # 'speakers' is a dict of timestamp -> speaker
    # audio descriptions are single words which match "^\[[A-Z ]+\]$"

    with open(file) as f:
        data = yaml.safe_load(f)

    # filter out words we don't care about
    words = [x for x in data['words'] if x[1] != '']  # empty words
    words = [x for x in words if x[0] not in data['speakers']] # speaker tokens
    words = [[int(x[0]), x[1]] for x in words if not re.match(r"^\[[A-Z ]+\]$", x[1])] # audio descriptions

    # split into paragraphs
    paragraphs = [[]]
    data['paragraphs'].append(99999999999)
    for p in range(0, len(data['paragraphs']) - 1):
        p_start = data['paragraphs'][p]
        p_end = data['paragraphs'][p + 1]
        for w in words:
            if p_start <= w[0] < p_end:
                paragraphs[-1].append(w[1])
        paragraphs.append([])
    
    return "\n".join([' '.join(x) for x in paragraphs if len(x)])
    

def load_whisper_json(file: Path) -> dict:
    """Load a whisper transcript file and convert it to the data structure 
    we need for processing."""    
    with open(file) as f:
        raw = json.load(f)    
    
    xscript = raw['_job']
    xscript['text'] = raw['text']   
    return xscript
    
    
def normalize_transcript_text(text: str) -> str:
    """Remove punctuation, case, extraneous whtiespace, etc"""    
    text = text.strip().lower()    
    # get rid of internal newlines, tabs, etc
    text = re.sub(r"[\r\n\t]", ' ', text)
    # spaceless punctuation
    text = re.sub(r"[_]+", '', text)
    # spaceful punctuation
    text = re.sub(r"[\-!@#$%^&*()+=\[\]{}\\|;:\",./<>?]+", ' ', text)
    # get rid of all extraneous whitespace...
    text = " ".join(text.split())    
    return text
    

def normalize_sheet_title(text: str) -> str:
    """Remove invalid characters from sheet titles"""
    ntext = ""
    cksum = 0
    for c in text:
        cksum += ord(c)
        if c in string.ascii_letters or c in string.digits:
            ntext += c
    if len(ntext) > 25:
        ntext = ntext[0:25]
    ntext += chr(65 + (cksum % 24))
    return ntext
    

def generate_visualization(output: jiwer.WordOutput, length=75, differences=False):
    results = [{'ref': '', 'hyp': '', 'chg': '', 'dif': 0}]
    stats = {'hit': 0, 'sub': 0, 'del': 0, 'ins': 0}
    for idx, (gt, hp, chunks) in enumerate(zip(output.references, output.hypotheses, output.alignments)):
        #print(idx, gt, hp, chunks)
        for chunk in chunks:
            if chunk.type == 'equal':
                # copy ref, and hyp words until either we
                # end up too long or we come to the end.                    
                for i in range(chunk.ref_end_idx - chunk.ref_start_idx):                
                    stats['hit'] += 1
                    word_len = len(gt[i + chunk.ref_start_idx]) 
                    if word_len + len(results[-1]['ref']) + 1> length:
                        # too long. create a new result
                        results.append({'ref': '', 'hyp': '', 'chg': '', 'dif': 0})
            
                    results[-1]['ref'] += gt[i + chunk.ref_start_idx] + " "
                    results[-1]['hyp'] += hp[i + chunk.hyp_start_idx] + " "
                    results[-1]['chg'] += ' ' * (word_len + 1)     
            elif chunk.type == 'insert':
                # hyp has an additional word that's not in ref.                
                for i in range(chunk.hyp_end_idx - chunk.hyp_start_idx):                
                    stats['ins'] += 1
                    word_len = len(hp[i + chunk.hyp_start_idx])
                    if word_len + len(results[-1]['ref']) + 1> length:
                        # too long. create a new result
                        results.append({'ref': '', 'hyp': '', 'chg': '', 'dif': 0})
            
                    results[-1]['ref'] += ('*' * word_len) + " "
                    results[-1]['hyp'] += hp[i + chunk.hyp_start_idx] + " "
                    results[-1]['chg'] += ('I' * word_len) + " "
                    results[-1]['dif'] += 1
            elif chunk.type == 'delete':
                # ref has an additional word that's not in hyp.                
                for i in range(chunk.ref_end_idx - chunk.ref_start_idx): 
                    stats['del'] += 1               
                    word_len = len(gt[i + chunk.ref_start_idx])
                    if word_len + len(results[-1]['ref']) + 1> length:
                        # too long. create a new result
                        results.append({'ref': '', 'hyp': '', 'chg': '', 'dif': 0})
            
                    results[-1]['ref'] += gt[i + chunk.ref_start_idx] + " "
                    results[-1]['hyp'] += ('*' * word_len) + " "                    
                    results[-1]['chg'] += ('D' * word_len) + " "
                    results[-1]['dif'] += 1
            elif chunk.type == 'substitute':
                # ref and hyp have different words (but the same number)                
                for i in range(chunk.ref_end_idx - chunk.ref_start_idx):
                    stats['sub'] += 1                
                    word_len = max([len(gt[i + chunk.ref_start_idx]),
                                    len(hp[i + chunk.hyp_start_idx])])
                    if word_len + len(results[-1]['ref']) + 1> length:
                        # too long. create a new result
                        results.append({'ref': '', 'hyp': '', 'chg': '', 'dif': 0})
            
                    results[-1]['ref'] += gt[i + chunk.ref_start_idx].ljust(word_len) + ' '
                    results[-1]['hyp'] += hp[i + chunk.hyp_start_idx].ljust(word_len) + ' '
                    results[-1]['chg'] += 'S' * (word_len) + ' '
                    results[-1]['dif'] += 1
            else:
                print(chunk)

    if differences:
        results = [x for x in results if x['dif'] > 0]

    # render the differences as text.
    report = []
    for s in results:
        report.append(f"BASE: {s['ref']}")
        report.append(f"COMP: {s['hyp']}")
        report.append(f"EDIT: {s['chg']}")
        report.append("")
        
    return report, stats


if __name__ == "__main__":
    main()