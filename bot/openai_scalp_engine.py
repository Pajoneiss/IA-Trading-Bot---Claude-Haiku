
"""
OpenAI Scalp Engine
Motor de decisão focado em SCALP usando OpenAI (GPT-4o-mini).
"""
import json
import logging
import os
from typing import Dict, List, Optional, Any
import openai
from bot.scalp_filters import ScalpFilters
from bot.ai_decision_logger import get_decision_logger

logger = logging.getLogger(__name__)


class OpenAiScalpEngine:
    """Motor de decisão IA focado em SCALP usando OpenAI"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini", mode_manager: Any = None):
        self.api_key = api_key
        self.model = model
        self.client = None
        self.enabled = False
        self.mode_manager = mode_manager
        
        # Obtém limites do modo se disponível, senão usa defaults
        daily_limit = 4
        if self.mode_manager:
            daily_limit = self.mode_manager.get_max_trades_scalp()
            
        # Inicializa filtros anti-overtrading
        self.filters = ScalpFilters(
            min_volatility_pct=0.7,
            min_tp_pct=0.6,
            min_notional=5.0,
            cooldown_duration_seconds=1800,  # 30 min
            max_trades_for_cooldown=3,
            max_scalp_positions_per_symbol=2,
            max_scalp_trades_per_day=daily_limit
        )
        
        if api_key:
            try:
                self.client = openai.OpenAI(api_key=api_key)
                self.enabled = True
                logger.info(f"✅ OpenAI Scalp Engine ativado com modelo: {model}")
            except Exception as e:
                logger.error(f"Erro ao inicializar OpenAI client: {e}")
        else:
            logger.warning("⚠️  OPENAI_API_KEY não configurada - Scalp Engine desativado")
    
    def get_scalp_decision(self, 
                           market_contexts: List[Dict[str, Any]],
                           account_info: Dict[str, Any],
                           open_positions: List[Dict[str, Any]],
                           risk_limits: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Gera decisões de SCALP.
        Retorna lista de decisões compatível com TradeDecision.
        """
        if not self.enabled or not self.client:
            return []
            
        prompt = self._build_scalp_prompt(market_contexts, account_info, open_positions, risk_limits)
        
        try:
            logger.debug("Consultando OpenAI (Scalp)...")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Você é um trader especialista em SCALP na Hyperliquid."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            response_text = response.choices[0].message.content
            logger.debug(f"Resposta OpenAI (raw): {response_text[:300]}...")
            
            decisions = self._parse_ai_response(response_text)
            
            # Aplica filtros anti-overtrading
            filtered_decisions = []
            trade_count = 0
            hold_count = 0
            blocked_count = 0
            
            # Logger para diagnóstico
            decision_logger = get_decision_logger()
            
            for dec in decisions:
                dec['source'] = 'openai_scalp'
                dec['style'] = 'scalp'
                
                action = dec.get('action', 'hold')
                
                if action == 'hold':
                    hold_count += 1
                    reason = dec.get('reason', 'Sem setup claro')
                    logger.info(f"🤚 [AI] IA SCALP decidiu HOLD: {reason}")
                    decision_logger.log_scalp_decision(
                        symbol=dec.get('symbol'),
                        decision_data=dec,
                        rejected=False
                    )
                    filtered_decisions.append(dec)
                    
                elif action == 'open':
                    symbol = dec.get('symbol', 'UNKNOWN')
                    
                    # Busca candles do símbolo para filtro de volatilidade
                    candles = []
                    for ctx in market_contexts:
                        if ctx.get('symbol') == symbol:
                            # Precisamos dos candles originais, não só do contexto
                            # Vamos assumir que o bot passa candles no contexto ou pular esse filtro
                            # Por ora, vamos aplicar os outros filtros
                            break
                    
                    # Aplica filtros (sem candles por enquanto, será passado pelo bot)
                    
                    # Filtro 0: Limite diário de trades SCALP
                    can_trade, reason = self.filters.check_daily_limit()
                    if not can_trade:
                        logger.warning(f"[RISK] SCALP bloqueado: {reason}")
                        decision_logger.log_scalp_decision(
                            symbol=symbol,
                            decision_data=dec,
                            rejected=True,
                            rejection_reason=reason,
                            rejected_by="daily_limit_filter"
                        )
                        blocked_count += 1
                        filtered_decisions.append({
                            'action': 'hold',
                            'reason': f"Filtro SCALP: {reason}",
                            'source': 'openai_scalp',
                            'style': 'scalp'
                        })
                        continue
                    
                    # Filtro 0.5: Losing streak cooldown
                    can_trade, reason = self.filters.check_losing_streak()
                    if not can_trade:
                        logger.warning(f"[RISK] SCALP bloqueado: {reason}")
                        decision_logger.log_scalp_decision(
                            symbol=symbol,
                            decision_data=dec,
                            rejected=True,
                            rejection_reason=reason,
                            rejected_by="losing_streak_filter"
                        )
                        blocked_count += 1
                        filtered_decisions.append({
                            'action': 'hold',
                            'reason': f"Filtro SCALP: {reason}",
                            'source': 'openai_scalp',
                            'style': 'scalp'
                        })
                        continue
                    
                    # Filtro 1: Cooldown por símbolo
                    can_trade, reason = self.filters.check_cooldown(symbol)
                    if not can_trade:
                        logger.warning(f"[RISK] SCALP bloqueado em {symbol}: {reason}")
                        decision_logger.log_scalp_decision(
                            symbol=symbol,
                            decision_data=dec,
                            rejected=True,
                            rejection_reason=reason,
                            rejected_by="cooldown_filter"
                        )
                        blocked_count += 1
                        # Converte para HOLD
                        filtered_decisions.append({
                            'action': 'hold',
                            'reason': f"Filtro SCALP: {reason}",
                            'source': 'openai_scalp',
                            'style': 'scalp'
                        })
                        continue

                    
                    can_trade, reason = self.filters.check_position_limit(symbol, open_positions)
                    if not can_trade:
                        logger.warning(f"[RISK] SCALP bloqueado em {symbol}: {reason}")
                        decision_logger.log_scalp_decision(
                            symbol=symbol,
                            decision_data=dec,
                            rejected=True,
                            rejection_reason=reason,
                            rejected_by="position_limit_filter"
                        )
                        blocked_count += 1
                        filtered_decisions.append({
                            'action': 'hold',
                            'reason': f"Filtro SCALP: {reason}",
                            'source': 'openai_scalp',
                            'style': 'scalp'
                        })
                        continue
                    
                    # Filtro de TP/SL
                    tp_pct = dec.get('take_profit_pct')
                    sl_pct = dec.get('stop_loss_pct')
                    
                    if tp_pct and sl_pct:
                        can_trade, reason = self.filters.check_fee_viability(
                            abs(float(tp_pct)), 
                            abs(float(sl_pct)), 
                            symbol
                        )
                        if not can_trade:
                            logger.warning(f"[RISK] SCALP bloqueado em {symbol}: {reason}")
                            decision_logger.log_scalp_decision(
                                symbol=symbol,
                                decision_data=dec,
                                rejected=True,
                                rejection_reason=reason,
                                rejected_by="fee_viability_filter"
                            )
                            blocked_count += 1
                            filtered_decisions.append({
                                'action': 'hold',
                                'reason': f"Filtro SCALP: {reason}",
                                'source': 'openai_scalp',
                                'style': 'scalp'
                            })
                            continue
                    
                    # Se passou pelos filtros, aprova
                    trade_count += 1
                    side = dec.get('side', '').upper()
                    leverage = dec.get('leverage', 0)
                    confidence = dec.get('confidence', 0)
                    
                    logger.info(
                        f"📊 [AI] IA SCALP decidiu TRADE: provider=openai style=scalp "
                        f"action=OPEN_{side} symbol={symbol} leverage={leverage}x "
                        f"tp={tp_pct}% sl={sl_pct}% confidence={confidence:.2f}"
                    )
                    decision_logger.log_scalp_decision(
                        symbol=symbol,
                        decision_data=dec,
                        rejected=False
                    )
                    filtered_decisions.append(dec)
            
            # Log resumo
            if trade_count == 0 and hold_count == 0 and blocked_count == 0:
                logger.info("ℹ️  [AI] IA SCALP não retornou decisões válidas")
                decision_logger.log_decision(
                    decision_type="SCALP",
                    symbol=None,
                    action="no_decision",
                    raw_reason="IA não retornou decisões válidas"
                )
            else:
                logger.info(
                    f"✅ [AI] IA SCALP: {trade_count} trade(s) aprovado(s), "
                    f"{hold_count} hold(s), {blocked_count} bloqueado(s) por filtros"
                )
            
            return filtered_decisions
            

        except Exception as e:
            logger.error(f"❌ [AI] Erro ao consultar IA SCALP (OpenAI): {e}", exc_info=True)
            return []

    def _build_scalp_prompt(self,
                            market_contexts: List[Dict[str, Any]],
                            account_info: Dict[str, Any],
                            open_positions: List[Dict[str, Any]],
                            risk_limits: Dict[str, Any]) -> str:
        """Constrói prompt para IA SCALP (OpenAI) com persona Trader Scalper Agressivo/Inteligente"""
        
        prompt = \"\"\"Você é o TRADER SCALPER CHEFE na Hyperliquid.
