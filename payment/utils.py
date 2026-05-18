import stripe


def release_funds_to_seller(order):
    """অর্ডার একসেপ্ট হলে এসক্রো থেকে টাকা সেলারের স্ট্রাইপ একাউন্টে পাঠানো"""
    seller = order.seller
    if not seller.stripe_account_id or not seller.stripe_onboarding_completed:
        return False, "Seller bank not connected."

    try:
        # সেলার পাবে: Item Total + Shipping
        amount_to_transfer = int((order.item_total + order.shipping_fee) * 100) # Cents এ রূপান্তর

        transfer = stripe.Transfer.create(
            amount=amount_to_transfer,
            currency=order.currency.lower(),
            destination=seller.stripe_account_id,
            transfer_group=f"ORDER_{order.order_number}",
            metadata={'order_id': order.id}
        )
        return True, transfer.id
    except stripe.error.StripeError as e:
        return False, str(e)