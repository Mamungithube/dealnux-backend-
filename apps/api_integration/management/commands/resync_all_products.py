from django.core.management.base import BaseCommand
from api_integration.models import ProductListing
from api_integration.tasks import sync_all_platforms_task


class Command(BaseCommand):
    help = 'Re-sync all existing products to update new fields'

    def handle(self, *args, **kwargs):
        titles = ProductListing.objects.values_list(
            'product__title', flat=True
        ).distinct()[:500]

        queries = set()
        for title in titles:
            words = title.strip().split()[:2]
            query = ' '.join(words)
            if len(query) > 3:
                queries.add(query)

        self.stdout.write(f"Total unique queries: {len(queries)}")

        for i, query in enumerate(queries):
            sync_all_platforms_task.apply_async(
                args=[query, 10],
                countdown=i * 5 
            )
            self.stdout.write(f"Queued: {query}")

        self.stdout.write(self.style.SUCCESS("All tasks queued!"))