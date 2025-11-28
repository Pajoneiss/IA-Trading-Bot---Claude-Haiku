"""
🤖 AUTONOMOUS TRADING BOT - Claude Haiku
=========================================
A IA decide TUDO: leverage, stop, take profit, tamanho, tudo.
O código apenas executa o que a IA mandar.

Autor: Baseado no conceito de IA verdadeiramente autônoma
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Hyperliquid
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Anthropic
import anthropic

# ==================== CONFIGURAÇÃO ====================
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== TELEGRAM SIMPLES ====================
class TelegramNotifier:
    """Notificações simples via Telegram"""
    
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = bool(self.token and self.chat_id)
        
        if self.enabled:
            logger.info("📱 Telegram ativado")
    
    def send(self, message: str):
        """Envia mensagem"""
        if not self.enabled:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=10)
        except Exception as e:
            logger.warning(f"Telegram erro: {e}")
    
    def notify_trade(self, action: str, symbol: str, side: str, size: float, 
                     price: float, leverage: int, sl: float, tp: float, reason: str):
        """Notifica trade"""
        emoji = "🟢" if side == "long" else "🔴"
        msg = (
            f"{emoji} **{action.upper()}** {symbol}\n\n"
            f"Lado: `{side.upper()}`\n"
            f"Tamanho: `${size:.2f}`\n"
            f"Preço: `${price:,.2f}`\n"
            f"Leverage: `{leverage}x`\n"
            f"Stop Loss: `${sl:,.2f}`\n"
            f"Take Profit: `${tp:,.2f}`\n\n"
            f"📝 _{reason}_"
        )
        self.send(msg)
    
    def notify_close(self, symbol: str, side: str, entry: float, exit_price: float, 
                     pnl_pct: float, pnl_usd: float, reason: str):
        """Notifica fechamento"""
        emoji = "✅" if pnl_pct > 0 else "❌"
        msg = (
            f"{emoji} **FECHOU** {symbol}\n\n"
            f"Lado: `{side.upper()}`\n"
            f"Entrada: `${entry:,.2f}`\n"
            f"Saída: `${exit_price:,.2f}`\n"
            f"PnL: `{pnl_pct:+.2f}%` (`${pnl_usd:+.2f}`)\n\n"
            f"📝 _{reason}_"
        )
        self.send(msg)
    
    def notify_status(self, equity: float, positions: int, msg_extra: str = ""):
        """Notifica status periódico"""
        msg = (
            f"📊 **STATUS**\n\n"
            f"Equity: `${equity:.2f}`\n"
            f"Posições: `{positions}`\n"
            f"{msg_extra}"
        )
        self.send(msg)


# ==================== HYPERLIQUID CLIENT ====================
class HyperliquidClient:
    """Client simplificado para Hyperliquid"""
    
    def __init__(self):
        self.wallet = os.getenv('HYPERLIQUID_WALLET_ADDRESS')
        self.private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
        
        if not self.wallet or not self.private_key:
            raise ValueError("Configure HYPERLIQUID_WALLET_ADDRESS e HYPERLIQUID_PRIVATE_KEY")
        
        self.account = Account.from_key(self.private_key)
        
        # Detecta rede
        network = os.getenv('HYPERLIQUID_NETWORK', 'mainnet')
        if network == 'mainnet':
            self.base_url = constants.MAINNET_API_URL
        else:
            self.base_url = constants.TESTNET_API_URL
        
        # Info (leitura) e Exchange (escrita)
        self.info = Info(self.base_url, skip_ws=True)
        self.exchange = Exchange(self.account, self.base_url, account_address=self.wallet)
        
        # Cache de metadados
        self._load_meta()
        
        logger.info(f"✅ Hyperliquid conectado ({network})")
        logger.info(f"   Wallet: {self.wallet[:8]}...{self.wallet[-6:]}")
    
    def _load_meta(self):
        """Carrega metadados dos ativos"""
        meta = self.info.meta()
        self.sz_decimals = {}
        self.asset_ids = {}
        
        for idx, asset in enumerate(meta.get('universe', [])):
            name = asset.get('name')
            self.sz_decimals[name] = asset.get('szDecimals', 4)
            self.asset_ids[name] = idx
    
    def get_account_state(self) -> Dict:
        """Retorna estado da conta"""
        state = self.info.user_state(self.wallet)
        return {
            'equity': float(state.get('marginSummary', {}).get('accountValue', 0)),
            'available': float(state.get('withdrawable', 0)),
            'margin_used': float(state.get('marginSummary', {}).get('totalMarginUsed', 0))
        }
    
    def get_positions(self) -> List[Dict]:
        """Retorna posições abertas"""
        state = self.info.user_state(self.wallet)
        positions = []
        
        for ap in state.get('assetPositions', []):
            pos = ap.get('position', {})
            size = float(pos.get('szi', 0))
            
            if size != 0:
                positions.append({
                    'symbol': pos.get('coin'),
                    'size': size,
                    'side': 'long' if size > 0 else 'short',
                    'entry_price': float(pos.get('entryPx', 0)),
                    'unrealized_pnl': float(pos.get('unrealizedPnl', 0)),
                    'leverage': int(ap.get('leverage', {}).get('value', 1)),
                    'liquidation_price': float(pos.get('liquidationPx', 0)) if pos.get('liquidationPx') else None
                })
        
        return positions
    
    def get_all_prices(self) -> Dict[str, float]:
        """Retorna preços mid de todos os ativos"""
        mids = self.info.all_mids()
        return {k: float(v) for k, v in mids.items()}
    
    def get_candles(self, symbol: str, interval: str = "1h", limit: int = 50) -> List[Dict]:
        """Retorna candles históricos"""
        end_time = int(time.time() * 1000)
        
        interval_ms = {
            "1m": 60_000, "5m": 300_000, "15m": 900_000,
            "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000
        }
        
        start_time = end_time - (limit * interval_ms.get(interval, 3_600_000))
        
        candles = self.info.candles_snapshot(symbol, interval, start_time, end_time)
        
        return [{
            'timestamp': c['t'],
            'open': float(c['o']),
            'high': float(c['h']),
            'low': float(c['l']),
            'close': float(c['c']),
            'volume': float(c['v'])
        } for c in candles]
    
    def get_funding_rates(self) -> Dict[str, float]:
        """Retorna funding rates"""
        meta = self.info.meta()
        rates = {}
        for asset in meta.get('universe', []):
            name = asset.get('name')
            funding = asset.get('funding')
            if funding:
                rates[name] = float(funding)
        return rates
    
    def set_leverage(self, symbol: str, leverage: int):
        """Define leverage para um ativo"""
        try:
            self.exchange.update_leverage(leverage, symbol, is_cross=True)
            logger.info(f"   Leverage {symbol} → {leverage}x")
        except Exception as e:
            logger.warning(f"   Erro ao setar leverage: {e}")
    
    def place_order(self, symbol: str, is_buy: bool, size: float, price: float, 
                    reduce_only: bool = False) -> Dict:
        """Coloca ordem market"""
        
        # Arredonda size
        decimals = self.sz_decimals.get(symbol, 4)
        size = round(size, decimals)
        
        # Preço com slippage para garantir fill
        if is_buy:
            exec_price = price * 1.02  # 2% slippage
        else:
            exec_price = price * 0.98
        
        # Arredonda preço (5 sig figs)
        exec_price = float(f"{exec_price:.5g}")
        
        logger.info(f"   Ordem: {'BUY' if is_buy else 'SELL'} {size} {symbol} @ ${exec_price:.2f}")
        
        try:
            result = self.exchange.order(
                name=symbol,
                is_buy=is_buy,
                sz=size,
                limit_px=exec_price,
                order_type={"limit": {"tif": "Ioc"}},
                reduce_only=reduce_only
            )
            return result
        except Exception as e:
            logger.error(f"   Erro na ordem: {e}")
            return {'status': 'error', 'error': str(e)}


# ==================== AI DECISION ENGINE ====================
class AutonomousAI:
    """
    IA 100% Autônoma - Decide TUDO
    """
    
    def __init__(self):
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("Configure ANTHROPIC_API_KEY")
        
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = os.getenv('AI_MODEL', 'claude-3-5-haiku-20241022')
        
        logger.info(f"🧠 IA inicializada: {self.model}")
    
    def decide(self, account: Dict, positions: List[Dict], prices: Dict[str, float],
               candles: Dict[str, List], funding: Dict[str, float], 
               pairs: List[str]) -> List[Dict]:
        """
        IA analisa TUDO e retorna decisões completas.
        
        Returns:
            Lista de ações com TODOS os parâmetros definidos pela IA
        """
        
        prompt = self._build_prompt(account, positions, prices, candles, funding, pairs)
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                temperature=0.3,  # Mais determinístico para trading
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = response.content[0].text
            logger.debug(f"IA resposta: {response_text[:500]}...")
            
            return self._parse_response(response_text)
            
        except Exception as e:
            logger.error(f"Erro na IA: {e}")
            return []
    
    def _build_prompt(self, account: Dict, positions: List[Dict], prices: Dict[str, float],
                      candles: Dict[str, List], funding: Dict[str, float], 
                      pairs: List[str]) -> str:
        """Constrói prompt completo para IA autônoma"""
        
        prompt = """Você é um TRADER AUTÔNOMO de criptomoedas operando na Hyperliquid (perpétuos).

