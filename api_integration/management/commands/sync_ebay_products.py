from django.core.management.base import BaseCommand, CommandError
from api_integration.models import Product, ProductListing, Platform, ProductImage, ProductSpecification, PriceHistory
from ...services.ebay_service import EbayService
from django.utils.text import slugify


class Command(BaseCommand):
    help = 'Sync products from eBay API to database'
    
    def add_arguments(self, parser):
        parser.add_argument('query', type=str, help='Search query for products')
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Number of products to sync (default: 20)'
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing products'
        )
    
    def handle(self, *args, **options):
        query = options['query']
        limit = options['limit']
        update_existing = options['update_existing']
        
        self.stdout.write(self.style.SUCCESS(f'Starting eBay sync for query: "{query}"'))
        
        # Get or create eBay platform
        platform, created = Platform.objects.get_or_create(
            code='ebay',
            defaults={
                'name': 'eBay',
                'api_enabled': True
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('Created eBay platform'))
        
        # Initialize eBay service
        ebay_service = EbayService()
        
        # Search products
        self.stdout.write(f'Searching eBay for "{query}"...')
        results = ebay_service.search_products(query, limit=limit)
        
        if not results:
            raise CommandError('Failed to fetch products from eBay API')
        
        items = results.get('itemSummaries', [])
        total_items = len(items)
        
        self.stdout.write(self.style.SUCCESS(f'Found {total_items} products'))
        
        synced_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        for idx, item in enumerate(items, 1):
            item_id = item.get('itemId')
            
            self.stdout.write(f'\nProcessing {idx}/{total_items}: {item_id}')
            
            try:
                # Check if listing already exists
                existing_listing = ProductListing.objects.filter(
                    platform=platform,
                    external_id=item_id
                ).first()
                
                if existing_listing and not update_existing:
                    self.stdout.write(self.style.WARNING('  Already exists, skipping...'))
                    skipped_count += 1
                    continue
                
                # Get detailed item information
                self.stdout.write('  Fetching details from eBay...')
                item_details = ebay_service.get_item_details(item_id)
                
                if not item_details:
                    self.stdout.write(self.style.ERROR('  Failed to fetch details'))
                    error_count += 1
                    continue
                
                # Extract product data
                product_data = ebay_service.extract_product_data(item_details)
                
                # Create or update product
                product, product_created = Product.objects.get_or_create(
                    title=product_data['title'],
                    defaults={
                        'description': product_data['description'],
                        'brand': product_data['brand'],
                        'model_number': product_data['model_number'],
                        'main_image': product_data['main_image'],
                    }
                )
                
                if product_created:
                    self.stdout.write(self.style.SUCCESS(f'  Created product: {product.title[:50]}'))
                else:
                    # Update product if needed
                    if update_existing:
                        product.description = product_data['description']
                        product.main_image = product_data['main_image']
                        product.save()
                        self.stdout.write(self.style.SUCCESS(f'  Updated product: {product.title[:50]}'))
                
                # Create or update listing
                shipping_info = product_data['shipping_info']
                
                listing_defaults = {
                    'external_url': product_data['external_url'],
                    'price': product_data['price'],
                    'currency': product_data['currency'],
                    'original_price': product_data['original_price'],
                    'discount_percentage': product_data['discount_percentage'],
                    'condition': product_data['condition'],
                    'quantity': product_data['quantity'],
                    'seller_username': product_data['seller_username'],
                    'seller_rating': product_data['seller_rating'],
                    'seller_feedback_count': product_data['seller_feedback_count'],
                    'item_location': product_data['item_location'],
                    'ships_from_country': product_data['ships_from_country'],
                    'shipping_cost': shipping_info['cost'],
                    'shipping_currency': shipping_info['currency'],
                    'free_shipping': shipping_info['free_shipping'],
                    'estimated_delivery_days': shipping_info['estimated_days'],
                    'returns_accepted': product_data['returns_accepted'],
                    'return_period_days': product_data['return_period_days'],
                    'is_available': product_data['is_available']
                }
                
                listing, listing_created = ProductListing.objects.update_or_create(
                    product=product,
                    platform=platform,
                    external_id=product_data['external_id'],
                    defaults=listing_defaults
                )
                
                if listing_created:
                    self.stdout.write(self.style.SUCCESS('  Created listing'))
                    synced_count += 1
                    
                    # Record initial price history
                    PriceHistory.objects.create(
                        listing=listing,
                        price=listing.price,
                        currency=listing.currency
                    )
                else:
                    self.stdout.write(self.style.SUCCESS('  Updated listing'))
                    updated_count += 1
                    
                    # Record price change if different
                    last_history = listing.price_history.first()
                    if not last_history or last_history.price != listing.price:
                        PriceHistory.objects.create(
                            listing=listing,
                            price=listing.price,
                            currency=listing.currency
                        )
                        self.stdout.write(self.style.SUCCESS('  Recorded price change'))
                
                # Save additional images
                if product_data.get('additional_images'):
                    ProductImage.objects.filter(product=product).delete()
                    for order, image_url in enumerate(product_data['additional_images'][:10]):
                        ProductImage.objects.create(
                            product=product,
                            image_url=image_url,
                            order=order
                        )
                    self.stdout.write(self.style.SUCCESS(f'  Saved {len(product_data["additional_images"])} images'))
                
                # Save specifications
                if product_data.get('specifications'):
                    ProductSpecification.objects.filter(product=product).delete()
                    for name, value in product_data['specifications'].items():
                        ProductSpecification.objects.create(
                            product=product,
                            name=name,
                            value=value
                        )
                    self.stdout.write(self.style.SUCCESS(f'  Saved {len(product_data["specifications"])} specifications'))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error: {str(e)}'))
                error_count += 1
                continue
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('Sync completed!'))
        self.stdout.write(f'Total processed: {total_items}')
        self.stdout.write(self.style.SUCCESS(f'Synced: {synced_count}'))
        self.stdout.write(self.style.WARNING(f'Updated: {updated_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped: {skipped_count}'))
        self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        self.stdout.write('='*60)