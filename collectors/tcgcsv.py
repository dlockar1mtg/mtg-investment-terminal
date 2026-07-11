"""
TCGCSV collector placeholder.

This module is intentionally conservative. TCGCSV can be integrated later for
product and price data, but local manual CSV inputs remain the source of truth
until live mapping is verified.

Suggested future behavior:
1. Download category/product group/product/price data.
2. Filter sealed collector booster boxes.
3. Match products to local box_name values.
4. Update current_price and low-price fields.
5. Save source timestamp and source confidence.
"""

def fetch_tcgcsv_prices():
    raise NotImplementedError("Live TCGCSV integration is intentionally not enabled in v1 terminal build.")