Você tem TOTAL AUTONOMIA para decidir:
- Se vai operar ou não
- Qual moeda operar
- Long ou Short
- Quanto dinheiro usar (em USD)
- Qual alavancagem (1x até 50x)
- Onde colocar Stop Loss (preço exato)
- Onde colocar Take Profit (preço exato)
- Se vai aumentar, diminuir ou fechar posições existentes

Você é responsável por:
- Gerenciar o risco (não destrua a conta!)
- Maximizar lucros
- Cortar perdas
- Decidir o tamanho certo de cada operação

REGRAS BÁSICAS DE SOBREVIVÊNCIA:
1. Nunca arrisque mais de 20% da conta em uma única operação
2. Leverage alto = stop mais apertado obrigatoriamente
3. Se não tiver certeza, não opere (retorne "hold")
4. Considere o funding rate (se muito negativo/positivo)
5. Posições perdendo muito? Considere fechar antes que piore

"""
        
        # Estado da conta
        prompt += f"""
══════════════════════════════════════════
ESTADO DA CONTA
══════════════════════════════════════════
Equity Total: ${account['equity']:.2f}
Disponível: ${account['available']:.2f}
Margem em Uso: ${account['margin_used']:.2f}

"""
        
        # Posições abertas
        prompt += "══════════════════════════════════════════\n"
        prompt += "POSIÇÕES ABERTAS\n"
        prompt += "══════════════════════════════════════════\n"
        
        if positions:
            for pos in positions:
                pnl_pct = (pos['unrealized_pnl'] / (abs(pos['size']) * pos['entry_price'])) * 100 if pos['entry_price'] else 0
                prompt += f"""
{pos['symbol']} - {pos['side'].upper()}
  Tamanho: {abs(pos['size']):.4f} (${abs(pos['size']) * prices.get(pos['symbol'], pos['entry_price']):.2f})
  Entrada: ${pos['entry_price']:.4f}
  Preço Atual: ${prices.get(pos['symbol'], 0):.4f}
  PnL: ${pos['unrealized_pnl']:.2f} ({pnl_pct:+.2f}%)
  Leverage: {pos['leverage']}x
  Liquidação: ${pos['liquidation_price']:.4f if pos['liquidation_price'] else 'N/A'}
