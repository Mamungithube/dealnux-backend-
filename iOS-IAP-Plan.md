# DEALNUX — Apple In-App Purchase (Direct StoreKit) Integration Plan

**Decision (client, final):** NO RevenueCat / no third-party. Premium subscription-er iOS payment **direct Apple StoreKit + Apple server APIs** diye — in-house, full control. Library: **`react-native-iap`**.

**Principle:** Surgical — **Android Stripe flow 0 change**. Physical products (Cart), Ads, Stripe Connect — sob age-er motoi. Shudhu `Subscription.tsx`-e iOS branch add hobe.

---

## 1. Architecture (kivabe kaj korbe)

```
iOS user "Subscribe" chape
        │
        ▼
react-native-iap ── Apple purchase sheet ── Apple charge kore
        │
        ▼  purchase.transactionReceipt (base64 JWS)
DealNux backend  ── Apple server API te verify kore  ── valid?
        │                                                 │
        │◄────────────── "premium active" ────────────────┘
        │  (backend user ke Premium mark kore)
        ▼
App: fetchSubscriptionStatus()  →  UI unlock  →  finishTransaction()

Renewal / cancel / refund:
Apple ──► App Store Server Notifications V2 ──► DealNux backend webhook ──► Premium on/off
```

- **Verification backend-e** (RevenueCat nai)। Backend Apple-er sathe kotha bole।
- **App user id = DealNux user id** — receipt-er sathe backend-e pathaবে, jate kon user bujha jay।

---

## 2. Naming (fixed)

| Jinis | Value |
|---|---|
| iOS product — monthly | `com.dealnux.app.premium.monthly` |
| iOS product — yearly | `com.dealnux.app.premium.yearly` |
| Subscription group | `DealNux Premium` |

> Backend plan table-e ekTA `apple_product_id` column add korle cleanest (plan_type MONTHLY/YEARLY → product id map)।

---

## 3. Part A — App Store Connect setup (⚠️ Admin role lage)

1. My Apps → DEALNUX → **Subscriptions**
2. Subscription Group: `DealNux Premium`
3. 2 ta auto-renewable subscription:
   - `com.dealnux.app.premium.monthly`
   - `com.dealnux.app.premium.yearly`
4. Price tier (Apple-er fixed tier — backend price-er kachakachi tier)
5. Free trial dorkar hole (`trial_days`) → **Introductory Offer**
6. Localization + review screenshot (Apple subscription-e product screenshot chay)
7. **In-App Purchase configuration:**
   - **App-Specific Shared Secret** (verifyReceipt path use korle) — App Store Connect → App → App Information, OR
   - **App Store Server API key** (.p8, Issuer ID, Key ID) — modern path (recommended)
8. **App Store Server Notifications** → Production + Sandbox URL = backend webhook URL

---

## 4. Part B — Package install & Expo config

```bash
npx expo install react-native-iap
```
- `react-native-iap`-e Expo config plugin ache → EAS build/prebuild-e native part auto।
- iOS-e **StoreKit 2** support (v12+).
- Kono API key app-e lage na (StoreKit device theke direct); backend-e-i Apple key.

---

## 5. Part C — Frontend code changes

### C1. IAP connection init (iOS only)
`App.tsx` (ba ekTA choto `src/iap/useIAP.ts` hook):
```tsx
import { Platform } from 'react-native';
import { initConnection, endConnection } from 'react-native-iap';

useEffect(() => {
  if (Platform.OS !== 'ios') return;
  initConnection();
  return () => { endConnection(); };
}, []);
```

### C2. `Subscription.tsx` — platform split (asol kaj)
`handleSubscribe(plan)`-er bhitore:
```tsx
if (Platform.OS === 'ios') {
  // ── iOS: Apple IAP (StoreKit) ──
  const sku = plan.plan_type.includes('YEARLY')
    ? 'com.dealnux.app.premium.yearly'
    : 'com.dealnux.app.premium.monthly';

  await getSubscriptions({ skus: [sku] });
  await requestSubscription({ sku });           // Apple purchase sheet
  // purchaseUpdatedListener e purchase ase (niche C3)
} else {
  // ── Android: EXISTING Stripe flow — hubohu unchanged ──
  // current axios SUBSCRIBE_ENDPOINT + initPaymentSheet + presentPaymentSheet
}
```
- **Android branch ekTA line-o change hobe na।**

### C3. Purchase listener (iOS) — receipt backend-e pathাo
```tsx
useEffect(() => {
  if (Platform.OS !== 'ios') return;
  const sub = purchaseUpdatedListener(async (purchase) => {
    const receipt = purchase.transactionReceipt;        // base64
    if (receipt) {
      // backend e pathao → backend Apple te verify → Premium grant
      await axios.post(`${API_BASE_URL}payment/apple/verify/`, {
        receipt,
        product_id: purchase.productId,
        transaction_id: purchase.transactionId,
      }, { headers: { Authorization: `Bearer ${token}` }});

      await finishTransaction({ purchase, isConsumable: false });  // ⚠️ obosshoই
      await fetchSubscriptionStatus();
      setSuccessVisible(true);
    }
  });
  const errSub = purchaseErrorListener((e) => { /* handle cancel/error */ });
  return () => { sub.remove(); errSub.remove(); };
}, []);
```
> `finishTransaction` na korle Apple bar bar purchase re-deliver korবে — joruri।

