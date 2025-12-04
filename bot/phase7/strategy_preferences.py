"""
Phase 7 - Strategy Preferences
Auto-otimização leve baseada em performance
"""
import json
import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any

logger = logging.getLogger(__name__)


class StrategyPreferences:
    """
    Mantém scores de símbolos/estratégias baseado em performance
    NÃO bloqueia completamente - apenas ajusta peso/confiança
    """
    
    PREFS_FILE = "data/strategy_preferences.json"
    
    # Thresholds
    MIN_TRADES_FOR_SCORE = 5  # Trades mínimos para considerar score
    DECAY_FACTOR = 0.95  # Decaimento temporal (95% por atualização)
    
    def __init__(self, performance_engine, logger_instance=None):
        self.perf_engine = performance_engine
        self.logger = logger_instance or logger
        
        # Scores internos
        self.symbol_scores = defaultdict(float)
        self.strategy_scores = defaultdict(float)
        self.style_scores = defaultdict(float)
        
        self._load_preferences()
        self.logger.info("[COACH] Strategy Preferences inicializado")
    
    def update_from_trade(self, trade_data: Dict[str, Any]):
        """
        Atualiza scores baseado em trade fechado
        
        Args:
            trade_data: Dados do trade
        """
        try:
            symbol = trade_data.get('symbol')
            strategy = trade_data.get('strategy_tag')
            style = trade_data.get('style')
            pnl_pct = trade_data.get('pnl_pct', 0)
            
            # Calcula delta baseado em resultado
            if pnl_pct > 0:
                delta = min(pnl_pct / 2, 2.0)  # Max +2 por win
            else:
                delta = max(pnl_pct / 2, -2.0)  # Max -2 por loss
            
            # Atualiza scores
            if symbol:
                self.symbol_scores[symbol] += delta
                self.logger.debug(f"[COACH] {symbol} score: {self.symbol_scores[symbol]:.2f}")
            
            if strategy:
                self.strategy_scores[strategy] += delta
            
            if style:
                self.style_scores[style] += delta
            
            # Aplica decay leve
            self._apply_decay()
            
            # Salva
            self._save_preferences()
            
        except Exception as e:
            self.logger.error(f"[COACH] Erro ao atualizar de trade: {e}")
    
    def refresh_from_performance(self):
        """
        Recalcula scores completos do Performance Engine
        Chamado periodicamente (ex: 1x por dia)
        """
        try:
            all_stats = self.perf_engine.get_symbol_stats()
            
            if 'error' in all_stats:
                return
            
            for symbol, stats in all_stats.items():
                trades = stats.get('trades', 0)
                
                if trades < self.MIN_TRADES_FOR_SCORE:
                    continue
                
                exp = stats.get('expectancy', 0)
                wr = stats.get('win_rate', 0)
                
                # Score = expectancy * weight de trades
                weight = min(trades / 10.0, 2.0)  # Max peso 2x
                score = exp * weight
                
                # Ajusta por win rate (bonus/penalty)
                if wr >= 60:
                    score *= 1.2
                elif wr <= 40:
                    score *= 0.8
                
                self.symbol_scores[symbol] = score
            
            self.logger.info(f"[COACH] Scores atualizados para {len(self.symbol_scores)} símbolos")
            self._save_preferences()
            
        except Exception as e:
            self.logger.error(f"[COACH] Erro ao refresh: {e}")
    
    def get_symbol_adjustment(self, symbol: str) -> Dict[str, Any]:
        """
        Retorna ajustes para um símbolo
        
        Args:
            symbol: Símbolo a consultar
            
        Returns:
            Dict com: confidence_multiplier, risk_tag, should_prefer
        """
        score = self.symbol_scores.get(symbol, 0.0)
        
        # Converte score em multiplicadores
        if score >= 3.0:
            return {
                'confidence_multiplier': 1.1,  # +10% confiança
                'risk_tag': 'outperforming',
                'should_prefer': True,
                'score': score
            }
        elif score <= -3.0:
            return {
                'confidence_multiplier': 0.9,  # -10% confiança
                'risk_tag': 'underperforming',
                'should_prefer': False,
                'score': score
            }
        else:
            return {
                'confidence_multiplier': 1.0,
                'risk_tag': 'neutral',
                'should_prefer': None,
                'score': score
            }
    
    def log_influence(self, symbol: str, action: str):
        """Loga quando preferências influenciam decisão"""
        adjustment = self.get_symbol_adjustment(symbol)
        
        if adjustment['should_prefer'] is not None:
            tag = adjustment['risk_tag']
            score = adjustment['score']
            self.logger.info(
                f"[COACH] {action} em {symbol}: {tag} (score {score:.2f})"
            )
    
    def _apply_decay(self):
        """Aplica decaimento temporal aos scores"""
        for key in self.symbol_scores:
            self.symbol_scores[key] *= self.DECAY_FACTOR
        
        for key in self.strategy_scores:
            self.strategy_scores[key] *= self.DECAY_FACTOR
        
        for key in self.style_scores:
            self.style_scores[key] *= self.DECAY_FACTOR
    
    def _load_preferences(self):
        """Carrega preferências do disco"""
        try:
            prefs_file = Path(self.PREFS_FILE)
            
            if not prefs_file.exists():
                return
            
            with open(prefs_file, 'r') as f:
                data = json.load(f)
            
            self.symbol_scores = defaultdict(float, data.get('symbol_scores', {}))
            self.strategy_scores = defaultdict(float, data.get('strategy_scores', {}))
            self.style_scores = defaultdict(float, data.get('style_scores', {}))
            
            self.logger.info(f"[COACH] Preferências carregadas: {len(self.symbol_scores)} símbolos")
            
        except Exception as e:
            self.logger.warning(f"[COACH] Erro ao carregar preferências: {e}")
    
    def _save_preferences(self):
        """Salva preferências no disco"""
        try:
            prefs_file = Path(self.PREFS_FILE)
            prefs_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'symbol_scores': dict(self.symbol_scores),
                'strategy_scores': dict(self.strategy_scores),
                'style_scores': dict(self.style_scores)
            }
            
            with open(prefs_file, 'w') as f:
                json.dump(data, f, indent=2)
            
        except Exception as e:
            self.logger.error(f"[COACH] Erro ao salvar preferências: {e}")
