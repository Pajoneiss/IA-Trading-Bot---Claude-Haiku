"""
Learning Engine - Sistema de Aprendizado Simples
================================================
Não é ML de verdade, mas funciona!

Filosofia:
- Salva trades que deram certo e errado
- Identifica padrões que funcionam
- Ajusta parâmetros automaticamente
- Evolui com o tempo

Autor: Claude (Trend Refactor v3)
Data: 2024-12-11
"""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Registro de um trade para aprendizado"""
    timestamp: str
    symbol: str
    side: str  # long/short
    entry_price: float
    exit_price: float
    pnl_pct: float
    pnl_usd: float
    duration_minutes: int
    
    # Contexto no momento da entrada
    trend_bias: str  # long/short/neutral
    regime: str  # TREND_BULL/TREND_BEAR/RANGE_CHOP
    confidence: float
    trigger_type: str  # ema_cross/momentum/structure
    
    # Indicadores
    ema_alignment: str  # aligned/misaligned
    volatility: str  # low/normal/high
    chop_score: float
    
    # Resultado
    was_profitable: bool
    was_aligned_with_trend: bool
    
    def to_dict(self) -> Dict:
        return asdict(self)


class LearningEngine:
    """
    Motor de aprendizado que evolui com os trades.
    
    O que ele faz:
    1. Salva todos os trades com contexto
    2. Calcula win rate por setup
    3. Ajusta parâmetros baseado no que funciona
    4. Gera "regras aprendidas"
    """
    
    DATA_FILE = "data/trade_history.json"
    PARAMS_FILE = "data/learned_params.json"
    
    def __init__(self, logger_instance=None):
        self.logger = logger_instance or logger
        self.trades: List[TradeRecord] = []
        self.learned_params: Dict[str, Any] = {}
        self.stats: Dict[str, Any] = {}
        
        # Parâmetros default que serão ajustados
        self.default_params = {
            "min_confidence": 0.65,
            "min_confidence_neutral": 0.80,
            "allow_counter_trend": False,
            "max_chop_score": 0.7,
            "pyramid_min_pnl": 0.5,
            "pyramid_max_adds": 2,
            "trailing_activation_pct": 1.0,
            "prefer_trend_aligned": True,
            "aggression_level": 0.5,  # 0 = conservador, 1 = agressivo
        }
        
        self._load_data()
    
    def _load_data(self):
        """Carrega histórico de trades e parâmetros aprendidos"""
        # Carrega trades
        if os.path.exists(self.DATA_FILE):
            try:
                with open(self.DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.trades = [TradeRecord(**t) for t in data.get('trades', [])]
                    self.logger.info(f"[LEARNING] 📚 Carregados {len(self.trades)} trades do histórico")
            except Exception as e:
                self.logger.error(f"[LEARNING] Erro ao carregar histórico: {e}")
                self.trades = []
        
        # Carrega parâmetros aprendidos
        if os.path.exists(self.PARAMS_FILE):
            try:
                with open(self.PARAMS_FILE, 'r') as f:
                    self.learned_params = json.load(f)
                    self.logger.info(f"[LEARNING] 🧠 Parâmetros aprendidos carregados")
            except Exception as e:
                self.logger.error(f"[LEARNING] Erro ao carregar parâmetros: {e}")
                self.learned_params = self.default_params.copy()
        else:
            self.learned_params = self.default_params.copy()
    
    def _save_data(self):
        """Salva dados em disco"""
        os.makedirs("data", exist_ok=True)
        
        # Salva trades
        try:
            with open(self.DATA_FILE, 'w') as f:
                json.dump({
                    'trades': [t.to_dict() for t in self.trades],
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            self.logger.error(f"[LEARNING] Erro ao salvar trades: {e}")
        
        # Salva parâmetros
        try:
            with open(self.PARAMS_FILE, 'w') as f:
                json.dump(self.learned_params, f, indent=2)
        except Exception as e:
            self.logger.error(f"[LEARNING] Erro ao salvar parâmetros: {e}")
    
    def record_trade(self, trade_data: Dict[str, Any]):
        """
        Registra um trade finalizado para aprendizado.
        
        Args:
            trade_data: Dict com dados do trade
        """
        try:
            record = TradeRecord(
                timestamp=datetime.now().isoformat(),
                symbol=trade_data.get('symbol', 'UNKNOWN'),
                side=trade_data.get('side', 'long'),
                entry_price=float(trade_data.get('entry_price', 0)),
                exit_price=float(trade_data.get('exit_price', 0)),
                pnl_pct=float(trade_data.get('pnl_pct', 0)),
                pnl_usd=float(trade_data.get('pnl_usd', 0)),
                duration_minutes=int(trade_data.get('duration_minutes', 0)),
                trend_bias=trade_data.get('trend_bias', 'neutral'),
                regime=trade_data.get('regime', 'UNKNOWN'),
                confidence=float(trade_data.get('confidence', 0)),
                trigger_type=trade_data.get('trigger_type', 'unknown'),
                ema_alignment=trade_data.get('ema_alignment', 'unknown'),
                volatility=trade_data.get('volatility', 'normal'),
                chop_score=float(trade_data.get('chop_score', 0)),
                was_profitable=float(trade_data.get('pnl_pct', 0)) > 0,
                was_aligned_with_trend=self._check_alignment(
                    trade_data.get('side'),
                    trade_data.get('trend_bias')
                )
            )
            
            self.trades.append(record)
            self._save_data()
            
            self.logger.info(
                f"[LEARNING] 📝 Trade registrado: {record.symbol} {record.side} "
                f"PnL={record.pnl_pct:+.2f}% aligned={record.was_aligned_with_trend}"
            )
            
            # Recalcula estatísticas e ajusta parâmetros
            self._update_stats()
            self._adjust_params()
            
        except Exception as e:
            self.logger.error(f"[LEARNING] Erro ao registrar trade: {e}")
    
    def _check_alignment(self, side: str, trend_bias: str) -> bool:
        """Verifica se trade estava alinhado com tendência"""
        if not side or not trend_bias:
            return False
        return (
            (side == 'long' and trend_bias == 'long') or
            (side == 'short' and trend_bias == 'short')
        )
    
    def _update_stats(self):
        """Atualiza estatísticas baseado nos trades"""
        if not self.trades:
            return
        
        # Filtra trades recentes (últimos 7 dias)
        cutoff = datetime.now() - timedelta(days=7)
        recent = [t for t in self.trades if datetime.fromisoformat(t.timestamp) > cutoff]
        
        if not recent:
            recent = self.trades[-50:]  # Últimos 50 se não tiver recentes
        
        # Estatísticas gerais
        total = len(recent)
        winners = [t for t in recent if t.was_profitable]
        
        self.stats = {
            'total_trades': total,
            'win_rate': len(winners) / total if total > 0 else 0,
            'avg_pnl': sum(t.pnl_pct for t in recent) / total if total > 0 else 0,
        }
        
        # Win rate por setup
        by_trend_aligned = defaultdict(list)
        by_regime = defaultdict(list)
        by_trigger = defaultdict(list)
        by_confidence = defaultdict(list)
        
        for t in recent:
            # Por alinhamento com tendência
            key = 'aligned' if t.was_aligned_with_trend else 'counter'
            by_trend_aligned[key].append(t.was_profitable)
            
            # Por regime
            by_regime[t.regime].append(t.was_profitable)
            
            # Por trigger
            by_trigger[t.trigger_type].append(t.was_profitable)
            
            # Por faixa de confidence
            if t.confidence >= 0.8:
                by_confidence['high'].append(t.was_profitable)
            elif t.confidence >= 0.65:
                by_confidence['medium'].append(t.was_profitable)
            else:
                by_confidence['low'].append(t.was_profitable)
        
        # Calcula win rates
        self.stats['wr_by_alignment'] = {
            k: sum(v) / len(v) if v else 0 
            for k, v in by_trend_aligned.items()
        }
        self.stats['wr_by_regime'] = {
            k: sum(v) / len(v) if v else 0 
            for k, v in by_regime.items()
        }
        self.stats['wr_by_trigger'] = {
            k: sum(v) / len(v) if v else 0 
            for k, v in by_trigger.items()
        }
        self.stats['wr_by_confidence'] = {
            k: sum(v) / len(v) if v else 0 
            for k, v in by_confidence.items()
        }
        
        self.logger.info(f"[LEARNING] 📊 Stats atualizadas: WR={self.stats['win_rate']:.1%}")
    
    def _adjust_params(self):
        """Ajusta parâmetros baseado no que está funcionando"""
        if len(self.trades) < 10:
            self.logger.info("[LEARNING] Poucos trades para ajustar parâmetros (mín 10)")
            return
        
        # Regra 1: Se trades alinhados têm win rate muito maior, força alinhamento
        wr_aligned = self.stats.get('wr_by_alignment', {}).get('aligned', 0.5)
        wr_counter = self.stats.get('wr_by_alignment', {}).get('counter', 0.5)
        
        if wr_aligned > wr_counter + 0.15:  # 15% melhor
            self.learned_params['allow_counter_trend'] = False
            self.learned_params['prefer_trend_aligned'] = True
            self.logger.info(f"[LEARNING] 🎯 Aprendido: Trades alinhados são {(wr_aligned-wr_counter)*100:.0f}% melhores")
        
        # Regra 2: Ajusta confidence mínima baseado no win rate por faixa
        wr_high = self.stats.get('wr_by_confidence', {}).get('high', 0)
        wr_medium = self.stats.get('wr_by_confidence', {}).get('medium', 0)
        wr_low = self.stats.get('wr_by_confidence', {}).get('low', 0)
        
        if wr_high > 0.6 and wr_medium > 0.5:
            # Pode ser mais agressivo
            self.learned_params['min_confidence'] = 0.60
            self.learned_params['aggression_level'] = min(0.8, self.learned_params['aggression_level'] + 0.1)
            self.logger.info("[LEARNING] 🚀 Aprendido: Win rate alto, aumentando agressividade")
        elif wr_high < 0.5:
            # Precisa ser mais conservador
            self.learned_params['min_confidence'] = 0.75
            self.learned_params['aggression_level'] = max(0.2, self.learned_params['aggression_level'] - 0.1)
            self.logger.info("[LEARNING] 🛡️ Aprendido: Win rate baixo, sendo mais conservador")
        
        # Regra 3: Ajusta por regime
        wr_trend = max(
            self.stats.get('wr_by_regime', {}).get('TREND_BULL', 0),
            self.stats.get('wr_by_regime', {}).get('TREND_BEAR', 0)
        )
        wr_range = self.stats.get('wr_by_regime', {}).get('RANGE_CHOP', 0)
        
        if wr_trend > wr_range + 0.2:
            # Muito melhor em tendência, evita range
            self.learned_params['max_chop_score'] = 0.5
            self.logger.info("[LEARNING] 📈 Aprendido: Melhor em tendência, evitando range")
        
        # Salva parâmetros ajustados
        self._save_data()
    
    def get_params(self) -> Dict[str, Any]:
        """Retorna parâmetros atuais (aprendidos ou default)"""
        return self.learned_params.copy()
    
    def should_take_trade(self, trade_context: Dict[str, Any]) -> tuple[bool, str, float]:
        """
        Usa aprendizado para decidir se deve tomar o trade.
        
        Returns:
            (should_trade, reason, confidence_adjustment)
        """
        confidence = trade_context.get('confidence', 0)
        trend_bias = trade_context.get('trend_bias', 'neutral')
        side = trade_context.get('side', 'long')
        regime = trade_context.get('regime', 'UNKNOWN')
        chop_score = trade_context.get('chop_score', 0)
        
        params = self.learned_params
        confidence_boost = 0.0
        
        # Check 1: Confidence mínima
        min_conf = params.get('min_confidence', 0.65)
        if trend_bias == 'neutral':
            min_conf = params.get('min_confidence_neutral', 0.80)
        
        if confidence < min_conf:
            return False, f"Confidence {confidence:.2f} < mínimo aprendido {min_conf:.2f}", 0
        
        # Check 2: Alinhamento com tendência
        is_aligned = self._check_alignment(side, trend_bias)
        if not is_aligned and not params.get('allow_counter_trend', False):
            return False, f"Trade {side} contra tendência {trend_bias} (aprendido)", 0
        
        # Check 3: Chop score
        if chop_score > params.get('max_chop_score', 0.7):
            return False, f"Chop score {chop_score:.2f} > máximo aprendido", 0
        
        # Boost de confidence se alinhado
        if is_aligned:
            confidence_boost = 0.05
            
        # Boost se regime favorável
        if regime in ['TREND_BULL', 'TREND_BEAR']:
            wr = self.stats.get('wr_by_regime', {}).get(regime, 0.5)
            if wr > 0.55:
                confidence_boost += 0.05
        
        return True, "Aprovado pelo Learning Engine", confidence_boost
    
    def get_pyramid_params(self) -> Dict[str, Any]:
        """Retorna parâmetros de pyramiding aprendidos"""
        return {
            'min_pnl': self.learned_params.get('pyramid_min_pnl', 0.5),
            'max_adds': self.learned_params.get('pyramid_max_adds', 2),
        }
    
    def get_summary(self) -> str:
        """Retorna resumo do aprendizado"""
        if not self.trades:
            return "📚 Learning Engine: Sem histórico ainda"
        
        return (
            f"📚 Learning Engine:\n"
            f"  Trades: {len(self.trades)}\n"
            f"  Win Rate: {self.stats.get('win_rate', 0):.1%}\n"
            f"  Avg PnL: {self.stats.get('avg_pnl', 0):+.2f}%\n"
            f"  Agressividade: {self.learned_params.get('aggression_level', 0.5):.0%}\n"
            f"  Min Confidence: {self.learned_params.get('min_confidence', 0.65):.2f}"
        )


# Função helper para uso global
_learning_engine: Optional[LearningEngine] = None

def get_learning_engine(logger_instance=None) -> LearningEngine:
    """Retorna instância singleton do Learning Engine"""
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = LearningEngine(logger_instance)
    return _learning_engine
