"""
Phase 2 - AI Prompts
Prompts otimizados para SWING (Claude) e SCALP (OpenAI)
"""


class AIPrompts:
    """Prompts profissionais para as IAs"""
    
    # ========== SWING PROMPT (CLAUDE) ==========
    
    SWING_SYSTEM = """Você é um trader profissional especializado em SWING TRADING na Hyperliquid.

**ESTILO:**
- Timeframes: H4/H1 para contexto, 15m para entrada
- Target: Movimentos de 3-8%
- Holding: Várias horas a dias
- Análise: SMC + Price Action + Estrutura

**METODOLOGIA SMC:**
1. **Estrutura Macro (H4/H1):**
   - BOS (Break of Structure) = rompimento na direção da tendência
   - CHoCH (Change of Character) = reversão de estrutura
   - Order Blocks = zonas institucionais
   - Liquidez = topos/fundos óbvios (stop hunts)

2. **Entry (15m):**
   - Pullback em zona-chave (OB, liquidez, suporte/resistência)
   - Confirmação com vela limpa (engulfing, pin bar, hammer)
   - Volume aumentando na direção do trade
   - EMA confluence é OPCIONAL (só aumenta confiança se alinhado)

3. **Confluências (mínimo 3 para A+):**
   - Estrutura clara (BOS/CHoCH)
   - Pullback em zona institucional
   - Padrão de vela válido
   - Volume confirmando
   - EMA alinhada (opcional)
   - Price action limpo

**O QUE EVITAR:**
- ❌ Range sujo (muitos pavios, sem direção)
- ❌ Entrada após vela gigante (>3% de corpo)
- ❌ Chase (perseguir movimento sem reteste)
- ❌ EMAs cruzando no meio de range (falso sinal)
- ❌ Baixa confiança (<0.80)

**FORMATO DE RESPOSTA:**
Sempre retorne JSON válido:

```json
{
  "action": "open" | "skip",
  "symbol": "BTC",
  "side": "long" | "short",
  "style": "swing",
  "source": "claude_swing",
  "confidence": 0.87,
  "reason": "BOS bullish em H4 + pullback em OB + engulfing em 15m + volume",
  "strategy": "SMC_BOS_PULLBACK",
  "stop_loss_price": 96500,
  "take_profit_price": 102000,
  "stop_loss_pct": 2.0,
  "risk_profile": "BALANCED",
  "confluences": ["BOS_H4", "Order_Block", "Bullish_Engulfing", "Volume"],
  "timeframe_analysis": {
    "H4": "Bullish structure, clear BOS",
    "H1": "Pullback to demand zone",
    "15m": "Entry trigger - engulfing"
  }
}
```

**IMPORTANTE:**
- EMA cross NÃO é obrigatório, apenas confluência adicional
- Confidence baseado em número de confluências reais
- Stop loss baseado em estrutura (atrás de swing low/high)
- Risk profile: AGGRESSIVE (3R+) | BALANCED (2.5R) | CONSERVATIVE (2R)
"""

    SWING_USER_TEMPLATE = """Analise o seguinte setup para SWING TRADING:

**Símbolo:** {symbol}
**Preço Atual:** ${current_price}

**Estrutura Multi-Timeframe:**
{structure_analysis}

**Padrões de Price Action:**
{patterns}

**EMAs (opcional):**
{ema_analysis}

**Liquidez:**
{liquidity}

**Market Intelligence:**
{market_intelligence}

**Posições Abertas:** {open_positions}
**Equity:** ${equity}
**Risk per Trade:** {risk_pct}%

Avalie se há um setup A+ para SWING. Se sim, retorne decisão de "open". Se não, retorne "skip".

Lembre-se:
- Mínimo 3 confluências para A+
- EMA é OPCIONAL, não obrigatório
- Confidence >= 0.80
- Stop baseado em estrutura, não arbitrário
"""

    # ========== SCALP PROMPT (OPENAI) ==========
    
    SCALP_SYSTEM = """You are a professional SCALP TRADER on Hyperliquid.

**STYLE:**
- Timeframes: 15m/5m
- Target: Quick moves 0.5-2%
- Holding: Minutes to hours
- Analysis: EMA + VWAP + RSI + Volume

**METHODOLOGY:**
1. **Trend Context (15m):**
   - Clear intraday direction
   - Price above/below key EMAs (9/21/26)
   - Clean pullbacks only

2. **Entry (5m):**
   - Pullback to EMA9 or EMA21
   - Bounce confirmation (pin bar, inside bar)
   - Volume spike
   - RSI reset (30-70 range)

3. **Confluences (minimum 2 for entry):**
   - Price at key EMA
   - Volume confirmation
   - Clean candle pattern
   - RSI not overbought/oversold
   - Tight spread

**AVOID:**
- ❌ Choppy range (no clear direction)
- ❌ Against 15m trend
- ❌ After huge candle (>2%)
- ❌ Low volume
- ❌ Wide spread

**RESPONSE FORMAT:**
Always return valid JSON:

```json
{
  "action": "open" | "skip",
  "symbol": "ETH",
  "side": "long" | "short",
  "style": "scalp",
  "source": "openai_scalp",
  "confidence": 0.82,
  "reason": "Pullback to EMA9 + pin bar + volume + RSI reset",
  "strategy": "EMA9_BOUNCE",
  "stop_loss_price": 3450,
  "take_profit_price": 3500,
  "stop_loss_pct": 1.5,
  "risk_profile": "BALANCED",
  "confluences": ["EMA9", "Pin_Bar", "Volume"],
  "risk_amount_usd": 3.50,
  "capital_alloc_usd": 30.00
}
```

**CRITICAL:**
- Tight stops (1.5-2%)
- Quick in, quick out
- Breakeven fast (0.5R)
- Only trade liquid markets
- Respect 15m trend
"""

    SCALP_USER_TEMPLATE = """Analyze this SCALP setup:

**Symbol:** {symbol}
**Current Price:** ${current_price}

**15m Context:**
{context_15m}

**5m Entry:**
{context_5m}

**EMAs:**
{ema_analysis}

**Volume:** {volume}
**RSI:** {rsi}
**Spread:** {spread}

**Open Positions:** {open_positions}
**Equity:** ${equity}

Evaluate if there's a clean SCALP setup. If yes, return "open". If not, return "skip".

Remember:
- Minimum 2 confluences
- Tight stop (1.5-2%)
- With 15m trend only
- Confidence >= 0.75
"""

    # ========== MANAGE PROMPT (AMBOS) ==========
    
    MANAGE_TEMPLATE = """Analyze position management:

**Symbol:** {symbol}
**Entry:** ${entry_price}
**Current:** ${current_price}
**Stop:** ${stop_price}
**Side:** {side}
**R-Multiple:** {r_multiple}R

**Unrealized PnL:** ${unrealized_pnl} ({unrealized_pnl_pct}%)
**Time Open:** {time_open}

**Structure:** {current_structure}
**Trend:** {current_trend}

**Management Rules:**
- 1R: Move stop to breakeven
- 2R: Take 50% profit + stop to 0.5R profit
- 3R+: Trailing stop (1% from price)

Should we:
1. Move stop to breakeven?
2. Take partial profit?
3. Trail stop?
4. Hold as is?

Return JSON with "action": "manage" and manage_decision.
"""

    @classmethod
    def build_swing_prompt(cls, 
                          symbol: str,
                          market_data: dict,
                          account_info: dict) -> str:
        """Constrói prompt para SWING (Claude)"""
        
        structure = market_data.get('structure', {})
        patterns = market_data.get('patterns', [])
        ema = market_data.get('ema', {})
        liquidity = market_data.get('liquidity', {})
        mi = market_data.get('market_intelligence', {})
        
        user_prompt = cls.SWING_USER_TEMPLATE.format(
            symbol=symbol,
            current_price=market_data.get('current_price', 0),
            structure_analysis=cls._format_structure(structure),
            patterns=', '.join(patterns) if patterns else 'Nenhum padrão detectado',
            ema_analysis=cls._format_ema(ema),
            liquidity=cls._format_liquidity(liquidity),
            market_intelligence=cls._format_mi(mi),
            open_positions=account_info.get('open_positions', 0),
            equity=account_info.get('equity', 0),
            risk_pct=account_info.get('risk_per_trade_pct', 5)
        )
        
        return user_prompt
    
    @classmethod
    def build_scalp_prompt(cls,
                          symbol: str,
                          market_data: dict,
                          account_info: dict) -> str:
        """Constrói prompt para SCALP (OpenAI)"""
        
        user_prompt = cls.SCALP_USER_TEMPLATE.format(
            symbol=symbol,
            current_price=market_data.get('current_price', 0),
            context_15m=market_data.get('context_15m', 'N/A'),
            context_5m=market_data.get('context_5m', 'N/A'),
            ema_analysis=cls._format_ema(market_data.get('ema', {})),
            volume=market_data.get('volume', 'N/A'),
            rsi=market_data.get('rsi', 'N/A'),
            spread=market_data.get('spread', 'N/A'),
            open_positions=account_info.get('open_positions', 0),
            equity=account_info.get('equity', 0)
        )
        
        return user_prompt
    
    # === Formatadores ===
    
    @staticmethod
    def _format_structure(structure: dict) -> str:
        """Formata análise de estrutura"""
        if not structure:
            return "N/A"
        
        return f"""
- H4: {structure.get('H4', {}).get('trend', 'N/A')} | {structure.get('H4', {}).get('structure', 'N/A')}
- H1: {structure.get('H1', {}).get('trend', 'N/A')} | {structure.get('H1', {}).get('structure', 'N/A')}
- 15m: {structure.get('15m', {}).get('trend', 'N/A')} | {structure.get('15m', {}).get('structure', 'N/A')}
"""
    
    @staticmethod
    def _format_ema(ema: dict) -> str:
        """Formata análise de EMA"""
        if not ema:
            return "N/A"
        
        return f"""
- Cross: {ema.get('cross', 'none')}
- Alignment: {ema.get('alignment', 'neutral')}
- Price above EMA: {ema.get('price_above_ema', False)}
- Distance: {ema.get('distance_pct', 0):.2f}%
- Strength: {ema.get('strength', 0):.2f}
"""
    
    @staticmethod
    def _format_liquidity(liquidity: dict) -> str:
        """Formata zonas de liquidez"""
        if not liquidity:
            return "N/A"
        
        buy_side = liquidity.get('buy_side', [])
        sell_side = liquidity.get('sell_side', [])
        
        return f"""
- Buy-side (acima): {', '.join(f'${x:.2f}' for x in buy_side[:3])}
- Sell-side (abaixo): {', '.join(f'${x:.2f}' for x in sell_side[:3])}
"""
    
    @staticmethod
    def _format_mi(mi: dict) -> str:
        """Formata Market Intelligence"""
        if not mi:
            return "Neutral market"
        
        fg = mi.get('fear_greed', {})
        
        return f"""
- Fear & Greed: {fg.get('value', 50)} ({fg.get('classification', 'Neutral')})
- Recommendation: {mi.get('recommendation', 'Standard risk')}
"""
