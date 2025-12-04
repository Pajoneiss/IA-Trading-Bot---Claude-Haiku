"""
BOT HYPERLIQUID 24/7 COM IA
Bot de trading autônomo que usa Claude API para decisões inteligentes
"""
import os
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Dependências HTTP para Hyperliquid
import json
import requests
from eth_account import Account
from eth_account.messages import encode_defunct

# Importa módulos do bot
from bot.risk_manager import RiskManager
from bot.ai_decision import AiDecisionEngine
from bot.dual_ai_engine import DualAiDecisionEngine
from bot.position_manager import PositionManager
from bot.market_context import MarketContext
from bot.indicators import TechnicalIndicators
from bot.trade_filter import TradeActionFilter
from bot.telegram_notifier import TelegramNotifier
from bot.telegram_interactive_pro import TelegramInteractivePRO as TelegramInteractive
from bot.scalp_filters import ScalpFilters
from bot.ai_manager import AIManager


# ==================== CONFIGURAÇÃO DE LOGGING ====================
def setup_logging(level: str = "INFO"):
    """Configura logging do bot"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=log_level,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Reduz verbosidade de bibliotecas externas
    logging.getLogger('anthropic').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)


# ==================== HYPERLIQUID CLIENT WRAPPER ====================
class HyperliquidBotClient:
    """
    Wrapper HTTP direto para Hyperliquid API
    Não depende do SDK, funciona com requisições HTTP puras
    """
    
    def __init__(self, network: str = "mainnet"):
        """Inicializa client HTTP"""
        import json
        import requests
        from eth_account import Account
        from hyperliquid.exchange import Exchange
        from hyperliquid.utils import constants
        
        self.network = network
        self.logger = logging.getLogger(__name__)
        
        # Carrega credenciais
        wallet_address = os.getenv('HYPERLIQUID_WALLET_ADDRESS')
        private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
        
        if not wallet_address or not private_key:
            raise ValueError("HYPERLIQUID_WALLET_ADDRESS e HYPERLIQUID_PRIVATE_KEY devem estar no .env")
        
        self.wallet_address = wallet_address
        self.private_key = private_key
        self.account = Account.from_key(private_key)
        
        # LOGS DE DEBUG CRÍTICOS PARA CARTEIRA
        self.logger.info(f"🔑 Endereço derivado da Private Key (Agent): {self.account.address}")
        self.logger.info(f"🔑 Endereço configurado no ENV (Master): {self.wallet_address}")
        
        if self.account.address.lower() != self.wallet_address.lower():
            self.logger.info("ℹ️  Modo API Wallet detectado (Agent assinando para Master)")
        
        # URLs da API
        if network == "mainnet":
            self.base_url = constants.MAINNET_API_URL
        else:
            self.base_url = constants.TESTNET_API_URL
        
        self.info_url = f"{self.base_url}/info"
        
        # Inicializa Exchange SDK
        # account_address=self.wallet_address é CRUCIAL para API Wallets
        self.exchange = Exchange(self.account, self.base_url, account_address=self.wallet_address)
        
        # Módulos necessários
        self.json = json
        self.requests = requests
        
        # Cache de mapeamento símbolo -> asset index
        self.asset_index_cache = {}
        self._load_asset_indices()
        
        self.logger.info(f"HyperliquidBotClient inicializado (network={network})")
    
    def _load_asset_indices(self):
        """Carrega mapeamento de símbolos para índices de assets"""
        try:
            payload = {"type": "meta"}
            response = self.requests.post(self.info_url, json=payload, timeout=10)
            response.raise_for_status()
            meta = response.json()
            
            self.sz_decimals_cache = {} # Cache de decimais de tamanho
            
            for idx, asset in enumerate(meta.get('universe', [])):
                symbol = asset.get('name')
                self.asset_index_cache[symbol] = idx
                self.sz_decimals_cache[symbol] = asset.get('szDecimals', 4) # Default 4
            
            self.logger.info(f"✅ Carregados {len(self.asset_index_cache)} assets e metadados")
        except Exception as e:
            self.logger.error(f"❌ Erro ao carregar asset indices: {e}")
    
    def _sign_message(self, message: Dict) -> str:
        """Assina mensagem para autenticação"""
        message_str = self.json.dumps(message, separators=(',', ':'))
        message_hash = encode_defunct(text=message_str)
        
        # VERIFICAÇÃO DE SEGURANÇA (Adaptado para API Wallets)
        if self.account.address.lower() != self.wallet_address.lower():
            self.logger.warning(f"⚠️  USANDO API WALLET: Assinando com {self.account.address} em nome de {self.wallet_address}")
            # Não levantamos erro aqui pois é um caso de uso válido (API Wallet)
            
        signed = self.account.sign_message(message_hash)
        return {
            "r": "0x" + signed.r.to_bytes(32, 'big').hex(),
            "s": "0x" + signed.s.to_bytes(32, 'big').hex(),
            "v": signed.v
        }
    
    def get_user_state(self) -> Dict[str, Any]:
        """Obtém estado completo da conta"""
        import time
        
        payload = {
            "type": "clearinghouseState",
            "user": self.wallet_address
        }
        
        # Rate limiting com retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Aguarda entre chamadas
                if attempt > 0:
                    wait_time = 2 ** attempt  # Exponential backoff: 2s, 4s
                    self.logger.warning(f"[HYPERLIQUID] Retry {attempt+1}/{max_retries}, aguardando {wait_time}s...")
                    time.sleep(wait_time)
                
                response = self.requests.post(self.info_url, json=payload, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                # Formata resposta
                return {
                    'account_value': float(data.get('marginSummary', {}).get('accountValue', 0)),
                    'total_margin_used': float(data.get('marginSummary', {}).get('totalMarginUsed', 0)),
                    'withdrawable': float(data.get('withdrawable', 0)),
                    'assetPositions': data.get('assetPositions', [])
                }
                
            except self.requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    # Rate limited
                    if attempt == max_retries - 1:
                        self.logger.error("[HYPERLIQUID] Rate limit persistente após retries")
                        raise
                    # Continua para próxima tentativa
                    continue
                else:
                    # Outro erro HTTP
                    raise
            
            except self.requests.exceptions.Timeout:
                self.logger.warning(f"[HYPERLIQUID] Timeout na tentativa {attempt+1}")
                if attempt == max_retries - 1:
                    raise
                continue
        
        raise Exception("Max retries atingido")
    
    def get_all_mids(self) -> Dict[str, float]:
        """Obtém preços mid de todos os pares"""
        import time
        
        payload = {"type": "allMids"}
        
        # Rate limiting com retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt
                    self.logger.warning(f"[HYPERLIQUID] get_all_mids retry {attempt+1}, aguardando {wait_time}s...")
                    time.sleep(wait_time)
                
                response = self.requests.post(self.info_url, json=payload, timeout=10)
                response.raise_for_status()
                data = response.json()
                # Converte valores para float pois API retorna strings
                return {k: float(v) for k, v in data.items()}
                
            except self.requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    if attempt == max_retries - 1:
                        self.logger.error("[HYPERLIQUID] Rate limit em get_all_mids")
                        raise
                    continue
                else:
                    raise
            
            except self.requests.exceptions.Timeout:
                if attempt == max_retries - 1:
                    raise
                continue
        
        raise Exception("Max retries atingido")
    
    def get_candles(self, coin: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
        """Obtém candles históricos"""
        import time
        
        def safe_float(value, default=0.0):
            """Converte valor para float com segurança"""
            if value is None:
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        end_time = int(time.time() * 1000)
        interval_ms = {
            "1m": 60_000, "5m": 300_000, "15m": 900_000,
            "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000
        }
        start_time = end_time - (limit * interval_ms.get(interval, 3_600_000))
        
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval,
                "startTime": start_time,
                "endTime": end_time
            }
        }
        
        response = self.requests.post(self.info_url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Formata candles
        formatted = []
        for candle in data:
            formatted.append({
                't': candle['t'],
                'o': safe_float(candle.get('o')),
                'h': safe_float(candle.get('h')),
                'l': safe_float(candle.get('l')),
                'c': safe_float(candle.get('c')),
                'v': safe_float(candle.get('v'))
            })
        
        return formatted
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Obtém posições abertas"""
        def safe_float(value, default=0.0):
            """Converte valor para float com segurança"""
            if value is None:
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        user_state = self.get_user_state()
        
        positions = []
        for asset_position in user_state.get('assetPositions', []):
            position = asset_position.get('position', {})
            size = safe_float(position.get('szi', 0))
            
            if size != 0:  # Apenas posições abertas
                positions.append({
                    'coin': position.get('coin'),
                    'size': size,
                    'entry_price': safe_float(position.get('entryPx', 0)),
                    'unrealized_pnl': safe_float(position.get('unrealizedPnl', 0)),
                    'leverage': int(asset_position.get('leverage', {}).get('value', 1)),
                    'liquidation_px': safe_float(position.get('liquidationPx', 0))
                })
        
        return positions
    
    def get_funding_rates(self) -> List[Dict[str, Any]]:
        """Obtém funding rates"""
        payload = {"type": "meta"}
        
        response = self.requests.post(self.info_url, json=payload, timeout=10)
        response.raise_for_status()
        meta = response.json()
        
        funding_rates = []
        for asset in meta.get('universe', []):
            funding_rates.append({
                'coin': asset.get('name'),
                'funding_rate': float(asset.get('funding', 0))
            })
        
        return funding_rates
    
    def _round_price(self, price: float, sz_decimals: int) -> float:
        """Arredonda preço conforme regras da Hyperliquid"""
        if price == 0:
            return 0.0
            
        # Regra 1: Max 5 algarismos significativos
        # O formato 'g' arredonda para sig figs
        price_sig = float(f"{price:.5g}")
        
        # Regra 2: Max decimais = 6 - sz_decimals
        max_decimals = 6 - sz_decimals
        if max_decimals < 0: max_decimals = 0
        
        # Garante que não excede o max de decimais permitido
        return round(price_sig, max_decimals)

    def place_order(self, coin: str, is_buy: bool, size: float, price: float,
                   order_type: str = "market", leverage: int = 1, reduce_only: bool = False) -> Dict:
        
        # Obtém decimais do tamanho (szDecimals)
        sz_decimals = self.sz_decimals_cache.get(coin, 4)
        
        # Arredonda tamanho (sz)
        rounded_size = round(size, sz_decimals)
        
        # Lógica de Market Order (Slippage)
        # Para garantir execução imediata (IOC), precisamos cruzar o spread
        # Aplicamos 5% de slippage para garantir o fill
        exec_price = price
        if order_type == "market":
            if is_buy:
                exec_price = price * 1.05  # Paga até 5% mais caro
            else:
                exec_price = price * 0.95  # Vende por até 5% mais barato
        
        # Arredonda preço (px) usando regras complexas (5 sig figs + max decimals)
        rounded_price = self._round_price(exec_price, sz_decimals)
        
        self.logger.info(f"🔍 SDK place_order: coin={coin}, size={rounded_size} (dec={sz_decimals}), price={rounded_price} (orig={price})")
        
        try:
            # SDK lida com formatação, assinatura e API Wallet automaticamente
            order_result = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=rounded_size,
                limit_px=rounded_price,
                order_type={"limit": {"tif": "Ioc"}}, 
                reduce_only=reduce_only
            )
            
            return order_result
            
        except Exception as e:
            self.logger.error(f"❌ Erro no SDK place_order: {e}")
            return {'status': 'err', 'response': str(e)}
    
    def adjust_leverage(self, coin: str, leverage: int, is_cross: bool = True):
        self.logger.info(f"🔍 SDK adjust_leverage: coin={coin}, lev={leverage}")
        
        try:
            # SDK lida com tudo
            result = self.exchange.update_leverage(leverage, coin, is_cross)
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Erro no SDK adjust_leverage: {e}")
            return {'status': 'err', 'response': str(e)}
    
    def cancel_all_orders(self, coin: Optional[str] = None):
        """Cancela todas as ordens"""
        import time
        
        if coin:
            action = {
                "type": "cancel",
                "cancels": [{
                    "a": self.wallet_address,
                    "o": 0  # 0 = todas as ordens do coin
                }]
            }
        else:
            action = {
                "type": "cancelAll"
            }
        
        signature = self._sign_message(action)
        
        payload = {
            "action": action,
            "signature": signature,
            "nonce": int(time.time() * 1000)
        }
        
        response = self.requests.post(self.exchange_url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()


# ==================== BOT PRINCIPAL ====================
class HyperliquidBot:
    """Bot de trading autônomo 24/7"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Inicializa componentes
        self.client = HyperliquidBotClient(network=config['network'])
        
        self.risk_manager = RiskManager(
            risk_per_trade_pct=config['risk_per_trade_pct'],
            max_daily_drawdown_pct=config['max_daily_drawdown_pct'],
            max_open_trades=config['max_open_trades'],
            max_leverage=config['max_leverage'],
            min_notional=config['min_notional']
        )
        
        # PARTE 2: Limite efetivo de posições (máximo 6)
        self.effective_max_positions = min(config['max_open_trades'], 6)
        self.logger.info(f"🛡️ Limite efetivo de posições: {self.effective_max_positions}")
        
        self.ai_engine = DualAiDecisionEngine(
            anthropic_key=config.get('anthropic_api_key'),
            openai_key=config.get('openai_api_key'),
            anthropic_model=config.get('ai_model', 'claude-3-5-haiku-20241022'),
            openai_model=config.get('openai_model_scalp', 'gpt-4o-mini')
        )
        
        self.position_manager = PositionManager(
            default_stop_pct=config['default_stop_pct'],
            default_tp_pct=config['default_tp_pct']
        )
        
        self.market_context = MarketContext()
        
        self.trading_pairs = config['trading_pairs']
        self.live_trading = config['live_trading']
        self.loop_sleep = config['loop_sleep_seconds']
        
        # ========== SISTEMA ANTI-OVERTRADING ==========
        # Cooldown: tempo mínimo entre ações no mesmo ativo (em segundos)
        self.action_cooldown_seconds = config.get('action_cooldown_seconds', 300)  # 5 minutos default
        self.last_action_time = {}  # {symbol: timestamp}
        
        # Confiança mínima para agir
        self.min_confidence_open = config.get('min_confidence_open', 0.75)
        self.min_confidence_adjust = config.get('min_confidence_adjust', 0.80)  # increase/decrease precisam de mais confiança
        
        # Máximo de ações de ajuste (increase/decrease) por iteração
        self.max_adjustments_per_iteration = config.get('max_adjustments_per_iteration', 1)
        
        # TradeActionFilter - camada extra de proteção
        self.trade_filter = TradeActionFilter({
            'min_seconds_between_adjustments': config.get('action_cooldown_seconds', 300),
            'min_price_move_pct': config.get('min_price_move_pct', 0.5),
            'min_position_change_ratio': config.get('min_position_change_ratio', 0.25),
            'min_notional_adjust': config.get('min_notional_adjust', 10.0),
            'max_adjustments_per_symbol_per_day': config.get('max_adjustments_per_symbol_per_day', 4),
            'min_confidence_open': self.min_confidence_open,
            'min_confidence_adjust': self.min_confidence_adjust,
            'min_confidence_close': 0.65,
            'min_seconds_to_reverse': config.get('min_seconds_to_reverse', 600),
            'emergency_pnl_threshold': config.get('emergency_pnl_threshold', -2.0),
        })
        
        # ========== TELEGRAM NOTIFIER ==========
        self.telegram = TelegramNotifier(
            bot_token=config.get('telegram_bot_token'),
            chat_id=config.get('telegram_chat_id')
        )
        
        # ========== TELEGRAM INTERACTIVE ==========
        self.telegram_interactive = TelegramInteractive(
            main_bot=self,
            token=config.get('telegram_bot_token')
        )
        
        self.paused = False  # Flag para pausar trading via Telegram
        
        # ========== CONTROLE DE CHAMADAS IA ==========
        # Constante para intervalo de SCALP (fixo em código)
        self.SCALP_CALL_INTERVAL_MINUTES = 5
        
        # IA SWING (Claude) - intervalo configurável
        self.ai_call_interval = int(os.getenv('AI_CALL_INTERVAL_MINUTES', '15')) * 60  # Em segundos
        self.last_swing_ai_call = 0  # Timestamp da última chamada SWING
        
        # ========== AI MANAGER (ORQUESTRADOR) ==========
        self.ai_manager = AIManager({
            'swing_interval_seconds': self.ai_call_interval,
            'scalp_symbol_cooldown': self.action_cooldown_seconds
        })
        
        # IA SCALP (OpenAI) - intervalo fixo de 5 minutos
        self.scalp_call_interval = self.SCALP_CALL_INTERVAL_MINUTES * 60  # Em segundos
        self.last_scalp_ai_call = 0  # Timestamp da última chamada SCALP
        
        # Contador de iterações para OpenAI (reduz rate limit)
        self.openai_analysis_interval = config.get('openai_analysis_interval', 5)  # Analisa 1 a cada N iterações
        self.iteration_counter = 0  # Contador de iterações
        
        # Cache de decisões
        self.last_swing_decisions = []  # Cache das últimas decisões SWING
        self.last_scalp_decisions = []  # Cache das últimas decisões SCALP
        
        # Flag para habilitar OpenAI
        self.openai_enabled = bool(config.get('openai_api_key'))
        if not self.openai_enabled:
            self.logger.info("[AI] OpenAI SCALP desativado: OPENAI_API_KEY não configurada.")
        else:
            self.logger.info(f"[AI] OpenAI SCALP: 1 análise a cada {self.openai_analysis_interval} iterações (reduz rate limit)")
        # ================================================
        
        self.logger.info("=" * 60)
        self.logger.info("🤖 HYPERLIQUID BOT INICIALIZADO")
        self.logger.info(f"Network: {config['network']}")
        self.logger.info(f"Modo: {'LIVE TRADING ⚠️' if self.live_trading else 'DRY RUN (simulação)'}")
        self.logger.info(f"Pares: {', '.join(self.trading_pairs)}")
        self.logger.info(f"IA: {'Ativada ✅' if config.get('anthropic_api_key') else 'Desativada (fallback)'}")
        self.logger.info(f"🛡️ Anti-Overtrading: cooldown={self.action_cooldown_seconds}s, min_conf_adjust={self.min_confidence_adjust}")
        self.logger.info(f"📱 Telegram: {'Ativado ✅' if self.telegram.enabled else 'Desativado'}")
        self.logger.info(f"🧠 IA SWING chamada a cada: {self.ai_call_interval // 60} minutos")
        if self.openai_enabled:
            self.logger.info(f"⚡ IA SCALP chamada a cada: {self.SCALP_CALL_INTERVAL_MINUTES} minutos")
        self.logger.info("=" * 60)
        
        self.risk_manager.log_risk_limits()
    
    def _is_on_cooldown(self, symbol: str) -> bool:
        """Verifica se o ativo está em cooldown"""
        if symbol not in self.last_action_time:
            return False
        
        elapsed = time.time() - self.last_action_time[symbol]
        return elapsed < self.action_cooldown_seconds
    
    def _get_cooldown_remaining(self, symbol: str) -> int:
        """Retorna segundos restantes de cooldown"""
        if symbol not in self.last_action_time:
            return 0
        
        elapsed = time.time() - self.last_action_time[symbol]
        remaining = self.action_cooldown_seconds - elapsed
        return max(0, int(remaining))
    
    def _set_cooldown(self, symbol: str):
        """Marca que uma ação foi executada no ativo"""
        self.last_action_time[symbol] = time.time()
    
    def run(self):
        """Loop principal do bot"""
        self.logger.info("🚀 Iniciando loop de trading...")
        
        # Inicia listener do Telegram (comandos)
        self.telegram_interactive.start()
        
        iteration = 0
        last_summary_time = 0
        summary_interval = 1800  # Envia resumo a cada 30 minutos
        
        try:
            while True:
                iteration += 1
                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"ITERAÇÃO #{iteration} - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
                self.logger.info(f"{'='*60}")
                
                try:
                    self._run_iteration()
                    
                    # Envia resumo periódico via Telegram
                    if time.time() - last_summary_time > summary_interval:
                        self._send_telegram_summary()
                        last_summary_time = time.time()
                        
                except Exception as e:
                    self.logger.error(f"❌ Erro na iteração: {e}", exc_info=True)
                    self.logger.warning("Continuando para próxima iteração...")
                
                self.logger.info(f"💤 Aguardando {self.loop_sleep}s até próxima iteração...")
                time.sleep(self.loop_sleep)
                
        except KeyboardInterrupt:
            self.logger.info("\n⚠️  Bot interrompido pelo usuário")
            self._shutdown()
        except Exception as e:
            self.logger.error(f"❌ Erro fatal: {e}", exc_info=True)
            self._shutdown()
    
    def _send_telegram_summary(self):
        """Envia resumo periódico via Telegram"""
        try:
            # Busca preços atuais para calcular PnL correto
            try:
                all_prices = self.client.get_all_mids()
            except Exception:
                self.logger.warning("Não foi possível buscar preços para o resumo Telegram")
                all_prices = {}

            equity = self.risk_manager.current_equity
            daily_pnl = self.risk_manager.daily_pnl_pct
            positions = self.position_manager.get_all_positions(current_prices=all_prices)
            
            self.telegram.notify_summary(
                equity=equity,
                daily_pnl_pct=daily_pnl,
                open_positions=positions
            )
        except Exception as e:
            self.logger.warning(f"Erro ao enviar resumo Telegram: {e}")
    
    def force_scalp_trade(self) -> Dict[str, Any]:
        """Força um scalp imediato via comando Telegram"""
        self.logger.info("[AI] FORCE_SCALP: iniciando...")
        
        try:
            # 1. Buscar snapshot de mercado
            self.logger.info("[AI] FORCE_SCALP: buscando snapshot de mercado...")
            user_state = self.client.get_user_state()
            all_prices = self.client.get_all_mids()
            
            equity = float(user_state.get('account_value', 0))
            self.risk_manager.update_equity(equity)
            self.logger.info(f"[AI] FORCE_SCALP: equity atual = ${equity:.2f}")
            
            # 2. Construir contextos de mercado
            self.logger.info("[AI] FORCE_SCALP: construindo contextos de mercado...")
            market_contexts = []
            for pair in self.trading_pairs:
                try:
                    price = all_prices.get(pair)
                    if not price:
                        continue
                    price = float(price)
                    candles = self.client.get_candles(pair, interval="1h", limit=50)
                    
                    context = self.market_context.build_context_for_pair(
                        symbol=pair,
                        current_price=price,
                        candles=candles,
                        funding_rate=None
                    )
                    market_contexts.append(context)
                except Exception as e:
                    self.logger.error(f"[AI] FORCE_SCALP: erro ao construir contexto para {pair}: {e}")
            
            if not market_contexts:
                self.logger.warning("[AI] FORCE_SCALP: nenhum contexto de mercado disponível")
                return {'status': 'error', 'reason': 'Nenhum contexto de mercado disponível'}
            
            self.logger.info(f"[AI] FORCE_SCALP: {len(market_contexts)} contextos construídos")
            
            # 3. Chamar motor SCALP
            self.logger.info("[AI] FORCE_SCALP: consultando IA SCALP (OpenAI)...")
            account_info = {
                'equity': equity,
                'daily_pnl_pct': self.risk_manager.daily_drawdown_pct,
                'daily_drawdown_pct': self.risk_manager.daily_drawdown_pct
            }
            
            risk_limits = {
                'risk_per_trade_pct': self.risk_manager.risk_per_trade_pct,
                'max_daily_drawdown_pct': self.risk_manager.max_daily_drawdown_pct,
                'max_open_trades': self.risk_manager.max_open_trades,
                'max_leverage': self.risk_manager.max_leverage
            }
            
            scalp_decisions = self.ai_engine.scalp_engine.get_scalp_decision(
                market_contexts=market_contexts,
                account_info=account_info,
                open_positions=self.position_manager.get_all_positions(),
                risk_limits=risk_limits
            )
            
            # 4. Processar decisão
            if not scalp_decisions:
                self.logger.info("[AI] FORCE_SCALP: IA não retornou decisões")
                return {'status': 'hold', 'reason': 'IA SCALP não retornou decisões'}
            
            # Pega primeira decisão
            decision = scalp_decisions[0]
            self.logger.info(f"[AI] FORCE_SCALP: decisão recebida -> {decision}")
            
            if decision.get('action') == 'hold':
                reason = decision.get('reason', 'Sem setup claro')
                self.logger.info(f"[AI] FORCE_SCALP: HOLD detectado - {reason}")
                return {'status': 'hold', 'reason': reason}
            
            # 5. Executar trade com risco reduzido (0.5x)
            if decision.get('action') == 'open':
                self.logger.info(f"[AI] FORCE_SCALP: trade detectado -> {decision.get('symbol')} {decision.get('side')}")
                
                symbol = decision.get('symbol')
                
                # Aplicar filtro de volatilidade com candles
                self.logger.info("[AI] FORCE_SCALP: aplicando filtros anti-overtrading...")
                
                # Busca candles para filtro de volatilidade
                try:
                    candles = self.client.get_candles(symbol, interval="1h", limit=20)
                    can_trade, reason = self.ai_engine.scalp_engine.filters.check_volatility(candles, symbol)
                    
                    if not can_trade:
                        self.logger.warning(f"[RISK] FORCE_SCALP bloqueado: {reason}")
                        return {'status': 'blocked', 'reason': f"Filtro de volatilidade: {reason}"}
                except Exception as e:
                    self.logger.warning(f"[AI] FORCE_SCALP: erro ao verificar volatilidade: {e}")
                
                # Aplicar multiplicador de risco reduzido
                decision['_risk_multiplier'] = 0.5
                decision['_force_scalp'] = True
                
                # Tentar executar
                try:
                    self.logger.info("[AI] FORCE_SCALP: filtros OK, executando trade...")
                    self._execute_open(decision, all_prices)
                    self.logger.info("[AI] FORCE_SCALP: trade executado com sucesso")
                    return {
                        'status': 'executed',
                        'decision': decision
                    }
                except Exception as e:
                    self.logger.error(f"[AI] FORCE_SCALP: bloqueado pelo RiskManager - {e}")
                    return {'status': 'blocked', 'reason': str(e)}
            
            self.logger.warning(f"[AI] FORCE_SCALP: decisão não é de abertura - action={decision.get('action')}")
            return {'status': 'hold', 'reason': 'Decisão não é de abertura'}
            
        except Exception as e:
            self.logger.error(f"[AI] FORCE_SCALP: erro fatal - {e}", exc_info=True)
            return {'status': 'error', 'reason': str(e)}
    
    def _run_iteration(self):
        """Executa uma iteração completa do bot"""
        
        if self.paused:
            self.logger.info("⏸️ Bot PAUSADO pelo usuário via Telegram. Aguardando...")
            return
        
        # PARTE 2: Contador de novos trades por iteração (máximo 1)
        new_trades_this_iteration = 0

        # 1. Buscar dados em tempo real
        self.logger.info("📊 Buscando dados de mercado...")
        
        try:
            user_state = self.client.get_user_state()
            all_prices = self.client.get_all_mids()
            positions = self.client.get_positions()
            
        except NotImplementedError:
            self.logger.error("⚠️  Client não implementado! Por favor, adapte HyperliquidBotClient para usar os clients reais do projeto.")
            self.logger.info("Veja os comentários no código e implemente as funções usando hyperliquid.info e hyperliquid.exchange")
            time.sleep(10)
            return
        
        # 2. Atualizar estado de risco
        equity = float(user_state.get('account_value', 0))
        self.risk_manager.update_equity(equity)
        
        # 3. Sincronizar posições
        self.position_manager.sync_with_exchange(positions)
        self.risk_manager.update_open_positions(self.position_manager.get_positions_count())
        
        self.logger.info(self.risk_manager.get_status_summary())
        
        # 4. Construir contexto de mercado
        self.logger.info("🔍 Analisando mercado...")
        market_contexts = []
        
        for pair in self.trading_pairs:
            try:
                price = all_prices.get(pair)
                if not price:
                    self.logger.warning(f"{pair}: Preço não disponível")
                    continue
                
                # Converte preço para float com segurança
                try:
                    price = float(price)
                except (ValueError, TypeError):
                    self.logger.warning(f"{pair}: Preço inválido: {price}")
                    continue
                
                candles = self.client.get_candles(pair, interval="1h", limit=50)
                
                # DEBUG: Log do formato de candle
                if candles:
                    self.logger.debug(f"[DEBUG CANDLES] {pair} formato: {list(candles[0].keys())}")
                
                # Busca funding rate
                try:
                    funding_rates = self.client.get_funding_rates()
                    funding = next((f['funding_rate'] for f in funding_rates if f['coin'] == pair), None)
                except:
                    funding = None
                
                context = self.market_context.build_context_for_pair(
                    symbol=pair,
                    current_price=price,
                    candles=candles,
                    funding_rate=funding
                )
                
                # ========== PHASE 2: TECHNICAL ANALYSIS ==========
                from bot.phase2 import TechnicalAnalysis
                
                if not hasattr(self, 'technical_analysis'):
                    self.technical_analysis = TechnicalAnalysis()
                
                # NORMALIZA CANDLES ANTES DA ANÁLISE
                normalized_candles = self.technical_analysis.normalize_candles(candles, logger_instance=self.logger)
                
                if not normalized_candles:
                    self.logger.warning(f"[TECHNICAL ANALYSIS] {pair}: Nenhum candle válido após normalização. Pulando análise técnica.")
                    structure = None
                    patterns = []
                    ema = None
                    liquidity = None
                else:
                    # Análise de estrutura
                    structure = self.technical_analysis.analyze_structure(normalized_candles, "15m")
                    
                    # Padrões
                    patterns = self.technical_analysis.detect_patterns(normalized_candles)
                    
                    # EMA confluence (opcional)
                    ema = self.technical_analysis.check_ema_confluence(normalized_candles)
                    
                    # Liquidez
                    liquidity = self.technical_analysis.identify_liquidity_zones(normalized_candles)
                
                # Adiciona ao contexto
                context['phase2'] = {
                    'structure': structure,
                    'patterns': patterns,
                    'ema': ema,
                    'liquidity': liquidity
                }
                # ================================================
                
                market_contexts.append(context)
                
            except Exception as e:
                self.logger.error(f"{pair}: Erro ao construir contexto: {e}")
        
        if not market_contexts:
            self.logger.warning("Nenhum contexto de mercado disponível, pulando iteração")
            return
        
        # 5. Verificar stops/TPs das posições abertas
        self.logger.info("🎯 Verificando stops/TPs...")
        self.position_manager.log_positions_summary(all_prices)
        
        # ========== PHASE 2: POSITION MANAGER PRO ==========
        # Gestão avançada: breakeven, parciais, trailing
        from bot.phase2 import PositionManagerPro
        
        # Instancia Position Manager Pro (singleton-like)
        if not hasattr(self, 'position_manager_pro'):
            self.position_manager_pro = PositionManagerPro(
                position_manager=self.position_manager,
                config={
                    'breakeven_at_r': 1.0,
                    'partial_at_r': 2.0,
                    'partial_pct': 0.5,
                    'trailing_at_r': 3.0,
                    'trailing_distance_pct': 1.0
                }
            )
        
        # Analisa cada posição para gestão
        management_decisions = []
        for position_dict in self.position_manager.get_all_positions():
            symbol = position_dict['symbol']
            current_price = all_prices.get(symbol)
            
            if not current_price:
                continue
            
            # Converte para float
            try:
                current_price = float(current_price)
            except:
                continue
            
            # Analisa e sugere gestão
            manage_suggestion = self.position_manager_pro.analyze_position(
                symbol=symbol,
                current_price=current_price
            )
            
            if manage_suggestion:
                management_decisions.append(manage_suggestion)
                self.logger.info(f"[PHASE2 PRO] 💎 Gestão sugerida para {symbol}: "
                               f"{manage_suggestion['manage_decision']['reason']}")
        
        # ================================================
        
        close_actions = self.position_manager.check_stops(all_prices)
        
        for action in close_actions:
            self._execute_close(action, all_prices)
        
        # 6. Consultar IA via AIManager (ORQUESTRADOR)
        
        # Monta snapshot do mercado para o AIManager
        market_snapshot = {
            'contexts': market_contexts,
            'prices': all_prices,
            'timestamp': time.time()
        }
        
        # Dados da conta para as IAs
        account_info = {
            'equity': equity,
            'daily_pnl_pct': self.risk_manager.daily_drawdown_pct,
            'daily_drawdown_pct': self.risk_manager.daily_drawdown_pct
        }
        
        risk_limits = {
            'risk_per_trade_pct': self.risk_manager.risk_per_trade_pct,
            'max_daily_drawdown_pct': self.risk_manager.max_daily_drawdown_pct,
            'max_open_trades': self.risk_manager.max_open_trades,
            'max_leverage': self.risk_manager.max_leverage
        }
        
        # === SWING (Claude) ===
        swing_decisions = []
        if self.ai_manager.should_call_swing(market_snapshot):
            self.logger.info("🤖 [AI MANAGER] Decidiu chamar SWING (Claude)...")
            
            try:
                all_decisions = self.ai_engine.swing_engine.decide(
                    market_contexts=market_contexts,
                    account_info=account_info,
                    open_positions=self.position_manager.get_all_positions(),
                    risk_limits=risk_limits
                )
                
                # Filtra e taggeia
                for dec in all_decisions:
                    if dec.get('action') not in ('hold', 'skip'):
                        dec['source'] = 'claude_swing'
                        dec['style'] = 'swing'
                        swing_decisions.append(dec)
                
                self.ai_manager.register_swing_call()
                self.last_swing_decisions = swing_decisions
                
            except Exception as e:
                self.logger.error(f"Erro ao chamar SWING: {e}")
        else:
            # Mantém cache se não for hora de chamar
            swing_decisions = self.last_swing_decisions

        # === SCALP (OpenAI) ===
        scalp_decisions = []
        if self.openai_enabled:
            # Incrementa contador de iterações
            self.iteration_counter += 1
            
            # Só analisa se chegou no intervalo (ex: 1 a cada 5 iterações)
            should_analyze_scalp = (self.iteration_counter % self.openai_analysis_interval == 0)
            
            if not should_analyze_scalp:
                self.logger.debug(f"[AI] Pulando análise OpenAI SCALP (iteração {self.iteration_counter}/{self.openai_analysis_interval})")
                scalp_decisions = self.last_scalp_decisions  # Usa cache
            else:
                self.logger.info(f"⚡ [AI] Executando análise OpenAI SCALP (iteração {self.iteration_counter})")
                
                # 1. Filtra candidatos (exclui posições abertas)
                all_symbols = self.trading_pairs
                open_positions_list = self.position_manager.get_all_positions()
                
                scalp_candidates = self.ai_manager.filter_symbols_for_scalp(
                    all_symbols, open_positions_list, market_snapshot
                )
                
                # 2. Para cada candidato, decide se chama IA
                for idx, symbol in enumerate(scalp_candidates):
                    if self.ai_manager.should_call_scalp(symbol, market_snapshot):
                        # Delay de 3s entre símbolos (exceto o primeiro)
                        if idx > 0:
                            self.logger.debug("[AI MANAGER] Aguardando 3s entre análises...")
                            time.sleep(3)
                        
                        self.logger.info(f"⚡ [AI MANAGER] Analisando SCALP para {symbol}...")
                        
                        # Filtra contexto apenas para este símbolo
                        symbol_context = [ctx for ctx in market_contexts if ctx['symbol'] == symbol]
                        
                        if not symbol_context:
                            continue
                            
                        try:
                            decisions = self.ai_engine.scalp_engine.get_scalp_decision(
                                market_contexts=symbol_context,
                                account_info=account_info,
                                open_positions=open_positions_list,
                                risk_limits=risk_limits
                            )
                            
                            if decisions:
                                # Taggeia
                                for dec in decisions:
                                    if dec.get('action') not in ('hold', 'skip'):
                                        dec['source'] = 'openai_scalp'
                                        dec['style'] = 'scalp'
                                        scalp_decisions.append(dec)
                                    
                                self.ai_manager.register_scalp_call(symbol)
                                
                        except Exception as e:
                            self.logger.error(f"Erro ao chamar SCALP para {symbol}: {e}")
                
                # Atualiza cache
                self.last_scalp_decisions = scalp_decisions
            
            # Atualiza cache de scalp (opcional, pois scalp é pontual)
            if scalp_decisions:
                self.last_scalp_decisions = scalp_decisions
            else:
                # Limpa cache antigo se não houve novas decisões, para não repetir trades velhos
                self.last_scalp_decisions = []
        
        # Combina decisões de ambos os motores + gestão de posição
        ai_decisions = swing_decisions + scalp_decisions + management_decisions
        
        # ========== PHASE 2: PARSE & QUALITY GATE ==========
        from bot.phase2 import DecisionParser, QualityGate
        
        # Instancia Quality Gate (singleton-like)
        if not hasattr(self, 'quality_gate'):
            self.quality_gate = QualityGate({
                'min_confidence': 0.80,
                'max_candle_body_pct': 3.0,
                'min_confluences': 2
            })
        
        # Parse e valida todas as decisões
        validated_decisions = []
        for raw_decision in ai_decisions:
            # Parse com validação
            parsed = DecisionParser.parse_ai_decision(raw_decision, raw_decision.get('source', 'unknown'))
            
            if not parsed:
                self.logger.warning(f"[PHASE2] Decisão inválida ignorada: {raw_decision.get('symbol', 'UNKNOWN')}")
                continue
            
            # Sanitiza (remove NaN/None)
            parsed = DecisionParser.sanitize_decision(parsed)
            
            # Quality Gate (só para action=open)
            if parsed.get('action') == 'open':
                # Busca contexto de mercado e MI
                symbol = parsed.get('symbol')
                market_ctx = market_snapshot.get(symbol, {})
                
                # Avalia Quality Gate
                gate_result = self.quality_gate.evaluate(
                    decision=parsed,
                    market_context=market_ctx,
                    market_intelligence=None  # TODO: integrar MI
                )
                
                if not gate_result.approved:
                    # REJEITADO
                    self.quality_gate.log_rejection(symbol, gate_result)
                    self.logger.warning(f"[PHASE2] 🚫 {symbol} rejeitado pelo Quality Gate")
                    continue
                
                # APROVADO - atualiza confidence ajustada
                parsed['confidence'] = gate_result.confidence_score
                self.logger.info(f"[PHASE2] ✅ {symbol} aprovado: confidence={gate_result.confidence_score:.2f}")
            
            validated_decisions.append(parsed)
        
        # Substitui decisões originais pelas validadas
        ai_decisions = validated_decisions
        # ================================================
        
        # 7. Executar decisões da IA
        for decision in ai_decisions:
            action = decision.get('action', '')
            symbol = decision.get('symbol', 'UNKNOWN')
            
            if action == 'open':
                # PARTE 2: Limitar 1 trade por iteração
                if new_trades_this_iteration >= 1:
                    self.logger.info("🛡️ Limite de 1 trade por iteração atingido. Ignorando demais sinais.")
                    break
                
                # Executar abertura
                success = self._execute_open(decision, all_prices)
                if success:
                    new_trades_this_iteration += 1
            
            elif action == 'manage':
                # PARTE 3: AI Management System
                self._execute_manage(decision, all_prices)
                
            elif action == 'increase':
                self._execute_increase(decision, all_prices)
                
            elif action == 'decrease':
                self._execute_decrease(decision, all_prices)
                
            elif action == 'close':
                # IA recomendou fechar posição específica
                symbol = decision['symbol']
                if self.position_manager.has_position(symbol):
                    position = self.position_manager.get_position(symbol)
                    
                    # --- CHURNING PROTECTION (Proteção contra giro excessivo) ---
                    from datetime import datetime, timezone
                    
                    # Calcula tempo de posição aberta
                    now = datetime.now(timezone.utc)
                    # Garante que opened_at tem timezone
                    if position.opened_at.tzinfo is None:
                        position.opened_at = position.opened_at.replace(tzinfo=timezone.utc)
                        
                    time_open = (now - position.opened_at).total_seconds()
                    
                    # Calcula PnL atual
                    current_price = all_prices.get(symbol, position.entry_price)
                    pnl_pct = position.get_unrealized_pnl_pct(current_price)
                    
                    # Regras Dinâmicas baseadas na Estratégia
                    strategy = getattr(position, 'strategy', 'swing')
                    
                    if strategy == 'scalp':
                        # SCALP: Mais permissivo para sair rápido
                        min_time = 60   # 1 minuto
                        min_pnl = 0.3   # 0.3%
                    else:
                        # SWING: Mais rigoroso para segurar
                        min_time = 180  # 3 minutos
                        min_pnl = 1.0   # 1%
                    
                    if time_open < min_time and abs(pnl_pct) < min_pnl:
                        self.logger.warning(
                            f"🛡️ Proteção ({strategy.upper()}): Ignorando fechamento de {symbol}. "
                            f"Tempo: {time_open:.0f}s (<{min_time}s), PnL: {pnl_pct:.2f}% (<{min_pnl}%)"
                        )
                        continue
                    # ---------------------------
                    
                    self._execute_close({
                        'symbol': symbol,
                        'action': 'close',
                        'reason': 'ai_recommendation',
                        'side': position.side,
                        'current_price': current_price
                    }, all_prices)
        
        self.logger.info("✅ Iteração completa")

    def _execute_increase(self, decision: Dict[str, Any], prices: Dict[str, float]):
        """Aumenta posição existente (DCA/Piramidagem)"""
        symbol = decision['symbol']
        quantity_pct = decision.get('quantity_pct', 0.5) # Default 50% de uma entrada normal
        
        if not self.position_manager.has_position(symbol):
            return
            
        pos = self.position_manager.get_position(symbol)
        current_price = prices.get(symbol)
        
        # Calcula tamanho do aumento
        # Baseado no tamanho de uma entrada padrão * quantity_pct
        base_calc = self.risk_manager.calculate_position_size(
            symbol=symbol,
            entry_price=current_price,
            stop_loss_pct=self.config['default_stop_pct'],
            risk_multiplier=1.0 # Increase sempre usa risco base ou até menor? Vamos manter 1.0 por enquanto
        )
        
        if not base_calc:
            return
            
        add_size = base_calc['size'] * quantity_pct
        
        # Arredonda size
        sz_decimals = self.client.sz_decimals_cache.get(symbol, 4)
        add_size = round(add_size, sz_decimals)
        
        self.logger.info(f"➕ AUMENTANDO POSIÇÃO: {symbol} (+{add_size}) | Motivo: {decision.get('comment')}")
        
        if not self.live_trading:
            # Simulação: Atualiza PM
            new_size = pos.size + add_size
            # Preço médio ponderado
            total_val = (pos.size * pos.entry_price) + (add_size * current_price)
            new_entry = total_val / new_size
            self.position_manager.update_position(symbol, new_size, new_entry)
            return

        # Executa na exchange
        try:
            result = self.client.place_order(
                coin=symbol,
                is_buy=(pos.side == 'long'),
                size=add_size,
                price=current_price,
                order_type="market"
            )
            
            if result.get('status') == 'ok':
                # Atualiza PM (simplificado, ideal seria pegar do fill)
                new_size = pos.size + add_size
                total_val = (pos.size * pos.entry_price) + (add_size * current_price)
                new_entry = total_val / new_size
                self.position_manager.update_position(symbol, new_size, new_entry)
        except Exception as e:
            self.logger.error(f"Erro ao aumentar posição: {e}")

    def _execute_decrease(self, decision: Dict[str, Any], prices: Dict[str, float]):
        """Reduz posição existente (Parcial)"""
        symbol = decision['symbol']
        quantity_pct = decision.get('quantity_pct', 0.5) # Default 50% da posição atual
        
        if not self.position_manager.has_position(symbol):
            return
            
        pos = self.position_manager.get_position(symbol)
        current_price = prices.get(symbol)
        
        # Calcula tamanho da redução
        reduce_size = pos.size * quantity_pct
        
        # Arredonda size
        sz_decimals = self.client.sz_decimals_cache.get(symbol, 4)
        reduce_size = round(reduce_size, sz_decimals)
        
        if reduce_size <= 0:
            return

        self.logger.info(f"✂️ REALIZANDO PARCIAL: {symbol} (-{reduce_size}) | Motivo: {decision.get('comment')}")
        
        if not self.live_trading:
            # Simulação
            new_size = pos.size - reduce_size
            if new_size < 0.0001:
                self.position_manager.remove_position(symbol)
            else:
                self.position_manager.update_position(symbol, new_size, pos.entry_price)
            return

        # Executa na exchange (Reduce Only)
        try:
            # Inverte lado para fechar
            is_buy_close = (pos.side == 'short')
            
            result = self.client.place_order(
                coin=symbol,
                is_buy=is_buy_close,
                size=reduce_size,
                price=current_price,
                order_type="market",
                reduce_only=True
            )
            
            if result.get('status') == 'ok':
                new_size = pos.size - reduce_size
                if new_size < 0.0001:
                    self.position_manager.remove_position(symbol)
                else:
                    self.position_manager.update_position(symbol, new_size, pos.entry_price)
        except Exception as e:
            self.logger.error(f"Erro ao realizar parcial: {e}")
    
    def _execute_open(self, decision: Dict[str, Any], prices: Dict[str, float]) -> bool:
        """Executa abertura de posição - USA VALORES DA IA
        Returns: True se posição foi aberta com sucesso, False caso contrário
        """
        symbol = decision['symbol']
        side = decision.get('side', 'long')
        size_usd = decision.get('size_usd', 20)
        reason = decision.get('reason', 'AI decision')
        leverage = decision.get('leverage', 5)   # IA decide leverage
        stop_loss_price = decision.get('stop_loss_price')  # IA decide SL
        take_profit_price = decision.get('take_profit_price')  # IA decide TP
        confidence = decision.get('confidence', 0.0)
        strategy = decision.get("setup_name") or decision.get("style") or "unknown"
        source = decision.get("source", "unknown")

        sl_str = f"{stop_loss_price:.2f}" if stop_loss_price is not None else "N/A"
        tp_str = f"{take_profit_price:.2f}" if take_profit_price is not None else "N/A"

        self.logger.info(
            f"[EXECUTE_OPEN] symbol={symbol} side={side} size_usd={size_usd} "
            f"lev={leverage} SL=${sl_str} TP=${tp_str} conf={confidence:.2f} "
            f"strategy={strategy} source={source} reason={reason}"
        )
        
        # PARTE 5: Quality Gate - Verificar confiança mínima
        if confidence < 0.60:
            self.logger.warning(f"[RISK] Sinal fraco descartado: {symbol} confidence={confidence:.2f} < 0.60")
            return False
        
        # Verifica se já tem posição
        if self.position_manager.has_position(symbol):
            self.logger.warning(f"{symbol}: Já existe posição aberta, ignorando")
            return False
        
        # PARTE 2: Bloquear trades opostos no mesmo símbolo
        existing_pos = self.position_manager.get_position(symbol)
        if existing_pos and existing_pos.side != side:
            self.logger.warning(
                f"[RISK] Trade bloqueado por conflito de direção: "
                f"Posição existente {existing_pos.side.upper()} vs novo sinal {side.upper()}"
            )
            return False
        
        # PARTE 2: Verificar limite efetivo de posições
        current_positions = self.position_manager.get_positions_count()
        if current_positions >= self.effective_max_positions:
            self.logger.warning(
                f"[RISK] Limite de posições atingido: {current_positions}/{self.effective_max_positions}"
            )
            return False
            
        # Obtém preço atual
        current_price = prices.get(symbol)
        if not current_price:
            self.logger.error(f"{symbol}: Preço não disponível")
            return False
            
        try:
            current_price = float(current_price)
        except:
            self.logger.error(f"{symbol}: Preço inválido")
            return False

        # 1. Define multiplicador de risco baseado no estilo
        risk_multiplier = 1.0
        if strategy == 'scalp' or source == 'openai_scalp':
            risk_multiplier = 0.5
            self.logger.info(f"⚡ SCALP detectado: Reduzindo risco para {risk_multiplier}x")
            
        # 2. Calcula SL em % para o Risk Manager
        # PARTE 1: FIX CRÍTICO - Extração segura de stop_loss_pct
        stop_loss_pct = decision.get("stop_loss_pct")
        if stop_loss_pct is None and stop_loss_price and current_price > 0:
            # Calcula % a partir do preço
            if side == 'long':
                stop_loss_pct = ((current_price - stop_loss_price) / current_price) * 100
            else:
                stop_loss_pct = ((stop_loss_price - current_price) / current_price) * 100
        
        # Se ainda for None, usa default
        if stop_loss_pct is None:
            stop_loss_pct = 2.0
        
        sl_pct = stop_loss_pct
        
        # 3. Calcula Position Size com Risk Manager
        position_data = self.risk_manager.calculate_position_size(
            symbol=symbol,
            entry_price=current_price,
            stop_loss_pct=sl_pct,
            risk_multiplier=risk_multiplier
        )
        
        if not position_data:
            self.logger.warning(f"{symbol}: Risk Manager bloqueou o trade")
            return False
            
        # Usa valores calculados pelo Risk Manager
        size = position_data['size']
        leverage = position_data['leverage']
        
        # Recalcula TP em % para o Position Manager
        take_profit_pct = decision.get("take_profit_pct")
        if take_profit_pct is None and take_profit_price:
            if side == 'long':
                take_profit_pct = ((take_profit_price - current_price) / current_price) * 100
            else:
                take_profit_pct = ((current_price - take_profit_price) / current_price) * 100
        
        if take_profit_pct is None:
            take_profit_pct = 6.0  # Default
        
        self.logger.info(f"💰 Size calculado: {size:.6f} {symbol}")
        
        # Modo DRY RUN
        if not self.live_trading:
            self.logger.warning("⚠️  DRY RUN MODE - Ordem NÃO executada na exchange")
            self.logger.info(f"[SIMULAÇÃO] Abrindo ISOLATED {side.upper()} {symbol} @ ${current_price:.2f}")
            
            self.position_manager.add_position(
                symbol=symbol,
                side=side,
                entry_price=current_price,
                size=size,
                leverage=leverage,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                strategy=strategy
            )
            return True
            
        # Modo LIVE
        try:
            # PARTE 1: Garantir margem ISOLATED
            self.logger.info(f"🚀 Abrindo posição ISOLATED {symbol}...")
            
            # 1. Ajusta alavancagem para ISOLATED
            self.logger.info(f"⚙️  Ajustando leverage para {leverage}x ISOLATED...")
            self.client.adjust_leverage(symbol, leverage, is_cross=False)  # ISOLATED = False
            
            # 2. Envia ordem
            self.logger.info(f"📤 Enviando ordem MARKET {side.upper()}...")
            result = self.client.place_order(
                coin=symbol,
                is_buy=(side == 'long'),
                size=size,
                price=current_price,
                order_type="market",
                leverage=leverage
            )
            
            self.logger.info(f"✅ Ordem executada: {result}")
            
            # Verifica sucesso
            if result.get('status') == 'ok':
                self.logger.info(f"✅ Posição ISOLATED adicionada: {symbol} {side.upper()}")
                self.position_manager.add_position(
                    symbol=symbol,
                    side=side,
                    entry_price=current_price,
                    size=size,
                    leverage=leverage,
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                    strategy=strategy
                )
                
                # 📱 Notifica via Telegram com informações completas
                self.telegram.notify_position_opened(
                    symbol=symbol,
                    side=side,
                    entry_price=current_price,
                    size=size,
                    leverage=leverage,
                    strategy=strategy,
                    confidence=confidence,
                    reason=reason,
                    source=source,
                    margin_type="ISOLATED"  # PARTE 6: Mostrar margem no Telegram
                )
                return True

            else:
                self.logger.error(f"❌ Falha ao abrir posição: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Erro crítico ao executar ordem: {e}", exc_info=True)
            self.telegram.notify_error("Erro ao abrir posição", f"{symbol}: {str(e)}")
            return False
    
    def _execute_manage(self, decision: Dict[str, Any], prices: Dict[str, float]):
        """PARTE 3: Executa gestão de posição decidida pela IA
        Suporta: parciais, ajuste de SL/TP, breakeven, trailing stop
        """
        symbol = decision.get('symbol')
        manage_decision = decision.get('manage_decision', {})
        
        if not symbol or not manage_decision:
            self.logger.warning("[AI MANAGE] Decisão inválida: faltam dados")
            return
        
        # Verifica se tem posição
        if not self.position_manager.has_position(symbol):
            self.logger.warning(f"[AI MANAGE] {symbol}: Sem posição para gerenciar")
            return
        
        position = self.position_manager.get_position(symbol)
        current_price = prices.get(symbol)
        
        if not current_price:
            self.logger.error(f"[AI MANAGE] {symbol}: Preço não disponível")
            return
        
        try:
            current_price = float(current_price)
        except:
            self.logger.error(f"[AI MANAGE] {symbol}: Preço inválido")
            return
        
        reason = manage_decision.get('reason', 'AI management')
        
        self.logger.info(f"🧠 [AI MANAGE] {symbol}: {reason}")
        
        # 1. PARCIAL (close_pct)
        close_pct = manage_decision.get('close_pct', 0)
        if close_pct > 0:
            self.logger.info(f"📊 Fechando {close_pct*100:.0f}% da posição...")
            
            reduce_size = position.size * close_pct
            sz_decimals = self.client.sz_decimals_cache.get(symbol, 4)
            reduce_size = round(reduce_size, sz_decimals)
            
            if not self.live_trading:
                # Simulação
                new_size = position.size - reduce_size
                if new_size < 0.0001:
                    self.position_manager.remove_position(symbol)
                else:
                    self.position_manager.update_position(symbol, new_size, position.entry_price)
            else:
                # Live
                try:
                    is_buy_close = (position.side == 'short')
                    result = self.client.place_order(
                        coin=symbol,
                        is_buy=is_buy_close,
                        size=reduce_size,
                        price=current_price,
                        order_type="market",
                        reduce_only=True
                    )
                    
                    if result.get('status') == 'ok':
                        new_size = position.size - reduce_size
                        if new_size < 0.0001:
                            self.position_manager.remove_position(symbol)
                        else:
                            self.position_manager.update_position(symbol, new_size, position.entry_price)
                except Exception as e:
                    self.logger.error(f"[AI MANAGE] Erro ao fechar parcial: {e}")
        
        # 2. AJUSTE DE STOP LOSS
        new_stop_price = manage_decision.get('new_stop_price')
        if new_stop_price:
            # Calcula novo SL em %
            if position.side == 'long':
                new_sl_pct = ((current_price - new_stop_price) / current_price) * 100
            else:
                new_sl_pct = ((new_stop_price - current_price) / current_price) * 100
            
            # Detecta breakeven
            if abs(new_stop_price - position.entry_price) < (position.entry_price * 0.001):  # 0.1% tolerance
                self.logger.info(f"🎯 BREAKEVEN detectado: Movendo SL para entry @ ${position.entry_price:.2f}")
            # Detecta trailing
            elif (position.side == 'long' and new_stop_price > position.entry_price) or \
                 (position.side == 'short' and new_stop_price < position.entry_price):
                self.logger.info(f"📈 TRAILING STOP: Movendo SL para ${new_stop_price:.2f} (no lucro)")
            else:
                self.logger.info(f"🛡️ Ajustando SL para ${new_stop_price:.2f} ({new_sl_pct:.2f}%)")
            
            self.position_manager.update_stop_loss(symbol, new_sl_pct)
        
        # 3. AJUSTE DE TAKE PROFIT
        new_tp_price = manage_decision.get('new_take_profit_price')
        if new_tp_price:
            if position.side == 'long':
                new_tp_pct = ((new_tp_price - current_price) / current_price) * 100
            else:
                new_tp_pct = ((current_price - new_tp_price) / current_price) * 100
            
            self.logger.info(f"🎯 Ajustando TP para ${new_tp_price:.2f} ({new_tp_pct:.2f}%)")
            self.position_manager.update_take_profit(symbol, new_tp_pct)
    
    def _execute_close(self, action: Dict[str, Any], prices: Dict[str, float]):

        """Executa fechamento de posição"""
        symbol = action['symbol']
        reason = action.get('reason', 'unknown')
        
        position = self.position_manager.get_position(symbol)
        if not position:
            self.logger.warning(f"{symbol}: Posição não encontrada no gerenciamento")
            return
        
        current_price = prices.get(symbol, action.get('current_price'))
        
        # Converte current_price para float com segurança
        try:
            current_price = float(current_price)
        except (ValueError, TypeError):
            self.logger.error(f"{symbol}: Preço inválido para fechar posição")
            return
        
        pnl_pct = position.get_unrealized_pnl_pct(current_price) if current_price else 0
        
        self.logger.info(f"\n{'='*50}")
        self.logger.info(f"🔴 FECHANDO POSIÇÃO: {symbol}")
        self.logger.info(f"Motivo: {reason.upper()} | PnL: {pnl_pct:+.2f}%")
        self.logger.info(f"{'='*50}")
        
        # Modo DRY RUN
        if not self.live_trading:
            self.logger.warning("⚠️  DRY RUN MODE - Ordem de fechamento NÃO executada")
            self.logger.info(f"[SIMULAÇÃO] Fechando {symbol} @ ${current_price:.2f}")
            self.position_manager.remove_position(symbol)
            return
        
        # MODO LIVE TRADING
        try:
            # Fecha posição com ordem market reduce_only
            is_buy = (position.side == 'short')  # Se está short, compra para fechar
            
            self.logger.info(f"📤 Enviando ordem de fechamento MARKET...")
            result = self.client.place_order(
                coin=symbol,
                is_buy=is_buy,
                size=abs(float(position.size)),  # Garante size positivo
                price=current_price,  # Para market order, preço é referência
                order_type="market",  # MARKET é mais confiável para fechar
                reduce_only=True  # Importante: só reduz posição existente
            )
            
            self.logger.info(f"✅ Posição fechada: {result}")
            
            # Calcula PnL em USD (aproximado)
            pnl_usd = (pnl_pct / 100) * (position.size * position.entry_price)
            
            # 📱 Notifica via Telegram
            if reason == 'stop_loss':
                self.telegram.notify_sl_hit(
                    symbol=symbol,
                    side=position.side,
                    entry_price=position.entry_price,
                    sl_price=current_price,
                    pnl_pct=pnl_pct
                )
            elif reason == 'take_profit':
                self.telegram.notify_tp_hit(
                    symbol=symbol,
                    side=position.side,
                    entry_price=position.entry_price,
                    tp_price=current_price,
                    pnl_pct=pnl_pct
                )
            else:
                self.telegram.notify_position_closed(
                    symbol=symbol,
                    side=position.side,
                    entry_price=position.entry_price,
                    exit_price=current_price,
                    pnl_pct=pnl_pct,
                    pnl_usd=pnl_usd,
                    reason=reason
                )
            
            self.position_manager.remove_position(symbol)
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao fechar posição: {e}", exc_info=True)
            self.telegram.notify_error("Erro ao fechar posição", f"{symbol}: {str(e)}")
    
    def _shutdown(self):
        """Encerra bot de forma segura"""
        self.logger.info("\n🛑 Encerrando bot...")
        
        try:
            # Cancela todas as ordens pendentes
            if self.live_trading:
                self.logger.info("Cancelando ordens pendentes...")
                self.client.cancel_all_orders()
        except Exception as e:
            self.logger.error(f"Erro ao cancelar ordens: {e}")
        
        self.logger.info("Bot encerrado. Até a próxima! 👋")


# ==================== MAIN ====================
def main():
    """Função principal"""
    
    # Carrega variáveis de ambiente
    load_dotenv()
    
    # Configuração de logging
    setup_logging(os.getenv('LOG_LEVEL', 'INFO'))
    
    logger = logging.getLogger(__name__)
    
    # Carrega configuração
    config = {
        'network': os.getenv('HYPERLIQUID_NETWORK', 'mainnet'),
        'anthropic_api_key': os.getenv('ANTHROPIC_API_KEY'),
        'ai_model': os.getenv('AI_MODEL', 'claude-3-5-haiku-20241022'),
        'openai_api_key': os.getenv('OPENAI_API_KEY'),
        'openai_model_scalp': os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
        'live_trading': os.getenv('LIVE_TRADING', 'false').lower() == 'true',
        'risk_per_trade_pct': float(os.getenv('RISK_PER_TRADE_PCT', '5.0')),  # ← CORRIGIDO: 5% em vez de 10%
        'max_daily_drawdown_pct': float(os.getenv('MAX_DAILY_DRAWDOWN_PCT', '10.0')),
        'max_open_trades': int(os.getenv('MAX_OPEN_TRADES', '10')),
        'max_leverage': int(os.getenv('MAX_LEVERAGE', '50')),
        'min_notional': float(os.getenv('MIN_NOTIONAL', '0.5')),
        'default_stop_pct': float(os.getenv('DEFAULT_STOP_PCT', '2.0')),
        'default_tp_pct': float(os.getenv('DEFAULT_TP_PCT', '4.0')),
        'loop_sleep_seconds': int(os.getenv('TRADING_LOOP_SLEEP_SECONDS', '60')),  # Aumentado para 60s
        'trading_pairs': os.getenv('PAIRS_TO_TRADE', 'BTCUSDC,ETHUSDC,SOLUSDC').split(','),
        
        # ===== CONFIGURAÇÕES ANTI-OVERTRADING =====
        'action_cooldown_seconds': int(os.getenv('ACTION_COOLDOWN_SECONDS', '300')),  # 5 min entre ações no mesmo ativo
        'min_confidence_open': float(os.getenv('MIN_CONFIDENCE_OPEN', '0.75')),       # Confiança mín para abrir
        'min_confidence_adjust': float(os.getenv('MIN_CONFIDENCE_ADJUST', '0.82')),   # Confiança mín para increase/decrease
        'max_adjustments_per_iteration': int(os.getenv('MAX_ADJUSTMENTS_PER_ITERATION', '1')),  # Máx 1 ajuste por ciclo
        'openai_analysis_interval': int(os.getenv('OPENAI_ANALYSIS_INTERVAL', '5')),  # Analisa 1 a cada N iterações (reduz rate limit)
        
        # ===== TELEGRAM NOTIFIER =====
        'telegram_bot_token': os.getenv('TELEGRAM_BOT_TOKEN'),
        'telegram_chat_id': os.getenv('TELEGRAM_CHAT_ID'),
    }
    
    # Validações
    if config['live_trading']:
        logger.warning("⚠️" * 20)
        logger.warning("ATENÇÃO: LIVE TRADING ATIVADO!")
        logger.warning("O bot irá executar ordens REAIS na Hyperliquid!")
        logger.warning("⚠️" * 20)
        
        # Confirmação automática para deploy em servidor (Railway)
        logger.info("✅ Modo LIVE confirmado automaticamente (servidor)")
    else:
        logger.info("✅ Modo DRY RUN ativado - apenas simulação (LIVE_TRADING=false)")
    
    # Cria e executa bot
    bot = HyperliquidBot(config)
    bot.run()


if __name__ == "__main__":
    main()
