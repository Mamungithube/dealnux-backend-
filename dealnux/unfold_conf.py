UNFOLD_CONFIG = {
    "SITE_TITLE": "Dealnux Admin",
    "SITE_HEADER": "Dealnux Administration",
    "SITE_LOGO": "/static/Logo.png",
    "SITE_ICON": "/static/Logo.png",
    "SITE_URL": "/",
    "DASHBOARD": {
        "callback": "dealnux.admin_logic.dashboard_callback", 
    },
    "COLORS": {
        "primary": {
            "50": "239 245 255", "100": "219 234 254", "200": "191 219 254",
            "300": "147 197 253", "400": "96 165 250", "500": "35 85 182",
            "600": "28 68 146", "700": "23 56 120", "800": "18 45 94",
            "900": "14 35 73", "950": "10 25 52",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "🖼️ Homepage Banners",
                "items": [
                    {"title": "Main Slider Banners", "icon": "slideshow", "link": "/admin/homepage/mainsliderbanner/"},
                    {"title": "Side Banners", "icon": "view_sidebar", "link": "/admin/homepage/sidebanner/"},
                ],
            },
            {
                "title": "👤 User Management",
                "items": [
                    {"title": "Users", "icon": "people", "link": "/admin/account/user/"},
                    {"title": "Profiles", "icon": "manage_accounts", "link": "/admin/account/profile/"},
                ],
            },
            {
                "title": "💎 Subscription Management",
                "separator": True,
                "items": [
                    {"title": "Plans", "icon": "card_membership", "link": "/admin/payment/subscriptionplan/"},
                    {"title": "User Subscriptions", "icon": "auto_awesome_motion", "link": "/admin/payment/usersubscription/"},
                ],
            },
            {
                "title": "🛍️ Products",
                "items": [
                    {"title": "Categories", "icon": "category", "link": "/admin/api_integration/category/"},
                    {"title": "Platforms & API", "icon": "device_hub", "link": "/admin/api_integration/platform/"},
                    {"title": "Product Listings", "icon": "list_alt", "link": "/admin/api_integration/productlisting/"},
                ],
            },
            {
                "title": "🏪 Seller Marketplace",
                "items": [
                    {"title": "Seller Requests", "icon": "store", "link": "/admin/store/sellerrequest/"},
                    {"title": "Seller Profiles", "icon": "storefront", "link": "/admin/store/sellerprofile/"},
                    {"title": "Seller Products", "icon": "shopping_bag", "link": "/admin/store/sellerproduct/"},
                    {"title": "Product Reviews", "icon": "rate_review", "link": "/admin/store/productreview/"},
                    {"title": "Orders", "icon": "receipt_long", "link": "/admin/store/order/"},
                    {"title": "Coupons", "icon": "local_offer", "link": "/admin/store/coupon/"},
                    {"title": "Disputes", "icon": "gavel", "link": "/admin/store/dispute/"},
                ],
            },
            {
                "title": "📢 Advertisements",
                "items": [
                    {"title": "Custom Ads", "icon": "campaign", "link": "/admin/custom_ads/customad/"},
                    {"title": "Advertiser Requests", "icon": "request_page", "link": "/admin/custom_ads/advertiserrequest/"},
                    {"title": "Ad Reviews", "icon": "rate_review", "link": "/admin/custom_ads/adreview/"},
                    {"title": "Ad Settings", "icon": "tune", "link": "/admin/custom_ads/adsetting/"},
                ],
            },
            {
                "title": "💳 Finance",
                "items": [
                    {"title": "Payments", "icon": "payments", "link": "/admin/payment/payment/"},
                    {"title": "Seller Payouts", "icon": "account_balance_wallet", "link": "/admin/payment/sellerpayout/"},
                    {"title": "Referral Reward Settings", "icon": "card_giftcard", "link": "/admin/account/sitesettings/"},
                ],
            },
            {
                "title": "� Notifications",
                "separator": True,
                "items": [
                    {"title": "Notifications", "icon": "notifications", "link": "/admin/notifications/notification/"},
                    {"title": "Preferences", "icon": "tune", "link": "/admin/notifications/notificationpreference/"},
                    {"title": "Device Tokens", "icon": "devices", "link": "/admin/notifications/devicetoken/"},
                ],
            },
            {
                "title": "�📋 Policy",
                "separator": True,
                "items": [
                    {"title": "Privacy Policy", "icon": "privacy_tip", "link": "/admin/policy/privacy_policy/"},
                    {"title": "About Us", "icon": "info", "link": "/admin/policy/about_us/"},
                    {"title": "Terms of Service", "icon": "assignment", "link": "/admin/policy/terms_of_service/"},
                    {"title": "Cookie Policy", "icon": "cookie", "link": "/admin/policy/cookie_policy/"},
                    {"title": "Refund Policy", "icon": "currency_exchange", "link": "/admin/policy/refund_policy/"},
                    {"title": "EMI Payment Policy", "icon": "credit_card", "link": "/admin/policy/emi_payment_policy/"},
                    {"title": "Warranty Policy", "icon": "verified_user", "link": "/admin/policy/warranty_policy/"},
                    {"title": "Exchange Policy", "icon": "swap_horiz", "link": "/admin/policy/exchange_policy/"},
                    {"title": "Delivery Policy", "icon": "local_shipping", "link": "/admin/policy/delivery_policy/"},
                    {"title": "Pre-Order Policy", "icon": "pending_actions", "link": "/admin/policy/preorder_policy/"},
                    {"title": "Return Policy", "icon": "assignment_return", "link": "/admin/policy/return_policy/"},
                    {"title": "Seller Policy", "icon": "store", "link": "/admin/policy/seller_policy/"},
                    {"title": "Buyer Protection Policy", "icon": "gavel", "link": "/admin/policy/buyer_protection_policy/"},
                    {"title": "Prohibited Products Policy", "icon": "block", "link": "/admin/policy/prohibited_products_policy/"},
                    {"title": "Intellectual Property Policy", "icon": "copyright", "link": "/admin/policy/intellectual_property_policy/"},
                    {"title": "Community Guidelines", "icon": "groups", "link": "/admin/policy/community_guidelines/"},
                    {"title": "Reviews", "icon": "reviews", "link": "/admin/policy/review/"},
                ],
            },
        ],
    },
}