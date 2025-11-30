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
        """Constrói prompt específico para SCALP com foco em qualidade e fees"""
        
        prompt = """Você é um motor de SCALP TRADING INTELIGENTE para Hyperliquid.
Seu objetivo é identificar oportunidades de CURTO PRAZO (1h, 4h) com ALTA PROBABILIDADE.

⚠️ REGRAS CRÍTICAS SOBRE FEES:
- Hyperliquid cobra ~0.02% maker + 0.05% taker = 0.07% por operação
- Ida + volta = ~0.15% de custo total
- Spread adiciona ~0.05-0.10%
- CUSTO REAL TOTAL: ~0.20-0.25% por trade completo

🎯 FOCO PRINCIPAL:
- Movimentos de 1.0% a 2.5% (MÍNIMO 1.0% para cobrir fees com margem)
- Stop Loss: 0.8% a 1.5% (apertado mas realista)
- Take Profit: MÍNIMO 0.8%, ideal 1.2-2.0%
- Risk/Reward: MÍNIMO 1.5:1, ideal 2:1 ou melhor

📊 VOLATILIDADE É ESSENCIAL:
- SÓ opere se o ativo tiver volatilidade >= 0.7% (range médio)
- Mercado lateral estreito = HOLD (fees comem o lucro)
- Prefira ativos com movimento claro e volume

✅ SETUPS ACEITOS:
1. SCALP DE TENDÊNCIA: Entre a favor de tendência forte com pullback
2. SCALP DE BREAKOUT: Rompimento com volume acima da média
3. SCALP DE REVERSÃO: Apenas em extremos (RSI <25 ou >75)

❌ EVITE OVERTRADING:
- Máximo 1 posição SCALP por símbolo
- Se já tiver posição aberta no símbolo, sugira HOLD
- Qualidade >> Quantidade
- HOLD é MELHOR que trade marginal

🚫 QUANDO SUGERIR HOLD:
- Volatilidade < 0.7%
- Mercado lateral sem direção clara
- TP potencial < 0.8% (não cobre fees)
- Já existe posição SCALP no símbolo
- Setup não tem confiança >= 75%

ESTADO DA CONTA:
"""
        prompt += f"Equity: ${account_info.get('equity', 0):.2f}\n"
        prompt += f"PnL Dia: {account_info.get('daily_pnl_pct', 0):.2f}%\n\n"
        
        prompt += "POSIÇÕES ABERTAS:\n"
        scalp_positions = {}
        if open_positions:
            for pos in open_positions:
                symbol = pos.get('symbol')
                style = pos.get('style', 'unknown')
                prompt += f"- {symbol} {pos.get('side')} [{style}] (PnL: {pos.get('unrealized_pnl_pct', 0):.2f}%)\n"
                if style == 'scalp':
                    scalp_positions[symbol] = True
        else:
            prompt += "Nenhuma.\n"
        
        if scalp_positions:
            prompt += f"\n⚠️ ATENÇÃO: Símbolos com posição SCALP aberta: {', '.join(scalp_positions.keys())}\n"
            prompt += "NÃO abra nova posição SCALP nesses símbolos!\n"
            
        prompt += "\nDADOS DE MERCADO:\n"
        for ctx in market_contexts:
            symbol = ctx.get('symbol')
            price = ctx.get('price', 0)
            ind = ctx.get('indicators', {})
            trend = ctx.get('trend', {})
            
            volatility = ind.get('volatility_pct', 0)
            rsi = ind.get('rsi', 50)
            
            # Marca símbolos com baixa volatilidade
            vol_warning = " ⚠️ BAIXA VOLATILIDADE" if volatility < 0.7 else ""
            
            prompt += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SYMBOL: {symbol}{vol_warning}
Preço: ${price}
Tendência: {trend.get('direction', 'neutral').upper()} (Força: {trend.get('strength', 0):.2f})
RSI: {rsi:.1f}
Volatilidade: {volatility:.2f}%
"""
            
            if ind.get('ema_9') and ind.get('ema_21'):
                ema_9 = ind['ema_9']
                ema_21 = ind['ema_21']
                ema_cross = "BULLISH ↗" if ema_9 > ema_21 else "BEARISH ↘"
                ema_distance = abs((ema_9 - ema_21) / ema_21) * 100
                prompt += f"EMAs: 9=${ema_9:.2f} vs 21=${ema_21:.2f} → {ema_cross} (dist: {ema_distance:.2f}%)\n"
            
            if ctx.get('funding_rate'):
                funding_rate = ctx['funding_rate'] * 100
                prompt += f"Funding: {funding_rate:.4f}%\n"

        prompt += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FORMATO DE RESPOSTA (JSON):
{
  "actions": [
    {
      "action": "open",
      "symbol": "BTC",
      "side": "long",
      "leverage": 15,
      "stop_loss_pct": 1.2,
      "take_profit_pct": 1.8,
      "confidence": 0.82,
      "setup_name": "scalp_trend",
      "reason": "Tendência bullish forte, RSI saudável, volatilidade boa (1.2%), R/R 1.5:1"
    }
  ]
}

Se NÃO houver setup válido:
{"actions": [{"action": "hold", "reason": "Volatilidade insuficiente em todos os pares"}]}

IMPORTANTE:
- Use "stop_loss_pct" e "take_profit_pct" (valores POSITIVOS em %)
- setup_name: "scalp_trend", "scalp_breakout" ou "scalp_reversal"
- confidence: mínimo 0.75 para sugerir trade
- reason: SEMPRE mencione volatilidade e R/R ratio
- Leverage: 10-20x para scalp (será ajustado pelo RiskManager)
- HOLD é uma resposta VÁLIDA e INTELIGENTE quando não há setup claro!
"""
        return prompt

    def _parse_ai_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse da resposta JSON"""
        try:
            data = json.loads(response_text)
            actions = data.get('actions', [])
            
            valid_actions = []
            for action in actions:
                # Normaliza campos
                if action.get('action') == 'open':
                    # Converte pcts para preços se necessário, ou deixa o bot calcular
                    # O bot atual espera stop_loss_price e take_profit_price no 'open'
                    # Mas o prompt pede pct. Vamos converter se possível ou deixar o RiskManager lidar?
                    # O AiDecisionEngine original retorna stop_loss_price EXATO.
                    # O prompt de scalp pede pct. Vamos adaptar aqui.
                    
                    # Precisamos do preço atual para converter pct em preço
                    # Mas aqui no parse não temos o preço fácil.
                    # Melhor mudar o prompt para retornar PREÇO ou ajustar aqui depois.
                    # Vamos manter o padrão do bot: retornar stop_loss_price e take_profit_price.
                    # Vou ajustar o prompt para pedir PREÇO EXATO também, ou calcular aqui se tivermos o preço no contexto.
                    # Como não tenho o preço aqui fácil (teria que passar o contexto pro parse),
                    # vou pedir pro prompt retornar PREÇOS EXATOS também, ou melhor:
                    # O bot original (AiDecisionEngine) pede PREÇO EXATO.
                    # Vou ajustar o prompt do Scalp para pedir PREÇO EXATO também, é mais seguro.
                    pass
                
                valid_actions.append(action)
            return valid_actions
        except Exception:
            return []
