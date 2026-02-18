import requests
from django.conf import settings
from django.core.cache import cache
import xml.etree.ElementTree as ET


class ClickBankService:
    """
    ClickBank Marketplace API Integration
    
    Note: ClickBank has different API endpoints:
    1. Marketplace Feed (XML) - Public, no auth needed
    2. Developer API - Needs API key and account
    3. Analytics API - For affiliates
    
    This service uses Marketplace Feed for product listings
    """
    
    def __init__(self):
        self.api_key = settings.CLICKBANK_API_KEY if hasattr(settings, 'CLICKBANK_API_KEY') else None
        self.marketplace_feed_url = "https://accounts.clickbank.com/mkplSearchResult.htm"
        # Alternative: Use ClickBank API if you have credentials
        self.api_base_url = "https://api.clickbank.com/rest/1.3"
    
    def search_products(self, query='', category='', limit=10, sort_by='popularity'):
        """
        Search ClickBank marketplace
        
        Args:
            query: Search keyword
            category: Category filter (e-business, health, etc.)
            limit: Number of results
            sort_by: popularity, gravity, commission
        
        Returns:
            List of product dictionaries
        """
        
        # Check cache first
        cache_key = f'clickbank_search_{query}_{category}_{limit}'
        cached_results = cache.get(cache_key)
        if cached_results:
            return cached_results
        
        try:
            # ClickBank Marketplace Search
            params = {
                'resultsPerPage': limit,
                'sortField': sort_by
            }
            
            if query:
                params['keywords'] = query
            
            if category:
                params['cat'] = category
            
            response = requests.get(
                self.marketplace_feed_url,
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"ClickBank Search Error: {response.status_code}")
                return None
            
            # Parse XML response
            products = self._parse_marketplace_xml(response.content)
            
            # Cache for 1 hour
            cache.set(cache_key, products, 3600)
            
            return products[:limit]
            
        except Exception as e:
            print(f"ClickBank Search Exception: {e}")
            return None
    
    def get_product_details(self, product_id):
        """
        Get detailed product information
        
        Args:
            product_id: ClickBank product ID (vendor)
        
        Returns:
            Product details dictionary
        """
        
        # Check cache
        cache_key = f'clickbank_product_{product_id}'
        cached_product = cache.get(cache_key)
        if cached_product:
            return cached_product
        
        try:
            # If you have API access
            if self.api_key:
                headers = {
                    'Authorization': self.api_key,
                    'Accept': 'application/json'
                }
                
                url = f"{self.api_base_url}/products/{product_id}"
                response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    product_data = response.json()
                    cache.set(cache_key, product_data, 3600)
                    return product_data
            
            # Fallback: Search for single product
            results = self.search_products(query=product_id, limit=1)
            if results and len(results) > 0:
                product_data = results[0]
                cache.set(cache_key, product_data, 3600)
                return product_data
            
            return None
            
        except Exception as e:
            print(f"ClickBank Product Details Exception: {e}")
            return None
    
    def _parse_marketplace_xml(self, xml_content):
        """
        Parse ClickBank marketplace XML feed
        
        Returns:
            List of product dictionaries
        """
        products = []
        
        try:
            # This is a simplified parser
            # You'll need to adjust based on actual ClickBank XML structure
            
            # For now, return mock data structure
            # In production, parse actual XML
            
            return products
            
        except Exception as e:
            print(f"XML Parse Error: {e}")
            return []
    
    def get_categories(self):
        """
        Get ClickBank categories
        
        Returns:
            List of category dictionaries
        """
        categories = [
            {'code': 'ebusiness', 'name': 'E-Business & E-Marketing'},
            {'code': 'health', 'name': 'Health & Fitness'},
            {'code': 'money', 'name': 'Money & Employment'},
            {'code': 'software', 'name': 'Software & Services'},
            {'code': 'home', 'name': 'Home & Garden'},
            {'code': 'fun', 'name': 'Fun & Entertainment'},
            {'code': 'sports', 'name': 'Sports'},
            {'code': 'travel', 'name': 'Travel'},
            {'code': 'reference', 'name': 'Reference'},
            {'code': 'self-help', 'name': 'Self-Help'},
            {'code': 'parenting', 'name': 'Parenting & Families'},
            {'code': 'politics', 'name': 'Politics & Current Events'},
            {'code': 'green', 'name': 'Green Products'},
            {'code': 'spirituality', 'name': 'Spirituality, New Age & Alternative Beliefs'},
        ]
        return categories
    
    def extract_product_data(self, item_data):
        """
        Extract and normalize ClickBank product data to match our model
        
        Args:
            item_data: Raw product data from ClickBank
        
        Returns:
            Dictionary ready for database insertion
        """
        
        # ClickBank products are digital, so some fields will be different
        return {
            # Basic Info
            'external_id': item_data.get('site', ''),  # ClickBank uses 'site' as product ID
            'title': item_data.get('title', ''),
            'description': item_data.get('description', ''),
            'external_url': item_data.get('url', ''),
            
            # Price (ClickBank shows commission, not actual price always)
            'price': float(item_data.get('price', 0)),
            'currency': 'USD',  # ClickBank primarily uses USD
            'original_price': None,
            'discount_percentage': None,
            
            # Condition (Digital products are always "new")
            'condition': 'NEW',
            'quantity': 999999,  # Digital products have unlimited quantity
            
            # Images
            'main_image': item_data.get('image_url', ''),
            'additional_images': [],
            
            # Seller (Vendor info)
            'seller_username': item_data.get('vendor', ''),
            'seller_rating': float(item_data.get('gravity', 0)),  # Use gravity as rating
            'seller_feedback_count': 0,
            
            # Location (Digital product - no physical location)
            'item_location': 'Digital Product',
            'ships_from_country': 'US',
            
            # Shipping (Digital - instant delivery)
            'shipping_info': {
                'cost': 0,
                'currency': 'USD',
                'free_shipping': True,
                'estimated_days': 0  # Instant digital delivery
            },
            
            # Returns (Usually no returns for digital products)
            'returns_accepted': False,
            'return_period_days': 0,
            
            # Specifications
            'specifications': {
                'Product Type': 'Digital Product',
                'Category': item_data.get('category', 'N/A'),
                'Gravity': str(item_data.get('gravity', 'N/A')),
                'Commission': f"${item_data.get('commission', 0)}",
                'Initial $/Sale': f"${item_data.get('initial_sale', 0)}",
                'Rebuild': item_data.get('rebuild', 'N/A'),
                'Vendor': item_data.get('vendor', 'N/A'),
            },
            
            # Brand/Model
            'brand': item_data.get('vendor', ''),
            'model_number': item_data.get('site', ''),
            
            # Category
            'category_path': item_data.get('category', ''),
            
            # Availability
            'is_available': True,
        }
    
    def search_mock_products(self, query='', limit=10):
        """
        Mock product data for testing
        Use this until you get actual ClickBank API access
        """
        mock_products = [
            {
                'site': 'prodname1',
                'title': 'Digital Marketing Mastery Course',
                'description': 'Complete guide to digital marketing with video tutorials',
                'price': 47.00,
                'commission': 35.00,
                'gravity': 156.5,
                'vendor': 'DigiMarketPro',
                'category': 'E-Business & E-Marketing',
                'url': 'https://hop.clickbank.net/?vendor=prodname1',
                'image_url': 'https://via.placeholder.com/400x300?text=Digital+Marketing',
                'initial_sale': 35.00,
                'rebuild': 75
            },
            {
                'site': 'fitpro2023',
                'title': 'Ultimate Weight Loss System',
                'description': 'Proven weight loss program with meal plans and workouts',
                'price': 37.00,
                'commission': 28.00,
                'gravity': 234.8,
                'vendor': 'HealthFitPro',
                'category': 'Health & Fitness',
                'url': 'https://hop.clickbank.net/?vendor=fitpro2023',
                'image_url': 'https://via.placeholder.com/400x300?text=Weight+Loss',
                'initial_sale': 28.00,
                'rebuild': 60
            },
            {
                'site': 'wealthbldr',
                'title': 'Passive Income Blueprint',
                'description': 'Step-by-step guide to building passive income streams',
                'price': 67.00,
                'commission': 50.00,
                'gravity': 189.3,
                'vendor': 'WealthBuilders',
                'category': 'Money & Employment',
                'url': 'https://hop.clickbank.net/?vendor=wealthbldr',
                'image_url': 'https://via.placeholder.com/400x300?text=Passive+Income',
                'initial_sale': 50.00,
                'rebuild': 85
            },
            {
                'site': 'guitarhero',
                'title': 'Learn Guitar in 30 Days',
                'description': 'Complete guitar course for beginners',
                'price': 29.00,
                'commission': 20.00,
                'gravity': 92.4,
                'vendor': 'MusicMaster',
                'category': 'Fun & Entertainment',
                'url': 'https://hop.clickbank.net/?vendor=guitarhero',
                'image_url': 'https://via.placeholder.com/400x300?text=Guitar+Course',
                'initial_sale': 20.00,
                'rebuild': 45
            },
            {
                'site': 'sleepfix',
                'title': 'Sleep Better Tonight Program',
                'description': 'Natural solutions for better sleep quality',
                'price': 39.00,
                'commission': 29.00,
                'gravity': 178.6,
                'vendor': 'SleepWell',
                'category': 'Health & Fitness',
                'url': 'https://hop.clickbank.net/?vendor=sleepfix',
                'image_url': 'https://via.placeholder.com/400x300?text=Sleep+Better',
                'initial_sale': 29.00,
                'rebuild': 70
            }
        ]
        
        # Filter by query if provided
        if query:
            mock_products = [
                p for p in mock_products 
                if query.lower() in p['title'].lower() or 
                   query.lower() in p['description'].lower() or
                   query.lower() in p['category'].lower()
            ]
        
        return mock_products[:limit]