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
from bot.telegram_interactive import TelegramInteractive


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
        payload = {
            "type": "clearinghouseState",
            "user": self.wallet_address
        }
        
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
    
    def get_all_mids(self) -> Dict[str, float]:
        """Obtém preços mid de todos os pares"""
        payload = {"type": "allMids"}
        
        response = self.requests.post(self.info_url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        # Converte valores para float pois API retorna strings
        return {k: float(v) for k, v in data.items()}
    
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
        # IA só é chamada a cada X minutos para economizar créditos
        self.ai_call_interval = int(os.getenv('AI_CALL_INTERVAL_MINUTES', '15')) * 60  # Em segundos
        self.last_ai_call_time = 0  # Timestamp da última chamada
        self.last_ai_decisions = []  # Cache das últimas decisões da IA
        # ================================================
        
        self.logger.info("=" * 60)
        self.logger.info("🤖 HYPERLIQUID BOT INICIALIZADO")
        self.logger.info(f"Network: {config['network']}")
        self.logger.info(f"Modo: {'LIVE TRADING ⚠️' if self.live_trading else 'DRY RUN (simulação)'}")
        self.logger.info(f"Pares: {', '.join(self.trading_pairs)}")
        self.logger.info(f"IA: {'Ativada ✅' if config.get('anthropic_api_key') else 'Desativada (fallback)'}")
        self.logger.info(f"🛡️ Anti-Overtrading: cooldown={self.action_cooldown_seconds}s, min_conf_adjust={self.min_confidence_adjust}")
        self.logger.info(f"📱 Telegram: {'Ativado ✅' if self.telegram.enabled else 'Desativado'}")
        self.logger.info(f"🧠 IA chamada a cada: {self.ai_call_interval // 60} minutos")
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
    
    def _run_iteration(self):
        """Executa uma iteração completa do bot"""
        
        if self.paused:
            self.logger.info("⏸️ Bot PAUSADO pelo usuário via Telegram. Aguardando...")
            return

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
                
                market_contexts.append(context)
                
            except Exception as e:
                self.logger.error(f"{pair}: Erro ao construir contexto: {e}")
        
        if not market_contexts:
            self.logger.warning("Nenhum contexto de mercado disponível, pulando iteração")
            return
        
        # 5. Verificar stops/TPs das posições abertas
        self.logger.info("🎯 Verificando stops/TPs...")
        self.position_manager.log_positions_summary(all_prices)
        
        close_actions = self.position_manager.check_stops(all_prices)
        
        for action in close_actions:
            self._execute_close(action, all_prices)
        
        # 6. Consultar IA para novas decisões (APENAS A CADA X MINUTOS)
        current_time = time.time()
        time_since_last_ai = current_time - self.last_ai_call_time
        
        if time_since_last_ai >= self.ai_call_interval:
            # Hora de chamar a IA!
            self.logger.info(f"🤖 Consultando IA para decisões... (última chamada há {time_since_last_ai/60:.1f} min)")
            
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
            
            ai_decisions = self.ai_engine.decide(
                market_contexts=market_contexts,
                account_info=account_info,
                open_positions=self.position_manager.get_all_positions(),
                risk_limits=risk_limits
            )
            
            # Atualiza cache e timestamp
            self.last_ai_decisions = ai_decisions
            self.last_ai_call_time = current_time
            
        else:
            # Usa decisões em cache (ou lista vazia se não houver)
            remaining = (self.ai_call_interval - time_since_last_ai) / 60
            self.logger.info(f"⏳ Próxima consulta IA em {remaining:.1f} min (usando cache: {len(self.last_ai_decisions)} decisões)")
            ai_decisions = self.last_ai_decisions
        
        # 7. Executar decisões da IA (SIMPLIFICADO - IA é autônoma)
        for decision in ai_decisions:
            action = decision.get('action', '')
            symbol = decision.get('symbol', 'UNKNOWN')
            
            if action == 'open':
                self._execute_open(decision, all_prices)
                
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
    
    def _execute_open(self, decision: Dict[str, Any], prices: Dict[str, float]):
        """Executa abertura de posição - USA VALORES DA IA"""
        symbol = decision['symbol']
        side = decision['side']
        reason = decision.get('reason', '')
        style = decision.get('style', 'swing')
        source = decision.get('source', 'unknown')
        
        # Define multiplicador de risco baseado no estilo
        risk_multiplier = 1.0
        if style == 'scalp':
            risk_multiplier = 0.5
            self.logger.info(f"⚡ SCALP DETECTADO: Aplicando multiplicador de risco {risk_multiplier}x")
        
        # ===== VALORES DECIDIDOS PELA IA =====
        size_usd = decision.get('size_usd', 20)  # IA decide quanto em USD
        leverage = decision.get('leverage', 5)   # IA decide leverage
        stop_loss_price = decision.get('stop_loss_price')  # IA decide SL
        take_profit_price = decision.get('take_profit_price')  # IA decide TP
        confidence = decision.get('confidence', 0.0)
        strategy = decision.get('setup_name', style) # Usa setup_name ou style como estratégia
        
        sl_str = f"{stop_loss_price:.2f}" if stop_loss_price else "N/A"
        tp_str = f"{take_profit_price:.2f}" if take_profit_price else "N/A"

        self.logger.info(f"\n{'='*50}")
        self.logger.info(f"📈 ABRINDO {side.upper()} em {symbol}")
        self.logger.info(f"   Size: ${size_usd:.2f} | Leverage: {leverage}x")
        self.logger.info(f"   SL: ${sl_str}")
        self.logger.info(f"   TP: ${tp_str}")
        self.logger.info(f"   Motivo: {reason}")
        self.logger.info(f"{'='*50}")
        
        # Verifica se já tem posição
        if self.position_manager.has_position(symbol):
            self.logger.warning(f"{symbol}: Já existe posição aberta, ignorando")
            return
        
        # Obtém preço atual
        current_price = prices.get(symbol)
        if not current_price:
            self.logger.error(f"{symbol}: Preço não disponível")
            return
        
        # Converte para float
        try:
            current_price = float(current_price)
        except:
            self.logger.error(f"{symbol}: Preço inválido")
            return
        
        # Calcula size em unidades do ativo
        size = size_usd / current_price
        
        # Arredonda size
        sz_decimals = self.client.sz_decimals_cache.get(symbol, 4)
        size = round(size, sz_decimals)
        
        # Valida leverage
        leverage = max(1, min(50, leverage))
        
        # Calcula SL/TP em percentual (para o position_manager)
        if stop_loss_price:
            if side == 'long':
                stop_loss_pct = ((current_price - stop_loss_price) / current_price) * 100
            else:
                stop_loss_pct = ((stop_loss_price - current_price) / current_price) * 100
        else:
            stop_loss_pct = 3.0  # Default
        
        if take_profit_price:
            if side == 'long':
                take_profit_pct = ((take_profit_price - current_price) / current_price) * 100
            else:
                take_profit_pct = ((current_price - take_profit_price) / current_price) * 100
        else:
            take_profit_pct = 6.0  # Default
        
        self.logger.info(f"💰 Size calculado: {size:.6f} {symbol}")
        
        # Modo DRY RUN
        if not self.live_trading:
            self.logger.warning("⚠️  DRY RUN MODE - Ordem NÃO executada na exchange")
            self.logger.info(f"[SIMULAÇÃO] Abrindo {side.upper()} {symbol} @ ${current_price:.2f}")
            
            self.position_manager.add_position(
                symbol=symbol,
                side=side,
                entry_price=current_price,
                size=size,
                leverage=leverage,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                strategy='ai_autonomous'
            )
            return
            
        # Modo LIVE
        try:
            self.logger.info("🚀 Enviando ordem para exchange...")
            
            # 1. Ajusta alavancagem
            self.logger.info(f"⚙️  Ajustando leverage para {leverage}x...")
            self.client.adjust_leverage(symbol, leverage, is_cross=True)
            
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
                self.logger.info(f"Posição adicionada: {symbol} {side.upper()}")
                self.position_manager.add_position(
                    symbol=symbol,
                    side=side,
                    entry_price=current_price,
                    size=size,
                    leverage=leverage,
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                    strategy='ai_autonomous'
                )
                
                # 📱 Notifica via Telegram
                self.telegram.notify_position_opened(
                    symbol=symbol,
                    side=side,
                    entry_price=current_price,
                    size=size,
                    leverage=leverage,
                    strategy=strategy,
                    confidence=confidence,
                    reason=reason,
                    source=source
                )

            else:
                self.logger.error(f"❌ Falha ao abrir posição: {result}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro crítico ao executar ordem: {e}", exc_info=True)
            self.telegram.notify_error("Erro ao abrir posição", f"{symbol}: {str(e)}")
    
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
        'risk_per_trade_pct': float(os.getenv('RISK_PER_TRADE_PCT', '2.0')),
        'max_daily_drawdown_pct': float(os.getenv('MAX_DAILY_DRAWDOWN_PCT', '10.0')),
        'max_open_trades': int(os.getenv('MAX_OPEN_TRADES', '3')),
        'max_leverage': int(os.getenv('MAX_LEVERAGE', '50')),
        'min_notional': float(os.getenv('MIN_NOTIONAL', '12.0')),
        'default_stop_pct': float(os.getenv('DEFAULT_STOP_PCT', '2.0')),
        'default_tp_pct': float(os.getenv('DEFAULT_TP_PCT', '4.0')),
        'loop_sleep_seconds': int(os.getenv('TRADING_LOOP_SLEEP_SECONDS', '60')),  # Aumentado para 60s
        'trading_pairs': os.getenv('PAIRS_TO_TRADE', 'BTCUSDC,ETHUSDC,SOLUSDC').split(','),
        
        # ===== CONFIGURAÇÕES ANTI-OVERTRADING =====
        'action_cooldown_seconds': int(os.getenv('ACTION_COOLDOWN_SECONDS', '300')),  # 5 min entre ações no mesmo ativo
        'min_confidence_open': float(os.getenv('MIN_CONFIDENCE_OPEN', '0.75')),       # Confiança mín para abrir
        'min_confidence_adjust': float(os.getenv('MIN_CONFIDENCE_ADJUST', '0.82')),   # Confiança mín para increase/decrease
        'max_adjustments_per_iteration': int(os.getenv('MAX_ADJUSTMENTS_PER_ITERATION', '1')),  # Máx 1 ajuste por ciclo
        
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
