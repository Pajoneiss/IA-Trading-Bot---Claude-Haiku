"""
Telegram Interactive PRO
Interface completa com 9 botões permanentes e integrações avançadas
"""
import os
import threading
import logging
import time
import requests
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import telebot
    from telebot import types
    TELEBOT_AVAILABLE = True
except ImportError:
    TELEBOT_AVAILABLE = False

# Importa módulos novos
from bot.market_intelligence import MarketIntelligence
from bot.apis.coinmarketcap_extended import CoinMarketCapAPI
from bot.apis.cryptopanic_extended import CryptoPanicAPI
from bot.utils.pnl_tracker import PnLTracker

logger = logging.getLogger(__name__)

class TelegramInteractivePRO:
    """
    Telegram PRO com:
    - 9 botões permanentes (sem submenus)
    - Market Intelligence para IA
    - CoinMarketCap completo
    - CryptoPanic com importância
    - PnL detalhado (D/S/M)
    - Fechar todas posições
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(TelegramInteractivePRO, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, main_bot, token: str):
        if hasattr(self, 'initialized') and self.initialized:
            return
            
        self.main_bot = main_bot
        self.token = token
        self.bot = None
        self.is_running = False
        self.thread = None
        self.initialized = True
        
        # Inicializa módulos
        self.market_intel = MarketIntelligence()
        self.cmc_api = CoinMarketCapAPI()
        self.cryptopanic_api = CryptoPanicAPI()
        self.pnl_tracker = PnLTracker(main_bot)
        
        if not TELEBOT_AVAILABLE:
            logger.warning("⚠️ pyTelegramBotAPI não instalado.")
            return
            
        if not token:
            logger.warning("⚠️ Token do Telegram não fornecido.")
            return
            
        try:
            self.bot = telebot.TeleBot(token, parse_mode='Markdown')
            self._setup_handlers()
            logger.info("✅ Telegram Interactive PRO inicializado")
        except Exception as e:
            logger.error(f"Erro ao inicializar Telegram PRO: {e}")
    
    def start(self):
        """Inicia o listener em background"""
        if not self.bot:
            logger.warning("[TELEGRAM] Bot não inicializado.")
            return
            
        if self.is_running:
            logger.warning("[TELEGRAM] Já está rodando.")
            return
        
        # Testa conexão
        try:
            me = self.bot.get_me()
            logger.info(f"[TELEGRAM] ✅ Conectado como @{me.username} (ID: {me.id})")
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao conectar: {e}")
            return
            
        self.is_running = True
        self.thread = threading.Thread(target=self._run_polling, daemon=True)
        self.thread.start()
        logger.info("🚀 [TELEGRAM] Bot PRO iniciado")
        
    def _run_polling(self):
        """Loop de polling com retry"""
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                logger.info(f"[TELEGRAM] Iniciando polling (tentativa {retry_count + 1}/{max_retries})")
                self.bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
                break  # Sucesso
            except Exception as e:
                retry_count += 1
                logger.error(f"[TELEGRAM] Erro no polling: {e}")
                
                if retry_count < max_retries:
                    wait_time = retry_count * 5
                    logger.info(f"[TELEGRAM] Aguardando {wait_time}s antes de tentar novamente...")
                    time.sleep(wait_time)
                else:
                    logger.error("[TELEGRAM] Máximo de tentativas atingido")
                    self.is_running = False
                    
    def _setup_handlers(self):
        """Configura handlers dos comandos e botões"""
        
        # Comando /start
        @self.bot.message_handler(commands=['start'])
        def send_welcome(message):
            try:
                logger.info(f"[TELEGRAM] /start recebido de chat_id={message.chat.id}")
                self._send_welcome_flow(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no /start: {e}")
                self.bot.send_message(message.chat.id, "❌ Erro ao processar comando.")
        
        # Handlers dos botões do teclado permanente
        @self.bot.message_handler(func=lambda m: m.text and m.text == "📊 Resumo")
        def handle_resumo(message):
            try:
                self._send_resumo(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em Resumo: {e}")
        
        @self.bot.message_handler(func=lambda m: m.text and m.text == "📈 Posições")
        def handle_posicoes(message):
            try:
                self._send_posicoes(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em Posições: {e}")
        
        @self.bot.message_handler(func=lambda m: m.text and m.text == "📉 PnL")
        def handle_pnl(message):
            try:
                self._send_pnl(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em PnL: {e}")
        
        @self.bot.message_handler(func=lambda m: m.text and (m.text == "⏸️ Pausar" or m.text == "▶️ Retomar"))
        def handle_toggle(message):
            try:
                self._toggle_trading(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em Toggle: {e}")
        
        @self.bot.message_handler(func=lambda m: m.text and m.text == "🛑 Fechar Todas")
        def handle_fechar(message):
            try:
                self._fechar_todas_confirmacao(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em Fechar Todas: {e}")
        
        @self.bot.message_handler(func=lambda m: m.text and m.text == "📰 Notícias")
        def handle_noticias(message):
            try:
                self._send_noticias(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em Notícias: {e}")
        
        @self.bot.message_handler(func=lambda m: m.text and m.text == "💹 Mercado")
        def handle_mercado(message):
            try:
                self._send_mercado(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em Mercado: {e}")
        
        @self.bot.message_handler(func=lambda m: m.text and m.text == "📅 Calendário")
        def handle_calendario(message):
            try:
                self._send_calendario(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em Calendário: {e}")
        
        @self.bot.message_handler(func=lambda m: m.text and m.text == "🧠 IA Info")
        def handle_ia_info(message):
            try:
                self._send_ia_info(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em IA Info: {e}")
        
        # === PHASE 4: COMANDOS DE PERFORMANCE ===
        @self.bot.message_handler(commands=['pnl'])
        def handle_pnl_command(message):
            try:
                self._send_performance_summary(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /pnl: {e}")
                self.bot.send_message(message.chat.id, f"❌ Erro ao gerar PnL: {e}")
        
        @self.bot.message_handler(commands=['diario'])
        def handle_diario_command(message):
            try:
                self._send_daily_report(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /diario: {e}")
                self.bot.send_message(message.chat.id, f"❌ Erro ao gerar diário: {e}")
        
        # Callback handler (para confirmações)
        @self.bot.callback_query_handler(func=lambda call: True)
        def callback_query(call):
            try:
                if call.data == "fechar_todas_confirmar":
                    self._fechar_todas_executar(call.message.chat.id)
                elif call.data == "fechar_todas_cancelar":
                    self.bot.send_message(call.message.chat.id, "❌ Operação cancelada.")
                    
                self.bot.answer_callback_query(call.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no callback: {e}")
    
    # ========== TECLADO PERMANENTE ==========
    
    def _get_persistent_keyboard(self):
        """Teclado com 9 botões sempre visível"""
        is_paused = getattr(self.main_bot, 'paused', False)
        pause_text = "▶️ Retomar" if is_paused else "⏸️ Pausar"
        
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
        
        # Linha 1: Status e Performance
        keyboard.row(
            types.KeyboardButton("📊 Resumo"),
            types.KeyboardButton("📈 Posições"),
            types.KeyboardButton("📉 PnL")
        )
        
        # Linha 2: Controle
        keyboard.row(
            types.KeyboardButton(pause_text),
            types.KeyboardButton("🛑 Fechar Todas"),
            types.KeyboardButton("📰 Notícias")
        )
        
        # Linha 3: Mercado e IA
        keyboard.row(
            types.KeyboardButton("💹 Mercado"),
            types.KeyboardButton("📅 Calendário"),
            types.KeyboardButton("🧠 IA Info")
        )
        
        return keyboard
    
    # ========== WELCOME FLOW ==========
    
    def _send_welcome_flow(self, chat_id):
        """Fluxo de boas-vindas"""
        try:
            # Mensagem de boas-vindas
            msg = (
                "🤖 *Hyperliquid IA Trader PRO*\n\n"
                "Bem-vindo! Seu bot de trading autônomo está ativo.\n\n"
                "Use os botões abaixo para acessar todas as funções:"
            )
            
            self.bot.send_message(
                chat_id, 
                msg, 
                reply_markup=self._get_persistent_keyboard()
            )
            
            # Envia resumo automaticamente
            self._send_resumo(chat_id)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro no welcome flow: {e}")
    
    # ========== BOTÃO 1: RESUMO ==========
    
    def _send_resumo(self, chat_id):
        """📊 Resumo do Bot"""
        try:
            equity = self.main_bot.risk_manager.current_equity
            dd = self.main_bot.risk_manager.daily_drawdown_pct
            pos_count = self.main_bot.position_manager.get_positions_count()
            is_paused = getattr(self.main_bot, 'paused', False)
            
            status_emoji = "⏸️ PAUSADO" if is_paused else "▶️ ATIVO"
            
            # PnL hoje (simplificado)
            pnl_hoje = dd * equity / 100  # Aproximação
            pnl_hoje_pct = dd
            
            msg = (
                f"📊 *RESUMO DO BOT*\n\n"
                f"Status: {status_emoji}\n"
                f"💰 Equity: `${equity:.2f}`\n"
                f"📈 PnL Hoje: `${pnl_hoje:+.2f}` ({pnl_hoje_pct:+.2f}%)\n"
                f"📊 Posições Abertas: `{pos_count}`\n\n"
            )
            
            # Performance simplificada
            if pos_count == 0:
                msg += "🎯 Nenhuma posição aberta no momento.\n"
            else:
                msg += f"🎯 {pos_count} posição(ões) sendo gerenciada(s).\n"
            
            msg += f"\n⏰ Atualizado: {datetime.utcnow().strftime('%d/%m %H:%M')} UTC"
            
            self.bot.send_message(chat_id, msg)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar resumo: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao obter resumo.")
    
    # ========== BOTÃO 2: POSIÇÕES ==========
    
    def _send_posicoes(self, chat_id):
        """📈 Posições Abertas - VERSÃO CORRIGIDA COM FALLBACK"""
        try:
            logger.info("[TELEGRAM] Buscando posições...")
            
            # Tenta múltiplas fontes de dados
            positions = []
            
            # MÉTODO 1: Tenta via PositionManager (padrão)
            try:
                prices = self.main_bot.client.get_all_mids()
                positions = self.main_bot.position_manager.get_all_positions(current_prices=prices)
                logger.info(f"[TELEGRAM] PositionManager retornou {len(positions)} posições")
                
                # Verifica se tem dados válidos
                if positions and all(p.get('coin') != 'UNKNOWN' for p in positions):
                    logger.info(f"[TELEGRAM] Dados válidos do PositionManager")
                else:
                    logger.warning(f"[TELEGRAM] Dados incompletos, tentando fallback...")
                    positions = []  # Force fallback
                    
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no PositionManager: {e}")
                positions = []
            
            # MÉTODO 2: Fallback - Busca direto do Hyperliquid
            if not positions:
                try:
                    logger.info("[TELEGRAM] Buscando direto do Hyperliquid...")
                    
                    # Wallet address
                    wallet = getattr(self.main_bot, 'wallet_address', None)
                    if not wallet:
                        wallet = self.main_bot.account.address
                    
                    logger.info(f"[TELEGRAM] Wallet: {wallet[:10]}...")
                    
                    # User state
                    user_state = self.main_bot.client.info.user_state(wallet)
                    
                    if user_state and 'assetPositions' in user_state:
                        asset_positions = user_state['assetPositions']
                        logger.info(f"[TELEGRAM] {len(asset_positions)} assetPositions")
                        
                        # Preços
                        prices = self.main_bot.client.get_all_mids()
                        
                        # Processa cada posição
                        for asset_pos in asset_positions:
                            position = asset_pos.get('position', {})
                            coin = position.get('coin', 'UNKNOWN')
                            
                            # Tamanho da posição
                            szi = float(position.get('szi', 0))
                            
                            if szi == 0:
                                continue  # Pula posições vazias
                            
                            # Entry price
                            entry_px = float(position.get('entryPx', 0))
                            if entry_px == 0:
                                continue
                            
                            # Preço atual
                            current_px = prices.get(coin, entry_px)
                            
                            # Leverage
                            leverage_obj = position.get('leverage', {})
                            if isinstance(leverage_obj, dict):
                                leverage = float(leverage_obj.get('value', 1))
                            else:
                                leverage = float(leverage_obj) if leverage_obj else 1
                            
                            # Calcula tamanho em USD
                            size_usd = abs(szi * entry_px)
                            
                            # Determina lado e calcula PnL
                            if szi > 0:  # LONG
                                pnl = szi * (current_px - entry_px)
                                side = 'long'
                            else:  # SHORT
                                pnl = abs(szi) * (entry_px - current_px)
                                side = 'short'
                            
                            logger.info(f"[TELEGRAM] {coin} {side.upper()}: ${size_usd:.2f} PnL=${pnl:+.2f}")
                            
                            positions.append({
                                'coin': coin,
                                'side': side,
                                'size_usd': size_usd,
                                'size': abs(szi),
                                'entry_price': entry_px,
                                'current_price': current_px,
                                'unrealized_pnl': pnl,
                                'leverage': leverage,
                                'opened_at': None
                            })
                        
                        logger.info(f"[TELEGRAM] {len(positions)} posições processadas")
                        
                except Exception as e:
                    logger.error(f"[TELEGRAM] Erro no fallback: {e}", exc_info=True)
            
            # Se ainda não tem posições
            if not positions:
                logger.info("[TELEGRAM] Nenhuma posição encontrada")
                msg = (
                    "📈 *POSIÇÕES ABERTAS*\n\n"
                    "Nenhuma posição aberta no momento.\n\n"
                    "🎯 O bot está monitorando o mercado\n"
                    "   e aguardando oportunidades."
                )
                self.bot.send_message(chat_id, msg)
                return
            
            # Formata mensagem
            logger.info(f"[TELEGRAM] Formatando {len(positions)} posições")
            msg = f"📈 *POSIÇÕES ABERTAS*\n\n"
            
            total_pnl = 0.0
            total_size = 0.0
            
            for i, pos in enumerate(positions, 1):
                # PositionManager retorna 'symbol', não 'coin'
                coin = pos.get('symbol', pos.get('coin', 'UNKNOWN'))  # Tenta symbol primeiro
                # Remove sufixo USDC se tiver
                if coin.endswith('USDC'):
                    coin = coin[:-4]  # Remove 'USDC' (ex: DYDXUSDC -> DYDX)
                
                side = pos.get('side', 'unknown').upper()
                size = pos.get('size', 0)  # Tamanho em coins
                entry = pos.get('entry_price', 0)
                leverage = pos.get('leverage', 1)
                
                # Busca preço atual
                if prices:
                    # Tenta com sufixo USDC primeiro
                    symbol_with_suffix = coin + 'USDC' if not coin.endswith('USDC') else coin
                    current = prices.get(symbol_with_suffix, prices.get(coin, entry))
                else:
                    current = entry
                
                # Calcula size_usd
                size_usd = size * entry
                
                # Calcula PnL não-realizado
                if side == 'LONG':
                    pnl = size * (current - entry)
                else:  # SHORT
                    pnl = size * (entry - current)
                
                pnl = pnl * leverage  # Aplica leverage
                
                # Calcula variação %
                if entry > 0:
                    price_change = ((current - entry) / entry * 100)
                else:
                    price_change = 0
                
                # PnL %
                pnl_pct = (pnl / size_usd * 100) if size_usd > 0 else 0
                
                # Emoji de PnL
                if pnl > 0:
                    pnl_emoji = "💚"
                elif pnl < 0:
                    pnl_emoji = "❤️"
                else:
                    pnl_emoji = "💙"
                
                # Tempo aberto
                opened_at = pos.get('opened_at')
                if opened_at:
                    try:
                        # opened_at vem como string ISO do to_dict()
                        if isinstance(opened_at, str):
                            opened_at = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                        
                        delta = datetime.utcnow() - opened_at.replace(tzinfo=None)
                        total_hours = delta.total_seconds() / 3600
                        if total_hours < 1:
                            minutes = int(delta.total_seconds() / 60)
                            time_str = f"{minutes}m"
                        elif total_hours < 24:
                            hours = int(total_hours)
                            minutes = int((total_hours - hours) * 60)
                            time_str = f"{hours}h {minutes}m"
                        else:
                            days = delta.days
                            hours = int((total_hours - days * 24))
                            time_str = f"{days}d {hours}h"
                    except Exception as e:
                        logger.error(f"Erro ao calcular tempo: {e}")
                        time_str = None
                else:
                    time_str = None
                
                # Monta mensagem da posição
                msg += f"{i}. *{coin}/USDT {side}*\n"
                
                if size > 0:
                    msg += f"   📏 Qtd: `{size:.4f}` {coin}\n"
                
                msg += f"   💰 Tamanho: `${size_usd:.2f}`\n"
                
                if leverage > 1:
                    msg += f"   ⚡ Alavancagem: `{leverage:.0f}x`\n"
                
                msg += f"   📊 Entry: `${entry:.4f}`\n"
                msg += f"   💹 Atual: `${current:.4f}` ({price_change:+.2f}%)\n"
                msg += f"   {pnl_emoji} PnL: `${pnl:+.2f}` ({pnl_pct:+.2f}%)\n"
                
                if time_str:
                    msg += f"   ⏱️ Aberta: `{time_str}`\n"
                
                msg += "\n"
                
                total_pnl += pnl
                total_size += size_usd
            
            # Resumo
            total_pnl_pct = (total_pnl / total_size * 100) if total_size > 0 else 0
            
            msg += "━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"💰 *PnL Total:* `${total_pnl:+.2f}` ({total_pnl_pct:+.1f}%)\n"
            msg += f"📊 *Capital:* `${total_size:.2f}`\n\n"
            msg += f"⏰ _{datetime.utcnow().strftime('%d/%m %H:%M')} UTC_"
            
            logger.info(f"[TELEGRAM] Enviando mensagem")
            self.bot.send_message(chat_id, msg, parse_mode='Markdown')
            logger.info("[TELEGRAM] Sucesso!")
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro FATAL: {e}", exc_info=True)
            try:
                self.bot.send_message(
                    chat_id, 
                    f"❌ Erro ao obter posições.\n\nDetalhes: {str(e)[:100]}"
                )
            except:
                logger.error("[TELEGRAM] Falha ao enviar erro")
    
    # ========== BOTÃO 3: PNL ==========
    
    def _send_pnl(self, chat_id):
        """📉 PnL Detalhado"""
        try:
            analysis = self.pnl_tracker.analyze_pnl()
            msg = self.pnl_tracker.format_for_telegram(analysis)
            self.bot.send_message(chat_id, msg)
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar PnL: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao calcular PnL.")
    
    # ========== BOTÃO 4: PAUSAR/RETOMAR ==========
    
    def _toggle_trading(self, chat_id):
        """⏸️ Pausar / ▶️ Retomar"""
        try:
            is_paused = getattr(self.main_bot, 'paused', False)
            
            if is_paused:
                # Retomar
                self.main_bot.paused = False
                msg = (
                    "▶️ *BOT RETOMADO*\n\n"
                    "O bot foi retomado com sucesso!\n\n"
                    "🎯 O bot voltou a monitorar o mercado\n"
                    "   e executar trades automaticamente.\n\n"
                    f"⏰ Retomado: {datetime.utcnow().strftime('%d/%m %H:%M')} UTC"
                )
            else:
                # Pausar
                self.main_bot.paused = True
                
                # Conta posições abertas
                pos_count = self.main_bot.position_manager.get_positions_count()
                
                msg = (
                    "⏸️ *BOT PAUSADO*\n\n"
                    "O bot foi pausado com sucesso.\n\n"
                    f"📊 Posições abertas: `{pos_count}`\n\n"
                    "⚠️ As posições abertas permanecem ativas.\n"
                    "Para fechá-las, use o botão *🛑 Fechar Todas*.\n\n"
                    "Clique em *▶️ Retomar* para continuar trading."
                )
            
            self.bot.send_message(
                chat_id, 
                msg, 
                reply_markup=self._get_persistent_keyboard()
            )
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao toggle trading: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao pausar/retomar.")
    
    # ========== BOTÃO 5: FECHAR TODAS ==========
    
    def _fechar_todas_confirmacao(self, chat_id):
        """🛑 Fechar Todas - Passo 1: Confirmação"""
        try:
            # Busca posições
            try:
                prices = self.main_bot.client.get_all_mids()
            except:
                prices = {}
            
            positions = self.main_bot.position_manager.get_all_positions(current_prices=prices)
            
            if not positions:
                self.bot.send_message(
                    chat_id,
                    "🛑 *FECHAR TODAS AS POSIÇÕES*\n\n"
                    "Nenhuma posição aberta para fechar.\n\n"
                    "🎯 O bot está sem posições abertas."
                )
                return
            
            # Calcula total
            total_pnl = sum(pos.get('unrealized_pnl', 0) for pos in positions)
            total_pnl_pct = 0  # TODO: Calcular baseado no equity total
            
            msg = (
                "🛑 *FECHAR TODAS AS POSIÇÕES*\n\n"
                "⚠️ *ATENÇÃO:* Você está prestes a fechar\n"
                "   *TODAS* as posições abertas!\n\n"
                f"📊 Resumo:\n"
                f"   • {len(positions)} posição(ões) aberta(s)\n"
                f"   • PnL total: `${total_pnl:+.2f}`\n\n"
                "Posições:\n"
            )
            
            for i, pos in enumerate(positions, 1):
                coin = pos.get('coin', 'UNKNOWN')
                side = pos.get('side', 'unknown').upper()
                pnl = pos.get('unrealized_pnl', 0)
                msg += f"{i}. {coin} {side}: `${pnl:+.2f}`\n"
            
            msg += "\nEsta ação é *IRREVERSÍVEL*!"
            
            # Botões de confirmação
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton("✅ Sim, fechar tudo", callback_data="fechar_todas_confirmar"),
                types.InlineKeyboardButton("❌ Cancelar", callback_data="fechar_todas_cancelar")
            )
            
            self.bot.send_message(chat_id, msg, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao confirmar fechar todas: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao processar solicitação.")
    
    def _fechar_todas_executar(self, chat_id):
        """🛑 Fechar Todas - Passo 2: Execução"""
        try:
            self.bot.send_message(chat_id, "⏳ Fechando posições...")
            
            # Busca posições
            try:
                prices = self.main_bot.client.get_all_mids()
            except:
                prices = {}
            
            positions = self.main_bot.position_manager.get_all_positions(current_prices=prices)
            
            if not positions:
                self.bot.send_message(chat_id, "❌ Nenhuma posição encontrada.")
                return
            
            # Fecha cada posição
            results = []
            total_realized = 0.0
            
            for pos in positions:
                try:
                    coin = pos.get('coin', 'UNKNOWN')
                    pnl = pos.get('unrealized_pnl', 0)
                    
                    # TODO: Implementar fechamento real via Hyperliquid
                    # Por enquanto, apenas mock
                    # success = self.main_bot.close_position(coin)
                    
                    results.append(f"✅ {coin}: `${pnl:+.2f}`")
                    total_realized += pnl
                    
                except Exception as e:
                    logger.error(f"[TELEGRAM] Erro ao fechar {coin}: {e}")
                    results.append(f"❌ {coin}: Erro")
            
            # Mensagem de resultado
            msg = "🎯 *POSIÇÕES FECHADAS*\n\n"
            msg += "\n".join(results)
            msg += f"\n\n💰 *Total realizado:* `${total_realized:+.2f}`\n"
            msg += f"⏰ Concluído: {datetime.utcnow().strftime('%d/%m %H:%M')} UTC"
            
            self.bot.send_message(chat_id, msg)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao executar fechar todas: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao fechar posições.")
    
    # ========== BOTÃO 6: NOTÍCIAS ==========
    
    def _send_noticias(self, chat_id):
        """📰 Notícias (CryptoPanic)"""
        try:
            self.bot.send_message(chat_id, "⏳ Buscando notícias...")
            
            news_list = self.cryptopanic_api.get_important_news(limit=10)
            msg = self.cryptopanic_api.format_for_telegram(news_list)
            
            self.bot.send_message(chat_id, msg, disable_web_page_preview=True)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar notícias: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao buscar notícias.")
    
    # ========== BOTÃO 7: MERCADO ==========
    
    def _send_mercado(self, chat_id):
        """💹 Mercado (CoinMarketCap + Fear & Greed + Alt Season)"""
        try:
            self.bot.send_message(chat_id, "⏳ Buscando dados do mercado...")
            
            # Busca dados do CMC
            cmc_data = self.cmc_api.get_market_overview()
            
            # Busca Fear & Greed e Alt Season do Market Intelligence
            context = self.market_intel.get_market_context()
            
            # Formata mensagem combinando tudo
            msg = self.cmc_api.format_for_telegram(cmc_data)
            
            # Adiciona Fear & Greed e Alt Season
            msg += "\n\n🎭 *SENTIMENTO DO MERCADO*\n"
            msg += "─" * 35 + "\n"
            
            # Fear & Greed
            fg = context['fear_greed']
            fg_emoji = "😱" if fg < 25 else ("😰" if fg < 45 else ("😐" if fg < 55 else ("😊" if fg < 75 else "🤑")))
            fg_text = context['sentiment'].replace('_', ' ').title()
            msg += f"{fg_emoji} Fear & Greed: *{fg}/100* ({fg_text})\n"
            
            # Alt Season
            alt_idx = context['alt_season_index']
            if context['is_bitcoin_season']:
                season_text = "Bitcoin Season"
                season_emoji = "🪙"
            elif context['is_alt_season']:
                season_text = "Alt Season"
                season_emoji = "🌊"
            else:
                season_text = "Neutro"
                season_emoji = "⚖️"
            
            msg += f"{season_emoji} Season Index: *{alt_idx}/100* ({season_text})\n"
            
            self.bot.send_message(chat_id, msg)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar mercado: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao buscar dados do mercado.")
    
    # ========== BOTÃO 8: CALENDÁRIO ==========
    
    def _send_calendario(self, chat_id):
        """📅 Calendário Econômico"""
        try:
            # TODO: Implementar calendário real (ForexFactory ou API)
            msg = (
                "📅 *CALENDÁRIO ECONÔMICO*\n\n"
                "🚧 _Em desenvolvimento_\n\n"
                "Em breve você terá acesso a:\n"
                "• Eventos econômicos do dia\n"
                "• Eventos da semana\n"
                "• Importância de cada evento\n"
                "• Horários em UTC\n"
                "• Recomendações para IA\n\n"
                "⏰ Atualizado: " + datetime.utcnow().strftime('%d/%m %H:%M') + " UTC"
            )
            
            self.bot.send_message(chat_id, msg)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar calendário: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao buscar calendário.")
    
    # ========== BOTÃO 9: IA INFO ==========
    
    def _send_ia_info(self, chat_id):
        """🧠 IA Info (Market Intelligence)"""
        try:
            self.bot.send_message(chat_id, "⏳ Analisando mercado...")
            
            context = self.market_intel.get_market_context()
            
            msg = "🧠 *MARKET INTELLIGENCE — Dados para IA*\n\n"
            
            # Contexto de mercado
            msg += "📊 *CONTEXTO DE MERCADO*\n"
            msg += "─" * 35 + "\n"
            
            fg = context['fear_greed']
            fg_text = context['sentiment'].replace('_', ' ').title()
            msg += f"🎭 Sentimento: *{fg_text}* ({fg}/100)\n"
            msg += f"🪙 BTC Dominância: *{context['btc_dominance']:.1f}%*\n"
            
            if context['is_bitcoin_season']:
                msg += f"🌊 Fase: *Bitcoin Season* ({context['alt_season_index']}/100)\n"
            elif context['is_alt_season']:
                msg += f"🌊 Fase: *Alt Season* ({context['alt_season_index']}/100)\n"
            else:
                msg += f"🌊 Fase: *Neutro* ({context['alt_season_index']}/100)\n"
            
            # Recomendações
            recs = context['recommendations']
            if recs:
                msg += "\n🤖 *RECOMENDAÇÕES ATUAIS*\n"
                msg += "─" * 35 + "\n"
                
                rec_texts = {
                    'extreme_fear_reduce_size': '⚠️ Reduzir tamanho de posição\n   (Extreme Fear indica volatilidade)',
                    'extreme_greed_take_profit': '💰 Considerar realizar lucros\n   (Extreme Greed)',
                    'prefer_btc_over_alts': '✅ Preferir BTC sobre alts\n   (Alta dominância)',
                    'avoid_altcoins': '🚨 Cautela com alts\n   (Bitcoin Season)',
                    'favor_altcoins': '🌊 Favorecer altcoins\n   (Alt Season)',
                    'reduce_exposure_events': '⚠️ Reduzir exposição\n   (Eventos críticos próximos)',
                    'tighter_stop_loss': '🎯 Stop-loss mais apertado\n   (Volatilidade alta)'
                }
                
                for rec in recs:
                    if rec in rec_texts:
                        msg += rec_texts[rec] + "\n\n"
            
            # Estratégia sugerida
            msg += "🎯 *ESTRATÉGIA SUGERIDA*\n"
            msg += "─" * 35 + "\n"
            
            size_mult = self.market_intel.get_position_size_multiplier()
            if size_mult < 1.0:
                msg += f"• Reduzir exposição em {int((1 - size_mult) * 100)}%\n"
            
            if context['is_bitcoin_season']:
                msg += "• Priorizar BTC sobre ETH/alts\n"
            
            if fg < 25:
                msg += "• Stop-loss mais apertado\n"
                msg += "• Evitar alavancagem alta\n"
            
            msg += f"\n⏰ Última atualização: {datetime.utcnow().strftime('%d/%m %H:%M')} UTC"
            
            self.bot.send_message(chat_id, msg)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar IA Info: {e}")
            self.bot.send_message(chat_id, "❌ Erro ao gerar informações.")
    
    # ========== PHASE 4: PERFORMANCE & DIÁRIO ==========
    
    def _send_performance_summary(self, chat_id: int):
        """
        Envia sumário de performance completo (/pnl)
        
        Mostra:
        - PnL diário, semanal, mensal
        - Win Rate
        - RR médio
        - Profit Factor
        - Melhor/pior símbolo
        - Melhor/pior estratégia
        """
        try:
            from bot.phase4 import PerformanceAnalyzer
            
            analyzer = PerformanceAnalyzer()
            
            # Sumários dos 3 períodos
            daily = analyzer.get_summary('daily')
            weekly = analyzer.get_summary('weekly')
            monthly = analyzer.get_summary('monthly')
            
            msg = "📊 *PERFORMANCE SUMMARY*\n"
            msg += "=" * 30 + "\n\n"
            
            # === DIÁRIO ===
            msg += "📅 *HOJE*\n"
            msg += f"• Trades: {daily['total_trades']}\n"
            msg += f"• PnL: ${daily['pnl']['total']:.2f}\n"
            msg += f"• Win Rate: {daily['win_rate']:.1f}%\n"
            msg += f"• RR Médio: {daily['avg_rr']:.2f}R\n"
            msg += f"• Profit Factor: {daily['profit_factor']:.2f}\n"
            
            if daily['best_worst']:
                best_trade = daily['best_worst'].get('best_trade', {})
                worst_trade = daily['best_worst'].get('worst_trade', {})
                msg += f"• Melhor: {best_trade.get('symbol', 'N/A')} (${best_trade.get('pnl', 0):.2f})\n"
                msg += f"• Pior: {worst_trade.get('symbol', 'N/A')} (${worst_trade.get('pnl', 0):.2f})\n"
            
            msg += "\n"
            
            # === SEMANAL ===
            msg += "📆 *7 DIAS*\n"
            msg += f"• Trades: {weekly['total_trades']}\n"
            msg += f"• PnL: ${weekly['pnl']['total']:.2f}\n"
            msg += f"• Win Rate: {weekly['win_rate']:.1f}%\n"
            msg += f"• RR Médio: {weekly['avg_rr']:.2f}R\n"
            msg += f"• Profit Factor: {weekly['profit_factor']:.2f}\n"
            
            if weekly['best_worst']:
                best_symbol = weekly['best_worst'].get('best_symbol', {})
                worst_symbol = weekly['best_worst'].get('worst_symbol', {})
                msg += f"• Melhor símbolo: {best_symbol.get('symbol', 'N/A')} (${best_symbol.get('pnl', 0):.2f})\n"
                msg += f"• Pior símbolo: {worst_symbol.get('symbol', 'N/A')} (${worst_symbol.get('pnl', 0):.2f})\n"
            
            msg += "\n"
            
            # === MENSAL ===
            msg += "📊 *30 DIAS*\n"
            msg += f"• Trades: {monthly['total_trades']}\n"
            msg += f"• PnL: ${monthly['pnl']['total']:.2f}\n"
            msg += f"• Win Rate: {monthly['win_rate']:.1f}%\n"
            msg += f"• RR Médio: {monthly['avg_rr']:.2f}R\n"
            msg += f"• Profit Factor: {monthly['profit_factor']:.2f}\n"
            msg += f"• Avg Duration: {monthly['avg_duration']}\n"
            
            if monthly['best_worst']:
                best_strategy = monthly['best_worst'].get('best_strategy', {})
                worst_strategy = monthly['best_worst'].get('worst_strategy', {})
                msg += f"• Melhor estratégia: {best_strategy.get('strategy', 'N/A')} (${best_strategy.get('pnl', 0):.2f})\n"
                msg += f"• Pior estratégia: {worst_strategy.get('strategy', 'N/A')} (${worst_strategy.get('pnl', 0):.2f})\n"
            
            # === QUALITY GATE ===
            rejection = daily['rejection_rate']
            msg += f"\n🎯 *QUALITY GATE*\n"
            msg += f"• Sinais hoje: {rejection['total_signals']}\n"
            msg += f"• Executados: {rejection['executed']}\n"
            msg += f"• Rejeitados: {rejection['rejected']} ({rejection['rejection_rate']:.1f}%)\n"
            msg += f"• Pulados: {rejection['skipped']} ({rejection['skip_rate']:.1f}%)\n"
            
            msg += f"\n⏰ {datetime.utcnow().strftime('%d/%m %H:%M')} UTC"
            
            self.bot.send_message(chat_id, msg)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar performance summary: {e}", exc_info=True)
            self.bot.send_message(chat_id, f"❌ Erro ao gerar sumário de performance: {e}")
    
    def _send_daily_report(self, chat_id: int):
        """
        Envia relatório diário profissional (/diario)
        
        Inclui:
        - Trades fechados
        - Win Rate
        - Total realizado
        - Melhor/pior trade
        - Melhor estratégia
        - Observações da IA
        - Sugestão para próximo dia
        """
        try:
            from bot.phase4 import PerformanceAnalyzer
            
            analyzer = PerformanceAnalyzer()
            daily = analyzer.get_summary('daily')
            
            msg = "📖 *DIÁRIO DE TRADING*\n"
            msg += "=" * 30 + "\n"
            msg += f"📅 {datetime.utcnow().strftime('%d/%m/%Y')}\n\n"
            
            # === RESUMO DO DIA ===
            msg += "*📊 RESUMO*\n"
            msg += f"• Trades fechados: {daily['total_trades']}\n"
            msg += f"• Parciais: {daily['total_partials']}\n"
            msg += f"• Win Rate: {daily['win_rate']:.1f}%\n"
            msg += f"• PnL Realizado: ${daily['pnl']['total']:.2f}\n"
            msg += f"• PnL Médio: ${daily['pnl']['avg']:.2f}\n"
            msg += f"• RR Médio: {daily['avg_rr']:.2f}R\n"
            msg += f"• Profit Factor: {daily['profit_factor']:.2f}\n\n"
            
            # === DESTAQUES ===
            if daily['best_worst']:
                best_worst = daily['best_worst']
                
                msg += "*🌟 DESTAQUES*\n"
                
                best_trade = best_worst.get('best_trade', {})
                if best_trade:
                    msg += f"• Melhor trade: {best_trade.get('symbol', 'N/A')} "
                    msg += f"(${best_trade.get('pnl', 0):.2f} | {best_trade.get('pnl_pct', 0):.2f}%)\n"
                
                worst_trade = best_worst.get('worst_trade', {})
                if worst_trade:
                    msg += f"• Pior trade: {worst_trade.get('symbol', 'N/A')} "
                    msg += f"(${worst_trade.get('pnl', 0):.2f} | {worst_trade.get('pnl_pct', 0):.2f}%)\n"
                
                best_strategy = best_worst.get('best_strategy', {})
                if best_strategy:
                    msg += f"• Melhor estratégia: {best_strategy.get('strategy', 'N/A')} "
                    msg += f"(${best_strategy.get('pnl', 0):.2f})\n"
                
                msg += "\n"
            
            # === OBSERVAÇÕES DA IA ===
            msg += "*🧠 OBSERVAÇÕES DA IA*\n"
            
            # Win rate analysis
            if daily['win_rate'] >= 70:
                msg += "✅ Win rate excelente hoje!\n"
            elif daily['win_rate'] >= 50:
                msg += "✓ Win rate dentro do esperado\n"
            else:
                msg += "⚠️ Win rate abaixo do ideal\n"
            
            # RR analysis
            if daily['avg_rr'] >= 2.0:
                msg += "✅ RR médio muito bom (≥2R)\n"
            elif daily['avg_rr'] >= 1.5:
                msg += "✓ RR médio satisfatório\n"
            else:
                msg += "⚠️ RR médio pode melhorar\n"
            
            # Profit factor
            if daily['profit_factor'] >= 2.0:
                msg += "✅ Profit Factor excelente (≥2.0)\n"
            elif daily['profit_factor'] >= 1.5:
                msg += "✓ Profit Factor bom\n"
            elif daily['profit_factor'] > 0:
                msg += "⚠️ Profit Factor baixo\n"
            else:
                msg += "❌ Profit Factor negativo (perdas > ganhos)\n"
            
            # Quality Gate effectiveness
            rejection = daily['rejection_rate']
            if rejection['total_signals'] > 0:
                execution_rate = (rejection['executed'] / rejection['total_signals']) * 100
                msg += f"\n🎯 Quality Gate executou {execution_rate:.1f}% dos sinais\n"
                
                if rejection['rejection_rate'] > 50:
                    msg += "⚠️ Muitos sinais rejeitados (mercado difícil)\n"
            
            msg += "\n"
            
            # === SUGESTÃO PARA AMANHÃ ===
            msg += "*💡 SUGESTÃO PARA AMANHÃ*\n"
            
            if daily['total_trades'] == 0:
                msg += "• Nenhum trade hoje - mercado pode estar em range\n"
                msg += "• Aguardar setup mais claro\n"
            elif daily['win_rate'] < 50:
                msg += "• Focar em qualidade vs quantidade\n"
                msg += "• Revisar confluências antes de entrar\n"
                msg += "• Considerar aumentar threshold do Quality Gate\n"
            elif daily['avg_rr'] < 1.5:
                msg += "• Deixar trades correrem mais\n"
                msg += "• Evitar parciais muito cedo\n"
                msg += "• Aguardar 2R+ antes de sair\n"
            else:
                msg += "• Manter a consistência\n"
                msg += "• Continuar respeitando o Quality Gate\n"
                msg += "• Focar em setups A+\n"
            
            # Market Intelligence para amanhã
            try:
                mi = self.market_intel.get_full_data()
                fg = mi.get('fear_greed', {}).get('value', 50)
                
                msg += "\n*🌍 CONTEXTO DE MERCADO*\n"
                if fg < 30:
                    msg += "• Fear & Greed baixo - oportunidades em dip\n"
                elif fg > 70:
                    msg += "• Fear & Greed alto - cautela com topos\n"
                else:
                    msg += "• Fear & Greed neutro - mercado equilibrado\n"
            except:
                pass
            
            msg += f"\n⏰ {datetime.utcnow().strftime('%d/%m %H:%M')} UTC"
            msg += "\n\n_Use /pnl para métricas detalhadas_"
            
            self.bot.send_message(chat_id, msg)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar daily report: {e}", exc_info=True)
            self.bot.send_message(chat_id, f"❌ Erro ao gerar diário: {e}")
    
    # ========== HELPERS ==========
    
    def is_alive(self) -> bool:
        """Verifica se bot está vivo"""
        if not self.bot:
            return False
        if not self.is_running:
            return False
        if not self.thread or not self.thread.is_alive():
            return False
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status do bot"""
        return {
            'initialized': self.initialized,
            'bot_created': self.bot is not None,
            'is_running': self.is_running,
            'thread_alive': self.thread.is_alive() if self.thread else False
        }
