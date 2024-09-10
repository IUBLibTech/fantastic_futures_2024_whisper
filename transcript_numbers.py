

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