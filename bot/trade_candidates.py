"""
Trade Candidates - Filtro de candidatos para IA
================================================

[CORE STRATEGY INTEGRATION]

Este módulo faz o pré-filtro técnico ANTES de chamar a IA:
1. Recebe setups do Core Strategy (core_setup_valid=True)
2. Aplica filtros rápidos (exposição, regime, posições existentes)
3. Retorna apenas candidatos "dignos" de consultar a IA

A IA é o CÉREBRO - ela só decide em cima de candidatos filtrados.
"""
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TradeCandidate:
    """Candidato a trade filtrado e pronto para IA"""
    symbol: str
    direction: str  # "long" ou "short"
    setup_type: str  # "entry_long", "entry_short", "add", etc
    trigger_reason: str  # Razão do trigger
    
    # Dados do Core Strategy
    trend_bias: str  # "long", "short", "neutral"
    daily_climate: str  # "strong_bull", "strong_bear", "neutral"
    h1_confirmation: str  # "aligned", "divergent", "neutral"
    
    # Métricas
    size_multiplier: float = 1.0
    confidence_adjustment: float = 0.0
    
    # Contexto adicional
    regime: str = "TREND_BULL"
    current_price: float = 0.0
    has_existing_position: bool = False
    existing_position_side: str = ""


class TradeCandidateFilter:
    """
    Filtro de Trade Candidates
    
    Aplica regras RÁPIDAS antes de chamar a IA:
    - Exposição máxima por símbolo
    - Limite de trades simultâneos
    - Regime de mercado
    - Posições existentes (evita flip imediato)
    """
    
    def __init__(self, 
                 position_manager=None,
                 mode_manager=None,
                 logger_instance=None):
        self.log = logger_instance or logger
        self.position_manager = position_manager
        self.mode_manager = mode_manager
        
        # Config (pode vir do mode_manager)
        self.max_open_positions = 5
        self.max_position_per_symbol = 1
        self.allow_flip = False  # Permite trocar de lado imediatamente?
        
        self.log.info("[TRADE CANDIDATE] Filtro inicializado")
    
    def filter_candidates(self,
                         market_contexts: List[Dict],
                         portfolio_state: Dict = None) -> List[TradeCandidate]:
        """
        Filtra contextos de mercado e retorna candidatos válidos
        
        Args:
            market_contexts: Lista de contextos com core_analysis
            portfolio_state: Estado atual do portfolio (posições, equity)
            
        Returns:
            Lista de TradeCandidate prontos para IA
        """
        candidates = []
        portfolio_state = portfolio_state or {}
        
        # Carrega config do mode_manager se disponível
        if self.mode_manager:
            mode_config = self.mode_manager.get_current_mode_config()
            self.max_open_positions = mode_config.get('max_open_positions', 5)
        
        # Conta posições abertas
        current_positions = {}
        if self.position_manager:
            positions = self.position_manager.get_all_positions()
            for pos in positions:
                symbol = pos.get('symbol', '')
                current_positions[symbol] = pos
        
        open_count = len(current_positions)
        
        for ctx in market_contexts:
            symbol = ctx.get('symbol', '')
            core_analysis = ctx.get('core_analysis', {})
            
            # Só considera se tem setup válido do CORE
            if not core_analysis.get('has_valid_setup'):
                continue
            
            setup_type = core_analysis.get('setup_type', 'none')
            setup_reason = core_analysis.get('setup_reason', '')
            trend_bias = core_analysis.get('trend_bias', 'neutral')
            
            # Determina direção
            if setup_type == 'entry_long':
                direction = 'long'
            elif setup_type == 'entry_short':
                direction = 'short'
            else:
                continue  # Setup não é de entrada
            
            # ========== PRÉ-FILTROS RÁPIDOS ==========
            
            # 1. Limite de posições abertas
            if open_count >= self.max_open_positions:
                self.log.info(
                    f"[TRADE CANDIDATE] ❌ {symbol} rejeitado: "
                    f"limite de posições ({open_count}/{self.max_open_positions})"
                )
                continue
            
            # 2. Já tem posição neste símbolo?
            existing_pos = current_positions.get(symbol)
            has_position = existing_pos is not None
            existing_side = existing_pos.get('side', '') if existing_pos else ''
            
            if has_position:
                # Se posição é na mesma direção, pode ser "add" no futuro
                if existing_side == direction:
                    self.log.debug(
                        f"[TRADE CANDIDATE] {symbol} já tem posição {direction}, "
                        f"ignorando nova entrada (add não implementado aqui)"
                    )
                    continue
                
                # Se posição é na direção oposta, verifica se permite flip
                if not self.allow_flip:
                    self.log.info(
                        f"[TRADE CANDIDATE] ❌ {symbol} rejeitado: "
                        f"posição {existing_side} existente, flip não permitido"
                    )
                    continue
            
            # 3. Regime de mercado (modo conservador não opera em RANGE_CHOP)
            regime_info = ctx.get('regime_info', {})
            regime = regime_info.get('regime', 'RANGE_CHOP')
            
            if self.mode_manager:
                mode = self.mode_manager.current_mode.value
                if mode == "CONSERVADOR" and regime == "RANGE_CHOP":
                    self.log.info(
                        f"[TRADE CANDIDATE] ❌ {symbol} rejeitado: "
                        f"regime RANGE_CHOP não permitido em modo CONSERVADOR"
                    )
                    continue
            
            # ========== CANDIDATO APROVADO ==========
            
            candidate = TradeCandidate(
                symbol=symbol,
                direction=direction,
                setup_type=setup_type,
                trigger_reason=setup_reason,
                trend_bias=trend_bias,
                daily_climate=core_analysis.get('daily_climate', 'neutral'),
                h1_confirmation=core_analysis.get('h1_confirmation', 'neutral'),
                size_multiplier=core_analysis.get('size_multiplier', 1.0),
                confidence_adjustment=core_analysis.get('confidence_adjustment', 0.0),
                regime=regime,
                current_price=ctx.get('price', 0),
                has_existing_position=has_position,
                existing_position_side=existing_side
            )
            
            candidates.append(candidate)
            
            self.log.info(
                f"[TRADE CANDIDATE] ✅ {symbol} {direction.upper()} aprovado: "
                f"{setup_type} | trend_bias={trend_bias} | regime={regime}"
            )
        
        return candidates


# Singleton
_candidate_filter: Optional[TradeCandidateFilter] = None

def get_candidate_filter(position_manager=None, mode_manager=None, logger_instance=None) -> TradeCandidateFilter:
    """Retorna instância singleton do TradeCandidateFilter"""
    global _candidate_filter
    if _candidate_filter is None:
        _candidate_filter = TradeCandidateFilter(
            position_manager=position_manager,
            mode_manager=mode_manager,
            logger_instance=logger_instance
        )
    return _candidate_filter
