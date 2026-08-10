# DEALNUX — Frontend Integration Guideline for Apple In-App Purchase (StoreKit 2)

---

## 📌 Overview
This document provides the exact contract and steps for integrating Apple Direct In-App Purchases (`react-native-iap`) in the DealNux mobile app.

> [!IMPORTANT]
> **Android & Web Stripe Flow:** 0 Changes (Keep existing Stripe code completely untouched).
> **iOS Flow:** Direct Apple StoreKit 2 + DealNux Backend Keyless Verification.

---

## 1. Product Identifiers (App Store Connect & Backend)

| Subscription Type | Apple Product ID (SKU) | DealNux Plan Type |
|---|---|---|
| Monthly Subscription | `com.dealnux.app.premium.monthly` | `PRO_MONTHLY` / `ULTIMATE_MONTHLY` |
| Yearly Subscription | `com.dealnux.app.premium.yearly` | `PRO_MAX_YEARLY` / `ULTIMANIA_YEARLY` |

---

## 2. API Specifications (Backend Endpoints)

### EndPoint 1: Verify & Grant Subscription (`POST /api/payment/apple/verify/`)

Call this endpoint immediately after receiving `purchase.transactionReceipt` or `purchase.transactionId` from Apple.

#### Request Headers:
```http
Authorization: Bearer <DealNux_JWT_Token>
Content-Type: application/json
```

#### Request Body:
```json
{
  "purchase_token": "<StoreKit_2_JWS_signedTransaction>",
  "product_id": "com.dealnux.app.premium.monthly",
  "transaction_id": "2000000123456789"
}
```

#### Success Response (`200 OK`):
```json
{
  "success": true,
  "is_active": true,
  "message": "Apple subscription verified and activated successfully.",
  "data": {
    "plan_name": "Dealnux PRO",
    "expires_at": "2026-09-10T14:40:00Z"
  }
}
```

#### Error Response (`400 Bad Request` or `401 Unauthorized`):
```json
{
  "success": false,
  "is_active": false,
  "error": "Invalid JWS signature or transaction expired."
}
```

> [!CAUTION]
> **Transaction Finishing:** Do **NOT** call `finishTransaction({ purchase })` if the backend returns a non-200 or `success: false` response. This allows StoreKit to safely retry transaction delivery later. Call `finishTransaction` **ONLY** after receiving `success: true` from the backend!

---

### EndPoint 2: Restore Purchases (`POST /api/payment/apple/verify/`)

When the user taps the **"Restore Purchases"** button on iOS:
1. Fetch active purchases using `getAvailablePurchases()`.
2. Loop over purchases and send each purchase's token to `POST /api/payment/apple/verify/`.
3. The backend is **Idempotent** — even if the user's subscription was already active, it will safely return `success: true` and refresh the status.

---

### EndPoint 3: Subscription Status Check (`GET /api/payment/subscription/status/`)

Existing status endpoint used across Android, iOS, and Web.

#### Response:
```json
{
  "success": true,
  "data": {
    "plan_name": "Dealnux PRO",
    "price": 9.99,
    "status": "ACTIVE",
    "is_active": true,
    "has_used_trial": true,
    "days_remaining": 30,
    "clicks_left": 100,
    "features": []
  }
}
```

---

## 3. Frontend Code Reference (`react-native-iap`)

### Subscription Listener Component
```tsx
import React, { useEffect } from 'react';
import { Platform, Alert } from 'react-native';
import {
  initConnection,
  endConnection,
  purchaseUpdatedListener,
  purchaseErrorListener,
  finishTransaction,
  getSubscriptions,
  requestSubscription,
  getAvailablePurchases
} from 'react-native-iap';
import axios from 'axios';

export const useAppleIAP = (userToken: string, refreshStatus: () => void) => {
  useEffect(() => {
    if (Platform.OS !== 'ios') return;

    initConnection();

    const purchaseSub = purchaseUpdatedListener(async (purchase) => {
      // StoreKit 2 signedTransaction JWS string
      const purchaseToken = purchase.transactionReceipt;

      if (purchaseToken) {
        try {
          const res = await axios.post(
            `${API_BASE_URL}payment/apple/verify/`,
            {
              purchase_token: purchaseToken,
              product_id: purchase.productId,
              transaction_id: purchase.transactionId,
            },
            {
              headers: { Authorization: `Bearer ${userToken}` }
            }
          );

          if (res.data?.success || res.data?.is_active) {
            // Finish transaction only after backend confirmation
            await finishTransaction({ purchase, isConsumable: false });
            refreshStatus();
            Alert.alert("Success", "Your subscription is now active!");
          }
        } catch (error) {
          console.error("Apple verification failed:", error);
          Alert.alert("Error", "Could not verify subscription with server.");
        }
      }
    });

    const errorSub = purchaseErrorListener((error) => {
      console.warn("Purchase error:", error);
    });

    return () => {
      purchaseSub.remove();
      errorSub.remove();
      endConnection();
    };
  }, [userToken]);
};
```

---

## 4. Checklist for App Store Review Compliance

- [x] **Restore Purchases Button:** Must be prominently visible on the `Subscription.tsx` screen for iOS users.
- [x] **Terms of Use & Privacy Policy Links:** Must be displayed on the subscription page.
- [x] **Clear Billing Details:** Price, billing period, and auto-renewable terms clearly displayed.
