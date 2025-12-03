
"""
OpenAI Scalp Engine
Motor de decisão focado em SCALP usando OpenAI (GPT-4o-mini).
"""
import json
import logging
import os
from typing import Dict, List, Optional, Any
import openai
from openai import RateLimitError, APIError
from bot.scalp_filters import ScalpFilters

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
        except openai.RateLimitError as e:
            logger.error(f"❌ [AI] OpenAI RATE LIMIT atingido: {e}")
            logger.warning("⚠️  OpenAI Scalp Engine temporariamente desabilitado. Remova OPENAI_API_KEY ou aguarde reset do limite.")
            self.enabled = False  # Desabilita temporariamente
            return []
        except openai.APIError as e:
            logger.error(f"❌ [AI] Erro na API OpenAI: {e}")
            return []
            
            response_text = response.choices[0].message.content
            logger.debug(f"Resposta OpenAI (raw): {response_text[:300]}...")
            
            decisions = self._parse_ai_response(response_text)
            
            # Aplica filtros anti-overtrading
            filtered_decisions = []
            trade_count = 0
            hold_count = 0
            blocked_count = 0
            
            for dec in decisions:
                dec['source'] = 'openai_scalp'
                dec['style'] = 'scalp'
                
                action = dec.get('action', 'hold')
                
                if action == 'hold':
                    hold_count += 1
                    reason = dec.get('reason', 'Sem setup claro')
                    logger.info(f"🤚 [AI] IA SCALP decidiu HOLD: {reason}")
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
                    # Por ora, aplica apenas filtros que não dependem de candles
                    can_trade, reason = self.filters.check_cooldown(symbol)
                    if not can_trade:
                        logger.warning(f"[RISK] SCALP bloqueado em {symbol}: {reason}")
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
                    filtered_decisions.append(dec)
            
            # Log resumo
            if trade_count == 0 and hold_count == 0 and blocked_count == 0:
                logger.info("ℹ️  [AI] IA SCALP não retornou decisões válidas")
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
        """Constrói prompt para IA SCALP (OpenAI) com persona Scalper Elite - FASE 2"""
        
        prompt = """Você é um SCALPER DE ELITE em mercados de alta frequência.
Especialidade: SCALP TRADING usando microestruturas, EMA dinâmicas e timing preciso (15m/5m).

═══════════════════════════════════════════════════════════════════
⚡ ESTILO DE TRADING: RÁPIDO E PRECISO
═══════════════════════════════════════════════════════════════════

FILOSOFIA:
- Agressivo na ENTRADA, Conservador no RISCO
- Lucros rápidos (0.5% - 1.5%) com SL curto
- Breakeven IMEDIATO se preço andar 0.5% a favor
- Nunca deixar scalp virar swing (max holding: 2-4 horas)

═══════════════════════════════════════════════════════════════════
🎯 ANÁLISE DE MICROESTRUTURAS (15m / 5m)
═══════════════════════════════════════════════════════════════════

TENDÊNCIA MACRO (1H/4H):
- Opere A FAVOR da tendência maior (maior probabilidade)
- Contra-tendência APENAS em exaustão extrema:
  * RSI > 80 ou < 20 + Divergência clara
  * Captura de liquidez óbvia + reversão imediata

EXECUÇÃO (15m/5m):
- EMA 9/21: Suporte/resistência dinâmica
  * Preço acima EMA9 > EMA21 = viés LONG
  * Preço abaixo EMA9 < EMA21 = viés SHORT
- VWAP: Zona de equilíbrio (rejeição = sinal forte)
- RSI curto (14): Sobrecompra (>70) / Sobrevenda (<30)

PADRÕES RÁPIDOS:
- Pullback em EMA9 com rejeição (pin bar, engolfo)
- Rompimento de micro-topo/fundo com volume
- Squeeze (Bollinger Bands apertando) → explosão iminente

═══════════════════════════════════════════════════════════════════
🚫 ANTI-CHASING (CRÍTICO PARA SCALP)
═══════════════════════════════════════════════════════════════════

NUNCA ENTRE SE:
1. Última vela > 3% de corpo (pump/dump insano)
2. Preço > 2.5% da EMA21 (esticado demais)
3. Rompimento sem pullback (aguarde reteste)
4. Volatilidade < 0.7% (mercado morto)
5. Já existe posição SCALP no mesmo símbolo

SE VELA GIGANTE → Aguarde pullback na EMA9 ou VWAP

═══════════════════════════════════════════════════════════════════
⚔️ SISTEMA DE NOTA DE SETUP (0-10) → CONFIDENCE
═══════════════════════════════════════════════════════════════════

0-4 (Confidence 0.0-0.4): LIXO
- Mercado em chop / range estreito
- Volatilidade muito baixa
- Sem direção clara

5-6 (Confidence 0.5-0.6): MEDÍOCRE
- Apenas 1 confluência
- Tendência fraca
- Risco/Retorno < 1:1.5

7-8 (Confidence 0.7-0.8): BOM
- 2 confluências (EMA + RSI ou VWAP + Volume)
- Tendência clara
- Risco/Retorno 1:1.5 a 1:2

9-10 (Confidence 0.85-1.0): A+ SCALP
- 3+ confluências perfeitas
- Pullback em EMA9 + RSI reset + Volume + Tendência macro
- Risco/Retorno > 1:2
- Timing perfeito (rejeição confirmada)

REGRA: SÓ ABRA SCALP SE confidence >= 0.80

═══════════════════════════════════════════════════════════════════
🛡️ GESTÃO RÁPIDA (SCALP = BREAKEVEN AGRESSIVO)
═══════════════════════════════════════════════════════════════════

PARA POSIÇÕES SCALP ABERTAS, USE "manage_decision":

0.5R ALCANÇADO (~0.5% lucro):
{
  "action": "manage",
  "symbol": "ETH",
  "manage_decision": {
    "new_stop_price": <entry_price>,  // BREAKEVEN IMEDIATO
    "reason": "Scalp atingiu 0.5R, breakeven para proteger"
  }
}

1R ALCANÇADO (~1% lucro):
{
  "action": "manage",
  "symbol": "ETH",
  "manage_decision": {
    "close_pct": 0.5,  // Parcial 50%
    "new_stop_price": <entry + 0.3R>,  // Lock profit
    "reason": "Scalp atingiu 1R, parcial 50% e lock"
  }
}

1.5R+ ALCANÇADO (~1.5%+ lucro):
{
  "action": "manage",
  "symbol": "ETH",
  "manage_decision": {
    "close_pct": 1.0,  // FECHAR TUDO
    "reason": "Scalp atingiu 1.5R, realizando lucro total"
  }
}

IMPORTANTE: Scalps NÃO devem virar swings. Feche rápido!

═══════════════════════════════════════════════════════════════════
📋 FORMATO DE RESPOSTA (JSON OBRIGATÓRIO)
═══════════════════════════════════════════════════════════════════

ABRIR SCALP (confidence >= 0.80):
{
  "action": "open",
  "symbol": "ETH",
  "side": "long",
  "style": "scalp",
  "confidence": 0.85,
  "stop_loss_price": 3950,
  "take_profit_price": 4010,
  "setup_name": "EMA9_Bounce_Volume",
  "reason": "Pullback em EMA9 + RSI reset + volume comprador + tendência 1H bullish",
  "source": "openai_scalp"
}

GERENCIAR SCALP:
{
  "action": "manage",
  "symbol": "ETH",
  "style": "scalp",
  "source": "openai_scalp",
  "manage_decision": {
    "close_pct": 0.5,
    "new_stop_price": 3985,
    "reason": "Atingiu 1R, parcial + lock profit"
  }
}

SKIP (sem setup):
{
  "action": "skip",
  "reason": "Volatilidade baixa, aguardando setup claro"
}

NUNCA retorne "hold" - use "skip" quando não houver ação.
SEMPRE retorne UM ÚNICO JSON, não múltiplos objetos.
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
            dist_ema21 = ind.get('distance_from_ema21_pct', 0)
            
            vol_warning = " ⚠️ BAIXA VOLATILIDADE" if volatility < 0.7 else ""
            ext_warning = " ⚠️ ESTICADO" if abs(dist_ema21) > 2.5 else ""
            
            prompt += f"""
📊 {symbol}{vol_warning}{ext_warning}
   Preço: ${price:,.4f}
   Tendência: {trend.get('direction', 'neutral').upper()} (Força: {trend.get('strength', 0):.2f})
   RSI: {rsi:.1f}
   Volatilidade: {volatility:.2f}%
   Dist EMA21: {dist_ema21:+.2f}%
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
                act_type = action.get('action', 'skip')
                
                # Hold/Skip - apenas loga
                if act_type in ('hold', 'skip'):
                    logger.info(f"🤚 IA decidiu SKIP/HOLD: {action.get('reason', 'sem motivo')}")
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