### C4. "Restore Purchases" button (⚠️ Apple baddhotamulok)
```tsx
{Platform.OS === 'ios' && (
  <TouchableOpacity onPress={async () => {
    const purchases = await getAvailablePurchases();
    // sob receipt backend e pathao → Premium re-grant
    for (const p of purchases) { /* POST payment/apple/verify/ */ }
    await fetchSubscriptionStatus();
  }}>
    <Text>Restore Purchases</Text>
  </TouchableOpacity>
)}
```

### C5. User id link
Login success-e user id AsyncStorage-e rakho (jodi already na thake), jate C3-er verify call-e backend user chine। (Confirm: app-e ekhon user id kothায় ache — token decode / profile endpoint?)

**Changed files (frontend):**
- `App.tsx` (init connection)
- `src/screens/Subscriptions/Subscription.tsx` (iOS branch + listeners + restore button)
- `.env` / `env.d.ts` — (product id chaile constant, no secret)
- `package.json`

---

## 6. Part D — Backend changes (⚠️ backend dev-er MAIN kaj)

RevenueCat nai, tai **Apple verification puro backend-e**. 2 ta poth:

### Poth 1 — Modern (recommended): App Store Server API + Notifications V2
- **Verify endpoint** (`POST payment/apple/verify/`):
  - App theke receipt/transactionId ase
  - Apple **App Store Server API** (`/inApps/v1/transactions/{id}`) diye JWS transaction verify (JWT signed with .p8 key)
  - Valid + active hole user ke Premium grant
- **Notifications V2 webhook** (`POST payment/apple/notifications/`):
  - Apple renewal/cancel/refund/billing-issue pathay (signed JWS payload)
  - decode + verify → Premium on/off

### Poth 2 — Simpler (legacy): verifyReceipt
- `POST https://buy.itunes.apple.com/verifyReceipt` (fail hole sandbox URL retry) + App-Specific Shared Secret
- Renewal-er জonno periodic re-check ba Server Notifications
- **Deprecated** kintu ekhono kaj kore — druto shuru korার জonno OK

> Recommendation: **Poth 1** (Apple future-e etai chay), kintu somoy kom thakle Poth 2 diye launch kore pore migrate।

**Backend dev-er scope:**
1. `payment/apple/verify/` — receipt verify + Premium grant
2. `payment/apple/notifications/` — App Store Server Notification webhook
3. Existing `payment/subscription/status/` — Premium je source-ei asuk same `is_active: true`
4. (Optional) plan table-e `apple_product_id`

---

## 7. Part E — Testing (Sandbox)

1. App Store Connect → **Sandbox → Test Account**
2. iPhone → Settings → App Store → Sandbox login
3. EAS dev/TestFlight build → purchase test (sandbox-e taka kate na, renewal fast — mins)
4. Verify: backend verify endpoint valid bole kina, Premium grant hoy kina, restore kaj kore kina

---

## 8. Part F — App Review requirements (na korle reject)

- ✅ **Restore Purchases** button
- ✅ Subscription **price, duration, auto-renew** clearly lekha
- ✅ **Terms of Use (EULA) + Privacy Policy** link subscription screen-e
- ✅ Reviewer **test login** (client dibe)
- ✅ App Store Connect subscription **"Ready to Submit"** + version-e attach

---

## 9. Part G — Build & submit sequence

```
1. App Store Connect products setup            [Admin role]
2. package install (react-native-iap)
3. Frontend code (App.tsx + Subscription.tsx)
4. Backend: verify + notifications endpoints    [backend dev — main work]
5. eas build --platform ios --profile production [2FA — user]
6. Sandbox test (purchase + renewal + restore + backend grant)
7. Upload + store listing (assets ready) + submit
```

---

## 10. Open items / decisions needed

- [ ] **Admin role** — client ekhono dey ni (product setup + server keys-e lage)
- [ ] **Backend dev** — Apple verify + Notifications V2 add korte raji + somoy? (eta boro kaj)
- [ ] Backend verification **Poth 1 (Server API)** naki **Poth 2 (verifyReceipt)** — backend dev decide korবe
- [ ] **User id** app-e kothায় ache (verify call-e lage) — confirm
- [ ] **Trial / price** — Apple Introductory Offer + fixed price tier-er sathe backend milaতে hobe

---

## 11. Effort estimate (rough)

| Part | Ke | Somoy |
|---|---|---|
| App Store Connect products | Ami/tumi (Admin lage) | ~2-3 ghonta |
| Frontend code | Ami | ~half–1 day |
| **Backend verify + notifications** | **Backend dev** | **~1-2 day** (RevenueCat theke beshi) |
| Sandbox testing | Ami/tumi | ~half day |

> Android + Stripe: **0 change** (untouched)।
> RevenueCat-er tulonায় backend-er kaj beshi — client jene-i ei poth beche niyeche।
