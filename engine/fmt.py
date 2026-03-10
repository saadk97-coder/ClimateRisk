"""
Currency formatting utility.
All values are stored natively; this module only handles display symbols.
No unit conversion is performed — the user is expected to input values in
their chosen currency and interpret outputs accordingly.
"""

CURRENCIES: dict[str, dict] = {
    "GBP": {"symbol": "£",     "label": "GBP — British Pound (£)"},
    "USD": {"symbol": "$",     "label": "USD — US Dollar ($)"},
    "EUR": {"symbol": "€",     "label": "EUR — Euro (€)"},
    "JPY": {"symbol": "¥",    "label": "JPY — Japanese Yen (¥)"},
    "CHF": {"symbol": "Fr ",   "label": "CHF — Swiss Franc (Fr)"},
    "CAD": {"symbol": "C$",    "label": "CAD — Canadian Dollar (C$)"},
    "AUD": {"symbol": "A$",    "label": "AUD — Australian Dollar (A$)"},
    "NZD": {"symbol": "NZ$",   "label": "NZD — New Zealand Dollar (NZ$)"},
    "SGD": {"symbol": "S$",    "label": "SGD — Singapore Dollar (S$)"},
    "HKD": {"symbol": "HK$",   "label": "HKD — Hong Kong Dollar (HK$)"},
    "SEK": {"symbol": "kr ",   "label": "SEK — Swedish Krona (kr)"},
    "NOK": {"symbol": "kr ",   "label": "NOK — Norwegian Krone (kr)"},
    "DKK": {"symbol": "kr ",   "label": "DKK — Danish Krone (kr)"},
    "INR": {"symbol": "₹",    "label": "INR — Indian Rupee (₹)"},
    "CNY": {"symbol": "¥",    "label": "CNY — Chinese Yuan (¥)"},
    "BRL": {"symbol": "R$",    "label": "BRL — Brazilian Real (R$)"},
    "MXN": {"symbol": "MX$",   "label": "MXN — Mexican Peso (MX$)"},
    "ZAR": {"symbol": "R ",    "label": "ZAR — South African Rand (R)"},
    "AED": {"symbol": "AED ",  "label": "AED — UAE Dirham"},
    "SAR": {"symbol": "SAR ",  "label": "SAR — Saudi Riyal"},
    "KWD": {"symbol": "KD ",   "label": "KWD — Kuwaiti Dinar"},
    "QAR": {"symbol": "QR ",   "label": "QAR — Qatari Riyal"},
}

_DEFAULT = "GBP"


def currency_symbol(code: str) -> str:
    """Return display symbol for ISO 4217 currency code. Falls back to '£'."""
    return CURRENCIES.get(code, CURRENCIES[_DEFAULT])["symbol"]


def fmt(amount: float, code: str = _DEFAULT, decimals: int = 0) -> str:
    """Format a monetary amount with the appropriate currency symbol.

    Args:
        amount:   Numeric value to format.
        code:     ISO 4217 currency code (e.g. "GBP", "USD").
        decimals: Number of decimal places (default 0).

    Returns:
        Formatted string, e.g. "£1,250,000" or "$1,250,000".
    """
    sym = currency_symbol(code)
    return f"{sym}{amount:,.{decimals}f}"
