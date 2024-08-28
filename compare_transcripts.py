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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", default=False, action="store_true", help="Turn on debugging")
    parser.add_argument("workdir", type=Path, help="Root of the media files")
    
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s [%(process)d:%(filename)s:%(lineno)d] [%(levelname)s] %(message)s")

    workdir: Path = args.workdir
    models = ('small', 'medium', 'large-v2', 'large-v3')
    for media_file in workdir.glob('*/*'):
        if media_file.suffix not in ('.wav', '.mp4'):
            continue        
        excel_file = media_file.with_suffix(".xlsx")

        workbook = Workbook()
        del(workbook['Sheet'])        
        # create the audio filter sheet...
        audio_sheet: Worksheet = workbook.create_sheet("Audio Filter")
        todo = []        
        for model in models:
            try:
                base_transcript = load_transcript(media_file.parent / f"{media_file.stem}.whisper.{model}_T_X.json")
                for filter in ('A', 'B'):
                    todo.append({'variant': [model, filter],
                                'base': base_transcript,
                                'comp': load_transcript(media_file.parent / f"{media_file.stem}.whisper.{model}_T_{filter}.json")})
            except Exception as e:
                logging.error(f"Audio filter sheet: Cannot handle model {model}")
        populate_sheet(audio_sheet, "Audio Filter Comparison vs Default",
                       ['model', 'filter'], todo)


        # create the previous text sheet.
        prevtext_sheet: Worksheet = workbook.create_sheet("Previous Text Disabled")
        todo = []
        for model in models:
            try:
                base_transcript = load_transcript(media_file.parent / f"{media_file.stem}.whisper.{model}_T_X.json")
                comp_transcript = load_transcript(media_file.parent / f"{media_file.stem}.whisper.{model}_F_X.json")
                todo.append({'variant': [model],
                            'base': base_transcript,
                            'comp': comp_transcript})
            except Exception as e:
                logging.error(f"Previous text sheet: Cannot handle model {model}: {e}")
        populate_sheet(prevtext_sheet, "Previous Text Disabled vs Default", 
                       ['model'], todo)

        # whisper model vs whisper model 
        model_sheet: Worksheet = workbook.create_sheet("Whisper Model Comparisons")
        todo = []
        for i in range(len(models)):
            try:
                base_transcript = load_transcript(media_file.parent / f"{media_file.stem}.whisper.{models[i]}_T_X.json")
                for j in range(i + 1, len(models)):
                    comp_transcript = load_transcript(media_file.parent / f"{media_file.stem}.whisper.{models[j]}_F_X.json")
                    todo.append({'variant': [models[i], models[j]],
                                'base': base_transcript,
                                'comp': comp_transcript})
            except Exception as e:
                logging.error(f"whisper vs whisper sheet: Cannot handle {models[i]}")
        populate_sheet(model_sheet, "Whisper Model vs Whisper Model", 
                       ['base model', 'comp model'], todo)

        workbook.save(excel_file)

        





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
        o = jiwer.process_words(this['base']['text'], this['comp']['text'])
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


def load_transcript(file: Path):
    """Load a transcript file and convert it to the data structure we need for
    processing.  We'll support plain text and json from whisper"""
    xscript = {'duration': None,
                'runtime': None,                
                'model': None,
                'device': None,
                'language': None,
                'previous_text': None,
                'audio_filter': None,
                'text': None}
    try:
        with open(file) as f:
            raw = json.load(f)
        
        xscript.update(raw['_job'])
        xscript['text'] = raw['text']
    except Exception:
        # just treat it like text.
        xscript['device'] = 'raw'
        xscript['text'] = file.read_text('utf-8')
          
    # normalize the text a bit:  get rid of newlines, carriage returns, and tabs    
    for n in ('\n', '\r', '\t'):
        xscript['text'] = xscript['text'].replace(n, " ")
    # and remove leading/trailing spaces.
    xscript['text'] = xscript['text'].strip()

    # we want to ignore case and punctuation.            
    # spaceless punctuation (and lowercase it while we're at it)
    xscript['text'] = re.sub(r"[_]+", '', xscript['text'].lower())
    # spaceful punctuation
    xscript['text'] = re.sub(r"[\-!@#$%^&*()+=\[\]{}\\|;:\",./<>?]+", ' ', xscript['text'])        
    return xscript


def pad(word, pad_len):
    while len(word) < pad_len:
        word += " "
    return word


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
            
                    results[-1]['ref'] += pad(gt[i + chunk.ref_start_idx], word_len) + " "
                    results[-1]['hyp'] += pad(hp[i + chunk.hyp_start_idx], word_len) + " "
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