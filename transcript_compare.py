import re
from transcript_numbers import ennumberize
import jiwer

def compare_transcripts(base: str, comp: str, edit_width=75, differences=True, gen_viz=True):
    """Compare two pieces of text and return the details of the comparison"""    
    c = jiwer.process_words(normalize_transcript_text(base),
                            normalize_transcript_text(comp))    
    results = vars(c)
    for n in ('alignments', 'references', 'hypotheses'):
        del(results[n])
    if gen_viz:
        vis, _ = generate_visualization(c, edit_width, differences=differences)
        results['visualization'] = vis
    return results


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
    

def generate_visualization(output: jiwer.WordOutput, length=75, differences=False):
    """Create a visualization of the differences in the text, optionally
       only showing the differences"""
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
