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
                                 'sheets': sheets,
                                 'all_sheets': all_worksheets})
        aggregate_sheet(sheet, f"Average across physical format \"{pf}\"", variations, data)

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
                                 'sheets': sheets,
                                 'all_sheets': all_worksheets})
        aggregate_sheet(sheet, f"Average across content type \"{pf}\"", variations, data)

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
        vis, stats = generate_visualization(o, differences=True) # Show everything?
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

    # WER stat headers
    stat_row_start = row
    for x in stat_headers:
        sheet.cell(row, 1, x).font = data_font
        row += 1

    if todo and 'all_sheets' in todo[0]:
        # also generate a "Excluding this category"
        row += 1
        sheet.cell(row, 1, "Excluding this category").font = data_font
        row += 1
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

        stat_base_row = row
        for k in stat_headers.values():            
            cell = sheet.cell(row, col)
            formula = f"=AVERAGE(" + ",".join([f"{x}!{cell.coordinate}" for x in this['sheets']]) + ")"
            sheet[cell.coordinate] = formula        
            cell.number_format = "0.00%"
            row += 1

        if 'all_sheets' in this:
            other_sheets = set(this['all_sheets']) - set(this['sheets'])
            row += 2
            for i, k in enumerate(stat_headers.values()):
                source_cell = sheet.cell(stat_base_row + i, col)
                formula = f"=AVERAGE(" + ",".join([f"{x}!{source_cell.coordinate}" for x in other_sheets]) + ")"
                sheet.cell(row, col, formula).number_format = "0.00%"
                row += 1

        col += 1


def load_transcripts(asset: Path, threeplay: Path) ->list[dict]:
    """Load all of the transcript data for a single asset and return
       them, along with a permutation tuple"""

    transcripts = []
    if not asset.is_dir():
        return transcripts 
    
    if not (asset / "metadata.yaml").exists():
        logging.warning(f"Skipping {asset.name} because there's no metadata.yaml")
        return transcripts

    if asset.name.endswith(".ignore"):
        logging.warning(f"Ignoring {asset}")
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
        if '.high' in nfile.name:
            base_filename += ".high"

        # It's great that we're normalized, but without a 3play transcript
        # this is for nothing.  Let's get it if it exists, otherwise move
        # to the next one.
        threeplay_base = base_filename.replace('.', '_')
        if not (threeplay / f"{threeplay_base}.json").exists():
            logging.warning(f"Skipping {asset.name}/{threeplay_base} since there isn't a corresponding 3play transcript")
            continue
        # load threeplay
        threeplay_transcript = load_3play_json(threeplay / f"{threeplay_base}.json")

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
    words = [[x[0], re.sub(r'\[\?', ' ', x[1])] for x in words] # remove leading ambiguity marker
    words = [[x[0], re.sub(r'\?\]', ' ', x[1])] for x in words] # remove trailing ambituity marker
    words = [[x[0], re.sub(r'\[.*?\]', ' ', x[1])] for x in words] # remove sound annotation
    words = [[x[0], re.sub(r'</?i>', ' ', x[1])] for x in words] # remove the italic markers
    words = [[x[0], re.sub(r'\([A-Z\s]*\)', ' ', x[1])] for x in words]

    # convert the timestamp to an integer
    words = [[int(x[0]), x[1]] for x in words]


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
    

def load_whisper_json(file: Path, use_text=False,
                      ignore_zero_words=True,
                      ignore_annotations=True) -> dict:
    """Load a whisper transcript file and convert it to the data structure 
    we need for processing."""    
    with open(file) as f:
        raw = json.load(f)    
    
    xscript = raw['_job']
    if use_text:
        xscript['text'] = raw['text']   
    else:
        # normally I just use the text that's generated by whisper, but let's 
        # create the text manually and skip any words with 0 duration...
        text = ""
        words = 0
        duration = 0        
        empty_words = 0
        discarded_words = 0
        # per the internet, people speak 110 - 170 words per minute in english.
        # so, let's assume that someone is speaking really slowly (say, 90
        # words per minute)...we could use that as a cutoff for words that
        # may be really long hallucinations (I've seen 29 second words in
        # whisper and that's clearly wrong).  BUT, whisper will sometimes
        # mis-time the words, so it's not really clear which things are
        # halllucinations and which ones aren't.
        word_duration_cutoff = 60 / 30
        
        # with 2s word cutoff and a 0.5 confidence cutoff, it was too aggressive
        confidence_cutoff = 0.5

        for s in raw['segments']:
            # whisper sound annotations start with '[' for the whole segment, so
            # we can drop the segment if we match that.
            if ignore_annotations and (s['text'].startswith(' [') or
                                       '(*' in s['text']):
                logging.debug(f"Removing sound annotation: {s['text']}")
                continue


            for position, w in enumerate(s['words']):
                words += 1
                word_duration = w['end'] - w['start']
                duration += word_duration
                if ignore_zero_words and word_duration == 0:
                    empty_words += 1
                    continue

                # get rid of music symbol.
                w['word'] = w['word'].replace('♪', ' ')


                # fix OKAY -> OK
                w['word'] = re.sub(r"/bokay/b", 'OK', w['word'], flags=re.IGNORECASE)

                if False and word_duration > word_duration_cutoff:
                    # compute confidence score
                    confidence = w['probability']# * (word_duration_cutoff/ word_duration)
                    logging.info(f"Discarding word '{w['word']}'@{position} {w['probability']*100:0.3f}%  {word_duration:0.3f}s/{word_duration_cutoff:0.3f}s, confidence {confidence * 100:0.3f}%")
                    #if confidence > confidence_cutoff:
                    text += w['word']
                    discarded_words += 1
                    continue
                
                text += w['word']

        logging.info(f"Whisper text stats for {file}:  {words} words, average {duration/words:0.3f} words per second, {empty_words} were empty, {discarded_words} were discarded for being longer than {word_duration_cutoff:0.3f}")
        xscript['text'] = text

    return xscript
    
    
