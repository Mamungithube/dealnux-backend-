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
    """
    টাইটেল থেকে গুরুত্বপূর্ণ স্পেসিফিকেশন (Storage, Series/Model, Model Code, iPhone Model Num, Screen Size) আলাদা করে।
    """
    specs = {}
    title_upper = title.upper()
    
    # ১. স্টোরেজ (e.g., 256GB, 1TB)
    storage = re.search(r'(\d+)\s*(GB|TB|MB)', title_upper)
    if storage:
        specs['storage'] = storage.group(0).replace(" ", "")

    # ২. স্যামসাং বা অন্যান্য ব্র্যান্ডের সিরিজ এবং মডেল (e.g., S25 FE, A17, Note 20 Ultra)
    # [SAZMN]\d{2} মানে S10, A20, Z Flip ইত্যাদি
    # (FE|ULTRA|PLUS|PRO|MAX) এই ধরনের ভেরিয়েন্টগুলোও ধরা হবে
    series_model_match = re.search(r'\b([SAZMN]\d{2}(?:\s*FE|\s*ULTRA|\s*PLUS|\s*PRO|\s*MAX)?)\b', title_upper)
    if series_model_match:
        # যেমন "S25 FE" কে একবারে ধরবে
        specs['series_model'] = series_model_match.group(1).replace(" ", "")

    # ৩. আইফোনের মডেল নম্বর (e.g., IPHONE 17, IPHONE SE)
    iphone_model_match = re.search(r'\bIPHONE\s+(?:SE|(\d+))\b', title_upper)
    if iphone_model_match:
        if iphone_model_match.group(1): # যদি মডেল নম্বর সংখ্যা হয় (যেমন 17)
            specs['iphone_model_num'] = iphone_model_match.group(1)
        elif "SE" in iphone_model_match.group(0): # যদি iPhone SE হয়
            specs['iphone_model_num'] = "SE"

    # ৪. ফুল মডেল কোড (e.g., SM-S731U, A1387)
    # এই রেজেক্সটি আরও সুনির্দিষ্টভাবে কাজ করবে
    model_code = re.search(r'\b(?:SM-|A|MH|ML|MQ)\d{3,}[A-Z]{0,2}\b|\b[A-Z0-9]{3,}-[A-Z0-9]{1,}\b', title_upper)
    if model_code:
        specs['model_code'] = model_code.group(0)

    # ৫. স্ক্রিন সাইজ (e.g., 6.3")
    screen_size_match = re.search(r'(\d+\.?\d*)\s*(INCH|INCHES|\")', title_upper)
    if screen_size_match:
        specs['screen_size'] = screen_size_match.group(0).replace(" ", "")

    return specs


def extract_core_title(title):
    """
    টাইটেল থেকে অপ্রয়োজনীয় জঞ্জাল (Noise) এবং স্পেসিফিকেশন (Attributes) বাদ দিয়ে শুধুমাত্র মূল প্রোডাক্টের নামটি (Core Name) বের করে।
    """
    if not title: return ""
    
    cleaned_title_text = title.lower()

    # স্টেজ ১: ম্যানুয়াল রেজেক্স ব্যবহার করে বিস্তৃত নয়েজ অপসারণ
    # এখানে আমরা নতুন করে '6.3\"' এবং 'Fully Unlocked' এর মতো শব্দগুলো যোগ করছি
    noise_patterns = [
        r'opens?\s+in\s+a\s+new.*',                                 # eBay's "opens in a new window"
        r'\d+%?\s*off', r'free\s*shipping', r'fast\s*delivery',     # Offers & Shipping
        r'\b(brand\s*new|new|used|excellent|mint|good|condition|graded|pre[\s-]?owned)\b', # Conditions
        r'\b(unlocked|fully\s*unlocked|factory\s*unlocked|carrier\s*locked|locked)\b', # Lock status
        r'\b(ai|5g|4g|lte)\b',                                      # Network/AI features
        r'\b(cell\s*phone|smartphone|mobile|android|ios)\b',       # Generic device types
        r'(\d+\.?\d*)\s*(inch|inches|\")',                         # Screen sizes (e.g., 6.3")
        r'(\d+)\s*(gb|tb|mb)',                                      # Storage capacity (e.g., 256GB)
        r'\s*,\s*$', r'\s*-\s*$',                                   # Trailing punctuation
        r'all\s*colors', r'jetblack', r'space\s*gray',             # Colors (mostly noise for matching core product)
        r'\b(display|battery|camera|warranty|durable|res|edits|manufacturer)\b', # Generic phone features
        r'\b(large|small|mini)\b',
        r'\(.*\)', r'\[.*\]', # Parentheses and brackets often contain noise
        r'\d{4}', # Remove years like '2025' if they are not part of model (e.g. 'iPhone 11 2025 Edition' vs 'iPhone 11')
    ]
    
    for pattern in noise_patterns:
        cleaned_title_text = re.sub(pattern, ' ', cleaned_title_text, flags=re.IGNORECASE).strip()

    # অতিরিক্ত স্পেস এবং ড্যাশ/কমা পরিষ্কার করা
    cleaned_title_text = re.sub(r'\s+', ' ', cleaned_title_text).strip()
    cleaned_title_text = re.sub(r'[\s,-]+$', '', cleaned_title_text).strip()
    
    # স্টেজ ২: spaCy ব্যবহার করে আরও সেমান্টিক ক্লিনিং
    doc = nlp(cleaned_title_text)
    # শুধুমাত্র Proper Nouns (ব্র্যান্ড নাম), Nouns (প্রোডাক্ট নাম) এবং Numbers (মডেল নম্বর) রাখা
    tokens = [
        t.text for t in doc 
        if t.pos_ in ['PROPN', 'NOUN', 'NUM'] # শুধুমাত্র নামবাচক, বিশেষ্য, সংখ্যাবাচক শব্দ
        and not t.is_stop and not t.is_punct and not t.is_space 
        and len(t.text.strip()) > 1 # ১ অক্ষরের শব্দ বাদ
    ]
    
    return " ".join(tokens).strip()


