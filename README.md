# Dealnux Backend Engine 🚀
### Multi-platform Price Aggregator & Secure Marketplace Architecture

Dealnux is a powerful backend engine that collects real-time data from various e-commerce platforms (Amazon, eBay, Walmart, etc.) to help users find the best deals. It is not just an aggregator, but a full-featured marketplace where local sellers can sell products through a secure Escrow payment system.

---

## 🌟 Key Features

### 1. Smart Price Aggregation & Comparison

- **Multi-Source Sync:** Automated data syncing from 10+ global platforms using Celery background tasks and RapidAPI.
- **NLP Matching Logic:** Algorithm based on Strict NLP (Token similarity) and unique identifiers (GTIN/ASIN) to detect the exact same product across platforms.
- **Lifetime Savings:** Dynamic savings dashboard to track how much money users have saved by choosing the best deals.

### 2. Comprehensive Seller Ecosystem

- **11-Step Onboarding:** Professional seller verification system including KYC, Business License, and Address Proof uploads.
- **Wallet & Escrow Model:** Buyer funds are held securely by Dealnux and automatically transferred to the seller's `Available Balance` once delivery is confirmed.
- **Shipping & Fulfillment:** Ability to set courier preferences and product-wise shipping costs.

### 3. Secure Payouts & Fees

- **Stripe Embedded Checkout:** Smooth payment experience for buyers without leaving the site.
- **Automated Service Fees:** Custom service fee calculation logic of 5–10% on every transaction.
- **Stripe Connect:** Seller bank account verification and secure payout management.

### 4. Advertisement System (CPC)

- **Budget-based Ads:** Pre-paid budget system for running advertisements.
- **Cost-Per-Click (CPC):** Logic to deduct budget per click and track real-time ad performance.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django REST Framework (DRF) |
| Database | PostgreSQL |
| Task Queue | Celery & Redis |
| Infrastructure | Docker & Docker Compose |
| Payment | Stripe API (Checkout & Connect) |
| Documentation | Swagger (drf-spectacular) |

---

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/dealnux-backend.git
cd dealnux-backend
```

### 2. Configure Environment Variables

Create a `.env` file in the root directory and add the required keys:

```env
DEBUG=True
SECRET_KEY=your_secret_key
STRIPE_SECRET_KEY=your_stripe_key
RAPIDAPI_KEY=your_rapidapi_key
DB_NAME=dealnux_db
DB_USER=postgres
DB_PASSWORD=your_password
```

### 3. Run the Project with Docker

```bash
docker compose up --build
```

### 4. Apply Migrations & Create Superuser

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

---

## 📡 API Documentation

Once the server is running, documentation is available at the following endpoints:

| Type | URL |
|------|-----|
| Swagger UI | http://localhost:8000/api/docs/ |
| Schema | http://localhost:8000/api/schema/ |

---

## 📁 System Architecture

The system operates across 3 core layers:

```
┌─────────────────────────────────────────────┐
│              API Layer (DRF)                │
│    Clean & secure data served to frontend   │
└───────────────────┬─────────────────────────┘
                    │
┌───────────────────▼─────────────────────────┐
│           Task Layer (Celery + Redis)        │
│   Background data refresh & coupon          │
│   validation                                │
└───────────────────┬─────────────────────────┘
                    │
┌───────────────────▼─────────────────────────┐
│            Service Layer                    │
│     Collects data from third-party APIs     │
└─────────────────────────────────────────────┘
```

---

## 📄 License

This project is licensed under the **MIT License**.
