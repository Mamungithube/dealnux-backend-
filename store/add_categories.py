import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dealnux.settings')
django.setup()

from api_integration.models import Category
from django.utils.text import slugify

categories = [
    "Smartphones", "Laptops", "Desktop Computers", "Tablets",
    "Audio & Headphones", "Cameras & Photo", "Smartwatches",
    "TV & Home Theater", "Video Games & Consoles", "Computer Accessories",
    "Printers & Ink", "Drones & RC", "Wearable Technology",
    "Men's Clothing", "Men's Shoes", "Men's Watches",
    "Men's Accessories & Belts", "Men's Sunglasses", "Men's Grooming",
    "Women's Clothing", "Women's Shoes", "Handbags & Wallets",
    "Women's Watches", "Fine Jewelry", "Fashion Accessories",
    "Lingerie & Sleepwear", "Beauty & Makeup",
    "Furniture", "Home Decor", "Kitchen & Dining", "Bedding & Bath",
    "Garden & Outdoor", "Tools & Home Improvement", "Lighting & Ceiling Fans",
    "Smart Home Devices", "Pet Supplies",
    "Skincare", "Hair Care", "Fragrances & Perfumes",
    "Vitamins & Dietary Supplements", "Personal Care & Hygiene",
    "Medical Supplies & Equipment", "Oral Care",
    "Exercise & Fitness Equipment", "Cycling & Bicycles", "Camping & Hiking",
    "Fishing Equipment", "Water Sports", "Team Sports", "Golf Equipment",
    "Baby Products & Accessories", "Toys & Games", "Kids Clothing",
    "Action Figures & Collectibles", "Puzzles & Board Games", "Baby Gear & Strollers",
    "Car Electronics & GPS", "Car Interior Accessories", "Car Exterior Accessories",
    "Motorcycle Parts & Accessories", "Automotive Tools & Equipment",
    "Fiction Books", "Non-Fiction & Educational Books", "Movies & TV Shows",
    "Music & Vinyl Records", "Musical Instruments",
    "Snack Foods", "Beverages & Coffee", "Pantry Staples", "Household Cleaning Supplies",
    "E-Business & E-Marketing", "Self-Help & Personal Development",
    "Software & Services", "Online Courses",
]

created = 0
skipped = 0
for name in categories:
    slug = slugify(name)
    obj, is_new = Category.objects.get_or_create(slug=slug, defaults={'name': name})
    if is_new:
        created += 1
        print(f"  + Created: {name}")
    else:
        skipped += 1

print(f"\nDone! Created: {created}, Skipped: {skipped}")
print(f"Total categories: {Category.objects.count()}")