"""
CoinMarketCap Extended API
Integração completa com dados de mercado, dominância, top moedas
"""
import os
import logging
import requests
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class CoinMarketCapAPI:
    """
    API CoinMarketCap com fallback para CoinGecko
    """
    
    def __init__(self):
        self.cmc_api_key = os.getenv('CMC_API_KEY', '')
        self.use_cmc = bool(self.cmc_api_key)
        
        if self.use_cmc:
            logger.info("[CMC] Usando CoinMarketCap API")
        else:
            logger.info("[CMC] CMC_API_KEY não configurada, usando CoinGecko (fallback)")
    
    def get_market_overview(self) -> Dict:
        """
        Visão completa do mercado
        
        Returns:
            {
                'total_market_cap': float,
                'total_volume_24h': float,
                'btc_dominance': float,
                'eth_dominance': float,
                'top_10': [...],
                'top_gainer': {...},
                'top_loser': {...}
            }
        """
        try:
            if self.use_cmc:
                return self._get_via_cmc()
            else:
                return self._get_via_coingecko()
        except Exception as e:
            logger.error(f"[CMC] Erro ao buscar market overview: {e}")
            return self._get_fallback_data()
    
    def _get_via_cmc(self) -> Dict:
        """Busca via CoinMarketCap"""
        try:
            # Global metrics
            url_global = "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest"
            headers = {'X-CMC_PRO_API_KEY': self.cmc_api_key}
            
            response = requests.get(url_global, headers=headers, timeout=10)
            global_data = response.json()['data']
            
            # Top cryptocurrencies
            url_crypto = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
            params = {'limit': 10, 'convert': 'USD'}
            
            response = requests.get(url_crypto, headers=headers, params=params, timeout=10)
            crypto_data = response.json()['data']
            
            # Parse top 10
            top_10 = []
            for coin in crypto_data:
                quote = coin['quote']['USD']
                top_10.append({
                    'symbol': coin['symbol'],
                    'name': coin['name'],
                    'price': quote['price'],
                    'change_24h': quote['percent_change_24h'],
                    'market_cap': quote['market_cap'],
                    'volume_24h': quote['volume_24h']
                })
            
            # Find top gainer/loser
            top_gainer = max(top_10, key=lambda x: x['change_24h'])
            top_loser = min(top_10, key=lambda x: x['change_24h'])
            
            return {
                'total_market_cap': global_data['quote']['USD']['total_market_cap'],
                'total_volume_24h': global_data['quote']['USD']['total_volume_24h'],
                'btc_dominance': global_data['btc_dominance'],
                'eth_dominance': global_data['eth_dominance'],
                'top_10': top_10,
                'top_gainer': top_gainer,
                'top_loser': top_loser,
                'updated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"[CMC] Erro na API CoinMarketCap: {e}")
            # Fallback para CoinGecko
            return self._get_via_coingecko()
    
    def _get_via_coingecko(self) -> Dict:
        """Busca via CoinGecko (fallback gratuito)"""
        try:
            # Global data
            url_global = "https://api.coingecko.com/api/v3/global"
            response = requests.get(url_global, timeout=10)
            global_data = response.json()['data']
            
            # Top coins
            url_coins = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': 10,
                'page': 1
            }
            response = requests.get(url_coins, params=params, timeout=10)
            coins_data = response.json()
            
            # Parse top 10
            top_10 = []
            for coin in coins_data:
                top_10.append({
                    'symbol': coin['symbol'].upper(),
                    'name': coin['name'],
                    'price': coin['current_price'],
                    'change_24h': coin['price_change_percentage_24h'] or 0,
                    'market_cap': coin['market_cap'],
                    'volume_24h': coin['total_volume']
                })
            
            # Top gainer/loser
            top_gainer = max(top_10, key=lambda x: x['change_24h'])
            top_loser = min(top_10, key=lambda x: x['change_24h'])
            
            return {
                'total_market_cap': global_data['total_market_cap']['usd'],
                'total_volume_24h': global_data['total_volume']['usd'],
                'btc_dominance': global_data['market_cap_percentage'].get('btc', 50.0),
                'eth_dominance': global_data['market_cap_percentage'].get('eth', 15.0),
                'top_10': top_10,
                'top_gainer': top_gainer,
                'top_loser': top_loser,
                'updated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"[CMC] Erro no CoinGecko: {e}")
            return self._get_fallback_data()
    
    def _get_fallback_data(self) -> Dict:
        """Dados de fallback se tudo falhar"""
        return {
            'total_market_cap': 0,
            'total_volume_24h': 0,
            'btc_dominance': 50.0,
            'eth_dominance': 15.0,
            'top_10': [],
            'top_gainer': None,
            'top_loser': None,
            'updated_at': datetime.utcnow().isoformat(),
            'error': True
        }
    
    def format_for_telegram(self, data: Dict) -> str:
        """
        Formata dados para enviar via Telegram
        """
        if data.get('error'):
            return "❌ Erro ao buscar dados do CoinMarketCap. Tente novamente."
        
        # Header
        msg = "💹 *COINMARKETCAP — Visão Completa*\n\n"
        
        # Global metrics
        msg += "📊 *VISÃO GERAL*\n"
        msg += "─" * 35 + "\n"
        msg += f"💎 Market Cap Total: ${self._format_large_number(data['total_market_cap'])}\n"
        msg += f"📊 Volume 24h: ${self._format_large_number(data['total_volume_24h'])}\n"
        msg += f"🪙 BTC Dominância: {data['btc_dominance']:.1f}%\n"
        msg += f"⚡ ETH Dominância: {data['eth_dominance']:.1f}%\n\n"
        
        # Top 10
        msg += "💰 *TOP 10 POR MARKET CAP*\n"
        msg += "─" * 35 + "\n"
        
        for i, coin in enumerate(data['top_10'], 1):
            emoji = "🟢" if coin['change_24h'] >= 0 else "🔴"
            price_str = self._format_price(coin['price'])
            change_str = f"{coin['change_24h']:+.2f}%"
            mcap_str = self._format_large_number(coin['market_cap'])
            
            msg += f"{i}. {emoji} *{coin['symbol']}*: ${price_str} ({change_str})\n"
            msg += f"   Market Cap: ${mcap_str}\n"
        
        msg += "\n"
        
        # Top gainer
        if data['top_gainer']:
            gainer = data['top_gainer']
            msg += "🚀 *MAIOR ALTA 24H*\n"
            msg += "─" * 35 + "\n"
            msg += f"🔥 {gainer['name']} ({gainer['symbol']}): *{gainer['change_24h']:+.2f}%*\n\n"
        
        # Top loser
        if data['top_loser'] and data['top_loser']['change_24h'] < 0:
            loser = data['top_loser']
            msg += "📉 *MAIOR QUEDA 24H*\n"
            msg += "─" * 35 + "\n"
            msg += f"❄️ {loser['name']} ({loser['symbol']}): *{loser['change_24h']:+.2f}%*\n\n"
        
        msg += "⏰ _Dados em tempo real_"
        
        return msg
    
    def _format_price(self, price: float) -> str:
        """Formata preço de forma inteligente"""
        if price >= 1000:
            return f"{price:,.0f}"
        elif price >= 1:
            return f"{price:,.2f}"
        elif price >= 0.01:
            return f"{price:.4f}"
        else:
            return f"{price:.6f}"
    
    def _format_large_number(self, num: float) -> str:
        """Formata números grandes (M, B, T)"""
        if num >= 1_000_000_000_000:  # Trilhões
            return f"{num/1_000_000_000_000:.2f}T"
        elif num >= 1_000_000_000:  # Bilhões
            return f"{num/1_000_000_000:.2f}B"
        elif num >= 1_000_000:  # Milhões
            return f"{num/1_000_000:.2f}M"
        else:
            return f"{num:,.0f}"
