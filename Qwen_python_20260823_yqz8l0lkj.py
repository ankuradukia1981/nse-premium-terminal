from dhanhq import dhanhq
import os
from dotenv import load_dotenv

load_dotenv()

class DhanClient:
    def __init__(self):
        self.client_id = os.getenv("DHAN_CLIENT_ID")
        self.access_token = os.getenv("DHAN_ACCESS_TOKEN")
        self.dhan = dhanhq(self.client_id, self.access_token)
    
    def get_option_chain(self, symbol, expiry):
        """Fetch option chain data from DhanHQ"""
        try:
            # Implementation depends on DhanHQ API version
            # This is a placeholder
            return self.dhan.get_option_chain(symbol, expiry)
        except Exception as e:
            print(f"Error fetching option chain: {e}")
            return None
    
    def get_quote(self, symbol):
        """Fetch real-time quote"""
        try:
            return self.dhan.get_quote(symbol)
        except Exception as e:
            print(f"Error fetching quote: {e}")
            return None