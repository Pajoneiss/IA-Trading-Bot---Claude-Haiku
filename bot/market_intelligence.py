"""
Market Intelligence - Dados de mercado para IA tomar decisões melhores
Fornece contexto completo: sentimento, dominância, eventos, notícias
"""
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class MarketIntelligence:
    """
    Centraliza dados de mercado para:
    1. IA consultar e tomar decisões mais inteligentes
    2. Usuário ver contexto completo via Telegram
    """
    
    def __init__(self):
        self.cache = {}
        self.cache_duration = 300  # 5 minutos
        
    def get_market_context(self) -> Dict[str, Any]:
        """
        Retorna contexto COMPLETO do mercado para IA usar
        
        Returns:
            {
                'fear_greed': 23,
                'sentiment': 'extreme_fear',
                'btc_dominance': 52.3,
                'eth_dominance': 16.8,
                'is_alt_season': False,
                'is_bitcoin_season': True,
                'alt_season_index': 38,
                'total_market_cap': 3240000000000,
                'volume_24h': 180500000000,
                'critical_events_today': [...],
                'important_news': [...],
                'recommendations': [...]
            }
        """
        try:
            context = {
                # Sentimento
                'fear_greed': self._get_fear_greed(),
                'sentiment': self._interpret_sentiment(),
                
                # Dominância
                'btc_dominance': self._get_btc_dominance(),
                'eth_dominance': self._get_eth_dominance(),
                
                # Fase do mercado
                'alt_season_index': self._get_alt_season_index(),
                'is_alt_season': self._is_alt_season(),
                'is_bitcoin_season': self._is_bitcoin_season(),
                
                # Métricas gerais
                'total_market_cap': self._get_total_market_cap(),
                'volume_24h': self._get_volume_24h(),
                
                # Eventos e notícias
                'critical_events_today': self._get_critical_events_today(),
                'important_news': self._get_important_news(),
                
                # Recomendações automáticas
                'recommendations': self._generate_recommendations(),
                
                # Timestamp
                'updated_at': datetime.utcnow().isoformat()
            }
            
            return context
            
        except Exception as e:
            logger.error(f"[MARKET_INTEL] Erro ao gerar contexto: {e}")
            return self._get_fallback_context()
    
    def _get_fear_greed(self) -> int:
        """
        Fear & Greed Index (0-100)
        API: Alternative.me (grátis, sem chave)
        """
        cache_key = 'fear_greed'
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]['value']
        
        try:
            url = "https://api.alternative.me/fng/"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            value = int(data['data'][0]['value'])
            self._set_cache(cache_key, value)
            return value
            
        except Exception as e:
            logger.warning(f"[MARKET_INTEL] Erro ao buscar Fear & Greed: {e}")
            return 50  # Neutro
    
    def _interpret_sentiment(self) -> str:
        """
        Interpreta Fear & Greed em categorias
        """
        fg = self._get_fear_greed()
        
        if fg >= 75:
            return 'extreme_greed'
        elif fg >= 55:
            return 'greed'
        elif fg >= 45:
            return 'neutral'
        elif fg >= 25:
            return 'fear'
        else:
            return 'extreme_fear'
    
    def _get_btc_dominance(self) -> float:
        """
        BTC Dominância (%)
        API: CoinMarketCap
        """
        cache_key = 'btc_dominance'
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]['value']
        
        try:
            # Tenta via CoinGecko (grátis, sem chave)
            url = "https://api.coingecko.com/api/v3/global"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            dominance = data['data']['market_cap_percentage']['btc']
            self._set_cache(cache_key, dominance)
            return round(dominance, 2)
            
        except Exception as e:
            logger.warning(f"[MARKET_INTEL] Erro ao buscar dominância BTC: {e}")
            return 50.0  # Valor padrão
    
    def _get_eth_dominance(self) -> float:
        """ETH Dominância (%)"""
        cache_key = 'eth_dominance'
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]['value']
        
        try:
            url = "https://api.coingecko.com/api/v3/global"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            dominance = data['data']['market_cap_percentage']['eth']
            self._set_cache(cache_key, dominance)
            return round(dominance, 2)
            
        except Exception as e:
            logger.warning(f"[MARKET_INTEL] Erro ao buscar dominância ETH: {e}")
            return 15.0
    
    def _get_alt_season_index(self) -> int:
        """
        Alt Season Index (0-100)
        API: BlockchainCenter.net (grátis)
        Nota: API tem problema de certificado SSL, usando verify=False
        """
        cache_key = 'alt_season'
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]['value']
        
        try:
            import urllib3
            # Silencia warning de SSL apenas para essa request
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            url = "https://api.blockchaincenter.net/v1/altseason/now"
            response = requests.get(url, timeout=5, verify=False)  # verify=False por problema no cert deles
            data = response.json()
            
            value = int(data['data']['altseason_index'])
            self._set_cache(cache_key, value)
            logger.debug(f"[MARKET_INTEL] Alt Season Index: {value}")
            return value
            
        except Exception as e:
            # Log menos verboso para não poluir os logs
            logger.debug(f"[MARKET_INTEL] Alt Season API indisponível, usando fallback (50)")
            return 50
    
    def _is_alt_season(self) -> bool:
        """Alt Season se index > 75"""
        return self._get_alt_season_index() > 75
    
    def _is_bitcoin_season(self) -> bool:
        """Bitcoin Season se index < 25"""
        return self._get_alt_season_index() < 25
    
    def _get_total_market_cap(self) -> float:
        """Market Cap total do crypto"""
        cache_key = 'total_mcap'
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]['value']
        
        try:
            url = "https://api.coingecko.com/api/v3/global"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            mcap = data['data']['total_market_cap']['usd']
            self._set_cache(cache_key, mcap)
            return mcap
            
        except Exception as e:
            logger.warning(f"[MARKET_INTEL] Erro ao buscar market cap: {e}")
            return 0
    
    def _get_volume_24h(self) -> float:
        """Volume 24h total"""
        cache_key = 'volume_24h'
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]['value']
        
        try:
            url = "https://api.coingecko.com/api/v3/global"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            volume = data['data']['total_volume']['usd']
            self._set_cache(cache_key, volume)
            return volume
            
        except Exception as e:
            logger.warning(f"[MARKET_INTEL] Erro ao buscar volume: {e}")
            return 0
    
    def _get_critical_events_today(self) -> List[Dict]:
        """
        Eventos econômicos críticos (hoje)
        TODO: Implementar ForexFactory scraping ou API
        """
        # Por enquanto, retorna lista vazia
        # Na próxima iteração, implementar calendário
        return []
    
    def _get_important_news(self) -> List[Dict]:
        """
        Notícias importantes (últimas 3 horas)
        TODO: Integrar com CryptoPanic
        """
        return []
    
    def _generate_recommendations(self) -> List[str]:
        """
        Gera recomendações automáticas baseadas no contexto
        
        Returns:
            Lista de códigos de recomendações:
            - 'extreme_fear_reduce_size'
            - 'extreme_greed_take_profit'
            - 'prefer_btc_over_alts'
            - 'favor_altcoins'
            - 'avoid_altcoins'
            - 'reduce_exposure_events'
            - 'tighter_stop_loss'
        """
        recs = []
        
        # 1. Baseado em Fear & Greed
        fg = self._get_fear_greed()
        if fg < 25:
            recs.append('extreme_fear_reduce_size')
            recs.append('tighter_stop_loss')
        elif fg > 75:
            recs.append('extreme_greed_take_profit')
        
        # 2. Baseado em Dominância BTC
        btc_dom = self._get_btc_dominance()
        if btc_dom > 50:
            recs.append('prefer_btc_over_alts')
        else:
            recs.append('alts_may_outperform')
        
        # 3. Baseado em Alt Season
        if self._is_bitcoin_season():
            recs.append('avoid_altcoins')
        elif self._is_alt_season():
            recs.append('favor_altcoins')
        
        # 4. Baseado em eventos
        critical_events = self._get_critical_events_today()
        if critical_events:
            recs.append('reduce_exposure_events')
        
        return recs
    
    def should_reduce_exposure(self) -> bool:
        """
        Decide se deve reduzir exposição agora
        """
        recs = self._generate_recommendations()
        return 'reduce_exposure_events' in recs or 'extreme_fear_reduce_size' in recs
    
    def get_position_size_multiplier(self) -> float:
        """
        Retorna multiplicador de tamanho (0.5 a 1.5)
        Baseado no contexto de mercado
        """
        fg = self._get_fear_greed()
        
        if fg < 20:  # Extreme Fear
            return 0.5  # Reduz 50%
        elif fg < 40:  # Fear
            return 0.75  # Reduz 25%
        elif fg > 80:  # Extreme Greed
            return 0.75  # Reduz 25% (também arriscado)
        else:
            return 1.0  # Tamanho normal
    
    def should_prefer_btc(self, coin: str) -> bool:
        """
        Retorna True se deve preferir BTC no momento
        """
        if coin == 'BTC':
            return True
        
        # Prefere BTC em Bitcoin Season ou alta dominância
        if self._is_bitcoin_season():
            return False  # Evita alts
        
        btc_dom = self._get_btc_dominance()
        return btc_dom > 55  # Alta dominância
    
    # === Cache Helper Methods ===
    
    def _is_cache_valid(self, key: str) -> bool:
        """Verifica se cache ainda é válido"""
        if key not in self.cache:
            return False
        
        cached_at = self.cache[key]['timestamp']
        age = (datetime.utcnow() - cached_at).total_seconds()
        return age < self.cache_duration
    
    def _set_cache(self, key: str, value: Any):
        """Salva no cache"""
        self.cache[key] = {
            'value': value,
            'timestamp': datetime.utcnow()
        }
    
    def _get_fallback_context(self) -> Dict:
        """Contexto de fallback se tudo falhar"""
        return {
            'fear_greed': 50,
            'sentiment': 'neutral',
            'btc_dominance': 50.0,
            'eth_dominance': 15.0,
            'alt_season_index': 50,
            'is_alt_season': False,
            'is_bitcoin_season': False,
            'total_market_cap': 0,
            'volume_24h': 0,
            'critical_events_today': [],
            'important_news': [],
            'recommendations': [],
            'updated_at': datetime.utcnow().isoformat()
        }
