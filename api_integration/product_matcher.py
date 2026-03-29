import re
import spacy
from rapidfuzz import fuzz

try:
    nlp = spacy.load("en_core_web_sm")
except:
    import spacy.cli
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

def extract_attributes(title):
    specs = {}
    title_upper = title.upper()
    
    # ১. স্টোরেজ (e.g., 256GB, 1TB)
    storage = re.search(r'(\d+)\s*(GB|TB|MB)', title_upper)
    if storage:
        specs['storage'] = storage.group(0).replace(" ", "")

    # ২. র‍্যাম (e.g., 32GB RAM) - ল্যাপটপের জন্য এটি গুরুত্বপূর্ণ
    ram = re.search(r'(\d+)\s*GB\s*RAM', title_upper)
    if ram:
        specs['ram'] = ram.group(0).replace(" ", "")

    # ৩. স্যামসাং সিরিজ/মডেল
    series_model_match = re.search(r'\b([SAZMN]\d{2}(?:\s*FE|\s*ULTRA|\s*PLUS|\s*PRO|\s*MAX)?)\b', title_upper)
    if series_model_match:
        specs['series_model'] = series_model_match.group(1).replace(" ", "")

    # ৪. আইফোন মডেল
    iphone_model_match = re.search(r'\bIPHONE\s+(?:SE|(\d+))\b', title_upper)
    if iphone_model_match:
        if iphone_model_match.group(1):
            specs['iphone_model_num'] = iphone_model_match.group(1)
        elif "SE" in iphone_model_match.group(0):
            specs['iphone_model_num'] = "SE"

    # ৫. মডেল কোড (e.g., SM-S731U, A1387)
    model_code = re.search(r'\b(?:SM-|A|MH|ML|MQ)\d{3,}[A-Z]{0,2}\b|\b[A-Z0-9]{3,}-[A-Z0-9]{1,}\b', title_upper)
    if model_code:
        specs['model_code'] = model_code.group(0)

    # ৬. স্ক্রিন সাইজ (e.g., 6.3", 15.6")
    screen_size_match = re.search(r'(\d+\.?\d*)\s*(INCH|INCHES|\")', title_upper)
    if screen_size_match:
        specs['screen_size'] = screen_size_match.group(0).replace(" ", "")

    return specs


def extract_core_title(title):
    if not title: return ""
    cleaned_title_text = title.lower()
    noise_patterns = [
        r'opens?\s+in\s+a\s+new.*', r'\d+%?\s*off', r'free\s*shipping',
        r'\b(brand\s*new|new|used|excellent|mint|good|condition|graded|pre[\s-]?owned)\b',
        r'\b(unlocked|fully\s*unlocked|factory\s*unlocked|carrier\s*locked|locked)\b',
        r'\b(ai|5g|4g|lte)\b', r'\b(cell\s*phone|smartphone|mobile|android|ios)\b',
        r'(\d+\.?\d*)\s*(inch|inches|\")', r'(\d+)\s*(gb|tb|mb)', r'\s*,\s*$', r'\s*-\s*$',
        r'all\s*colors', r'\(.*\)', r'\[.*\]', r'\d{4}',
    ]
    for pattern in noise_patterns:
        cleaned_title_text = re.sub(pattern, ' ', cleaned_title_text, flags=re.IGNORECASE).strip()
    
    cleaned_title_text = re.sub(r'\s+', ' ', cleaned_title_text).strip()
    doc = nlp(cleaned_title_text)
    tokens = [t.text for t in doc if t.pos_ in ['PROPN', 'NOUN', 'NUM'] and not t.is_stop and len(t.text.strip()) > 1]
    return " ".join(tokens).strip()

def extract_brand(title):
    title_upper = title.upper()
    # ল্যাপটপের জন্য ব্র্যান্ড লিস্ট বড় করা হলো
    brands = ['HP', 'DELL', 'SAMSUNG', 'APPLE', 'IPHONE', 'LENOVO', 'ASUS', 'ACER', 'MICROSOFT', 'MSI', 'RAZER', 'GOOGLE']
    for b in brands:
        if b in title_upper:
            return b
    return None

def calculate_match_score(title1, title2):
    if not title1 or not title2: return 0.0

    f1 = get_product_fingerprint(title1)
    f2 = get_product_fingerprint(title2)

    # ১. ব্র্যান্ড ব্লক (HP vs Dell রোধ করবে)
    brand1 = extract_brand(title1)
    brand2 = extract_brand(title2)
    if brand1 and brand2 and brand1 != brand2:
        return 0.0

    # ২. হার্ড ব্লক: স্টোরেজ মিসম্যাচ
    if f1['attributes'].get('storage') and f2['attributes'].get('storage'):
        if f1['attributes']['storage'] != f2['attributes']['storage']:
            return 0.0

    # ৩. হার্ড ব্লক: র‍্যাম মিসম্যাচ (ল্যাপটপের জন্য ইম্পরট্যান্ট)
    if f1['attributes'].get('ram') and f2['attributes'].get('ram'):
        if f1['attributes']['ram'] != f2['attributes']['ram']:
            return 0.0

    # ৪. হার্ড ব্লক: মডেল/সিরিজ মিসম্যাচ
    if f1['attributes'].get('series_model') and f2['attributes'].get('series_model'):
        if f1['attributes']['series_model'] != f2['attributes']['series_model']:
            return 0.0

    # ৫. হার্ড ব্লক: আইফোন মডেল নম্বর
    if f1['attributes'].get('iphone_model_num') and f2['attributes'].get('iphone_model_num'):
        if f1['attributes']['iphone_model_num'] != f2['attributes']['iphone_model_num']:
            return 0.0

    # ৬. হার্ড ব্লক: স্ক্রিন সাইজ
    if f1['attributes'].get('screen_size') and f2['attributes'].get('screen_size'):
        if f1['attributes']['screen_size'] != f2['attributes']['screen_size']:
            return 0.0

    # মূল স্কোরিং
    core1 = f1['core_name']
    core2 = f2['core_name']
    score = fuzz.token_set_ratio(core1, core2)
    
    # বোনাস বুস্ট
    if f1['attributes'].get('model_code') and f1['attributes']['model_code'].lower() in title2.lower():
        score += 20
    elif f2['attributes'].get('model_code') and f2['attributes']['model_code'].lower() in title1.lower():
        score += 20

    return min(100.0, score)

def get_product_fingerprint(title):
    return {
        'core_name': extract_core_title(title),
        'attributes': extract_attributes(title)
    }

def clean_product_title(title): return extract_core_title(title)
def product_match_score(title1, title2): return calculate_match_score(title1, title2)