def normalize_transcript_text(text: str) -> str:
    """Remove punctuation, case, extraneous whtiespace, etc"""    
    text = text.strip().lower()   
    # remove commas from numbers
    text = re.sub(r"(\d),(\d)", r'\1\2', text) 
    # get rid of internal newlines, tabs, etc
    text = re.sub(r"[\r\n\t]", ' ', text)
    # spaceless punctuation
    text = re.sub(r"[_]+", '', text)
    # spaceful punctuation
    text = re.sub(r"[\-!@#$%^&*()+=\[\]{}\\|;:\",./<>?]+", ' ', text)
    # get rid of all extraneous whitespace...
    text = " ".join(ennumberize(text.split()))
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


numbers = {'ones': {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4,
                    'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9},
            'teens': {'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13,
                    'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 
                    'seventeen': 17, 'eighteen': 18, 'nineteen': 19},
            'tens': {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
                    'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90},
            'powers': {'hundred': 100, 'thousand': 1000, 'million': 1000000}}


def find_number(number: str):
    for k, v in numbers.items():
        if number in v:
            return (k, v[number])
    return (None, None)

def reduce_accumulator(numbers: list[tuple[str, int]], words: list[str]):
    """Take an accumulation of numbers and make them a thing."""
    if len(numbers) == 1:
        # this is easy, we've already got what we need.
        return str(numbers[0][1])
    if all([x[0] == 'ones' for x in numbers]):
        if len(numbers) <= 10:
            # string of digits as a number
            return "".join([str(x[1]) for x in numbers])
        else:
            # this is a really long number, so treat them separately
            return " ".join([str(x[1]) for x in numbers])
    if len(numbers) == 2:
        if numbers[-1][0] == 'teens' and numbers[-1][0] != 'powers':
            # nineteen nineteen
            return str(numbers[0][1] * 100 + numbers[1][1])
        if numbers[0][0] == 'powers':
            return str(numbers[0][1] + numbers[1][1])

    # I give up.
    result = " ".join([str(x[1]) for x in numbers])
    #print(f"Converted {' '.join(words)} to {result}")
    return str(result)


def ennumberize(words: list[str]):
    "Try real hard to turn words into numbers!"    
    result = []
    accumulator = []
    start_idx = 0
    in_number = False
    for here, w in enumerate(words):
        ntype, value  = find_number(w)
        if not in_number:
            if ntype is None:
                # this is a non-number word.
                result.append(w)
            else:
                # we've got a fresh new number.
                accumulator = [(ntype, value)]
                start_idx = here
                in_number = True                
        else:
            match ntype:
                case None:
                    # we were parsing numbers, now we don't have one.                    
                    result.append(reduce_accumulator(accumulator, words[start_idx:here]))
                    result.append(w)
                    in_number = False                    
                case 'ones' | 'teens':                
                    if ntype == 'ones' and accumulator and accumulator[-1][0] == 'tens':
                        # fifty one
                        accumulator[-1] = (ntype, accumulator[-1][1] + value)
                    else:
                        accumulator.append((ntype, value))                    
                case 'tens':
                    if not accumulator:
                        accumulator.append((ntype, value))
                    else:
                        if accumulator[-1][0] in ('ones', 'teens', 'tens'):
                            # this is something like: nine twenty (920),  twenty twenty (2020)
                            accumulator[-1] = (ntype, accumulator[-1][1] * 100 + value)
                        else:
                            # hundrend twenty, thousand twenty.
                            accumulator[-1] = (ntype, accumulator[-1][1] + value)
                case 'powers':
                    if not accumulator:
                        # million points of light
                        accumulator.append((ntype, value))
                    else:
                        accumulator[-1] = (ntype, accumulator[-1][1] * value)

    if in_number:        
        result.append(reduce_accumulator(accumulator, words[start_idx:here]))
      
    
    return result

if __name__ == "__main__":
    main()