Sua missão: GERAR CAPITAL DE GIRO rápido com trades curtos (5m/15m).

═══════════════════════════════════════════════════════
🚀 FILOSOFIA: AÇÃO INTELIGENTE
═══════════════════════════════════════════════════════

1. NAO SEJA MEDROSO. Se o setup técnico existe, OPERE.
2. TIMING É TUDO: Use EMAs (9/21) e VWAP para entrar no momento exato (pullback ou rompimento com volume).
3. MULTI-ATIVO:
   - Se já existe Swing em ZEC, você PODE e DEVE operar Scalp em ETH ou BTC.
   - Não concentre risco abrindo Scalp + Swing no MESMO par na MESMA direção se já estiver pesado.
   - Mas operar pares diferentes é encorajado para diversificar.

═══════════════════════════════════════════════════════
📊 REGRAS TÉCNICAS (EMAs + VWAP)
═══════════════════════════════════════════════════════

TREND FOLLOWING (Setup A+):
- Preço acima da VWAP e EMA 21.
- Correção (Pullback) até a EMA 9 ou 21.
- Candle de rejeição/força a favor da tendência.
- GATILHO: Rompimento da máxima desse candle.

REVERSÃO / COUNTER-TREND (Setup B - Modo Agessivo):
- Preço esticado longe das médias (sobrecompra/sovenda RSI).
- Divergência de RSI.
- Perda da EMA 9 com força.
- Alvo: Mínimo até a EMA 21 ou VWAP.