"""
        else:
            prompt += "\nNenhuma posição aberta.\n"
        
        # Dados de mercado
        prompt += "\n══════════════════════════════════════════\n"
        prompt += "DADOS DE MERCADO\n"
        prompt += "══════════════════════════════════════════\n"
        
        for pair in pairs:
            price = prices.get(pair, 0)
            fund = funding.get(pair, 0)
            pair_candles = candles.get(pair, [])
            
            if not price:
                continue
            
            prompt += f"\n📊 {pair}\n"
            prompt += f"   Preço: ${price:,.4f}\n"
            prompt += f"   Funding: {fund*100:.4f}%\n"
            
            # Análise simples dos candles
            if len(pair_candles) >= 10:
                recent = pair_candles[-10:]
                
                # Variação
                first_close = recent[0]['close']
                last_close = recent[-1]['close']
                change_pct = ((last_close - first_close) / first_close) * 100
                
                # Volatilidade
                highs = [c['high'] for c in recent]
                lows = [c['low'] for c in recent]
                volatility = ((max(highs) - min(lows)) / last_close) * 100
                
                # Tendência simples
                closes = [c['close'] for c in recent]
                avg_first_half = sum(closes[:5]) / 5
                avg_second_half = sum(closes[5:]) / 5
                trend = "ALTA" if avg_second_half > avg_first_half else "BAIXA"
                
                prompt += f"   Variação 10h: {change_pct:+.2f}%\n"
                prompt += f"   Volatilidade: {volatility:.2f}%\n"
                prompt += f"   Tendência: {trend}\n"
                prompt += f"   Último candle: O=${recent[-1]['open']:.2f} H=${recent[-1]['high']:.2f} L=${recent[-1]['low']:.2f} C=${recent[-1]['close']:.2f}\n"
        
        # Instruções de resposta
        prompt += """

