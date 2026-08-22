"""
Test script to verify Product API lookup by both ID & Slug,
and verify AI Recommendation Notification creation & URL resolution.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dealnux.settings')
import django
django.setup()

from rest_framework.test import APIClient
from api_integration.models import Product, ProductListing
from notifications.models import Notification
from notifications.tasks import send_daily_ai_recommendations
from account.models import User

client = APIClient()

print("\n==========================================")
print("  TEST 1: Product API Lookup (ID vs Slug)")
print("==========================================")

product = Product.objects.filter(is_active=True).first()

if not product:
    print("No active product found in DB to test.")
else:
    print(f"Testing with Product:")
    print(f"  ID   : {product.id}")
    print(f"  Slug : {product.slug}")
    print(f"  Title: {product.title}")

    # 1. Test lookup by Numeric ID: /api/products/<id>/
    res_id = client.get(f"/api/products/{product.id}/")
    print(f"\n[GET /api/products/{product.id}/ (by ID)]")
    print(f"  Status Code: {res_id.status_code}")
    if res_id.status_code == 200:
        print(f"  SUCCESS! Product Title fetched: {res_id.data.get('title')}")
        print(f"  Price: {res_id.data.get('price')}, Lowest: {res_id.data.get('lowest_price')}")
    else:
        print(f"  FAILED: {res_id.data}")

    # 2. Test lookup by Slug: /api/products/<slug>/
    if product.slug:
        res_slug = client.get(f"/api/products/{product.slug}/")
        print(f"\n[GET /api/products/{product.slug}/ (by Slug)]")
        print(f"  Status Code: {res_slug.status_code}")
        if res_slug.status_code == 200:
            print(f"  SUCCESS! Product Title fetched: {res_slug.data.get('title')}")
        else:
            print(f"  FAILED: {res_slug.data}")

print("\n==========================================")
print("  TEST 2: AI Recommendation Notification")
print("==========================================")

# Run the recommendation task
task_result = send_daily_ai_recommendations()
print(f"Task executed: {task_result}")

latest_notif = Notification.objects.filter(notification_type='AI_RECOMMENDATION').order_by('-created_at').first()
if latest_notif:
    print(f"\nLatest AI Recommendation Notification:")
    print(f"  Title   : {latest_notif.title}")
    print(f"  Body    : {latest_notif.body}")
    print(f"  CTA Link: {latest_notif.cta_link}")
    
    # Test if cta_link resolves
    if latest_notif.cta_link:
        # e.g. /product/123 or /product/slug
        param = latest_notif.cta_link.replace('/product/', '').strip('/')
        test_api_url = f"/api/products/{param}/"
        res_link = client.get(test_api_url)
        print(f"\n[Testing API call with CTA Link param -> GET {test_api_url}]")
        print(f"  Status Code: {res_link.status_code}")
        if res_link.status_code == 200:
            print(f"  SUCCESS! Recommendation target product loaded correctly without error.")
        else:
            print(f"  FAILED to load product via CTA link param: {res_link.data}")
else:
    print("No AI Recommendation notification created (maybe no active users or hot deals in DB).")

print("\n==========================================")
print("  TESTS COMPLETED")
print("==========================================\n")