═══════════════════════════════════════════════════════
🎚️ COMPORTAMENTO POR MODO
═══════════════════════════════════════════════════════

MODO CONSERVADOR:
- Só opera a favor da tendência macro (1H/4H).
- Exige toque na EMA/VWAP (pullback perfeito).
- Alvos curtos (1:1 ou 1:1.5).

MODO BALANCEADO:
- Aceita setup de reversão se houver falha de topo/fundo clara.
- Pode entrar no rompimento de bandeira/pivô.
- RR mínimo 1.5:1.

MODO AGRESSIVO:
- PODE ANTECIPAR: Entrar na barra de força que cruza as médias.
- Aceita maior frequência de trades.
- Aceita setups com RR 1:1 se a probabilidade for alta.
- RSI extremo não impede entrada se o Price Action confirmar continuação (Barra de exaustão vs Barra de força).

═══════════════════════════════════════════════════════
📝 FORMATO DA RESPOSTA (JSON OBRIGATÓRIO)
═══════════════════════════════════════════════════════

Responda APENAS com este JSON.

{
  "action": "hold" | "open_long" | "open_short",
  "symbol": "TICKER",
  "side": "long" | "short",
  "setup_name": "pullback_ema" | "vwap_reject" | "breakout",
  "entry_price": preco_atual,
  "stop_loss_price": PRECO_OBRIGATORIO,
  "take_profit_price": PRECO_ALVO,
  "confidence": 0.0 a 1.0 (Agressivo aceita > 0.60),
  "leverage": 5 a 20,
  "reason": "Explique o timing (ex: toque na ema21, rompimento vwap)"
}

Se não for operar: {"action": "hold", "reason": "..."}

