import requests
import base64
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


class EbayService:
    """eBay API Integration Service"""
    
    def __init__(self):
        self.app_id = settings.EBAY_APP_ID
        self.cert_id = settings.EBAY_CERT_ID
        self.base_url = settings.EBAY_BASE_URL
        self.token = None
    
    def get_access_token(self):
        """Get OAuth access token with caching"""
        
        # Check cache first
        cached_token = cache.get('ebay_access_token')
        if cached_token:
            return cached_token
        
        # Get new token
        credentials = f"{self.app_id}:{self.cert_id}"
        encoded = base64.b64encode(credentials.encode()).decode()
        
        url = f"{self.base_url}/identity/v1/oauth2/token"
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded}"
        }
        
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"
        }
        
        try:
            response = requests.post(url, headers=headers, data=data)
            
            if response.status_code == 200:
                token = response.json().get('access_token')
                
                # Cache for 2 hours
                cache.set('ebay_access_token', token, 7000)
                
                return token
            else:
                print(f"eBay Token Error: {response.text}")
                return None
                
        except Exception as e:
            print(f"eBay Token Exception: {e}")
            return None
    
    def search_products(self, query, limit=20, offset=0, filters=None):
        """Search products on eBay"""
        
        token = self.get_access_token()
        if not token:
            return None
        
        url = f"{self.base_url}/buy/browse/v1/item_summary/search"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
        }
        
        params = {
            "q": query,
            "limit": limit,
            "offset": offset
        }
        
        # Add filters if provided
        if filters:
            if 'price_min' in filters and 'price_max' in filters:
                params['filter'] = f"price:[{filters['price_min']}..{filters['price_max']}]"
            
            if 'condition' in filters:
                params['filter'] = f"conditions:{{{filters['condition']}}}"
            
            if 'sort' in filters:
                params['sort'] = filters['sort']
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"eBay Search Error: {response.text}")
                return None
                
        except Exception as e:
            print(f"eBay Search Exception: {e}")
            return None
    
    def get_item_details(self, item_id):
        """Get detailed information for a specific item"""
        
        token = self.get_access_token()
        if not token:
            return None
        
        url = f"{self.base_url}/buy/browse/v1/item/{item_id}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
        }
        
        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"eBay Item Details Error: {response.text}")
                return None
                
        except Exception as e:
            print(f"eBay Item Details Exception: {e}")
            return None
    
    def extract_product_data(self, item_data):
        """
        Extract and normalize product data from eBay API response
        Returns a dictionary ready for database insertion
        """
        
        return {
            # Basic Info
            "external_id": item_data.get('itemId'),
            "title": item_data.get('title'),
            "description": item_data.get('description', ''),
            "external_url": item_data.get('itemWebUrl'),
            
            # Price
            "price": item_data.get('price', {}).get('value'),
            "currency": item_data.get('price', {}).get('currency', 'USD'),
            "original_price": item_data.get('marketingPrice', {}).get('originalPrice', {}).get('value'),
            "discount_percentage": item_data.get('marketingPrice', {}).get('discountPercentage'),
            
            # Condition
            "condition": self._map_condition(item_data.get('condition')),
            "quantity": item_data.get('quantity', 0),
            
            # Images
            "main_image": item_data.get('image', {}).get('imageUrl'),
            "additional_images": [img.get('imageUrl') for img in item_data.get('additionalImages', [])],
            
            # Seller
            "seller_username": item_data.get('seller', {}).get('username'),
            "seller_rating": item_data.get('seller', {}).get('feedbackPercentage'),
            "seller_feedback_count": item_data.get('seller', {}).get('feedbackScore'),
            
            # Location
            "item_location": f"{item_data.get('itemLocation', {}).get('city')}, {item_data.get('itemLocation', {}).get('country')}",
            "ships_from_country": item_data.get('itemLocation', {}).get('country'),
            
            # Shipping
            "shipping_info": self._extract_shipping_info(item_data.get('shippingOptions', [])),
            
            # Returns
            "returns_accepted": item_data.get('returnTerms', {}).get('returnsAccepted', False),
            "return_period_days": self._extract_return_period(item_data.get('returnTerms', {})),
            
            # Specifications
            "specifications": self._extract_specifications(item_data.get('localizedAspects', [])),
            
            # Brand/Model
            "brand": item_data.get('product', {}).get('brand', ''),
            "model_number": item_data.get('product', {}).get('mpn', ''),
            
            # Category
            "category_path": item_data.get('categoryPath', ''),
            
            # Availability
            "is_available": self._check_availability(item_data),
        }
    
    def _map_condition(self, condition):
        """Map eBay condition to our standard conditions"""
        condition_mapping = {
            'New': 'NEW',
            'New other': 'NEW',
            'New with defects': 'NEW',
            'Open box': 'OPEN_BOX',
            'Used': 'USED',
            'Refurbished': 'REFURBISHED',
        }
        return condition_mapping.get(condition, 'OTHER')
    
    def _extract_shipping_info(self, shipping_options):
        """Extract shipping information"""
        if not shipping_options:
            return {
                'cost': 0,
                'currency': 'USD',
                'free_shipping': False,
                'estimated_days': None
            }
        
        first_option = shipping_options[0]
        
        return {
            'cost': first_option.get('shippingCost', {}).get('value', 0),
            'currency': first_option.get('shippingCost', {}).get('currency', 'USD'),
            'free_shipping': first_option.get('shippingCostType') == 'FREE',
            'estimated_days': self._calculate_delivery_days(first_option)
        }
    
    def _calculate_delivery_days(self, shipping_option):
        """Calculate estimated delivery days"""
        try:
            max_date = shipping_option.get('maxEstimatedDeliveryDate')
            if max_date:
                # Parse date and calculate days from now
                # Simplified version - you might want more sophisticated parsing
                return 7  # Default to 7 days
        except:
            pass
        return None
    
    def _extract_return_period(self, return_terms):
        """Extract return period in days"""
        if not return_terms:
            return None
        
        period = return_terms.get('returnPeriod', {})
        value = period.get('value')
        unit = period.get('unit')
        
        if value and unit:
            if unit == 'DAY' or unit == 'CALENDAR_DAY':
                return int(value)
            elif unit == 'MONTH':
                return int(value) * 30
        
        return None
    
    def _extract_specifications(self, aspects):
        """Extract product specifications"""
        specs = {}
        for aspect in aspects:
            name = aspect.get('name')
            value = aspect.get('value')
            if name and value:
                specs[name] = value
        return specs
    
    def _check_availability(self, item_data):
        """Check if product is available"""
        availability = item_data.get('estimatedAvailabilities', [])
        if availability:
            status = availability[0].get('estimatedAvailabilityStatus')
            return status == 'IN_STOCK'
        return True  # Assume available if no info