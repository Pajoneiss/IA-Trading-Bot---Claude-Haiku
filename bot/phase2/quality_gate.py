"""
Phase 2 - Quality Gate
Filtro rigoroso para sinais A+
"""
import logging
from typing import Dict, Any, Optional, List
from bot.phase2.models import QualityGateResult

logger = logging.getLogger(__name__)


class QualityGate:
    """
    Quality Gate - Filtro de sinais A+
    
    Critérios:
    - Confidence >= 0.80
    - Estrutura macro coerente
    - Não entrar após vela gigante (>3%)
    - Não chase (vários candles atrasado)
    - Market Intelligence alignment
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Inicializa Quality Gate
        
        Args:
            config: Configurações opcionais
        """
        self.config = config or {}
        
        # Thresholds configuráveis
        self.min_confidence = self.config.get('min_confidence', 0.80)
        self.max_candle_body_pct = self.config.get('max_candle_body_pct', 3.0)
        self.min_confluences = self.config.get('min_confluences', 2)
        
        logger.info(f"[QUALITY GATE] Inicializado: min_conf={self.min_confidence} | "
                   f"max_body={self.max_candle_body_pct}% | min_confluences={self.min_confluences}")
    
    def evaluate(self, 
                 decision: Dict[str, Any],
                 market_context: Optional[Dict[str, Any]] = None,
                 market_intelligence: Optional[Dict[str, Any]] = None) -> QualityGateResult:
        """
        Avalia se decisão passa no Quality Gate
        
        Args:
            decision: Decisão da IA (já parseada)
            market_context: Contexto de mercado do símbolo
            market_intelligence: Dados de Market Intelligence
            
        Returns:
            QualityGateResult com aprovação e razões
        """
        result = QualityGateResult()
        
        # Se não for action=open, aprova automaticamente
        if decision.get('action') != 'open':
            result.approved = True
            result.confidence_score = 1.0
            result.reasons.append("Non-open action, auto-approved")
            return result
        
        symbol = decision.get('symbol', 'UNKNOWN')
        confidence = decision.get('confidence', 0.0)
        
        logger.info(f"[QUALITY GATE] Avaliando {symbol}: confidence={confidence:.2f}")
        
        # === CRITÉRIO 1: CONFIDENCE MÍNIMA ===
        if confidence < self.min_confidence:
            result.approved = False
            result.confidence_score = confidence
            result.reasons.append(f"Confidence muito baixa: {confidence:.2f} < {self.min_confidence}")
            logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado: confidence={confidence:.2f}")
            return result
        
        # === CRITÉRIO 2: VELA GIGANTE ===
        if market_context:
            last_candle_change = self._check_last_candle_size(market_context)
            if last_candle_change and abs(last_candle_change) > self.max_candle_body_pct:
                result.approved = False
                result.confidence_score = confidence * 0.5  # Penaliza muito
                result.reasons.append(f"Vela gigante detectada: {last_candle_change:.1f}% > {self.max_candle_body_pct}%")
                result.warnings.append("Possível chase após movimento explosivo")
                logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado: vela gigante {last_candle_change:.1f}%")
                return result
        
        # === CRITÉRIO 3: CONFLUÊNCIAS ===
        confluences = decision.get('confluences', [])
        if len(confluences) < self.min_confluences:
            # Não rejeita, mas penaliza confidence
            penalty = 0.05 * (self.min_confluences - len(confluences))
            adjusted_conf = max(0.0, confidence - penalty)
            
            result.warnings.append(f"Poucas confluências: {len(confluences)} < {self.min_confluences}")
            result.adjustments['confidence_penalty'] = penalty
            
            # Se após penalidade cair abaixo do mínimo, rejeita
            if adjusted_conf < self.min_confidence:
                result.approved = False
                result.confidence_score = adjusted_conf
                result.reasons.append(f"Confluence penalty levou confidence para {adjusted_conf:.2f}")
                logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado após confluence penalty")
                return result
            
            confidence = adjusted_conf
        
        # === CRITÉRIO 4: MARKET INTELLIGENCE ===
        if market_intelligence:
            mi_check = self._check_market_intelligence(decision, market_intelligence)
            
            if not mi_check['aligned']:
                # Penaliza confiança
                penalty = mi_check.get('penalty', 0.1)
                confidence = max(0.0, confidence - penalty)
                
                result.warnings.append(mi_check['reason'])
                result.adjustments['mi_penalty'] = penalty
                
                if confidence < self.min_confidence:
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"Market Intelligence conflito: {mi_check['reason']}")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado por MI conflito")
                    return result
        
        # === CRITÉRIO 5: RISK PROFILE vs MARKET CONDITIONS ===
        risk_profile = decision.get('risk_profile', 'BALANCED')
        if market_intelligence:
            profile_check = self._check_risk_profile_alignment(risk_profile, market_intelligence)
            
            if not profile_check['aligned']:
                result.warnings.append(profile_check['reason'])
                confidence *= profile_check.get('multiplier', 0.9)
        
        # === APROVADO ===
        result.approved = True
        result.confidence_score = confidence
        result.reasons.append(f"Sinal A+ aprovado com confidence={confidence:.2f}")
        
        if result.warnings:
            result.reasons.append(f"Com {len(result.warnings)} avisos")
        
        logger.info(f"[QUALITY GATE] ✅ {symbol} APROVADO: final_conf={confidence:.2f}")
        
        return result
    
    def _check_last_candle_size(self, market_context: Dict[str, Any]) -> Optional[float]:
        """
        Verifica tamanho da última vela
        
        Returns:
            % change do corpo da vela ou None
        """
        try:
            candles = market_context.get('candles', [])
            if not candles:
                return None
            
            last = candles[-1]
            open_price = last.get('open', 0)
            close_price = last.get('close', 0)
            
            if open_price > 0:
                change_pct = ((close_price - open_price) / open_price) * 100
                return change_pct
            
            return None
            
        except Exception as e:
            logger.error(f"[QUALITY GATE] Erro ao checar candle size: {e}")
            return None
    
    def _check_market_intelligence(self, 
                                   decision: Dict[str, Any],
                                   market_intelligence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verifica alinhamento com Market Intelligence
        
        Returns:
            {'aligned': bool, 'reason': str, 'penalty': float}
        """
        try:
            fear_greed = market_intelligence.get('fear_greed', {})
            fg_value = fear_greed.get('value', 50)
            fg_class = fear_greed.get('classification', 'Neutral')
            
            risk_profile = decision.get('risk_profile', 'BALANCED')
            
            # Extreme Fear + AGGRESSIVE = conflito
            if fg_class in ['Extreme Fear', 'Fear'] and risk_profile == 'AGGRESSIVE':
                return {
                    'aligned': False,
                    'reason': f"Mercado em {fg_class} mas trade AGGRESSIVE",
                    'penalty': 0.15
                }
            
            # Extreme Greed + AGGRESSIVE = conflito
            if fg_class in ['Extreme Greed', 'Greed'] and risk_profile == 'AGGRESSIVE':
                return {
                    'aligned': False,
                    'reason': f"Mercado em {fg_class} mas trade AGGRESSIVE",
                    'penalty': 0.10
                }
            
            # Tudo OK
            return {'aligned': True, 'reason': 'Market Intelligence OK'}
            
        except Exception as e:
            logger.error(f"[QUALITY GATE] Erro ao checar MI: {e}")
            return {'aligned': True, 'reason': 'MI check error, permitindo'}
    
    def _check_risk_profile_alignment(self,
                                     risk_profile: str,
                                     market_intelligence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verifica se risk profile está adequado ao mercado
        
        Returns:
            {'aligned': bool, 'reason': str, 'multiplier': float}
        """
        try:
            alt_season = market_intelligence.get('alt_season', {})
            season_value = alt_season.get('value', 0)
            
            # Bitcoin season (< 25) + AGGRESSIVE em altcoin = aviso
            if season_value < 25 and risk_profile == 'AGGRESSIVE':
                return {
                    'aligned': False,
                    'reason': 'Bitcoin season mas trade AGGRESSIVE em alt',
                    'multiplier': 0.85
                }
            
            # Altcoin season (> 75) + CONSERVATIVE = talvez muito conservador
            if season_value > 75 and risk_profile == 'CONSERVATIVE':
                return {
                    'aligned': True,
                    'reason': 'Alt season + conservative OK',
                    'multiplier': 1.0
                }
            
            return {'aligned': True, 'reason': 'Risk profile OK', 'multiplier': 1.0}
            
        except Exception as e:
            logger.error(f"[QUALITY GATE] Erro ao checar risk profile: {e}")
            return {'aligned': True, 'reason': 'Error, permitindo', 'multiplier': 1.0}
    
    def log_rejection(self, symbol: str, result: QualityGateResult):
        """Loga rejeição de forma clara"""
        logger.warning(f"[QUALITY GATE] 🚫 {symbol} REJEITADO:")
        logger.warning(f"  Confidence: {result.confidence_score:.2f}")
        
        for reason in result.reasons:
            logger.warning(f"  • {reason}")
        
        for warning in result.warnings:
            logger.warning(f"  ⚠️  {warning}")
