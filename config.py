"""
Instrument universe & constants for the NSE/MCX Combined-Premium Terminal.

Index security IDs below are Dhan's stable IDX_I identifiers (verified against
Dhan/DhanHQ SDK docs & examples). Commodity (MCX) underlyings are futures
contracts that roll monthly, so their security IDs are NOT hardcoded here —
the app resolves them at runtime from Dhan's scrip master CSV
(see dhan_service.resolve_mcx_underlying). This avoids ever shipping a stale
or wrong commodity security ID.
"""

INDEX_INSTRUMENTS = {
    "NIFTY": {
        "label": "NIFTY 50",
        "security_id": 13,
        "segment": "IDX_I",
        "exchange": "NSE",
        "strike_step": 50,
        "lot_size": 75,
        "asset_class": "INDEX",
    },
    "BANKNIFTY": {
        "label": "BANK NIFTY",
        "security_id": 25,
        "segment": "IDX_I",
        "exchange": "NSE",
        "strike_step": 100,
        "lot_size": 30,
        "asset_class": "INDEX",
    },
    "FINNIFTY": {
        "label": "FIN NIFTY",
        "security_id": 27,
        "segment": "IDX_I",
        "exchange": "NSE",
        "strike_step": 50,
        "lot_size": 65,
        "asset_class": "INDEX",
        # NOTE: verify this ID against a fresh scrip-master pull if option
        # chain calls for FINNIFTY start failing — Dhan has occasionally
        # renumbered less-liquid index IDs.
    },
    "SENSEX": {
        "label": "SENSEX",
        "security_id": 51,
        "segment": "IDX_I",
        "exchange": "BSE",
        "strike_step": 100,
        "lot_size": 20,
        "asset_class": "INDEX",
    },
}

# Commodities are resolved dynamically (see dhan_service.resolve_mcx_underlying)
# because their underlying futures contract changes every expiry cycle.
COMMODITY_INSTRUMENTS = {
    "CRUDEOIL": {
        "label": "CRUDE OIL",
        "segment": "MCX_COMM",
        "exchange": "MCX",
        "strike_step": 50,
        "asset_class": "COMMODITY",
    },
    "NATURALGAS": {
        "label": "NATURAL GAS",
        "segment": "MCX_COMM",
        "exchange": "MCX",
        "strike_step": 5,
        "asset_class": "COMMODITY",
    },
    "GOLD": {
        "label": "GOLD",
        "segment": "MCX_COMM",
        "exchange": "MCX",
        "strike_step": 100,
        "asset_class": "COMMODITY",
    },
    "SILVER": {
        "label": "SILVER",
        "segment": "MCX_COMM",
        "exchange": "MCX",
        "strike_step": 250,
        "asset_class": "COMMODITY",
    },
}

ALL_INSTRUMENTS = {**INDEX_INSTRUMENTS, **COMMODITY_INSTRUMENTS}

SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

DEFAULT_THRESHOLD_PCT = 5.0
DEFAULT_REFRESH_SECONDS = 15
MAX_HISTORY_POINTS = 300
