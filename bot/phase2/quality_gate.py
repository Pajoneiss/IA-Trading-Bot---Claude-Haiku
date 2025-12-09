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
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, mode_manager=None):
        """
        Inicializa Quality Gate
        
        Args:
            config: Configurações opcionais
            mode_manager: TradingModeManager para thresholds dinâmicos por modo
        """
        self.config = config or {}
        self.mode_manager = mode_manager
        
        # Thresholds configuráveis (usados como fallback se mode_manager não existir)
        self.min_confidence = self.config.get('min_confidence', 0.80)
        self.max_candle_body_pct = self.config.get('max_candle_body_pct', 3.0)
        self.min_confluences = self.config.get('min_confluences', 2)
        
        # Phase 3: Market Regime Analyzer
        try:
            from bot.phase3 import MarketRegimeAnalyzer
            self._regime_analyzer = MarketRegimeAnalyzer(logger_instance=logger)
            logger.info("[QUALITY GATE] Phase 3 habilitada: Market Regime + Anti-Chop")
        except ImportError:
            self._regime_analyzer = None
            logger.debug("[QUALITY GATE] Phase 3 não disponível")
        
        mode_str = mode_manager.current_mode.value if mode_manager else "N/A"
        logger.info(f"[QUALITY GATE] Inicializado: mode={mode_str} | min_conf={self.min_confidence} | "
                   f"max_body={self.max_candle_body_pct}% | min_confluences={self.min_confluences}")
    
    def get_min_confidence(self, ai_type: str = 'swing') -> float:
        """
        Retorna confiança mínima considerando modo atual
        
        Args:
            ai_type: 'swing' ou 'scalp'
        """
        if self.mode_manager:
            if ai_type == 'scalp':
                return self.mode_manager.get_min_conf_scalp()
            return self.mode_manager.get_min_conf_swing()
        return self.min_confidence
    
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
        ai_type = decision.get('style', 'swing')  # Determina se é swing ou scalp
        
        # Obtém min_confidence dinâmico baseado no modo e tipo
        min_conf = self.get_min_confidence(ai_type)
        mode_str = self.mode_manager.current_mode.value if self.mode_manager else "N/A"
        
        logger.info(f"[QUALITY GATE] Avaliando {symbol}: confidence={confidence:.2f} | mode={mode_str} | ai_type={ai_type} | min_conf={min_conf:.2f}")
        
        # === CRITÉRIO 0: REGIME PERMITIDO POR MODO ===
        if self.mode_manager and market_context:
            # Tenta obter regime do contexto
            regime = market_context.get('regime') or market_context.get('phase3', {}).get('regime')
            if regime:
                if not self.mode_manager.is_regime_allowed_for_type(regime, ai_type):
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"Regime '{regime}' não permitido para {ai_type.upper()} em modo {mode_str}")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado: regime {regime} não compatível com modo {mode_str}")
                    return result
        
        # === CRITÉRIO 1: CONFIDENCE MÍNIMA ===
        if confidence < min_conf:
            result.approved = False
            result.confidence_score = confidence
            result.reasons.append(f"Confidence muito baixa: {confidence:.2f} < {min_conf:.2f} (modo {mode_str})")
            logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado: confidence={confidence:.2f} < {min_conf:.2f}")
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
            if adjusted_conf < min_conf:
                result.approved = False
                result.confidence_score = adjusted_conf
                result.reasons.append(f"Confluence penalty levou confidence para {adjusted_conf:.2f}")
                logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado após confluence penalty")
                return result
            
            confidence = adjusted_conf
        
        # === CRITÉRIO 4: MARKET REGIME + ANTI-CHOP (PHASE 3) ===
        # Integração da Phase 3 para filtrar regimes ruins
        try:
            from bot.phase3 import MarketRegimeAnalyzer, detect_chop
            
            # Regime analysis (se tiver candles disponíveis)
            regime_info = None
            chop_info = None
            
            if market_context and hasattr(self, '_regime_analyzer'):
                # Tenta pegar candles do contexto
                candles_m15 = market_context.get('candles_15m', [])
                candles_h1 = market_context.get('candles_h1', [])
                
                if candles_m15 and candles_h1:
                    regime_info = self._regime_analyzer.evaluate(
                        symbol=symbol,
                        candles_m15=candles_m15,
                        candles_h1=candles_h1,
                        market_intel=market_intelligence
                    )
                    
                    # Chop detection
                    chop_info = detect_chop(candles_m15, logger_instance=logger)
            
            # BLOQUEIA em PANIC_HIGH_VOL
            if regime_info and regime_info['regime'] == 'PANIC_HIGH_VOL':
                # Só aprova se confidence muito alta E não aggressive
                if confidence < 0.90 or decision.get('risk_profile') == 'AGGRESSIVE':
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"PANIC_HIGH_VOL: vol={regime_info['volatility']}, risk_off={regime_info['risk_off']}")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} bloqueado: PANIC_HIGH_VOL")
                    return result
                else:
                    result.warnings.append("PANIC_HIGH_VOL mas confidence >= 0.90")
            
            # BLOQUEIA em RANGE_CHOP ou CHOPPY
            if (regime_info and regime_info['regime'] == 'RANGE_CHOP') or \
               (chop_info and chop_info['is_choppy']):
                
                chop_score = chop_info.get('chop_score', 0) if chop_info else 0.5
                
                # Exige confluências extras
                if len(confluences) < 3:
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"RANGE_CHOP/Choppy (score={chop_score:.2f}) + poucas confluências ({len(confluences)} < 3)")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} bloqueado: mercado sujo + poucas confluências")
                    return result
                
                # Se scalp em chop, bloqueia
                style = decision.get('style', 'swing')
                if style == 'scalp':
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"Scalp bloqueado em CHOP (score={chop_score:.2f})")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} bloqueado: scalp em chop")
                    return result
                
                # Aviso mas permite passar se tiver confluências
                result.warnings.append(f"Mercado choppy (score={chop_score:.2f}) mas tem {len(confluences)} confluências")
            
            # BLOQUEIA em LOW_VOL_DRIFT para scalps
            if regime_info and regime_info['regime'] == 'LOW_VOL_DRIFT':
                style = decision.get('style', 'swing')
                if style == 'scalp':
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append("Scalp bloqueado em LOW_VOL_DRIFT")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} bloqueado: scalp em low vol")
                    return result
            
            # RISK_OFF: ajusta confidence
            if regime_info and regime_info['risk_off']:
                confidence *= 0.9  # Reduz 10%
                result.warnings.append("risk_off ativo: confidence reduzida")
                
                # Eleva threshold temporariamente
                temp_threshold = max(self.min_confidence, 0.88)
                if confidence < temp_threshold:
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"risk_off: confidence {confidence:.2f} < {temp_threshold:.2f}")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} bloqueado: risk_off + confidence insuficiente")
                    return result
            
            # Log do regime (se disponível)
            if regime_info:
                logger.debug(
                    f"[QUALITY GATE] {symbol} regime={regime_info['regime']}, "
                    f"chop={chop_info.get('chop_score', 0):.2f if chop_info else 'N/A'}"
                )
        
        except ImportError:
            # Phase 3 não disponível, continua normalmente
            logger.debug("[QUALITY GATE] Phase 3 não disponível, pulando regime check")
        except Exception as e:
            # Erro na Phase 3, não quebra o Quality Gate
            logger.error(f"[QUALITY GATE] Erro na Phase 3: {e}")
        
        # === CRITÉRIO 5 (original 4): MARKET INTELLIGENCE ===
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
        
        # === CRITÉRIO 6 (original 5): RISK PROFILE vs MARKET CONDITIONS ===
        risk_profile = decision.get('risk_profile', 'BALANCED')
        if market_intelligence:
            profile_check = self._check_risk_profile_alignment(risk_profile, market_intelligence)
            
            if not profile_check['aligned']:
                result.warnings.append(profile_check['reason'])
                confidence *= profile_check.get('multiplier', 0.9)
                
        # === CRITÉRIO 7: EMA TIMING (Novo) ===
        ema_timing = market_context.get('ema_timing') if market_context else None
        
        # Se não tem no contexto direto, tenta no objeto self do bot se estivesse acessível (mas não está fácil).
        # Assume que foi passado em market_context['ema_timing'] pelo loop principal
        
        if ema_timing:
            if not self._check_ema_timing(decision, ema_timing):
                # Se falhar no filtro EMA
                mode_str = self.mode_manager.current_mode.value if self.mode_manager else "N/A"
                result.approved = False
                result.confidence_score = confidence
                result.reasons.append(f"EMA Timing bloqueado para modo {mode_str} (score={ema_timing.get('score', 0):.2f})")
                logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado por EMA Timing ({mode_str})")
                return result
            else:
                logger.info(f"[QUALITY GATE] ✅ {symbol} aprovado no EMA Timing")

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
    
    def _check_ema_timing(self, decision: Dict[str, Any], ema_timing: Dict[str, Any]) -> bool:
        """
        Verifica se o timing das EMAs está alinhado com o modo atual.
        """
        try:
            mode = self.mode_manager.current_mode.value if self.mode_manager else "BALANCED"
            proposed_direction = decision.get('side', 'long').lower()
            
            # Recupera dados brutos
            score = ema_timing.get('score', 0)
            states = ema_timing.get('states', {})
            
            # --- CONSERVADOR ---
            if mode == "CONSERVATIVE":
                if score < 0.7: return False
                
                # Exige alinhamento em 4h e 1h
                s4h_dir = states.get('4h')
                s1h_dir = states.get('1h')
                
                if proposed_direction == 'long':
                    if s4h_dir != 'bull' or s1h_dir != 'bull': return False
                else:
                    if s4h_dir != 'bear' or s1h_dir != 'bear': return False
                    
                return True

            # --- BALANCEADO ---
            elif mode == "BALANCED":
                if score < 0.5: return False
                
                # Exige 1h a favor e 4h não contra
                s4h_dir = states.get('4h')
                s1h_dir = states.get('1h')
                
                if proposed_direction == 'long':
                    if s1h_dir != 'bull': return False # 1h TEM que ser bull
                    if s4h_dir == 'bear': return False # 4h não pode ser bear (pode ser flat/bull)
                else:
                    if s1h_dir != 'bear': return False
                    if s4h_dir == 'bull': return False
                
                return True

            # --- AGRESSIVO ---
            elif mode == "AGGRESSIVE":
                if score < 0.3: return False
                
                # Muito permissivo: só não opera se 1h estiver explicitamente contra E não houver sinal forte LTF
                # Como simplificação aqui, bloqueamos apenas se 1h for contra E 15m também for contra
                s1h_dir = states.get('1h')
                s15m_dir = states.get('15m')
                
                if proposed_direction == 'long':
                    if s1h_dir == 'bear' and s15m_dir == 'bear': return False
                else:
                    if s1h_dir == 'bull' and s15m_dir == 'bull': return False
                    
                return True
                
            return True
            
        except Exception as e:
            logger.error(f"[QUALITY GATE] Erro ao checar EMA timing: {e}")
            return True # Fail open para não travar produção por erro de lógica nova

    def log_rejection(self, symbol: str, result: QualityGateResult):
        """Loga rejeição de forma clara"""
        logger.warning(f"[QUALITY GATE] 🚫 {symbol} REJEITADO:")
        logger.warning(f"  Confidence: {result.confidence_score:.2f}")
        
        for reason in result.reasons:
            logger.warning(f"  • {reason}")
        
        for warning in result.warnings:
            logger.warning(f"  ⚠️  {warning}")
