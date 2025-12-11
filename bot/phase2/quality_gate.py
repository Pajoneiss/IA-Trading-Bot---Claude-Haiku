"""
Phase 2 - Quality Gate
Filtro rigoroso para sinais A+

PATCH v2.0:
- ModeQualityParams: parâmetros diferentes por modo (Conservador/Balanceado/Agressivo)
- Penalização de confluência menos agressiva para Balanceado/Agressivo
- Tratamento especial para daily EMA cross em swing trades
- allow_high_rsi_on_daily_shift: permite RSI alto quando daily cross favorável

[Claude Trend Refactor] Data: 2024-12-11:
- Integração com TrendGuard para bloquear trades contra-tendência
- Thresholds ajustados por regime (mais tolerante em tendência, mais rígido em range)
"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from bot.phase2.models import QualityGateResult

logger = logging.getLogger(__name__)


# ===== NOVO: Parâmetros por Modo =====
@dataclass
class ModeQualityParams:
    """Parâmetros de Quality Gate por modo de trading"""
    min_conf_swing: float
    min_conf_scalp: float
    min_confluences_swing: int
    min_confluences_scalp: int
    ema_alignment_weight: float
    allow_high_rsi_on_daily_shift: bool
    confluence_penalty_factor: float  # Quanto penalizar por confluência faltante


# Parâmetros padrão por modo
QUALITY_PARAMS = {
    "CONSERVADOR": ModeQualityParams(
        min_conf_swing=0.78,
        min_conf_scalp=0.80,
        min_confluences_swing=3,
        min_confluences_scalp=3,
        ema_alignment_weight=1.0,
        allow_high_rsi_on_daily_shift=False,
        confluence_penalty_factor=0.08,
    ),
    "BALANCEADO": ModeQualityParams(
        min_conf_swing=0.72,
        min_conf_scalp=0.74,
        min_confluences_swing=2,
        min_confluences_scalp=2,
        ema_alignment_weight=0.8,
        allow_high_rsi_on_daily_shift=True,
        confluence_penalty_factor=0.05,
    ),
    "AGRESSIVO": ModeQualityParams(
        min_conf_swing=0.68,
        min_conf_scalp=0.70,
        min_confluences_swing=1,
        min_confluences_scalp=1,
        ema_alignment_weight=0.6,
        allow_high_rsi_on_daily_shift=True,
        confluence_penalty_factor=0.03,
    ),
}


class QualityGate:
    """
    Quality Gate - Filtro de sinais A+
    
    PATCH v2.0:
    - Parâmetros dinâmicos por modo
    - Tratamento especial para daily EMA cross
    - Penalização de confluência ajustada por modo
    
    Critérios:
    - Confidence >= threshold (varia por modo)
    - Estrutura macro coerente
    - Não entrar após vela gigante (>3%)
    - Não chase (vários candles atrasado)
    - Market Intelligence alignment
    - EMA Timing + Daily Trend Shift
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
    
    def _get_mode_params(self) -> ModeQualityParams:
        """Retorna parâmetros do modo atual"""
        mode_str = self.mode_manager.current_mode.value if self.mode_manager else "BALANCEADO"
        return QUALITY_PARAMS.get(mode_str, QUALITY_PARAMS["BALANCEADO"])
    
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
        
        PATCH v2.0:
        - Usa parâmetros por modo
        - Tratamento especial para daily EMA cross
        - Penalização de confluência ajustada
        
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
        ai_type = decision.get('style', 'swing')
        
        # Obtém parâmetros do modo
        params = self._get_mode_params()
        mode_str = self.mode_manager.current_mode.value if self.mode_manager else "N/A"
        
        # Obtém min_confidence dinâmico baseado no modo e tipo
        min_conf = self.get_min_confidence(ai_type)
        
        logger.info(f"[QUALITY GATE] Avaliando {symbol}: confidence={confidence:.2f} | mode={mode_str} | ai_type={ai_type} | min_conf={min_conf:.2f}")
        
        # ===== EXTRAIR EMA CONTEXT PARA USO POSTERIOR =====
        ema_context = market_context.get('ema_context') if market_context else None
        daily_trend_shift = None
        ema_alignment_score = 0.0
        allow_high_rsi_override = False
        
        if ema_context:
            daily_trend_shift = getattr(ema_context, 'daily_trend_shift', None)
            ema_alignment_score = getattr(ema_context, 'alignment_score', 0.0)
            allow_high_rsi_override = getattr(ema_context, 'allow_high_rsi_override', False)
        
        # === CRITÉRIO 0: REGIME PERMITIDO POR MODO ===
        if self.mode_manager and market_context:
            regime = market_context.get('regime') or market_context.get('phase3', {}).get('regime')
            if regime:
                if not self.mode_manager.is_regime_allowed_for_type(regime, ai_type):
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"Regime '{regime}' não permitido para {ai_type.upper()} em modo {mode_str}")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado: regime {regime} não compatível com modo {mode_str}")
                    return result
        
        # === CRITÉRIO 0.5: TREND GUARD - ALINHAMENTO COM TENDÊNCIA ===
        # [Claude Trend Refactor] Verifica se trade está A FAVOR da tendência
        try:
            from bot.phase3 import TrendGuard
            
            # Obtém regime_info do contexto
            regime_info = market_context.get('regime_info', {}) if market_context else {}
            
            # Se não tiver regime_info no contexto, tenta extrair de outras fontes
            if not regime_info:
                phase3_data = market_context.get('phase3', {}) if market_context else {}
                regime_info = {
                    'regime': phase3_data.get('regime', 'RANGE_CHOP'),
                    'trend_bias': phase3_data.get('trend_bias', 'neutral')
                }
            
            # Cria TrendGuard e avalia
            trend_guard = TrendGuard(mode_manager=self.mode_manager, logger_instance=logger)
            tg_result = trend_guard.evaluate(decision, regime_info, confidence)
            
            if not tg_result.allowed:
                result.approved = False
                result.confidence_score = confidence
                result.reasons.append(f"[TREND GUARD] {tg_result.reason}")
                logger.warning(
                    f"[QUALITY GATE] 🚫 {symbol} BLOQUEADO pelo TrendGuard: "
                    f"action={tg_result.original_action}, side={tg_result.original_side}, "
                    f"trend_bias={tg_result.trend_bias}"
                )
                return result
            
            # Adiciona warnings do TrendGuard
            for warning in tg_result.warnings:
                result.warnings.append(warning)
            
            logger.info(
                f"[QUALITY GATE] ✅ {symbol} aprovado pelo TrendGuard: "
                f"trend_bias={tg_result.trend_bias}, regime={tg_result.regime}"
            )
            
        except ImportError:
            logger.debug("[QUALITY GATE] TrendGuard não disponível, pulando verificação")
        except Exception as e:
            logger.error(f"[QUALITY GATE] Erro no TrendGuard: {e}")
        
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
                result.confidence_score = confidence * 0.5
                result.reasons.append(f"Vela gigante detectada: {last_candle_change:.1f}% > {self.max_candle_body_pct}%")
                result.warnings.append("Possível chase após movimento explosivo")
                logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado: vela gigante {last_candle_change:.1f}%")
                return result
        
        # === CRITÉRIO 3: CONFLUÊNCIAS (AJUSTADO POR MODO) ===
        confluences = decision.get('confluences', [])
        min_confluences = params.min_confluences_swing if ai_type == 'swing' else params.min_confluences_scalp
        
        if len(confluences) < min_confluences:
            # PATCH v2.0: Penalização ajustada por modo
            missing = min_confluences - len(confluences)
            penalty = params.confluence_penalty_factor * missing
            adjusted_conf = max(0.0, confidence - penalty)
            
            result.warnings.append(f"Poucas confluências: {len(confluences)} < {min_confluences}")
            result.adjustments['confidence_penalty'] = penalty
            
            logger.info(f"[QUALITY GATE] Confluences={len(confluences)}/{min_confluences} (mode={mode_str}), applying penalty -{penalty:.2f}")
            
            # Se após penalidade cair abaixo do mínimo, verifica se pode ser salvo pelo daily shift
            if adjusted_conf < min_conf:
                # PATCH v2.0: Se tiver daily trend shift favorável, pode passar mesmo assim
                if self._check_daily_shift_override(decision, daily_trend_shift, ema_alignment_score, params, mode_str):
                    logger.info(f"[QUALITY GATE][DAILY_EMA] Permitindo {symbol} apesar de confluências baixas - daily shift favorável")
                    confidence = adjusted_conf + 0.05  # Pequeno boost
                else:
                    result.approved = False
                    result.confidence_score = adjusted_conf
                    result.reasons.append(f"Confluence penalty levou confidence para {adjusted_conf:.2f}")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado após confluence penalty")
                    return result
            else:
                confidence = adjusted_conf
        
        # === CRITÉRIO 4: MARKET REGIME + ANTI-CHOP (PHASE 3) ===
        try:
            from bot.phase3 import MarketRegimeAnalyzer, detect_chop
            
            regime_info = None
            chop_info = None
            
            if market_context and hasattr(self, '_regime_analyzer'):
                candles_m15 = market_context.get('candles_15m', [])
                candles_h1 = market_context.get('candles_h1', [])
                
                if candles_m15 and candles_h1:
                    regime_info = self._regime_analyzer.evaluate(
                        symbol=symbol,
                        candles_m15=candles_m15,
                        candles_h1=candles_h1,
                        market_intel=market_intelligence
                    )
                    
                    chop_info = detect_chop(candles_m15, logger_instance=logger)
            
            # BLOQUEIA em PANIC_HIGH_VOL
            if regime_info and regime_info['regime'] == 'PANIC_HIGH_VOL':
                if confidence < 0.90 or decision.get('risk_profile') == 'AGGRESSIVE':
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"PANIC_HIGH_VOL: vol={regime_info['volatility']}, risk_off={regime_info['risk_off']}")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} bloqueado: PANIC_HIGH_VOL")
                    return result
                else:
                    result.warnings.append("PANIC_HIGH_VOL mas confidence >= 0.90")
            
            # BLOQUEIA em RANGE_CHOP ou CHOPPY - AJUSTADO POR MODO
            # [Claude Trend Refactor] Mais tolerante se trend_bias indica tendência clara
            trend_bias = regime_info.get('trend_bias', 'neutral') if regime_info else 'neutral'
            is_trending = trend_bias in ['long', 'short']
            
            if (regime_info and regime_info['regime'] == 'RANGE_CHOP') or \
               (chop_info and chop_info['is_choppy']):
                
                chop_score = chop_info.get('chop_score', 0) if chop_info else 0.5
                
                # [Claude Trend Refactor] Se temos tendência clara, somos mais tolerantes
                if is_trending:
                    # Em tendência, só bloqueia se chop MUITO alto (>0.8)
                    if chop_score > 0.8:
                        result.warnings.append(f"Chop alto ({chop_score:.2f}) mas permitido por tendência {trend_bias}")
                    logger.info(f"[QUALITY GATE] Chop tolerado em {symbol} por tendência {trend_bias}")
                else:
                    # Sem tendência clara, aplica regras normais por modo
                    if mode_str == "CONSERVADOR":
                        if len(confluences) < 3:
                            result.approved = False
                            result.confidence_score = confidence
                            result.reasons.append(f"RANGE_CHOP/Choppy (score={chop_score:.2f}) + poucas confluências ({len(confluences)} < 3)")
                            logger.warning(f"[QUALITY GATE] ❌ {symbol} bloqueado: mercado sujo + poucas confluências")
                            return result
                    elif mode_str == "BALANCEADO":
                        # Balanceado: só bloqueia se chop muito alto e poucas confluências
                        if chop_score > 0.7 and len(confluences) < 2:
                            result.approved = False
                            result.confidence_score = confidence
                            result.reasons.append(f"RANGE_CHOP alto (score={chop_score:.2f}) + confluências < 2")
                            return result
                    # Agressivo: não bloqueia por chop em swing
                
                # Se scalp em chop E sem tendência, bloqueia
                if ai_type == 'scalp' and not is_trending:
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"Scalp bloqueado em CHOP (score={chop_score:.2f}) sem tendência")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} bloqueado: scalp em chop")
                    return result
                
                result.warnings.append(f"Mercado choppy (score={chop_score:.2f}) mas permitido no modo {mode_str}")
            
            # BLOQUEIA em LOW_VOL_DRIFT para scalps
            if regime_info and regime_info['regime'] == 'LOW_VOL_DRIFT':
                if ai_type == 'scalp':
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append("Scalp bloqueado em LOW_VOL_DRIFT")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} bloqueado: scalp em low vol")
                    return result
            
            # RISK_OFF: ajusta confidence
            if regime_info and regime_info['risk_off']:
                confidence *= 0.9
                result.warnings.append("risk_off ativo: confidence reduzida")
                
                temp_threshold = max(self.min_confidence, 0.88)
                if confidence < temp_threshold:
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"risk_off: confidence {confidence:.2f} < {temp_threshold:.2f}")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} bloqueado: risk_off + confidence insuficiente")
                    return result
            
            if regime_info:
                logger.debug(
                    f"[QUALITY GATE] {symbol} regime={regime_info['regime']}, "
                    f"chop={chop_info.get('chop_score', 0):.2f if chop_info else 'N/A'}"
                )
        
        except ImportError:
            logger.debug("[QUALITY GATE] Phase 3 não disponível, pulando regime check")
        except Exception as e:
            logger.error(f"[QUALITY GATE] Erro na Phase 3: {e}")
        
        # === CRITÉRIO 5: MARKET INTELLIGENCE ===
        if market_intelligence:
            mi_check = self._check_market_intelligence(decision, market_intelligence)
            
            if not mi_check['aligned']:
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
        
        # === CRITÉRIO 6: RISK PROFILE vs MARKET CONDITIONS ===
        risk_profile = decision.get('risk_profile', 'BALANCED')
        if market_intelligence:
            profile_check = self._check_risk_profile_alignment(risk_profile, market_intelligence)
            
            if not profile_check['aligned']:
                result.warnings.append(profile_check['reason'])
                confidence *= profile_check.get('multiplier', 0.9)
                
        # === CRITÉRIO 7: EMA TIMING (PATCH v2.0) ===
        ema_timing = market_context.get('ema_timing') if market_context else None
        
        if ema_timing:
            if not self._check_ema_timing(decision, ema_timing):
                # Antes de rejeitar, verifica se tem daily shift favorável
                if self._check_daily_shift_override(decision, daily_trend_shift, ema_alignment_score, params, mode_str):
                    logger.info(f"[QUALITY GATE][DAILY_EMA] Permitindo {symbol} apesar de EMA timing ruim - daily shift favorável")
                else:
                    result.approved = False
                    result.confidence_score = confidence
                    result.reasons.append(f"EMA Timing bloqueado para modo {mode_str} (score={ema_timing.get('score', 0):.2f})")
                    logger.warning(f"[QUALITY GATE] ❌ {symbol} rejeitado por EMA Timing ({mode_str})")
                    return result
            else:
                logger.info(f"[QUALITY GATE] ✅ {symbol} aprovado no EMA Timing")

        # === CRITÉRIO 8: DAILY TREND SHIFT ESPECIAL (NOVO) ===
        if ai_type == 'swing' and self._check_daily_shift_for_swing(decision, daily_trend_shift, ema_alignment_score, params, mode_str, symbol):
            # Trade já aprovado, apenas marca para gestão defensiva se RSI alto
            if allow_high_rsi_override and params.allow_high_rsi_on_daily_shift:
                result.adjustments['defensive_management'] = True
                result.warnings.append("Daily shift favorável com RSI elevado - gestão defensiva ativada")

        # === APROVADO ===
        result.approved = True
        result.confidence_score = confidence
        result.reasons.append(f"Sinal A+ aprovado com confidence={confidence:.2f}")
        
        if result.warnings:
            result.reasons.append(f"Com {len(result.warnings)} avisos")
        
        logger.info(f"[QUALITY GATE] ✅ {symbol} APROVADO: final_conf={confidence:.2f}")
        
        return result
    
    def _check_daily_shift_override(self, decision: Dict, daily_trend_shift: Optional[str], 
                                     ema_alignment_score: float, params: ModeQualityParams, 
                                     mode_str: str) -> bool:
        """
        Verifica se o daily trend shift pode fazer override de rejeição
        
        PATCH v2.0: Permite trades mesmo com confluências baixas se daily shift favorável
        """
        if not daily_trend_shift:
            return False
        
        if not params.allow_high_rsi_on_daily_shift:
            return False
        
        direction = decision.get('side', 'buy').lower()
        if direction == 'buy':
            direction = 'long'
        elif direction == 'sell':
            direction = 'short'
        
        # Verifica se daily shift está a favor
        is_daily_in_favor = (
            (direction == 'long' and daily_trend_shift == 'bull') or
            (direction == 'short' and daily_trend_shift == 'bear')
        )
        
        if is_daily_in_favor and ema_alignment_score >= 0.6:
            return True
        
        return False
    
    def _check_daily_shift_for_swing(self, decision: Dict, daily_trend_shift: Optional[str],
                                      ema_alignment_score: float, params: ModeQualityParams,
                                      mode_str: str, symbol: str) -> bool:
        """
        Verifica e loga quando trade é aceito por daily shift
        
        PATCH v2.0: Log especial quando daily EMA cross aprova o trade
        """
        if not daily_trend_shift:
            return False
        
        direction = decision.get('side', 'buy').lower()
        if direction == 'buy':
            direction = 'long'
        elif direction == 'sell':
            direction = 'short'
        
        is_daily_in_favor = (
            (direction == 'long' and daily_trend_shift == 'bull') or
            (direction == 'short' and daily_trend_shift == 'bear')
        )
        
        if is_daily_in_favor and ema_alignment_score >= 0.6:
            dir_str = "LONG" if direction == "long" else "SHORT"
            logger.info(
                f"[QUALITY GATE][DAILY_EMA] Swing {dir_str} em {symbol} aprovado com "
                f"daily {daily_trend_shift} shift recente e alignment_score={ema_alignment_score:.2f} (mode={mode_str})."
            )
            return True
        
        return False
    
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
        
        PATCH v2.0: Usa apenas 30m, 1h, 4h, 1d (não mais 5m/15m)
        """
        try:
            mode = self.mode_manager.current_mode.value if self.mode_manager else "BALANCED"
            proposed_direction = decision.get('side', 'long').lower()
            if proposed_direction == 'buy':
                proposed_direction = 'long'
            elif proposed_direction == 'sell':
                proposed_direction = 'short'
            
            # Recupera dados
            score = ema_timing.get('score', 0)
            states = ema_timing.get('states', {})
            
            # Helper para extrair dados seguros do estado
            def get_st(tf):
                st = states.get(tf)
                if not st: return None
                if isinstance(st, dict):
                    return st
                return {"trend": st}

            s1d = get_st('1d')
            s4h = get_st('4h')
            s1h = get_st('1h')
            s30m = get_st('30m')

            # --- CONSERVADOR ---
            if mode == "CONSERVADOR" or mode == "CONSERVATIVE":
                if score < 0.7: return False
                
                if proposed_direction == 'long':
                    if not (s4h and s4h.get('trend') == 'bull'): return False
                    if not (s1h and s1h.get('trend') == 'bull'): return False
                    if not (s30m and s30m.get('trend') == 'bull'): return False
                    
                    if s1h and s1h.get('is_overextended'): return False
                    if s30m and s30m.get('is_overextended'): return False

                else:
                    if not (s4h and s4h.get('trend') == 'bear'): return False
                    if not (s1h and s1h.get('trend') == 'bear'): return False
                    if not (s30m and s30m.get('trend') == 'bear'): return False
                    
                    if s1h and s1h.get('is_overextended'): return False
                    if s30m and s30m.get('is_overextended'): return False
                    
                return True

            # --- BALANCEADO ---
            elif mode == "BALANCEADO" or mode == "BALANCED":
                if score < 0.5: return False
                
                if proposed_direction == 'long':
                    if s1h and s1h.get('trend') == 'bear': return False
                    if s4h and s4h.get('trend') == 'bear': return False
                    has_trigger = (s30m and s30m.get('trend') == 'bull') or \
                                  (s1h and s1h.get('trend') == 'bull')
                    if not has_trigger: return False
                    
                else:
                    if s1h and s1h.get('trend') == 'bull': return False
                    if s4h and s4h.get('trend') == 'bull': return False
                    has_trigger = (s30m and s30m.get('trend') == 'bear') or \
                                  (s1h and s1h.get('trend') == 'bear')
                    if not has_trigger: return False
                
                return True

            # --- AGRESSIVO ---
            elif mode == "AGRESSIVO" or mode == "AGGRESSIVE":
                if proposed_direction == 'long':
                    if s1h and s1h.get('trend') == 'bear':
                         has_fresh = (s30m and s30m.get('is_fresh') and s30m.get('last_cross') == 'bull')
                         if not has_fresh: return False
                else:
                    if s1h and s1h.get('trend') == 'bull':
                         has_fresh = (s30m and s30m.get('is_fresh') and s30m.get('last_cross') == 'bear')
                         if not has_fresh: return False
                
                if score < 0.3: return False 
                return True
                
            return True
            
        except Exception as e:
            logger.error(f"[QUALITY GATE] Erro ao checar EMA timing: {e}")
            return True

    def log_rejection(self, symbol: str, result: QualityGateResult):
        """Loga rejeição de forma clara"""
        logger.warning(f"[QUALITY GATE] 🚫 {symbol} REJEITADO:")
        logger.warning(f"  Confidence: {result.confidence_score:.2f}")
        
        for reason in result.reasons:
            logger.warning(f"  • {reason}")
        
        for warning in result.warnings:
            logger.warning(f"  ⚠️  {warning}")
