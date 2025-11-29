"""
OpenAI Scalp Engine
Motor de decisão focado em SCALP usando OpenAI (GPT-4o-mini).
"""
import json
import logging
import os
from typing import Dict, List, Optional, Any
import openai

logger = logging.getLogger(__name__)

class OpenAiScalpEngine:
    """Motor de decisão IA focado em SCALP usando OpenAI"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.client = None
        self.enabled = False
        
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
            
            # Taggear decisões
            for dec in decisions:
                dec['source'] = 'openai_scalp'
                dec['style'] = 'scalp'
                
                if dec.get('action') != 'hold':
                    logger.info(
                        f"⚡ SCALP ({dec.get('symbol')}): {dec.get('action')} {dec.get('side', '')} "
                        f"| Conf: {dec.get('confidence', 0):.2f}"
                    )
            
            return decisions
            
        except Exception as e:
            logger.error(f"Erro ao consultar OpenAI: {e}")
            return []

    def _build_scalp_prompt(self,
                            market_contexts: List[Dict[str, Any]],
                            account_info: Dict[str, Any],
                            open_positions: List[Dict[str, Any]],
                            risk_limits: Dict[str, Any]) -> str:
        """Constrói prompt específico para SCALP"""
        
        prompt = """Você é um motor de SCALP TRADING.
Seu objetivo é identificar oportunidades de CURTO PRAZO (5m, 15m, 1h).

FOCO:
- Movimentos rápidos de 1% a 2.5%.
- Stop Loss APERTADO (0.5% a 1.5%).
- Take Profit curto (1% a 2.5%).
- Evitar operar em mercado lateral (chop) se não houver setup claro.
- Se o mercado estiver neutro/morto, responda HOLD.

REGRAS:
1. Analise os dados de mercado fornecidos.
2. Identifique setups de alta probabilidade (Breakouts, Reversões em suporte/resistência, Continuação de tendência).
3. Retorne um JSON com suas decisões.

ESTADO DA CONTA:
"""
        prompt += f"Equity: ${account_info.get('equity', 0):.2f}\n"
        prompt += f"PnL Dia: {account_info.get('daily_pnl_pct', 0):.2f}%\n\n"
        
        prompt += "POSIÇÕES ABERTAS:\n"
        if open_positions:
            for pos in open_positions:
                prompt += f"- {pos.get('symbol')} {pos.get('side')} (PnL: {pos.get('unrealized_pnl_pct', 0):.2f}%)\n"
        else:
            prompt += "Nenhuma.\n"
            
        prompt += "\nDADOS DE MERCADO:\n"
        for ctx in market_contexts:
            symbol = ctx.get('symbol')
            price = ctx.get('price', 0)
            ind = ctx.get('indicators', {})
            
            prompt += f"""
SYMBOL: {symbol}
Price: {price}
Trend: {ind.get('trend')} (Strength: {ind.get('trend_strength', 0):.2f})
RSI: {ind.get('rsi', 50):.1f}
Volatility: {ind.get('volatility_pct', 0):.2f}%
Funding: {ctx.get('funding_rate', 0)*100:.4f}%
"""
            if ind.get('ema_9') and ind.get('ema_21'):
                 ema_cross = "BULLISH" if ind['ema_9'] > ind['ema_21'] else "BEARISH"
                 prompt += f"EMAs Cross: {ema_cross}\n"

        prompt += """
FORMATO DE RESPOSTA (JSON):
{
  "actions": [
    {
      "action": "open", "symbol": "SOL", "side": "short",
      "leverage": 10, 
      "stop_loss_price": 23.50, 
      "take_profit_price": 21.00,
      "confidence": 0.85, "setup_name": "bear_flag_breakout",
      "reason": "Rompimento de suporte com volume"
    }
  ]
}

Se não houver trade: {"actions": [{"action": "hold", "reason": "..."}]}

IMPORTANTE:
- Calcule "stop_loss_price" e "take_profit_price" baseado no preço atual e nos percentuais alvo (SL 0.5-1.5%, TP 1-2.5%).
- O RiskManager calculará o tamanho da posição, você só sugere a entrada e os parâmetros de saída.
- NÃO force trades. Qualidade > Quantidade.
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
