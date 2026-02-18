from django.core.management.base import BaseCommand, CommandError
from api_integration.models import Product, ProductListing, Platform, ProductSpecification, PriceHistory
from api_integration.services.clickbank_service import ClickBankService
from django.db import transaction


class Command(BaseCommand):
    help = 'Sync products from ClickBank to database'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'query',
            type=str,
            nargs='?',
            default='',
            help='Search query for products (optional)'
        )
        parser.add_argument(
            '--category',
            type=str,
            default='',
            help='ClickBank category (e.g., health, money, ebusiness)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Number of products to sync (default: 10)'
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing products'
        )
    
    def handle(self, *args, **options):
        query = options['query']
        category = options['category']
        limit = options['limit']
        update_existing = options['update_existing']
        
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(self.style.SUCCESS('Starting ClickBank Product Sync'))
        self.stdout.write(self.style.SUCCESS('='*60))
        
        if query:
            self.stdout.write(f'Search Query: {query}')
        if category:
            self.stdout.write(f'Category: {category}')
        self.stdout.write(f'Limit: {limit}')
        
        # Get or create ClickBank platform
        platform, created = Platform.objects.get_or_create(
            code='clickbank',
            defaults={
                'name': 'ClickBank',
                'api_enabled': True
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created ClickBank platform'))
        
        # Initialize service
        clickbank_service = ClickBankService()
        
        # Search products (using mock data for now)
        self.stdout.write('\nSearching ClickBank products...')
        # Replace with actual API call when ready:
        # products = clickbank_service.search_products(query, category, limit)
        products = clickbank_service.search_mock_products(query, limit)
        
        if not products:
            raise CommandError('No products found or API error')
        
        total_products = len(products)
        self.stdout.write(self.style.SUCCESS(f'✓ Found {total_products} products'))
        
        synced_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        for idx, item in enumerate(products, 1):
            external_id = item.get('site')
            
            self.stdout.write(f'\n[{idx}/{total_products}] Processing: {external_id}')
            
            try:
                # Check if exists
                existing_listing = ProductListing.objects.filter(
                    platform=platform,
                    external_id=external_id
                ).first()
                
                if existing_listing and not update_existing:
                    self.stdout.write(self.style.WARNING('  ○ Already exists, skipping'))
                    skipped_count += 1
                    continue
                
                # Extract product data
                product_data = clickbank_service.extract_product_data(item)
                
                with transaction.atomic():
                    # Create or get product
                    product, product_created = Product.objects.get_or_create(
                        title=product_data['title'],
                        defaults={
                            'description': product_data['description'],
                            'brand': product_data['brand'],
                            'model_number': product_data['model_number'],
                            'main_image': product_data['main_image']
                        }
                    )
                    
                    if product_created:
                        self.stdout.write(self.style.SUCCESS(f'  ✓ Created product: {product.title[:50]}'))
                    else:
                        self.stdout.write(f'  • Using existing product: {product.title[:50]}')
                    
                    # Create or update listing
                    shipping_info = product_data['shipping_info']
                    
                    listing, listing_created = ProductListing.objects.update_or_create(
                        product=product,
                        platform=platform,
                        external_id=external_id,
                        defaults={
                            'external_url': product_data['external_url'],
                            'price': product_data['price'],
                            'currency': product_data['currency'],
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
                    )
                    
                    if listing_created:
                        self.stdout.write(self.style.SUCCESS('  ✓ Created listing'))
                        synced_count += 1
                        
                        # Record price history
                        PriceHistory.objects.create(
                            listing=listing,
                            price=listing.price,
                            currency=listing.currency
                        )
                    else:
                        self.stdout.write(self.style.SUCCESS('  ✓ Updated listing'))
                        updated_count += 1
                        
                        # Record price change
                        last_history = listing.price_history.first()
                        if not last_history or last_history.price != listing.price:
                            PriceHistory.objects.create(
                                listing=listing,
                                price=listing.price,
                                currency=listing.currency
                            )
                            self.stdout.write('  ✓ Recorded price change')
                    
                    # Save specifications
                    if product_data.get('specifications'):
                        ProductSpecification.objects.filter(product=product).delete()
                        for name, value in product_data['specifications'].items():
                            ProductSpecification.objects.create(
                                product=product,
                                name=name,
                                value=value
                            )
                        self.stdout.write(f'  ✓ Saved {len(product_data["specifications"])} specifications')
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error: {str(e)}'))
                error_count += 1
                continue
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('Sync Completed!'))
        self.stdout.write('='*60)
        self.stdout.write(f'Total processed: {total_products}')
        self.stdout.write(self.style.SUCCESS(f'Synced (new): {synced_count}'))
        self.stdout.write(self.style.WARNING(f'Updated: {updated_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped: {skipped_count}'))
        self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        self.stdout.write('='*60)