IMPORTANTE:
- O Risk Manager calcula o tamanho da posição. Você foca na QUALIDADE da entrada e no STOP.
- NUNCA abra sem stop loss definido.
\"\"\"
        
        # Estado Da Conta
        prompt += f"\\n📊 CONTA:\\nEquity: ${account_info.get('equity', 0):.2f} | Risco/Trade Limite: {risk_limits.get('risk_per_trade_pct', 1.0)}%\\n"
        
        # Posições
        prompt += f"Posições Abertas: {len(open_positions)} (Veja abaixo para não duplicar no mesmo par, mas OUTROS pares estão OK)\\n"
        if open_positions:
            for p in open_positions:
                prompt += f"- {p.get('symbol')} ({p.get('side')}): PnL {p.get('pnl_pct', 0):.2f}%\\n"

        # Dados de Mercado
        prompt += "\\n🔎 MERCADO (15m/5m):\\n"
        for ctx in market_contexts:
            symbol = ctx.get('symbol')
            # Pular se já tem posição SCALP nesse símbolo (bot filtra, mas bom reforçar)
            # Mas SWING no mesmo símbolo permite SCALP se a direção alinhar ou for hedge (hedge não implementado agora, então evitar contra)
            
            price = ctx.get('price', 0)
            inds = ctx.get('indicators', {})
            ema9 = inds.get('ema_9', 0)
            ema21 = inds.get('ema_21', 0)
            rsi = inds.get('rsi', 50)
            vol = inds.get('volatility_pct', 0)
            
            # Formata info técnica rápida
            trend_signal = "NEUTRO"
            if ema9 > ema21: trend_signal = "BULLISH (EMAs alinhadas)"
            if ema9 < ema21: trend_signal = "BEARISH (EMAs alinhadas)"
            
            prompt += f"=== {symbol} (${price:.4f}) ===\\n"
            prompt += f"Trend: {trend_signal}\\n"
            prompt += f"Indicadores: EMA9={ema9:.4f}, EMA21={ema21:.4f}, RSI={rsi:.1f}, Vol={vol:.2f}%\\n"
            prompt += f"Contexto: {ctx.get('trend', {}).get('direction', 'neutral').upper()}\\n"
            
            if ctx.get('funding_rate'):
                funding_rate = ctx['funding_rate'] * 100
                prompt += f"   Funding: {funding_rate:.4f}%\\n"

        return prompt

    def _parse_ai_response(self, response_text: str) -> List[Dict[str, Any]]:
        \"\"\"Parse da resposta JSON (suporta formato antigo e novo)\"\"\"
        try:
            # Limpa markdown
            text = response_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            data = json.loads(text)
            
            # Normaliza para lista de ações
            actions = []
            if isinstance(data, list):
                actions = data
            elif isinstance(data, dict):
                if 'actions' in data:
                    actions = data['actions']
                else:
                    # Formato novo: objeto único
                    actions = [data]
            
            valid_actions = []
            for action in actions:
                act_type = action.get('action', 'hold')
                
                # Hold - apenas loga
                if act_type == 'hold':
                    logger.info(f"🤚 IA decidiu HOLD: {action.get('reason', 'sem motivo')}")
                    # Mantém o hold para contagem de estatísticas
                    valid_actions.append(action)
                    continue
                
                # Open - valida campos obrigatórios
                if act_type in ('open', 'open_long', 'open_short'):
                    # Normaliza action para 'open' e define side se vier no action
                    if act_type == 'open_long':
                        action['action'] = 'open'
                        action['side'] = 'long'
                    elif act_type == 'open_short':
                        action['action'] = 'open'
                        action['side'] = 'short'
                        
                    if not all([
                        action.get('symbol'),
                        action.get('side'),
                        # Scalp pode não ter size_usd definido se for calculado por risco
                        # Mas o prompt pede size_usd ou 0. Vamos aceitar se tiver leverage.
                    ]):
                        logger.warning(f"Ação 'open' incompleta, ignorando: {action}")
                        continue
                    
                    # Defaults para campos opcionais
                    if not action.get('leverage'):
                        action['leverage'] = 10 # Default maior para scalp
                    
                    # Garante limites
                    action['leverage'] = max(1, min(50, int(float(action['leverage']))))
                    
                    valid_actions.append(action)
                
                # Close/Manage
                elif act_type in ('close', 'manage'):
                    if not action.get('symbol'):
                        continue
                    valid_actions.append(action)
            
            return valid_actions
            
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao fazer parse do JSON da IA: {e}")
            logger.debug(f"Resposta problemática: {response_text[:500]}")
            return []
        except Exception as e:
            logger.error(f"Erro inesperado ao processar resposta IA: {e}")
            return []
