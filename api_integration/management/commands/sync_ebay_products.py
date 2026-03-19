"""
sync_ebay_products.py  —  Management command
Fix: EbayService → EbayRapidService (ImportError ছিল)
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api_integration.models import (
    Product, ProductListing, Platform,
    ProductImage, ProductSpecification, PriceHistory
)
# Fix: EbayRapidService — আগে EbayService লেখা ছিল যেটা exist করে না
from api_integration.services.ebay_service import EbayRapidService
from api_integration.db_helpers import save_generic_product_to_db


class Command(BaseCommand):
    help = 'Sync products from eBay API to database'

    def add_arguments(self, parser):
        parser.add_argument('query', type=str, help='Search query for products')
        parser.add_argument(
            '--limit', type=int, default=20,
            help='Number of products to sync (default: 20)'
        )
        parser.add_argument(
            '--update-existing', action='store_true',
            help='Update existing products'
        )

    def handle(self, *args, **options):
        query          = options['query']
        limit          = options['limit']
        update_existing = options['update_existing']

        self.stdout.write(self.style.SUCCESS(f'Starting eBay sync for: "{query}"'))

        platform, created = Platform.objects.get_or_create(
            code='ebay',
            defaults={'name': 'eBay', 'api_enabled': True}
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Created eBay platform'))

        service = EbayRapidService()

        self.stdout.write(f'Searching eBay for "{query}"...')
        raw_items = service.search_products(query, limit=limit)

        if not raw_items:
            raise CommandError('No products found or API error')

        self.stdout.write(self.style.SUCCESS(f'Found {len(raw_items)} raw results'))

        synced_count  = 0
        updated_count = 0
        skipped_count = 0
        error_count   = 0

        for idx, item in enumerate(raw_items, 1):
            self.stdout.write(f'\n[{idx}/{len(raw_items)}] Processing...')

            try:
                product_data = service.extract_product_data(item)

                # Non-USD skip
                if product_data.get('_is_non_usd'):
                    self.stdout.write(self.style.WARNING(
                        f'  ○ Non-USD listing skipped: {product_data.get("title","")[:50]}'
                    ))
                    skipped_count += 1
                    continue

                external_id = product_data.get('external_id')

                existing = ProductListing.objects.filter(
                    platform=platform, external_id=external_id
                ).first()

                if existing and not update_existing:
                    self.stdout.write(self.style.WARNING('  ○ Already exists, skipping'))
                    skipped_count += 1
                    continue

                with transaction.atomic():
                    product, listing, created_new = save_generic_product_to_db(
                        product_data, platform, query=query
                    )

                if product and listing:
                    if created_new:
                        self.stdout.write(self.style.SUCCESS(
                            f'  ✓ Created: {product.title[:50]}'
                        ))
                        synced_count += 1
                    else:
                        self.stdout.write(f'  • Updated: {product.title[:50]}')
                        updated_count += 1
                else:
                    self.stdout.write(self.style.WARNING('  ○ Skipped (validation)'))
                    skipped_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error: {str(e)}'))
                error_count += 1
                continue

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('Sync completed!'))
        self.stdout.write(f'Total raw:    {len(raw_items)}')
        self.stdout.write(self.style.SUCCESS(f'Synced (new): {synced_count}'))
        self.stdout.write(self.style.WARNING(f'Updated:      {updated_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped:      {skipped_count}'))
        self.stdout.write(self.style.ERROR(f'Errors:       {error_count}'))
        self.stdout.write('=' * 60)