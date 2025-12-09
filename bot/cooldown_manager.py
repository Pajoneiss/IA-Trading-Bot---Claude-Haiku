import time
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class CooldownManager:
    """
    Gerencia cooldowns temporários para prevenir reentrada imediata após Stop Loss (Revenge Trading)
    """
    def __init__(self, default_cooldown_minutes: int = 30):
        self.default_cooldown_seconds = default_cooldown_minutes * 60
        self.last_stop_time: Dict[str, float] = {}  # symbol -> timestamp
        
    def register_stop(self, symbol: str):
        """Registra que ocorreu um stop no símbolo agora"""
        self.last_stop_time[symbol] = time.time()
        logger.info(f"❄️ Cooldown iniciado para {symbol} por {self.default_cooldown_seconds/60:.0f}min")
        
    def is_in_cooldown(self, symbol: str) -> bool:
        """Verifica se o símbolo está em cooldown"""
        last_time = self.last_stop_time.get(symbol)
        if not last_time:
            return False
            
        elapsed = time.time() - last_time
        if elapsed < self.default_cooldown_seconds:
            remaining = (self.default_cooldown_seconds - elapsed) / 60
            logger.debug(f"{symbol} em cooldown por mais {remaining:.1f}min")
            return True
            
        return False
    
    def get_cooldown_remaining(self, symbol: str) -> float:
        """Retorna tempo restante em segundos"""
        last_time = self.last_stop_time.get(symbol)
        if not last_time:
            return 0.0
            
        elapsed = time.time() - last_time
        return max(0.0, self.default_cooldown_seconds - elapsed)
