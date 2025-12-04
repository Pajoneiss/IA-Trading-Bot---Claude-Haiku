"""
AI Manager (Orquestrador)
Responsável por coordenar quando e como chamar as IAs (Swing e Scalp).
"""
import time
import logging
from typing import List, Dict, Any, Set

logger = logging.getLogger(__name__)

class AIManager:
    """
    Orquestrador central que decide:
    1. Se deve chamar IA SWING (Claude)
    2. Quais símbolos enviar para IA SCALP (OpenAI)
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Configurações de intervalo
        # Swing: intervalo maior (ex: 15-60 min)
        self.swing_interval_seconds = self.config.get('swing_interval_seconds', 1800)  # 30 min default (era 15)
        
        # Scalp: intervalo por símbolo (cooldown)
        self.scalp_symbol_cooldown = self.config.get('scalp_symbol_cooldown', 900)    # 15 min default (era 5)
        
        # Estado interno
        self.last_swing_call = 0
        self.last_scalp_calls = {}  # {symbol: timestamp}
        
        logger.info(f"🧠 AIManager iniciado | Swing Interval: {self.swing_interval_seconds}s | Scalp Cooldown: {self.scalp_symbol_cooldown}s")

    def should_call_swing(self, market_snapshot: Dict[str, Any]) -> bool:
        """
        Decide se deve chamar a IA SWING.
        Critérios:
        1. Intervalo de tempo
        2. (Futuro) Gatilhos de volatilidade/regime
        """
        now = time.time()
        
        # 1. Checa intervalo
        if now - self.last_swing_call < self.swing_interval_seconds:
            return False
            
        # Aqui poderíamos adicionar lógica de "gatilho de emergência"
        # Ex: se BTC caiu 5% em 1h, força chamada mesmo antes do intervalo
        
        return True

    def register_swing_call(self):
        """Registra que SWING foi chamado com sucesso"""
        self.last_swing_call = time.time()

    def filter_symbols_for_scalp(self, 
                               all_symbols: List[str], 
                               open_positions: List[Dict[str, Any]],
                               market_snapshot: Dict[str, Any]) -> List[str]:
        """
        Filtra quais símbolos são candidatos para SCALP.
        Regra de Ouro: NÃO operar símbolo que já tem posição aberta (Swing ou Scalp).
        
        IMPORTANTE: Limita a 2 símbolos por iteração para evitar rate limit
        """
        candidates = []
        
        # Cria set de símbolos com posição aberta para busca rápida
        open_symbols = {p['symbol'] for p in open_positions}
        
        for symbol in all_symbols:
            # 1. Regra Global: Se tem posição, ignora
            if symbol in open_symbols:
                # Opcional: logar apenas em debug para não spammar
                # logger.debug(f"[AIManager] Ignorando {symbol} para SCALP (posição aberta)")
                continue
                
            # 2. Checa cooldown de scalp para este símbolo
            last_call = self.last_scalp_calls.get(symbol, 0)
            if time.time() - last_call < self.scalp_symbol_cooldown:
                continue
                
            # 3. (Futuro) Filtros técnicos rápidos (ex: volume mínimo)
            # if not self._check_min_volume(symbol, market_snapshot):
            #     continue
            
            candidates.append(symbol)
            
            # LIMITE: Máximo 2 símbolos por iteração para evitar rate limit
            if len(candidates) >= 2:
                logger.info(f"[AIManager] Limitando análise SCALP a 2 símbolos por iteração (rate limit)")
                break
            
        return candidates

    def should_call_scalp(self, symbol: str, market_snapshot: Dict[str, Any]) -> bool:
        """
        Decide se vale a pena gastar tokens com SCALP para este símbolo específico.
        Pode checar volatilidade, RSI extremo, etc.
        """
        # Por enquanto, se passou no filtro de símbolos, aprovamos.
        # Futuramente: checar se RSI < 30 ou > 70 antes de chamar IA
        
        # Exemplo de pré-filtro técnico (opcional, deixado simples por enquanto)
        # context = market_snapshot.get(symbol)
        # if context and context['volatility'] < 0.5:
        #     return False
            
        return True

    def register_scalp_call(self, symbol: str):
        """Registra que SCALP foi chamado para este símbolo"""
        self.last_scalp_calls[symbol] = time.time()
