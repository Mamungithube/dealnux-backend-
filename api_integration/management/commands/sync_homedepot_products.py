


from api_integration.views import _generic_sync_loop, error_response, save_generic_product_to_db, success_response


def sync_homedepot_products(platform, query, limit):
    """Sync Home Depot products — শুধু numeric productId দিয়ে কাজ করে"""
    from api_integration.services.homedepot_service import HomeDepotService
    service = HomeDepotService()

    if not str(query).strip().isdigit():
        return error_response(
            f"Home Depot requires a numeric product ID, got: '{query}'",
            code=400
        )

    items = service.search_products(query, limit=limit)

    if not items:
        return error_response("No Home Depot products found", code=404)

    normalized = []
    for item in items:
        try:
            normalized.append(service.extract_product_data(item))
        except Exception:
            continue

    result = _generic_sync_loop(normalized, platform, 'external_id', save_generic_product_to_db)
    result['query'] = query
    result['limit'] = limit

    return success_response(result, message="Home Depot sync completed")