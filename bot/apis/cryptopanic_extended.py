"""
CryptoPanic Extended API
Notícias crypto com classificação de importância e sentimento
"""
import os
import logging
import requests
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class CryptoPanicAPI:
    """
    API CryptoPanic para notícias crypto
    """
    
    def __init__(self):
        self.api_key = os.getenv('CRYPTOPANIC_API_KEY', '')
        self.use_api = bool(self.api_key)
        
        if self.use_api:
            logger.info("[CRYPTOPANIC] API key configurada")
        else:
            logger.info("[CRYPTOPANIC] API key não configurada (modo limitado)")
    
    def get_important_news(self, limit: int = 20) -> List[Dict]:
        """
        Busca notícias importantes
        
        Returns:
            [
                {
                    'title': str,
                    'source': str,
                    'url': str,
                    'published_at': str,
                    'importance': 'high' | 'medium' | 'low',
                    'sentiment': 'bullish' | 'bearish' | 'neutral',
                    'currencies': ['BTC', 'ETH'],
                    'votes': {...}
                }
            ]
        """
        try:
            url = "https://cryptopanic.com/api/v1/posts/"
            
            params = {
                'filter': 'important',
                'kind': 'news',
                'currencies': 'BTC,ETH,SOL,XRP',
                'regions': 'en'
            }
            
            if self.use_api:
                params['auth_token'] = self.api_key
            else:
                params['public'] = 'true'
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if 'results' not in data:
                logger.warning(f"[CRYPTOPANIC] Resposta inesperada: {data}")
                return []
            
            news_list = []
            for item in data['results'][:limit]:
                news_list.append({
                    'title': item.get('title', ''),
                    'source': item.get('source', {}).get('title', 'Unknown'),
                    'url': item.get('url', ''),
                    'published_at': item.get('published_at', ''),
                    'importance': self._calculate_importance(item),
                    'sentiment': self._detect_sentiment(item),
                    'currencies': item.get('currencies', []),
                    'votes': item.get('votes', {})
                })
            
            return news_list
            
        except Exception as e:
            logger.error(f"[CRYPTOPANIC] Erro ao buscar notícias: {e}")
            return []
    
    def _calculate_importance(self, item: Dict) -> str:
        """
        Calcula importância da notícia
        
        Critérios:
        - Hot/trending = HIGH
        - Saved > 10 = HIGH
        - Votes importantes/negativos = MEDIUM/HIGH
        - Restante = LOW
        """
        votes = item.get('votes', {})
        
        # Check hot/trending
        if item.get('metadata', {}).get('hot'):
            return 'high'
        
        # Check saved count
        saved = votes.get('saved', 0)
        if saved > 10:
            return 'high'
        elif saved > 5:
            return 'medium'
        
        # Check vote ratios
        important = votes.get('important', 0)
        liked = votes.get('liked', 0)
        disliked = votes.get('disliked', 0)
        
        if important > 5:
            return 'high'
        elif liked > disliked and liked > 3:
            return 'medium'
        
        return 'low'
    
    def _detect_sentiment(self, item: Dict) -> str:
        """
        Detecta sentimento da notícia
        
        Baseado em:
        - Votes (positive, negative, important)
        - Palavras-chave no título
        """
        votes = item.get('votes', {})
        title = item.get('title', '').lower()
        
        # Check votes primeiro
        positive = votes.get('positive', 0)
        negative = votes.get('negative', 0)
        
        if positive > negative + 2:
            return 'bullish'
        elif negative > positive + 2:
            return 'bearish'
        
        # Palavras-chave bullish
        bullish_keywords = [
            'surge', 'pump', 'rally', 'breakout', 'soar', 
            'all-time high', 'ath', 'bullish', 'buy', 'adoption',
            'partnership', 'upgrade', 'launch'
        ]
        
        # Palavras-chave bearish
        bearish_keywords = [
            'crash', 'dump', 'plunge', 'drop', 'fall', 'decline',
            'bearish', 'sell', 'hack', 'scam', 'regulation',
            'ban', 'lawsuit'
        ]
        
        bullish_count = sum(1 for kw in bullish_keywords if kw in title)
        bearish_count = sum(1 for kw in bearish_keywords if kw in title)
        
        if bullish_count > bearish_count:
            return 'bullish'
        elif bearish_count > bullish_count:
            return 'bearish'
        else:
            return 'neutral'
    
    def format_for_telegram(self, news_list: List[Dict]) -> str:
        """
        Formata notícias para Telegram
        Organizado por importância
        """
        if not news_list:
            return ("📰 *CRYPTOPANIC — Notícias*\n\n"
                   "Nenhuma notícia importante no momento.\n\n"
                   "💡 _Configure CRYPTOPANIC_API_KEY para mais notícias._")
        
        msg = "📰 *CRYPTOPANIC — Notícias Importantes*\n\n"
        
        # Separa por importância
        high = [n for n in news_list if n['importance'] == 'high']
        medium = [n for n in news_list if n['importance'] == 'medium']
        low = [n for n in news_list if n['importance'] == 'low']
        
        # High importance
        if high:
            msg += "🔴 *ALTA IMPORTÂNCIA* (Impacto Alto)\n"
            msg += "─" * 35 + "\n"
            for i, news in enumerate(high[:3], 1):
                msg += self._format_news_item(i, news)
            msg += "\n"
        
        # Medium importance
        if medium:
            msg += "🟡 *MÉDIA IMPORTÂNCIA*\n"
            msg += "─" * 35 + "\n"
            for i, news in enumerate(medium[:3], 1):
                msg += self._format_news_item(i, news)
            msg += "\n"
        
        # Low importance (só se tiver espaço)
        if low and len(high) + len(medium) < 5:
            msg += "⚪ *BAIXA IMPORTÂNCIA*\n"
            msg += "─" * 35 + "\n"
            for i, news in enumerate(low[:2], 1):
                msg += self._format_news_item(i, news)
            msg += "\n"
        
        msg += "⏰ _Atualizado agora_"
        
        return msg
    
    def _format_news_item(self, index: int, news: Dict) -> str:
        """Formata um item de notícia"""
        # Emoji de importância
        if news['importance'] == 'high':
            stars = "⭐⭐⭐"
        elif news['importance'] == 'medium':
            stars = "⭐⭐"
        else:
            stars = "⭐"
        
        # Emoji de sentimento
        if news['sentiment'] == 'bullish':
            sentiment_emoji = "📈"
        elif news['sentiment'] == 'bearish':
            sentiment_emoji = "📉"
        else:
            sentiment_emoji = "➡️"
        
        # Tempo atrás
        try:
            published = datetime.fromisoformat(news['published_at'].replace('Z', '+00:00'))
            now = datetime.utcnow()
            delta = now - published.replace(tzinfo=None)
            
            if delta.seconds < 3600:
                time_ago = f"Há {delta.seconds // 60}m"
            elif delta.seconds < 86400:
                time_ago = f"Há {delta.seconds // 3600}h"
            else:
                time_ago = f"Há {delta.days}d"
        except:
            time_ago = "Recente"
        
        msg = f"{index}. {stars} *{news['title']}*\n"
        msg += f"   {sentiment_emoji} {news['sentiment'].title()} | 🕐 {time_ago}\n"
        msg += f"   🏢 {news['source']}\n"
        msg += f"   📖 [Ler notícia completa]({news['url']})\n\n"
        
        return msg