══════════════════════════════════════════
SUA DECISÃO
══════════════════════════════════════════

Analise TUDO acima e decida o que fazer.

IMPORTANTE: Você deve retornar APENAS um JSON válido, sem explicações antes ou depois.

Para cada ação, especifique TODOS os parâmetros:

{
  "actions": [
    {
      "action": "open",           // "open", "close", "increase", "decrease", "hold"
      "symbol": "BTC",            // Qual moeda
      "side": "long",             // "long" ou "short" (só para open)
      "size_usd": 50.0,           // Quanto em USD (você decide!)
      "leverage": 10,             // Qual alavancagem (você decide! 1-50)
      "stop_loss": 94500.0,       // Preço do stop loss (você decide!)
      "take_profit": 98000.0,     // Preço do take profit (você decide!)
      "reason": "Tendência de alta forte, volatilidade baixa, bom R:R"
    }
  ]
}

Se não quiser fazer nada, retorne:
{
  "actions": [
    {
      "action": "hold",
      "reason": "Mercado indefinido, prefiro aguardar"
    }
  ]
}

Para FECHAR posição existente:
{
  "actions": [
    {
      "action": "close",
      "symbol": "BTC",
      "reason": "Stop mental atingido, tendência virou"
    }
  ]
}

RESPONDA APENAS COM O JSON:"""
        
        return prompt
    
    def _parse_response(self, response_text: str) -> List[Dict]:
        """Parse da resposta da IA"""
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
            actions = data.get('actions', [])
            
            # Valida e normaliza
            valid_actions = []
            for action in actions:
                act_type = action.get('action', 'hold')
                
                if act_type == 'hold':
                    logger.info(f"🤚 IA decidiu: HOLD - {action.get('reason', 'sem motivo')}")
                    continue
                
                if act_type == 'open':
                    # Validações básicas
                    if not action.get('symbol'):
                        continue
                    if not action.get('side'):
                        continue
                    if not action.get('size_usd') or action['size_usd'] <= 0:
                        continue
                    if not action.get('leverage') or action['leverage'] < 1:
                        action['leverage'] = 5  # Default
                    if action['leverage'] > 50:
                        action['leverage'] = 50  # Max
                    
                    valid_actions.append(action)
                    logger.info(f"📈 IA decidiu: OPEN {action['side'].upper()} {action['symbol']} | ${action['size_usd']} @ {action['leverage']}x")
                
                elif act_type == 'close':
                    if not action.get('symbol'):
                        continue
                    valid_actions.append(action)
                    logger.info(f"📉 IA decidiu: CLOSE {action['symbol']} - {action.get('reason', '')}")
                
                elif act_type in ('increase', 'decrease'):
                    if not action.get('symbol'):
                        continue
                    valid_actions.append(action)
                    logger.info(f"📊 IA decidiu: {act_type.upper()} {action['symbol']}")
            
            return valid_actions
            
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao parsear JSON da IA: {e}")
            logger.debug(f"Resposta: {response_text[:500]}")
            return []
        except Exception as e:
            logger.error(f"Erro ao processar resposta IA: {e}")
            return []


# ==================== BOT PRINCIPAL ====================
class AutonomousBot:
    """Bot que executa as decisões da IA"""
    
    def __init__(self):
        # Componentes
        self.client = HyperliquidClient()
        self.ai = AutonomousAI()
        self.telegram = TelegramNotifier()
        
        # Configuração
        self.pairs = os.getenv('PAIRS_TO_TRADE', 'BTC,ETH,SOL').split(',')
        self.loop_interval = int(os.getenv('LOOP_INTERVAL_SECONDS', '60'))
        self.ai_interval = int(os.getenv('AI_CALL_INTERVAL_MINUTES', '15')) * 60
        self.live_trading = os.getenv('LIVE_TRADING', 'false').lower() == 'true'
        
        # Estado
        self.last_ai_call = 0
        self.cached_decisions = []
        
        # Tracking de posições locais (para SL/TP)
        self.tracked_positions = {}  # {symbol: {'sl': x, 'tp': y, 'side': 'long'}}
        
        logger.info("=" * 50)
        logger.info("🤖 AUTONOMOUS BOT INICIADO")
        logger.info(f"   Modo: {'🔴 LIVE' if self.live_trading else '🟡 DRY RUN'}")
        logger.info(f"   Pares: {', '.join(self.pairs)}")
        logger.info(f"   Loop: {self.loop_interval}s")
        logger.info(f"   IA a cada: {self.ai_interval // 60} min")
        logger.info("=" * 50)
        
        # Notifica início
        self.telegram.send(
            f"🚀 **Bot Iniciado**\n\n"
            f"Modo: `{'LIVE' if self.live_trading else 'DRY RUN'}`\n"
            f"Pares: `{', '.join(self.pairs)}`"
        )
    
    def run(self):
        """Loop principal"""
        iteration = 0
        status_interval = 1800  # Status a cada 30 min
        last_status = 0
        
        while True:
            iteration += 1
            
            try:
                logger.info(f"\n{'='*40}")
                logger.info(f"⏰ Iteração #{iteration}")
                logger.info(f"{'='*40}")
                
                self._run_iteration()
                
                # Status periódico
                if time.time() - last_status > status_interval:
                    self._send_status()
                    last_status = time.time()
                
            except KeyboardInterrupt:
                logger.info("\n👋 Bot encerrado pelo usuário")
                self.telegram.send("🛑 Bot encerrado")
                break
            except Exception as e:
                logger.error(f"❌ Erro na iteração: {e}", exc_info=True)
                self.telegram.send(f"⚠️ Erro: {str(e)[:100]}")
            
            time.sleep(self.loop_interval)
    
    def _run_iteration(self):
        """Executa uma iteração"""
        
        # 1. Busca dados
        logger.info("📊 Buscando dados...")
        account = self.client.get_account_state()
        positions = self.client.get_positions()
        prices = self.client.get_all_prices()
        funding = self.client.get_funding_rates()
        
        logger.info(f"   Equity: ${account['equity']:.2f}")
        logger.info(f"   Posições: {len(positions)}")
        
        # 2. Verifica SL/TP das posições trackadas
        self._check_sl_tp(positions, prices)
        
        # 3. Busca candles
        candles = {}
        for pair in self.pairs:
            try:
                candles[pair] = self.client.get_candles(pair, "1h", 50)
            except:
                candles[pair] = []
        
        # 4. Consulta IA (se passou o intervalo)
        current_time = time.time()
        
        if current_time - self.last_ai_call >= self.ai_interval:
            logger.info(f"🧠 Consultando IA...")
            
            decisions = self.ai.decide(
                account=account,
                positions=positions,
                prices=prices,
                candles=candles,
                funding=funding,
                pairs=self.pairs
            )
            
            self.cached_decisions = decisions
            self.last_ai_call = current_time
            
            # Executa decisões
            for decision in decisions:
                self._execute_decision(decision, prices, account)
        else:
            remaining = (self.ai_interval - (current_time - self.last_ai_call)) / 60
            logger.info(f"⏳ Próxima consulta IA em {remaining:.1f} min")
    
    def _check_sl_tp(self, positions: List[Dict], prices: Dict[str, float]):
        """Verifica Stop Loss e Take Profit"""
        
        for symbol, track in list(self.tracked_positions.items()):
            price = prices.get(symbol)
            if not price:
                continue
            
            sl = track.get('sl')
            tp = track.get('tp')
            side = track.get('side')
            
            # Verifica se posição ainda existe
            pos = next((p for p in positions if p['symbol'] == symbol), None)
            if not pos:
                # Posição foi fechada externamente
                del self.tracked_positions[symbol]
                continue
            
            hit_sl = False
            hit_tp = False
            
            if side == 'long':
                if sl and price <= sl:
                    hit_sl = True
                if tp and price >= tp:
                    hit_tp = True
            else:  # short
                if sl and price >= sl:
                    hit_sl = True
                if tp and price <= tp:
                    hit_tp = True
            
            if hit_sl or hit_tp:
                reason = "Stop Loss" if hit_sl else "Take Profit"
                logger.info(f"🎯 {reason} atingido para {symbol}!")
                
                self._close_position(symbol, pos, price, reason)
    
    def _execute_decision(self, decision: Dict, prices: Dict[str, float], account: Dict):
        """Executa uma decisão da IA"""
        
        action = decision.get('action')
        symbol = decision.get('symbol')
        
        if action == 'open':
            self._open_position(decision, prices, account)
        
        elif action == 'close':
            positions = self.client.get_positions()
            pos = next((p for p in positions if p['symbol'] == symbol), None)
            if pos:
                self._close_position(symbol, pos, prices.get(symbol, 0), decision.get('reason', 'IA'))
        
        elif action == 'increase':
            self._adjust_position(decision, prices, increase=True)
        
        elif action == 'decrease':
            self._adjust_position(decision, prices, increase=False)
    
    def _open_position(self, decision: Dict, prices: Dict[str, float], account: Dict):
        """Abre posição"""
        
        symbol = decision['symbol']
        side = decision['side']
        size_usd = decision['size_usd']
        leverage = decision['leverage']
        sl = decision.get('stop_loss')
        tp = decision.get('take_profit')
        reason = decision.get('reason', '')
        
        price = prices.get(symbol)
        if not price:
            logger.warning(f"   Preço não disponível para {symbol}")
            return
        
        # Valida se não excede o disponível
        if size_usd > account['available'] * 0.95:
            size_usd = account['available'] * 0.8
            logger.warning(f"   Tamanho ajustado para ${size_usd:.2f} (limite de disponível)")
        
        # Calcula quantidade
        size = size_usd / price
        
        logger.info(f"\n{'='*40}")
        logger.info(f"🚀 ABRINDO {side.upper()} {symbol}")
        logger.info(f"   Size: {size:.6f} (${size_usd:.2f})")
        logger.info(f"   Leverage: {leverage}x")
        logger.info(f"   SL: ${sl:.2f if sl else 'N/A'}")
        logger.info(f"   TP: ${tp:.2f if tp else 'N/A'}")
        logger.info(f"   Motivo: {reason}")
        logger.info(f"{'='*40}")
        
        if not self.live_trading:
            logger.info("   ⚠️ DRY RUN - Ordem não executada")
            # Simula tracking
            self.tracked_positions[symbol] = {'sl': sl, 'tp': tp, 'side': side}
            return
        
        # Executa
        try:
            # Seta leverage
            self.client.set_leverage(symbol, leverage)
            
            # Ordem
            is_buy = (side == 'long')
            result = self.client.place_order(symbol, is_buy, size, price)
            
            if result.get('status') == 'ok' or 'response' in result:
                logger.info(f"   ✅ Ordem executada!")
                
                # Tracka SL/TP
                self.tracked_positions[symbol] = {'sl': sl, 'tp': tp, 'side': side}
                
                # Notifica
                self.telegram.notify_trade(
                    action="ABRIU",
                    symbol=symbol,
                    side=side,
                    size=size_usd,
                    price=price,
                    leverage=leverage,
                    sl=sl or 0,
                    tp=tp or 0,
                    reason=reason
                )
            else:
                logger.error(f"   ❌ Falha: {result}")
                
        except Exception as e:
            logger.error(f"   ❌ Erro ao abrir: {e}")
    
    def _close_position(self, symbol: str, position: Dict, price: float, reason: str):
        """Fecha posição"""
        
        logger.info(f"\n{'='*40}")
        logger.info(f"🔴 FECHANDO {symbol}")
        logger.info(f"   Motivo: {reason}")
        logger.info(f"{'='*40}")
        
        # Calcula PnL
        entry = position['entry_price']
        size = abs(position['size'])
        side = position['side']
        
        if side == 'long':
            pnl_pct = ((price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - price) / entry) * 100
        
        pnl_usd = position['unrealized_pnl']
        
        if not self.live_trading:
            logger.info(f"   ⚠️ DRY RUN - PnL simulado: {pnl_pct:+.2f}%")
            if symbol in self.tracked_positions:
                del self.tracked_positions[symbol]
            return
        
        # Executa
        try:
            is_buy = (side == 'short')  # Inverte para fechar
            result = self.client.place_order(symbol, is_buy, size, price, reduce_only=True)
            
            if result.get('status') == 'ok' or 'response' in result:
                logger.info(f"   ✅ Posição fechada! PnL: {pnl_pct:+.2f}%")
                
                if symbol in self.tracked_positions:
                    del self.tracked_positions[symbol]
                
                # Notifica
                self.telegram.notify_close(
                    symbol=symbol,
                    side=side,
                    entry=entry,
                    exit_price=price,
                    pnl_pct=pnl_pct,
                    pnl_usd=pnl_usd,
                    reason=reason
                )
            else:
                logger.error(f"   ❌ Falha ao fechar: {result}")
                
        except Exception as e:
            logger.error(f"   ❌ Erro ao fechar: {e}")
    
    def _adjust_position(self, decision: Dict, prices: Dict[str, float], increase: bool):
        """Ajusta posição (increase/decrease)"""
        
        symbol = decision['symbol']
        size_usd = decision.get('size_usd', 0)
        reason = decision.get('reason', '')
        
        positions = self.client.get_positions()
        pos = next((p for p in positions if p['symbol'] == symbol), None)
        
        if not pos:
            logger.warning(f"   Posição {symbol} não encontrada para ajuste")
            return
        
        price = prices.get(symbol)
        if not price:
            return
        
        action_name = "AUMENTANDO" if increase else "REDUZINDO"
        logger.info(f"\n📊 {action_name} {symbol}: ${size_usd:.2f}")
        logger.info(f"   Motivo: {reason}")
        
        if not self.live_trading:
            logger.info("   ⚠️ DRY RUN")
            return
        
        size = size_usd / price
        is_buy = (pos['side'] == 'long') if increase else (pos['side'] == 'short')
        
        try:
            result = self.client.place_order(
                symbol, 
                is_buy, 
                size, 
                price, 
                reduce_only=(not increase)
            )
            
            if result.get('status') == 'ok' or 'response' in result:
                logger.info(f"   ✅ Ajuste executado!")
            else:
                logger.error(f"   ❌ Falha: {result}")
                
        except Exception as e:
            logger.error(f"   ❌ Erro no ajuste: {e}")
    
    def _send_status(self):
        """Envia status via Telegram"""
        try:
            account = self.client.get_account_state()
            positions = self.client.get_positions()
            
            pos_info = ""
            for p in positions:
                emoji = "🟢" if p['unrealized_pnl'] > 0 else "🔴"
                pos_info += f"\n{emoji} {p['symbol']}: ${p['unrealized_pnl']:+.2f}"
            
            self.telegram.notify_status(
                equity=account['equity'],
                positions=len(positions),
                msg_extra=pos_info
            )
        except Exception as e:
            logger.warning(f"Erro ao enviar status: {e}")


# ==================== MAIN ====================
if __name__ == "__main__":
    bot = AutonomousBot()
    bot.run()
