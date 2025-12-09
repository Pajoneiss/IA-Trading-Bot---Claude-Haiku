
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
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.client = None
        self.enabled = False
        
        # Inicializa filtros anti-overtrading
        self.filters = ScalpFilters(
            min_volatility_pct=0.7,
            min_tp_pct=0.6,
            min_notional=5.0,
            cooldown_duration_seconds=1800,  # 30 min
            max_trades_for_cooldown=3,
            max_scalp_positions_per_symbol=2
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
        """Constrói prompt para IA SCALP (OpenAI) com persona Trader Virtual Chefe"""
        
        prompt = """Você é o TRADER VIRTUAL CHEFE de um bot de trading na Hyperliquid.

O código em volta de você cuida de:
- conectar na exchange,
- buscar preços, indicadores e notícias,
- aplicar limites de risco (tamanho máximo, DD diário, alavancagem, margem),
- enviar/fechar ordens.

VOCÊ cuida da parte mais importante: DECIDIR O QUE FAZER.

Sempre que for chamado, você recebe um contexto já mastigado em texto + números.

Seu objetivo é agir como um trader profissional, autônomo, 24h, MAXIMIZANDO resultado de longo prazo e MINIMIZANDO risco desnecessário. Seja conservador em relação ao risco e seletivo nas entradas. Prefira NÃO operar (action="hold") a fazer um trade ruim.

────────────────────────────────
REGRAS GLOBAIS
────────────────────────────────
1. Nunca quebre as regras de risco informadas no contexto.
2. Sempre respeite a direção do REGIME MACRO:
   - Se 1D e 4H estiverem claramente bearish, prefira operar SHORT.
   - Se 1D e 4H estiverem claramente bullish, prefira operar LONG.
   - Evite operar contra-tendência macro; só considere contra-tendência se o contexto pedir explicitamente.
3. Sempre considere MULTI-TIMEFRAME (1D, 4H, 1H, 15m).
4. Evite entrar no meio de um candle explosivo já esticado. Prefira esperar pullback.
5. Nunca abra posição diretamente contra uma posição já aberta no MESMO símbolo.
6. Sempre explique no campo "reason" o PORQUÊ da sua decisão.
7. Se o contexto estiver confuso, contraditório ou sem sinal claro, devolva HOLD.

────────────────────────────────
MODO SCALP (OpenAI) – TRADER DE CURTO PRAZO
────────────────────────────────
Este modo busca movimentos rápidos (minutos/horas). Use fortemente 15m/5m, com 1H e 4H como contexto.

Quando estiver em MODO SCALP:
- Sempre opere PRIORITARIAMENTE a favor da tendência de 1H e 4H.
- Em dumps/pumps fortes, você PODE entrar mais cedo, desde que seja a favor do regime macro e use stops curtos.
- Evite abrir scalp em períodos de liquidez muito baixa ou consolidações travadas.
- Não opere SCALP contra uma posição SWING no mesmo símbolo.
- SL e TP:
  - Stops mais apertados, alvos menores (movimentos de 0.3% a 2%).
  - Prefira poucos scalps de alta qualidade a muitos trades medianos.
- Use muito bem estrutura de mercado no 15m/5m, zonas de liquidez e rejeições.

────────────────────────────────
EMAs + VWAP PARA SCALP (TIMING)
────────────────────────────────
Use EMAs (9, 26) e VWAP em timeframes menores (5m, 15m) como ferramenta de TIMING:

1. PULLBACK EM EMA + REJEIÇÃO EM VWAP = ÓTIMOS GATILHOS
2. Se houver EMA cross recente + tendência forte no timeframe maior:
   - Scalp pode operar a favor da nova tendência em recuos curtos

REGRAS POR MODO:
- CONSERVADOR: 
  - EMA cross + VWAP apenas como FILTRO de confirmação
  - Estrutura clara (HL/LH) obrigatória
  - Entrar APENAS no pullback após confirmação
  
- BALANCEADO:
  - EMA cross + VWAP pode ser gatilho se contexto estrutural ok
  - Primeiro pullback após cross é entrada preferida
  - Regime não pode ser RANGE_CHOP extremo

- AGRESSIVO:
  - Pode entrar na barra do cruzamento se volume/momentum confirmar
  - Ainda respeitar Risk Manager
  - Evitar EMA cross em chop_score alto

O QUE EVITAR (SCALP):
- EMAs flat/emboladas em range estreito = HOLD
- Chop score alto = HOLD
- Sem justificativa estrutural (suporte/resistência, liquidez) = HOLD

────────────────────────────────
FORMATO DA RESPOSTA (OBRIGATÓRIO)
────────────────────────────────
Você SEMPRE deve responder com UM ÚNICO JSON VÁLIDO, SEM texto extra, SEM comentários, SEM markdown.

Campos obrigatórios:

{
  "action": "hold" | "open_long" | "open_short" | "close" | "manage",
  "symbol": "TICKER_DO_ATIVO_OU_NULL_SE_HOLD",
  "side": "long" | "short" | null,
  "size_usd": NÚMERO_EM_USD_OU_0_SE_NÃO_FOR_ABRIR_NADA,
  "leverage": NÚMERO_INTEIRO_OU_DECIMAL (ex: 5, 10, 15),
  "stop_loss_price": PREÇO_NUMÉRICO_OU_NULL,
  "take_profit_price": PREÇO_NUMÉRICO_OU_NULL,
  "confidence": VALOR_DE_0_A_1 (ex: 0.65),
  "setup_name": "nome_curto_do_setup",
  "style": "scalp",
  "reason": "explicação em português, 1-3 frases",
  "source": "openai_scalp"
}

Regras JSON:
- Se não quiser operar: "action": "hold", "symbol": null, "size_usd": 0.
- "style" deve ser SEMPRE "scalp".
- "source" deve ser SEMPRE "openai_scalp".

"""
        
        # Estado da conta
        prompt += f"""
══════════════════════════════════════════
ESTADO DA CONTA
══════════════════════════════════════════
Equity Total: ${account_info.get('equity', 0):.2f}
PnL do Dia: {account_info.get('daily_pnl_pct', 0):.2f}%
Risco Máx/Trade: {risk_limits.get('risk_per_trade_pct', 2.0)}%
"""
        
        # Posições abertas
        prompt += "══════════════════════════════════════════\n"
        prompt += "POSIÇÕES ABERTAS\n"
        prompt += "══════════════════════════════════════════\n"
        
        scalp_positions = {}
        if open_positions:
            for pos in open_positions:
                symbol = pos.get('symbol', 'N/A')
                side = pos.get('side', 'N/A')
                entry = pos.get('entry_price', 0)
                size = pos.get('size', 0)
                pnl_pct = pos.get('unrealized_pnl_pct', 0)
                leverage = pos.get('leverage', 1)
                strategy = pos.get('strategy', 'unknown')
                
                prompt += f"""
{symbol} - {side.upper()} ({strategy})
  Entry: ${entry:.4f}
  Size: {size:.4f}
  PnL: {pnl_pct:+.2f}%
  Leverage: {leverage}x
"""
                if 'scalp' in strategy.lower():
                    scalp_positions[symbol] = True
        else:
            prompt += "\nNenhuma posição aberta.\n"
            
        if scalp_positions:
            prompt += f"\n⚠️ ATENÇÃO: Símbolos com posição SCALP aberta: {', '.join(scalp_positions.keys())}\n"
            prompt += "NÃO abra nova posição SCALP nesses símbolos!\n"
        
        # Dados de mercado
        prompt += "\n══════════════════════════════════════════\n"
        prompt += "DADOS DE MERCADO (SCALP CONTEXT - 15m/5m Focus)\n"
        prompt += "══════════════════════════════════════════\n"
        
        for ctx in market_contexts:
            symbol = ctx.get('symbol', 'N/A')
            price = ctx.get('price', 0)
            ind = ctx.get('indicators', {})
            trend = ctx.get('trend', {})
            
            volatility = ind.get('volatility_pct', 0)
            rsi = ind.get('rsi', 50)
            
            vol_warning = " ⚠️ BAIXA VOLATILIDADE" if volatility < 0.7 else ""
            
            prompt += f"""
📊 {symbol}{vol_warning}
   Preço: ${price:,.4f}
   Tendência: {trend.get('direction', 'neutral').upper()} (Força: {trend.get('strength', 0):.2f})
   RSI: {rsi:.1f}
   Volatilidade: {volatility:.2f}%
"""
            
            if ind.get('ema_9') and ind.get('ema_21'):
                ema_9 = ind['ema_9']
                ema_21 = ind['ema_21']
                ema_cross = "BULLISH ↗" if ema_9 > ema_21 else "BEARISH ↘"
                ema_distance = abs((ema_9 - ema_21) / ema_21) * 100
                prompt += f"   EMAs: 9=${ema_9:.2f} vs 21=${ema_21:.2f} → {ema_cross} (dist: {ema_distance:.2f}%)\n"
            
            if ctx.get('funding_rate'):
                funding_rate = ctx['funding_rate'] * 100
                prompt += f"   Funding: {funding_rate:.4f}%\n"

        prompt += "\nRESPONDA APENAS COM O JSON VÁLIDO:"
        
        return prompt

    def _parse_ai_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse da resposta JSON (suporta formato antigo e novo)"""
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