def calculate_match_score(title1, title2):
    """
    দুইটি প্রোডাক্ট টাইটেলের মধ্যে নির্ভুলভাবে ম্যাচিং স্কোর ক্যালকুলেট করে (0-100)।
    সিরিজ/মডেল মিসম্যাচ, স্টোরেজ মিসম্যাচ হলে সরাসরি 0 রিটার্ন করে।
    """
    if not title1 or not title2: return 0.0

    f1 = get_product_fingerprint(title1)
    f2 = get_product_fingerprint(title2)

    # --- হার্ড ব্লক ১: স্টোরেজ মিসম্যাচ (e.g., 128GB vs 256GB) ---
    if f1['attributes'].get('storage') and f2['attributes'].get('storage'):
        if f1['attributes']['storage'] != f2['attributes']['storage']:
            return 0.0

    # --- হার্ড ব্লক ২: আইফোন মডেল নম্বর মিসম্যাচ (e.g., iPhone 17 vs iPhone 16) ---
    if f1['attributes'].get('iphone_model_num') and f2['attributes'].get('iphone_model_num'):
        if f1['attributes']['iphone_model_num'] != f2['attributes']['iphone_model_num']:
            return 0.0

    # --- হার্ড ব্লক ৩: স্যামসাং সিরিজ/মডেল মিসম্যাচ (e.g., S25 vs A17) ---
    if f1['attributes'].get('series_model') and f2['attributes'].get('series_model'):
        if f1['attributes']['series_model'] != f2['attributes']['series_model']:
            return 0.0

    # --- হার্ড ব্লক ৪: ফুল মডেল কোড মিসম্যাচ (e.g., SM-S731U vs SM-A176U) ---
    if f1['attributes'].get('model_code') and f2['attributes'].get('model_code'):
        if f1['attributes']['model_code'] != f2['attributes']['model_code']:
            return 0.0
            
    # --- হার্ড ব্লক ৫: স্ক্রিন সাইজ মিসম্যাচ (যদি উভয় টাইটেল থেকেই পাওয়া যায়) ---
    if f1['attributes'].get('screen_size') and f2['attributes'].get('screen_size'):
        if f1['attributes']['screen_size'] != f2['attributes']['screen_size']:
            return 0.0

    # কোর টাইটেল ম্যাচিং (নয়েজ পরিষ্কার করার পর)
    core1 = f1['core_name']
    core2 = f2['core_name']

    # Primary scoring using token_set_ratio (বেশি নমনীয়, শব্দের ক্রম এলোমেলো হলেও কাজ করে)
    score = fuzz.token_set_ratio(core1, core2)
    
    # --- বোনাস বুস্ট (যদি স্পেসিফিক ক্রিটিক্যাল অ্যাট্রিবিউটগুলো স্পষ্টভাবে উপস্থিত থাকে) ---
    # মডেল কোড বুস্ট: যদি ফুল মডেল কোড (SM-S731U, A1387) টাইটেলে থাকে
    if f1['attributes'].get('model_code') and f1['attributes']['model_code'].lower() in title2.lower():
        score += 15
    elif f2['attributes'].get('model_code') and f2['attributes']['model_code'].lower() in title1.lower():
        score += 15
    
    # সিরিজ/মডেল বুস্ট: যদি S25FE/A17 টাইটেলে থাকে
    if f1['attributes'].get('series_model') and f1['attributes']['series_model'].lower() in title2.lower():
        score += 10
    elif f2['attributes'].get('series_model') and f2['attributes']['series_model'].lower() in title1.lower():
        score += 10

    # আইফোন মডেল বুস্ট: যদি আইফোন মডেল নম্বর টাইটেলে থাকে
    if f1['attributes'].get('iphone_model_num') and f1['attributes']['iphone_model_num'].lower() in title2.lower():
        score += 10
    elif f2['attributes'].get('iphone_model_num') and f2['attributes']['iphone_model_num'].lower() in title1.lower():
        score += 10

    return min(100.0, score) # স্কোর ১০০ এর বেশি হবে না


def get_product_fingerprint(title):
    return {
        'core_name': extract_core_title(title),
        'attributes': extract_attributes(title)
    }

def clean_product_title(title): return extract_core_title(title)
def product_match_score(title1, title2): return calculate_match_score(title1, title2)