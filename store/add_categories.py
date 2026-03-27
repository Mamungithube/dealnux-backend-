#add_categories.py
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dealnux.settings')
django.setup()

from api_integration.models import Category
from django.utils.text import slugify

# ============================================================
# Delete all previous categories and start over.
# ============================================================
deleted, _ = Category.objects.all().delete()

CATEGORY_TREE = [

    # ── 1. ELECTRONICS ──────────────────────────────────────
    ("Electronics", [
        "Smartphones & Cell Phones",
        "Laptops",
        "Desktop Computers",
        "Tablets & E-Readers",
        "Monitors & Displays",
        "Computer Components & Parts",
        "Computer Accessories",
        "Printers, Scanners & Ink",
        "Networking & Wi-Fi",
        "Storage Devices",
        "Audio & Headphones",
        "Cameras & Photography",
        "Camcorders & Action Cameras",
        "Smartwatches & Fitness Bands",
        "Wearable Technology",
        "TV & Home Theater",
        "Projectors & Screens",
        "Smart Home Devices",
        "Home Security & Surveillance",
        "Video Games & Consoles",
        "Gaming Accessories",
        "Drones & RC Vehicles",
        "Virtual Reality (VR) & AR",
        "Batteries & Chargers",
        "Cables & Adapters",
        "Office Electronics",
        "Refurbished Electronics",
    ]),

    # ── 2. MEN'S FASHION ────────────────────────────────────
    ("Men's Fashion", [
        "Men's Clothing",
        "Men's Shoes & Footwear",
        "Men's Watches",
        "Men's Accessories & Belts",
        "Men's Sunglasses",
        "Men's Grooming & Shaving",
        "Men's Underwear & Socks",
        "Men's Sportswear & Activewear",
        "Men's Formal Wear",
        "Men's Bags & Backpacks",
    ]),

    # ── 3. WOMEN'S FASHION ──────────────────────────────────
    ("Women's Fashion", [
        "Women's Clothing",
        "Women's Shoes & Footwear",
        "Handbags, Purses & Wallets",
        "Women's Watches",
        "Fine Jewelry",
        "Fashion Jewelry & Accessories",
        "Lingerie & Sleepwear",
        "Beauty & Makeup",
        "Women's Sportswear & Activewear",
        "Women's Sunglasses",
        "Hair Accessories",
        "Maternity Clothing",
        "Swimwear & Cover-Ups",
        "Plus Size Fashion",
        "Vintage & Collectible Fashion",
    ]),

    # ── 4. HOME & KITCHEN ───────────────────────────────────
    ("Home & Kitchen", [
        "Furniture",
        "Home Decor & Accents",
        "Kitchen & Dining",
        "Cookware & Bakeware",
        "Kitchen Appliances",
        "Bedding & Pillows",
        "Bath Towels & Accessories",
        "Storage & Organization",
        "Cleaning Supplies & Tools",
        "Laundry & Fabric Care",
        "Lighting & Ceiling Fans",
        "Heating, Cooling & Air Quality",
        "Vacuums & Floor Care",
        "Large Appliances",
        "Patio, Lawn & Garden",
        "Outdoor Furniture & Decor",
        "Grills & Outdoor Cooking",
        "Tools & Home Improvement",
        "Plumbing & Hardware",
        "Electrical & Safety",
        "Paint & Wall Treatments",
        "Flooring & Area Rugs",
        "Window Treatments",
        "Pet Supplies",
        "Moving & Packing Supplies",
    ]),

    # ── 5. HEALTH & BEAUTY ──────────────────────────────────
    ("Health & Beauty", [
        "Skincare",
        "Hair Care",
        "Fragrances & Perfumes",
        "Vitamins & Dietary Supplements",
        "Sports Nutrition",
        "Personal Care & Hygiene",
        "Oral Care",
        "Medical Supplies & Equipment",
        "Health Monitors & Tests",
        "Eye Care",
        "Feminine Care",
        "Men's Health",
        "Weight Loss & Slimming",
        "Mental Wellness & Meditation",
        "Sexual Wellness",
        "Baby & Child Health",
        "First Aid & Safety",
    ]),

    # ── 6. SPORTS & OUTDOORS ────────────────────────────────
    ("Sports & Outdoors", [
        "Exercise & Fitness Equipment",
        "Cycling & Bicycles",
        "Camping, Hiking & Backpacking",
        "Fishing Equipment",
        "Water Sports & Swimming",
        "Team Sports",
        "Golf Equipment",
        "Hunting & Shooting",
        "Martial Arts & Combat Sports",
        "Climbing & Caving",
        "Winter Sports & Snowboarding",
        "Skateboarding & Scooters",
        "Fan Shop & Memorabilia",
        "Sports Clothing & Footwear",
        "Sports Nutrition & Recovery",
    ]),

    # ── 7. BABY & KIDS ──────────────────────────────────────
    ("Baby & Kids", [
        "Baby Products & Accessories",
        "Baby Gear & Strollers",
        "Baby Clothing & Shoes",
        "Baby Food & Formula",
        "Diapering & Potty Training",
        "Nursery Furniture & Decor",
        "Toys & Games",
        "Action Figures & Collectibles",
        "Dolls & Dollhouses",
        "Building Toys & LEGO",
        "Puzzles & Board Games",
        "Outdoor Toys & Play Equipment",
        "Arts & Crafts for Kids",
        "Kids Clothing & Shoes",
        "Kids Books & Educational",
        "Kids Electronics & Gadgets",
        "School Supplies",
    ]),

    # ── 8. AUTOMOTIVE ───────────────────────────────────────
    ("Automotive", [
        "Car Electronics & GPS",
        "Car Interior Accessories",
        "Car Exterior Accessories",
        "Car Care & Detailing",
        "Motor Oil & Fluids",
        "Automotive Tools & Equipment",
        "Tires & Wheels",
        "Replacement Parts & OEM",
        "Motorcycle Parts & Accessories",
        "RV, Trailer & Camper Parts",
        "Boat & Marine Accessories",
        "ATV & Powersports Parts",
        "Performance & Racing Parts",
    ]),

    # ── 9. BOOKS & ENTERTAINMENT ────────────────────────────
    ("Books & Entertainment", [
        "Fiction Books",
        "Non-Fiction & Educational Books",
        "Children's Books",
        "Textbooks & Academic",
        "Comics & Graphic Novels",
        "Magazines & Newspapers",
        "Movies & TV Shows",
        "Music & Vinyl Records",
        "Musical Instruments",
        "Sheet Music & Songbooks",
        "Video Game Software & DLC",
    ]),

    # ── 10. FOOD & GROCERY ──────────────────────────────────
    ("Food & Grocery", [
        "Snack Foods",
        "Beverages & Coffee",
        "Pantry Staples & Dry Goods",
        "Organic & Natural Foods",
        "International & Ethnic Foods",
        "Candy & Chocolate",
        "Gourmet & Specialty Foods",
        "Cooking Oils & Condiments",
        "Baking Supplies",
        "Frozen Foods",
        "Fresh Produce & Meat",
        "Wine, Beer & Spirits",
    ]),

    # ── 11. OFFICE & BUSINESS ───────────────────────────────
    ("Office & Business", [
        "Office Furniture",
        "Office Supplies & Stationery",
        "Printer Cartridges & Paper",
        "Presentation & Whiteboards",
        "Mailing & Shipping Supplies",
        "Industrial & Scientific",
        "Janitorial & Sanitation",
        "Safety & Security Equipment",
        "Point of Sale (POS) Systems",
        "Business Signs & Displays",
    ]),

    # ── 12. ARTS, CRAFTS & COLLECTIBLES ─────────────────────
    ("Arts, Crafts & Collectibles", [
        "Art Supplies & Painting",
        "Sewing, Knitting & Crochet",
        "Scrapbooking & Paper Crafts",
        "DIY Craft Kits",
        "Coins & Currency",
        "Stamps & Philately",
        "Sports Cards & Memorabilia",
        "Antiques & Vintage Items",
        "Trading Cards (Pokemon, MTG)",
        "Autographs & Signed Items",
        "Movie & TV Collectibles",
        "Comic Books & Original Art",
        "Handmade & Custom Items",
        "Pottery & Ceramics",
        "Photography & Prints",
    ]),

    # ── 13. DIGITAL PRODUCTS & SERVICES ─────────────────────
    ("Digital Products & Services", [
        "E-Business & E-Marketing",
        "Self-Help & Personal Development",
        "Software & SaaS",
        "Online Courses & E-Learning",
        "Health & Fitness Programs",
        "Wealth & Investment Programs",
        "Relationship & Dating Advice",
        "Spirituality & New Age",
        "Green Products & Environment",
        "Language Learning",
        "Photography & Video Courses",
        "Music Production & DJ",
        "Parenting & Family Programs",
        "Legal & Financial Guides",
        "Travel Guides & Membership",
        "Subscription Boxes",
        "NFT & Digital Art",
        "Website Templates & Themes",
        "Plugins & Extensions",
    ]),

    # ── 14. TRAVEL & EXPERIENCES ────────────────────────────
    ("Travel & Experiences", [
        "Luggage & Travel Bags",
        "Travel Accessories",
        "Travel Pillows & Comfort",
        "Outdoor & Adventure Gear",
        "Hotel & Accommodation Deals",
        "Flight Deals",
        "Vacation Packages",
        "Travel Insurance",
        "Cruise Accessories",
    ]),

    # ── 15. REAL ESTATE & HOME SERVICES ─────────────────────
    ("Real Estate & Home Services", [
        "Home Improvement Services",
        "Moving & Relocation",
        "Home Security Services",
        "Solar & Energy Solutions",
        "Home Warranty & Insurance",
        "Mortgages & Refinancing",
    ]),

    # ── 16. FINANCIAL PRODUCTS ──────────────────────────────
    ("Financial Products", [
        "Credit Cards & Banking",
        "Personal Loans",
        "Insurance (Life, Auto, Health)",
        "Investment & Trading Platforms",
        "Cryptocurrency & Blockchain",
        "Tax Software & Services",
        "Debt Relief Programs",
    ]),

    # ── 17. WEDDING & EVENTS ────────────────────────────────
    ("Wedding & Events", [
        "Wedding Dresses & Accessories",
        "Wedding Decorations",
        "Wedding Invitations & Stationery",
        "Party Supplies & Decorations",
        "Holiday Decorations",
        "Gift Wrapping & Packaging",
        "Personalized & Custom Gifts",
        "Gift Cards & Vouchers",
        "Flowers & Plants",
        "Greeting Cards",
    ]),

    # ── 18. INDUSTRIAL & PROFESSIONAL ───────────────────────
    ("Industrial & Professional", [
        "Test & Measurement Equipment",
        "Lab & Scientific Equipment",
        "Farm & Agricultural Supplies",
        "Construction & Building Materials",
        "HVAC & Plumbing Wholesale",
        "Restaurant & Food Service",
        "Medical & Dental Equipment",
        "Wholesale & Bulk Items",
    ]),
]

# ============================================================
# Seeder — parent then children
# ============================================================
created = 0
skipped = 0

for parent_name, children in CATEGORY_TREE:
    parent_slug = slugify(parent_name)
    parent_obj, parent_new = Category.objects.get_or_create(
        slug=parent_slug,
        defaults={'name': parent_name, 'parent': None}
    )
    if parent_new:
        created += 1
        # print(f"  ✚ {parent_name}")
    else:
        skipped += 1
        # print(f"  • {parent_name} (exists)")

    for child_name in children:
        child_slug = slugify(child_name)
        _, child_new = Category.objects.get_or_create(
            slug=child_slug,
            defaults={'name': child_name, 'parent': parent_obj}
        )
        if child_new:
            created += 1
            # print(f"      + {child_name}")
        else:
            skipped += 1