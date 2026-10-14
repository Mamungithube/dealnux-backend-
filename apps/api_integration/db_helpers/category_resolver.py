import time
from django.utils.text import slugify
from .category_mapping import _KEYWORD_CATEGORY_MAP

_CATEGORY_CACHE = None


def _get_category_cache():
    global _CATEGORY_CACHE
    now = time.time()
    if _CATEGORY_CACHE is None or (now - _CATEGORY_CACHE['loaded_at']) > 300:
        from ..models import Category
        qs = Category.objects.all().only('id', 'name', 'slug')
        _CATEGORY_CACHE = {
            'by_slug':       {cat.slug: cat for cat in qs},
            'by_name_lower': {cat.name.lower(): cat for cat in qs},
            'all':           list(qs),
            'loaded_at':     now,
        }
    return _CATEGORY_CACHE


def _resolve_category(category_path, title, cache):
    title_lower = (title or '').lower()

    GLOBAL_FORBIDDEN = [
        'libido', 'gummies', 'supplement', 'sticker only', 'manual only', 
        'digital image', 'wallpaper', 'tutorial', 'guide only'
    ]
    if any(f in title_lower for f in GLOBAL_FORBIDDEN):
        return None

    if category_path:
        parts = [p.strip() for p in category_path.split('>')]
        for part in parts:
            slug_key = slugify(part)
            if slug_key in cache['by_slug']:
                return cache['by_slug'][slug_key]
            if part.lower() in cache['by_name_lower']:
                return cache['by_name_lower'][part.lower()]

        for part in parts:
            for cat_name_lower, cat_obj in cache['by_name_lower'].items():
                if len(cat_name_lower) >= 6 and (cat_name_lower in part.lower() or part.lower() in cat_name_lower):
                    return cat_obj

    if title_lower:
        padded = f' {title_lower} '
        for keywords, target_slug in _KEYWORD_CATEGORY_MAP:
            for kw in keywords:
                if f' {kw} ' in padded or padded.startswith(f'{kw} ') or padded.endswith(f' {kw}'):
                    
                    if target_slug == 'desktop-computers':
                        tech_junk = ['motherboard', 'mouse pad', 'fan', 'light bar', 'bracket', 'parts', 'case only', 'sleeve', 'statue', 'memo board', 'adapter']
                        if any(x in title_lower for x in tech_junk):
                            continue 
                    
                    if target_slug == 'smartphones-cell-phones':
                        phone_junk = ['case', 'cover', 'cable', 'screen protector', 'charger', 'adapter', 'magsafe']
                        if any(x in title_lower for x in phone_junk):
                            continue 

                    if target_slug == 'monitors-displays':
                        monitor_junk = ['baby', 'blood', 'pressure', 'heart', 'medical', 'caliper', 'measuring']
                        if any(m in title_lower for m in monitor_junk):
                            continue 

                    cat = cache['by_slug'].get(target_slug)
                    if cat:
                        return cat
                    
                    readable = target_slug.replace('-', ' ')
                    for cat_name_lower, cat_obj in cache['by_name_lower'].items():
                        if readable in cat_name_lower or cat_name_lower in readable:
                            return cat_obj

    return None
