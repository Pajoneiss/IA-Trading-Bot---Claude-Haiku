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
        
        @self.bot.message_handler(func=lambda m: m.text and m.text == "🎚️ Modo")
        def handle_modo_button(message):
            try:
                self._send_modo_menu(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em Modo: {e}")
        
        @self.bot.message_handler(func=lambda m: m.text and m.text == "🛡 Risco")
        def handle_risco_button(message):
            try:
                self._send_risk_status(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em Risco: {e}")
        
        # PATCH: Handler do botão Execução
        @self.bot.message_handler(func=lambda m: m.text and m.text == "⚙️ Execução")
        def handle_execucao_button(message):
            try:
                self._send_execution_menu(message.chat.id, user_id=message.from_user.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em Execução: {e}")
        
        # GLOBAL_IA: Handler do botão IA (abre menu de conversa/ativação)
        @self.bot.message_handler(func=lambda m: m.text and (m.text == "🧠 IA" or m.text == "🧠 IA ON"))
        def handle_ia_button(message):
            try:
                self._send_ia_menu(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro em IA: {e}")
        
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
        
        # === PHASE 5: COMANDO DE MODO ===
        @self.bot.message_handler(commands=['modo'])
        def handle_modo_command(message):
            try:
                self._send_modo_menu(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /modo: {e}")
                self.bot.send_message(message.chat.id, f"❌ Erro ao exibir modos: {e}")
        
        # === PHASE 6: COMANDO DE RISCO ===
        @self.bot.message_handler(commands=['risco'])
        def handle_risco_command(message):
            try:
                self._send_risk_status(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /risco: {e}")
                self.bot.send_message(message.chat.id, f"❌ Erro ao exibir risco: {e}")
        
        # === PHASE 7: COMANDOS DE JOURNAL & COACH ===
        @self.bot.message_handler(commands=['journal'])
        def handle_journal_command(message):
            try:
                self._send_journal(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /journal: {e}")
        
        @self.bot.message_handler(commands=['performance'])
        def handle_performance_command(message):
            try:
                self._send_performance(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /performance: {e}")
        
        @self.bot.message_handler(commands=['semana'])
        def handle_semana_command(message):
            try:
                self._send_weekly_summary(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /semana: {e}")
        
        @self.bot.message_handler(commands=['coach'])
        def handle_coach_command(message):
            try:
                self._send_coach_insights(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /coach: {e}")
        
        # === PHASE 8: COMANDOS DE PAPER TRADING ===
        @self.bot.message_handler(commands=['execution', 'exec', 'execucao'])
        def handle_execution_command(message):
            try:
                self._send_execution_menu(message.chat.id, user_id=message.from_user.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /execution: {e}")
        
        @self.bot.message_handler(commands=['paper_vs_real', 'compare'])
        def handle_compare_command(message):
            try:
                self._send_real_vs_paper(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /paper_vs_real: {e}")
        
        # === MODO GLOBAL_IA: CHAT COM TRADER ===
        @self.bot.message_handler(commands=['ia', 'trader', 'chat'])
        def handle_ia_chat(message):
            """Comando /ia <pergunta> - Chat com o Trader IA"""
            try:
                # Extrai a pergunta (remove o comando)
                text = message.text
                question = text.split(maxsplit=1)[1] if ' ' in text else ''
                
                if not question:
                    self.bot.send_message(
                        message.chat.id,
                        "🧠 *Chat com Trader IA*\n\n"
                        "Use: `/ia <sua pergunta>`\n\n"
                        "Exemplos:\n"
                        "• `/ia Por que você abriu BTC long?`\n"
                        "• `/ia Qual sua visão do mercado agora?`\n"
                        "• `/ia Devo aumentar minha posição em SOL?`\n"
                        "• `/ia Quais oportunidades você vê?`",
                        parse_mode='Markdown'
                    )
                    return
                
                self.bot.send_message(message.chat.id, "🧠 Pensando...")
                self._handle_ia_chat(message.chat.id, question)
                
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /ia: {e}")
                self.bot.send_message(message.chat.id, f"❌ Erro: {str(e)}")
        
        @self.bot.message_handler(commands=['modo_global', 'global', 'global_ia'])
        def handle_modo_global(message):
            """Comando /modo_global [on|off] - Ativa/desativa modo GLOBAL_IA"""
            try:
                text = message.text.lower()
                
                if 'on' in text or 'ativar' in text:
                    self._set_global_mode(message.chat.id, True)
                elif 'off' in text or 'desativar' in text:
                    self._set_global_mode(message.chat.id, False)
                else:
                    # Mostra status atual
                    self._show_global_mode_status(message.chat.id)
                    
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /modo_global: {e}")
                self.bot.send_message(message.chat.id, f"❌ Erro: {str(e)}")
        
        @self.bot.message_handler(commands=['state', 'status_global'])
        def handle_state(message):
            """Comando /state - Mostra o STATE atual que a IA vê"""
            try:
                self._send_global_state(message.chat.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no comando /state: {e}")
        
        # Callback handler (para confirmações)
        @self.bot.callback_query_handler(func=lambda call: True)
        def callback_query(call):
            try:
                if call.data == "fechar_todas_confirmar":
                    self._fechar_todas_executar(call.message.chat.id)
                elif call.data == "fechar_todas_cancelar":
                    self.bot.send_message(call.message.chat.id, "❌ Operação cancelada.")
                
                # Phase 5: Callbacks de modo
                elif call.data.startswith("modo_"):
                    mode_name = call.data.replace("modo_", "")
                    self._change_mode(call.message.chat.id, mode_name)
                
                # Phase 6: Callbacks de risco
                elif call.data == "risk_force_cooldown":
                    self._handle_force_cooldown(call.message.chat.id)
                elif call.data == "risk_reset_daily_confirm":
                    self._ask_reset_daily_confirmation(call.message.chat.id)
                elif call.data == "risk_reset_daily_execute":
                    self._execute_reset_daily(call.message.chat.id)
                elif call.data == "risk_reset_weekly_confirm":
                    self._ask_reset_weekly_confirmation(call.message.chat.id)
                elif call.data == "risk_reset_weekly_execute":
                    self._execute_reset_weekly(call.message.chat.id)
                elif call.data.startswith("risk_cancel"):
                    self.bot.send_message(call.message.chat.id, "❌ Operação cancelada", parse_mode=None)
                
                # Phase 8: Callbacks de execution mode
                elif call.data == "exec_mode_live":
                    self._set_execution_mode(call.message.chat.id, "LIVE", user_id=call.from_user.id)
                elif call.data == "exec_mode_paper":
                    self._set_execution_mode(call.message.chat.id, "PAPER_ONLY", user_id=call.from_user.id)
                elif call.data == "exec_mode_shadow":
                    self._set_execution_mode(call.message.chat.id, "SHADOW", user_id=call.from_user.id)
                
                # GLOBAL_IA: Callbacks
                elif call.data == "global_ia_on":
                    self._set_global_mode(call.message.chat.id, True)
                elif call.data == "global_ia_off":
                    self._set_global_mode(call.message.chat.id, False)
                elif call.data == "global_ia_state":
                    self._send_global_state(call.message.chat.id)
                elif call.data == "ia_ask_market":
                    # Pergunta rápida sobre o mercado
                    self.bot.send_message(call.message.chat.id, "🧠 Analisando mercado...")
                    self._handle_ia_chat(call.message.chat.id, "Qual sua visão do mercado agora? O que você está vendo?")
                    
                self.bot.answer_callback_query(call.id)
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro no callback: {e}")
    
    # ========== TECLADO PERMANENTE ==========
    
    def _get_persistent_keyboard(self):
        """Teclado com 12 botões sempre visível"""
        is_paused = getattr(self.main_bot, 'paused', False)
        pause_text = "▶️ Retomar" if is_paused else "⏸️ Pausar"
        
        # Verifica se está em modo GLOBAL_IA
        from bot.phase5 import TradingMode
        mode_manager = getattr(self.main_bot, 'mode_manager', None)
        is_global = mode_manager and mode_manager.current_mode == TradingMode.GLOBAL_IA
        global_text = "🧠 IA ON" if is_global else "🧠 IA"
        
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
            types.KeyboardButton("🎚️ Modo")  # Phase 5: Botão de Modo
        )
        
        # Linha 3: Informações e Risco
        keyboard.row(
            types.KeyboardButton("📰 Notícias"),
            types.KeyboardButton("💹 Mercado"),
            types.KeyboardButton("🛡 Risco")  # Phase 6: Botão de Risco
        )
        
        # Linha 4: IA + Execução (NOVO - GLOBAL_IA)
        keyboard.row(
            types.KeyboardButton(global_text),  # Botão para chat/ativar IA
            types.KeyboardButton("⚙️ Execução")  # Modo de execução
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
            
            # PATCH: Obter modo de execução
            exec_mode_str = "LIVE"
            exec_mode_emoji = "🟢"
            exec_manager = getattr(self.main_bot, 'execution_manager', None)
            if exec_manager:
                try:
                    exec_mode_str = exec_manager.execution_mode.value
                    if exec_mode_str == "LIVE":
                        exec_mode_emoji = "🟢"
                    elif exec_mode_str == "PAPER_ONLY":
                        exec_mode_emoji = "📝"
                    else:  # SHADOW
                        exec_mode_emoji = "👥"
                except:
                    pass
            
            msg = (
                f"📊 *RESUMO DO BOT*\n\n"
                f"Status: {status_emoji}\n"
                f"Execução: {exec_mode_emoji} `{exec_mode_str}`\n"
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
                    
                    # Wallet address - tenta múltiplas fontes
                    wallet = getattr(self.main_bot, 'wallet_address', None)
                    if not wallet:
                        wallet = getattr(self.main_bot.client, 'wallet_address', None)
                    if not wallet:
                        raise AttributeError("wallet_address não encontrado")
                    
                    logger.info(f"[TELEGRAM] Wallet: {wallet[:10]}...")
                    
                    # User state - usa método direto do client
                    user_state = self.main_bot.client.get_user_state()
                    
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
            
            # Calcula PnL total em USD
            total_pnl = 0.0
            for pos in positions:
                symbol = pos.get('symbol', 'UNKNOWN')
                size = pos.get('size', 0)
                entry_price = pos.get('entry_price', 0)
                current_price = prices.get(symbol, entry_price)
                side = pos.get('side', 'long')
                
                # Calcula PnL em USD
                try:
                    current_price = float(current_price)
                    if side == 'long':
                        pnl_usd = (current_price - entry_price) * size
                    else:
                        pnl_usd = (entry_price - current_price) * size
                    pos['_pnl_usd'] = pnl_usd
                    total_pnl += pnl_usd
                except:
                    pos['_pnl_usd'] = 0.0
            
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
                symbol = pos.get('symbol', 'UNKNOWN')
                side = pos.get('side', 'unknown').upper()
                pnl = pos.get('_pnl_usd', 0)
                msg += f"{i}. {symbol} {side}: `${pnl:+.2f}`\n"
            
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
                symbol = pos.get('symbol', 'UNKNOWN')
                try:
                    size = pos.get('size', 0)
                    entry_price = pos.get('entry_price', 0)
                    current_price = prices.get(symbol, entry_price)
                    side = pos.get('side', 'long')
                    
                    # Calcula PnL em USD
                    try:
                        current_price = float(current_price)
                        if side == 'long':
                            pnl_usd = (current_price - entry_price) * size
                        else:
                            pnl_usd = (entry_price - current_price) * size
                    except:
                        pnl_usd = 0.0
                    
                    # Executa fechamento real via _execute_close
                    close_action = {
                        'symbol': symbol,
                        'action': 'close',
                        'reason': 'telegram_close_all',
                        'side': side,
                        'current_price': current_price
                    }
                    
                    # Chama o método do bot principal
                    self.main_bot._execute_close(close_action, prices)
                    
                    results.append(f"✅ {symbol}: `${pnl_usd:+.2f}`")
                    total_realized += pnl_usd
                    
                except Exception as e:
                    logger.error(f"[TELEGRAM] Erro ao fechar {symbol}: {e}")
                    results.append(f"❌ {symbol}: Erro")
            
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
            from bot.utils.telegram_utils import escape_markdown_v2, build_safe_line, format_number
            
            analyzer = PerformanceAnalyzer()
            
            # Sumários dos 3 períodos
            daily = analyzer.get_summary('daily')
            weekly = analyzer.get_summary('weekly')
            monthly = analyzer.get_summary('monthly')
            
            # Monta mensagem com SANITIZAÇÃO COMPLETA
            lines = []
            
            # Header
            lines.append("📊 " + escape_markdown_v2("PERFORMANCE SUMMARY"))
            lines.append(escape_markdown_v2("=" * 30))
            lines.append("")
            
            # === DIÁRIO ===
            lines.append("📅 " + escape_markdown_v2("HOJE"))
            lines.append(build_safe_line("• Trades: ", daily['total_trades']))
            lines.append(build_safe_line("• PnL: ", f"${daily['pnl']['total']:.2f}"))
            lines.append(build_safe_line("• Win Rate: ", f"{daily['win_rate']:.1f}%"))
            lines.append(build_safe_line("• RR Médio: ", f"{daily['avg_rr']:.2f}R"))
            lines.append(build_safe_line("• Profit Factor: ", f"{daily['profit_factor']:.2f}"))
            
            if daily['best_worst']:
                best_trade = daily['best_worst'].get('best_trade', {})
                worst_trade = daily['best_worst'].get('worst_trade', {})
                
                if best_trade:
                    symbol = best_trade.get('symbol', 'N/A')
                    pnl = best_trade.get('pnl', 0)
                    line = escape_markdown_v2(f"• Melhor: {symbol} (${pnl:.2f})")
                    lines.append(line)
                
                if worst_trade:
                    symbol = worst_trade.get('symbol', 'N/A')
                    pnl = worst_trade.get('pnl', 0)
                    line = escape_markdown_v2(f"• Pior: {symbol} (${pnl:.2f})")
                    lines.append(line)
            
            lines.append("")
            
            # === SEMANAL ===
            lines.append("📆 " + escape_markdown_v2("7 DIAS"))
            lines.append(build_safe_line("• Trades: ", weekly['total_trades']))
            lines.append(build_safe_line("• PnL: ", f"${weekly['pnl']['total']:.2f}"))
            lines.append(build_safe_line("• Win Rate: ", f"{weekly['win_rate']:.1f}%"))
            lines.append(build_safe_line("• RR Médio: ", f"{weekly['avg_rr']:.2f}R"))
            lines.append(build_safe_line("• Profit Factor: ", f"{weekly['profit_factor']:.2f}"))
            
            if weekly['best_worst']:
                best_symbol = weekly['best_worst'].get('best_symbol', {})
                worst_symbol = weekly['best_worst'].get('worst_symbol', {})
                
                if best_symbol:
                    symbol = best_symbol.get('symbol', 'N/A')
                    pnl = best_symbol.get('pnl', 0)
                    line = escape_markdown_v2(f"• Melhor símbolo: {symbol} (${pnl:.2f})")
                    lines.append(line)
                
                if worst_symbol:
                    symbol = worst_symbol.get('symbol', 'N/A')
                    pnl = worst_symbol.get('pnl', 0)
                    line = escape_markdown_v2(f"• Pior símbolo: {symbol} (${pnl:.2f})")
                    lines.append(line)
            
            lines.append("")
            
            # === MENSAL ===
            lines.append("📊 " + escape_markdown_v2("30 DIAS"))
            lines.append(build_safe_line("• Trades: ", monthly['total_trades']))
            lines.append(build_safe_line("• PnL: ", f"${monthly['pnl']['total']:.2f}"))
            lines.append(build_safe_line("• Win Rate: ", f"{monthly['win_rate']:.1f}%"))
            lines.append(build_safe_line("• RR Médio: ", f"{monthly['avg_rr']:.2f}R"))
            lines.append(build_safe_line("• Profit Factor: ", f"{monthly['profit_factor']:.2f}"))
            lines.append(build_safe_line("• Avg Duration: ", monthly['avg_duration']))
            
            if monthly['best_worst']:
                best_strategy = monthly['best_worst'].get('best_strategy', {})
                worst_strategy = monthly['best_worst'].get('worst_strategy', {})
                
                if best_strategy:
                    strategy = best_strategy.get('strategy', 'N/A')
                    pnl = best_strategy.get('pnl', 0)
                    line = escape_markdown_v2(f"• Melhor estratégia: {strategy} (${pnl:.2f})")
                    lines.append(line)
                
                if worst_strategy:
                    strategy = worst_strategy.get('strategy', 'N/A')
                    pnl = worst_strategy.get('pnl', 0)
                    line = escape_markdown_v2(f"• Pior estratégia: {strategy} (${pnl:.2f})")
                    lines.append(line)
            
            # === QUALITY GATE ===
            rejection = daily['rejection_rate']
            lines.append("")
            lines.append("🎯 " + escape_markdown_v2("QUALITY GATE"))
            lines.append(build_safe_line("• Sinais hoje: ", rejection['total_signals']))
            lines.append(build_safe_line("• Executados: ", rejection['executed']))
            
            rejected_str = f"{rejection['rejected']} ({rejection['rejection_rate']:.1f}%)"
            lines.append(build_safe_line("• Rejeitados: ", rejected_str))
            
            skipped_str = f"{rejection['skipped']} ({rejection['skip_rate']:.1f}%)"
            lines.append(build_safe_line("• Pulados: ", skipped_str))
            
            lines.append("")
            lines.append("⏰ " + escape_markdown_v2(datetime.utcnow().strftime('%d/%m %H:%M UTC')))
            
            # Junta tudo
            msg = "\n".join(lines)
            
            # Envia com MarkdownV2
            self.bot.send_message(chat_id, msg, parse_mode="MarkdownV2")
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar performance summary: {e}", exc_info=True)
            # Fallback sem formatação
            try:
                self.bot.send_message(
                    chat_id,
                    f"❌ Erro ao gerar sumário: {str(e)[:100]}",
                    parse_mode=None
                )
            except:
                pass
    
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
            from bot.utils.telegram_utils import escape_markdown_v2, build_safe_line, format_number
            
            analyzer = PerformanceAnalyzer()
            daily = analyzer.get_summary('daily')
            
            # Monta mensagem com SANITIZAÇÃO COMPLETA
            lines = []
            
            # Header
            lines.append("📖 " + escape_markdown_v2("DIÁRIO DE TRADING"))
            lines.append(escape_markdown_v2("=" * 30))
            lines.append("📅 " + escape_markdown_v2(datetime.utcnow().strftime('%d/%m/%Y')))
            lines.append("")
            
            # === RESUMO DO DIA ===
            lines.append("📊 " + escape_markdown_v2("RESUMO"))
            lines.append(build_safe_line("• Trades fechados: ", daily['total_trades']))
            lines.append(build_safe_line("• Parciais: ", daily['total_partials']))
            lines.append(build_safe_line("• Win Rate: ", f"{daily['win_rate']:.1f}%"))
            lines.append(build_safe_line("• PnL Realizado: ", format_number(daily['pnl']['total'], 2, "$")))
            lines.append(build_safe_line("• PnL Médio: ", format_number(daily['pnl']['avg'], 2, "$")))
            lines.append(build_safe_line("• RR Médio: ", f"{daily['avg_rr']:.2f}R"))
            lines.append(build_safe_line("• Profit Factor: ", f"{daily['profit_factor']:.2f}"))
            lines.append("")
            
            # === DESTAQUES ===
            if daily['best_worst']:
                best_worst = daily['best_worst']
                
                lines.append("🌟 " + escape_markdown_v2("DESTAQUES"))
                
                best_trade = best_worst.get('best_trade', {})
                if best_trade:
                    symbol = best_trade.get('symbol', 'N/A')
                    pnl = best_trade.get('pnl', 0)
                    pnl_pct = best_trade.get('pnl_pct', 0)
                    
                    line = escape_markdown_v2(f"• Melhor trade: {symbol} (${pnl:.2f} | {pnl_pct:.2f}%)")
                    lines.append(line)
                
                worst_trade = best_worst.get('worst_trade', {})
                if worst_trade:
                    symbol = worst_trade.get('symbol', 'N/A')
                    pnl = worst_trade.get('pnl', 0)
                    pnl_pct = worst_trade.get('pnl_pct', 0)
                    
                    line = escape_markdown_v2(f"• Pior trade: {symbol} (${pnl:.2f} | {pnl_pct:.2f}%)")
                    lines.append(line)
                
                best_strategy = best_worst.get('best_strategy', {})
                if best_strategy:
                    strategy = best_strategy.get('strategy', 'N/A')
                    pnl = best_strategy.get('pnl', 0)
                    
                    line = escape_markdown_v2(f"• Melhor estratégia: {strategy} (${pnl:.2f})")
                    lines.append(line)
                
                lines.append("")
            
            # === OBSERVAÇÕES DA IA ===
            lines.append("🧠 " + escape_markdown_v2("OBSERVAÇÕES DA IA"))
            
            # Win rate analysis
            if daily['win_rate'] >= 70:
                lines.append(escape_markdown_v2("✅ Win rate excelente hoje!"))
            elif daily['win_rate'] >= 50:
                lines.append(escape_markdown_v2("✓ Win rate dentro do esperado"))
            else:
                lines.append(escape_markdown_v2("⚠️ Win rate abaixo do ideal"))
            
            # RR analysis
            if daily['avg_rr'] >= 2.0:
                lines.append(escape_markdown_v2("✅ RR médio muito bom (≥2R)"))
            elif daily['avg_rr'] >= 1.5:
                lines.append(escape_markdown_v2("✓ RR médio satisfatório"))
            else:
                lines.append(escape_markdown_v2("⚠️ RR médio pode melhorar"))
            
            # Profit factor
            if daily['profit_factor'] >= 2.0:
                lines.append(escape_markdown_v2("✅ Profit Factor excelente (≥2.0)"))
            elif daily['profit_factor'] >= 1.5:
                lines.append(escape_markdown_v2("✓ Profit Factor bom"))
            elif daily['profit_factor'] > 0:
                lines.append(escape_markdown_v2("⚠️ Profit Factor baixo"))
            else:
                lines.append(escape_markdown_v2("❌ Profit Factor negativo (perdas > ganhos)"))
            
            # Quality Gate effectiveness
            rejection = daily['rejection_rate']
            if rejection['total_signals'] > 0:
                execution_rate = (rejection['executed'] / rejection['total_signals']) * 100
                line = escape_markdown_v2(f"🎯 Quality Gate executou {execution_rate:.1f}% dos sinais")
                lines.append(line)
                
                if rejection['rejection_rate'] > 50:
                    lines.append(escape_markdown_v2("⚠️ Muitos sinais rejeitados (mercado difícil)"))
            
            lines.append("")
            
            # === SUGESTÃO PARA AMANHÃ ===
            lines.append("💡 " + escape_markdown_v2("SUGESTÃO PARA AMANHÃ"))
            
            if daily['total_trades'] == 0:
                lines.append(escape_markdown_v2("• Nenhum trade hoje - mercado pode estar em range"))
                lines.append(escape_markdown_v2("• Aguardar setup mais claro"))
            elif daily['win_rate'] < 50:
                lines.append(escape_markdown_v2("• Focar em qualidade vs quantidade"))
                lines.append(escape_markdown_v2("• Revisar confluências antes de entrar"))
                lines.append(escape_markdown_v2("• Considerar aumentar threshold do Quality Gate"))
            elif daily['avg_rr'] < 1.5:
                lines.append(escape_markdown_v2("• Deixar trades correrem mais"))
                lines.append(escape_markdown_v2("• Evitar parciais muito cedo"))
                lines.append(escape_markdown_v2("• Aguardar 2R+ antes de sair"))
            else:
                lines.append(escape_markdown_v2("• Manter a consistência"))
                lines.append(escape_markdown_v2("• Continuar respeitando o Quality Gate"))
                lines.append(escape_markdown_v2("• Focar em setups A+"))
            
            # Market Intelligence para amanhã
            try:
                mi = self.market_intel.get_full_data()
                fg = mi.get('fear_greed', {}).get('value', 50)
                
                lines.append("")
                lines.append("🌍 " + escape_markdown_v2("CONTEXTO DE MERCADO"))
                if fg < 30:
                    lines.append(escape_markdown_v2("• Fear & Greed baixo - oportunidades em dip"))
                elif fg > 70:
                    lines.append(escape_markdown_v2("• Fear & Greed alto - cautela com topos"))
                else:
                    lines.append(escape_markdown_v2("• Fear & Greed neutro - mercado equilibrado"))
            except:
                pass
            
            lines.append("")
            lines.append("⏰ " + escape_markdown_v2(datetime.utcnow().strftime('%d/%m %H:%M UTC')))
            lines.append("")
            lines.append(escape_markdown_v2("Use /pnl para métricas detalhadas"))
            
            # Junta tudo
            msg = "\n".join(lines)
            
            # Envia com MarkdownV2
            self.bot.send_message(chat_id, msg, parse_mode="MarkdownV2")
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar daily report: {e}", exc_info=True)
            # Fallback sem formatação
            try:
                self.bot.send_message(
                    chat_id, 
                    f"❌ Erro ao gerar diário formatado. Detalhes: {str(e)[:100]}",
                    parse_mode=None
                )
            except:
                pass
    
    # ========== PHASE 5: TRADING MODES ==========
    
    def _send_modo_menu(self, chat_id: int):
        """
        Envia menu de seleção de modo
        """
        try:
            from bot.phase5 import TradingMode, TradingModeConfig, TradingModeManager
            
            # Tenta pegar modo manager do bot principal
            mode_manager = getattr(self.main_bot, 'mode_manager', None)
            
            # Se não tiver, cria um temporário (para poder testar)
            if not mode_manager:
                logger.warning("[TELEGRAM] mode_manager não encontrado no bot, criando temporário")
                mode_manager = TradingModeManager()
                # Salva no bot para próxima vez
                self.main_bot.mode_manager = mode_manager
            
            current_mode = mode_manager.get_current_mode()
            current_config = mode_manager.get_current_config()
            
            # Monta mensagem (texto simples sem markdown)
            msg = "🎚️ MODOS DE TRADING\n"
            msg += "=" * 30 + "\n\n"
            
            msg += f"Modo atual: {current_config['emoji']} {current_mode.value}\n"
            msg += f"{current_config['description']}\n\n"
            
            msg += "Escolha o modo de operação:\n\n"
            
            # Descrição dos modos
            for mode, config in TradingModeConfig.get_all_modes().items():
                emoji = config['emoji']
                name = mode.value
                desc = config['description']
                
                msg += f"{emoji} {name}\n"
                msg += f"   Risco: {config['risk_multiplier']*100:.0f}% do base\n"
                msg += f"   Sinais/dia: até {config['max_signals_per_day']}\n"
                msg += f"   Regimes: {len(config['allowed_regimes'])}\n\n"
            
            # Cria botões inline
            from telebot import types
            markup = types.InlineKeyboardMarkup(row_width=1)
            
            for mode in [TradingMode.CONSERVADOR, TradingMode.BALANCEADO, TradingMode.AGRESSIVO]:
                config = TradingModeConfig.get_config(mode)
                emoji = config['emoji']
                
                # Marca modo atual com ✓
                if mode == current_mode:
                    button_text = f"✓ {emoji} {mode.value}"
                else:
                    button_text = f"{emoji} {mode.value}"
                
                button = types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"modo_{mode.value}"
                )
                markup.add(button)
            
            # Envia sem parse_mode para evitar erros
            self.bot.send_message(chat_id, msg, reply_markup=markup, parse_mode=None)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar modo menu: {e}", exc_info=True)
            self.bot.send_message(
                chat_id,
                f"❌ Erro ao exibir modos: {str(e)[:100]}",
                parse_mode=None
            )
    
    def _change_mode(self, chat_id: int, mode_name: str):
        """
        Altera modo de trading
        
        Args:
            chat_id: ID do chat
            mode_name: Nome do modo (CONSERVADOR, BALANCEADO, AGRESSIVO)
        """
        try:
            from bot.phase5 import TradingMode, TradingModeConfig, TradingModeManager
            
            # Pega mode manager do bot principal
            mode_manager = getattr(self.main_bot, 'mode_manager', None)
            
            # Se não tiver, cria um
            if not mode_manager:
                logger.warning("[TELEGRAM] mode_manager não encontrado, criando novo")
                mode_manager = TradingModeManager()
                self.main_bot.mode_manager = mode_manager
            
            # Converte string para enum
            try:
                new_mode = TradingMode[mode_name]
            except KeyError:
                self.bot.send_message(
                    chat_id,
                    f"❌ Modo inválido: {mode_name}",
                    parse_mode=None
                )
                return
            
            # Verifica se já está nesse modo
            if mode_manager.get_current_mode() == new_mode:
                config = TradingModeConfig.get_config(new_mode)
                msg = f"{config['emoji']} Já está no modo {new_mode.value}"
                self.bot.send_message(chat_id, msg, parse_mode=None)
                return
            
            # Altera modo
            success = mode_manager.set_mode(new_mode, source="telegram")
            
            if success:
                config = TradingModeConfig.get_config(new_mode)
                
                msg = f"✅ Modo alterado para: {config['emoji']} {new_mode.value}\n\n"
                
                # Explica o que mudou
                if new_mode == TradingMode.CONSERVADOR:
                    msg += "O bot ficará mais seletivo:\n"
                    msg += "• Risco reduzido (50% do padrão)\n"
                    msg += "• Confiança mínima +10%\n"
                    msg += "• Apenas trends limpos\n"
                    msg += "• Máx 10 sinais/dia"
                
                elif new_mode == TradingMode.BALANCEADO:
                    msg += "Modo equilibrado ativado:\n"
                    msg += "• Risco padrão (100%)\n"
                    msg += "• Confiança padrão\n"
                    msg += "• Todos regimes permitidos\n"
                    msg += "• Máx 20 sinais/dia"
                
                elif new_mode == TradingMode.AGRESSIVO:
                    msg += "Modo agressivo ativado:\n"
                    msg += "• Risco aumentado (120% do padrão)\n"
                    msg += "• Confiança mínima -5%\n"
                    msg += "• Mais regimes permitidos\n"
                    msg += "• Máx 40 sinais/dia"
                
                self.bot.send_message(chat_id, msg, parse_mode=None)
            else:
                self.bot.send_message(
                    chat_id,
                    "❌ Erro ao alterar modo",
                    parse_mode=None
                )
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao alterar modo: {e}", exc_info=True)
            self.bot.send_message(
                chat_id,
                f"❌ Erro: {str(e)[:100]}",
                parse_mode=None
            )
    
    # ========== PHASE 6: RISK STATUS & CONTROLS ==========
    
    def _send_risk_status(self, chat_id: int):
        """
        Envia status de risco com controles
        """
        try:
            # Pega risk manager do bot principal
            risk_manager = getattr(self.main_bot, 'risk_manager', None)
            
            if not risk_manager:
                self.bot.send_message(
                    chat_id,
                    "⚠️ Sistema de risco não disponível",
                    parse_mode=None
                )
                return
            
            status = risk_manager.get_status()
            
            # Monta mensagem (texto simples para evitar erros)
            msg = "🛡 STATUS DE RISCO\n"
            msg += "=" * 30 + "\n\n"
            
            # Estado atual
            state = status['state']
            if state == 'RUNNING':
                msg += "✅ Estado: OPERANDO NORMALMENTE\n\n"
            elif state == 'COOLDOWN':
                cooldown_end = datetime.fromtimestamp(status['cooldown_until']).strftime('%H:%M')
                msg += f"⏸️ Estado: COOLDOWN até {cooldown_end}\n\n"
            elif state == 'HALTED_DAILY':
                msg += "🔴 Estado: CIRCUIT BREAKER DIÁRIO\n\n"
            elif state == 'HALTED_WEEKLY':
                msg += "🔴 Estado: CIRCUIT BREAKER SEMANAL\n\n"
            elif state == 'HALTED_DRAWDOWN':
                msg += "🔴 Estado: CIRCUIT BREAKER DRAWDOWN\n\n"
            
            # Métricas
            msg += "📊 MÉTRICAS\n"
            msg += f"• Equity Peak: ${status['equity_peak']:.2f}\n"
            msg += f"• PnL Hoje: ${status['daily_pnl']:.2f} ({status['daily_pnl_pct']:.2f}%)\n"
            msg += f"• PnL Semana: ${status['weekly_pnl']:.2f} ({status['weekly_pnl_pct']:.2f}%)\n"
            msg += f"• Drawdown: {status['drawdown_pct']:.2f}%\n"
            msg += f"• Losing Streak: {status['losing_streak']}\n\n"
            
            # Limites
            limits = status['limits']
            msg += "🚨 LIMITES\n"
            msg += f"• Perda Diária Máx: {limits['daily_loss_limit_pct']:.1f}%\n"
            msg += f"• Perda Semanal Máx: {limits['weekly_loss_limit_pct']:.1f}%\n"
            msg += f"• Drawdown Máx: {limits['max_drawdown_pct']:.1f}%\n"
            msg += f"• Losing Streak Máx: {limits['max_losing_streak']}\n"
            
            # Cria botões inline
            from telebot import types
            markup = types.InlineKeyboardMarkup(row_width=1)
            
            # Botão Cooldown
            if state == 'RUNNING':
                btn_cooldown = types.InlineKeyboardButton(
                    text="⏸️ Ativar Cooldown (60 min)",
                    callback_data="risk_force_cooldown"
                )
                markup.add(btn_cooldown)
            
            # Botão Reset Diário (se não HALTED_DAILY)
            if state != 'HALTED_DAILY':
                btn_reset_daily = types.InlineKeyboardButton(
                    text="🔄 Reset Diário",
                    callback_data="risk_reset_daily_confirm"
                )
                markup.add(btn_reset_daily)
            
            # Botão Reset Semanal (se não HALTED_WEEKLY)
            if state != 'HALTED_WEEKLY':
                btn_reset_weekly = types.InlineKeyboardButton(
                    text="🔄 Reset Semanal",
                    callback_data="risk_reset_weekly_confirm"
                )
                markup.add(btn_reset_weekly)
            
            # Envia
            self.bot.send_message(chat_id, msg, reply_markup=markup, parse_mode=None)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar risk status: {e}", exc_info=True)
            self.bot.send_message(
                chat_id,
                f"❌ Erro ao exibir status de risco: {str(e)[:100]}",
                parse_mode=None
            )
    
    def _handle_force_cooldown(self, chat_id: int):
        """Ativa cooldown manual"""
        try:
            risk_manager = getattr(self.main_bot, 'risk_manager', None)
            
            if not risk_manager:
                self.bot.send_message(chat_id, "⚠️ Sistema de risco não disponível", parse_mode=None)
                return
            
            success = risk_manager.force_cooldown(source="telegram")
            
            if success:
                msg = "✅ Cooldown ativado por 60 minutos\n\n"
                msg += "O bot não abrirá novas posições até o fim do cooldown."
                self.bot.send_message(chat_id, msg, parse_mode=None)
            else:
                self.bot.send_message(chat_id, "❌ Erro ao ativar cooldown", parse_mode=None)
                
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao ativar cooldown: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)[:100]}", parse_mode=None)
    
    def _ask_reset_daily_confirmation(self, chat_id: int):
        """Pede confirmação para reset diário"""
        try:
            from telebot import types
            
            msg = "⚠️ CONFIRMAÇÃO NECESSÁRIA\n\n"
            msg += "Tem certeza que deseja resetar os limites diários?\n\n"
            msg += "Isso irá zerar:\n"
            msg += "• PnL do dia\n"
            msg += "• Losing streak\n"
            msg += "• Circuit breaker diário (se ativo)\n\n"
            msg += "Use com cuidado!"
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn_confirm = types.InlineKeyboardButton(
                text="✅ Confirmar",
                callback_data="risk_reset_daily_execute"
            )
            btn_cancel = types.InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="risk_cancel"
            )
            markup.add(btn_confirm, btn_cancel)
            
            self.bot.send_message(chat_id, msg, reply_markup=markup, parse_mode=None)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro na confirmação: {e}")
    
    def _execute_reset_daily(self, chat_id: int):
        """Executa reset diário"""
        try:
            risk_manager = getattr(self.main_bot, 'risk_manager', None)
            
            if not risk_manager:
                self.bot.send_message(chat_id, "⚠️ Sistema de risco não disponível", parse_mode=None)
                return
            
            success = risk_manager.reset_daily_limits(source="telegram")
            
            if success:
                msg = "✅ Limites diários resetados com sucesso\n\n"
                msg += "PnL do dia zerado e circuit breaker diário desativado."
                self.bot.send_message(chat_id, msg, parse_mode=None)
            else:
                self.bot.send_message(chat_id, "❌ Erro ao resetar limites", parse_mode=None)
                
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao resetar daily: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)[:100]}", parse_mode=None)
    
    def _ask_reset_weekly_confirmation(self, chat_id: int):
        """Pede confirmação para reset semanal"""
        try:
            from telebot import types
            
            msg = "⚠️ CONFIRMAÇÃO NECESSÁRIA\n\n"
            msg += "Tem certeza que deseja resetar os limites semanais?\n\n"
            msg += "Isso irá zerar:\n"
            msg += "• PnL da semana\n"
            msg += "• Circuit breaker semanal (se ativo)\n\n"
            msg += "Use com cuidado!"
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn_confirm = types.InlineKeyboardButton(
                text="✅ Confirmar",
                callback_data="risk_reset_weekly_execute"
            )
            btn_cancel = types.InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="risk_cancel"
            )
            markup.add(btn_confirm, btn_cancel)
            
            self.bot.send_message(chat_id, msg, reply_markup=markup, parse_mode=None)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro na confirmação: {e}")
    
    def _execute_reset_weekly(self, chat_id: int):
        """Executa reset semanal"""
        try:
            risk_manager = getattr(self.main_bot, 'risk_manager', None)
            
            if not risk_manager:
                self.bot.send_message(chat_id, "⚠️ Sistema de risco não disponível", parse_mode=None)
                return
            
            success = risk_manager.reset_weekly_limits(source="telegram")
            
            if success:
                msg = "✅ Limites semanais resetados com sucesso\n\n"
                msg += "PnL da semana zerado e circuit breaker semanal desativado."
                self.bot.send_message(chat_id, msg, parse_mode=None)
            else:
                self.bot.send_message(chat_id, "❌ Erro ao resetar limites", parse_mode=None)
                
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao resetar weekly: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)[:100]}", parse_mode=None)
    
    # ========== PHASE 7: JOURNAL & COACH ==========
    
    def _send_journal(self, chat_id: int):
        """Envia últimos trades do journal"""
        try:
            journal = getattr(self.main_bot, 'trade_journal', None)
            if not journal:
                self.bot.send_message(chat_id, "⚠️ Journal não disponível", parse_mode=None)
                return
            
            trades = journal.get_recent_trades(limit=5)
            
            if not trades:
                self.bot.send_message(chat_id, "📒 Journal vazio. Nenhum trade registrado ainda.", parse_mode=None)
                return
            
            msg = "📒 ÚLTIMOS TRADES\n"
            msg += "=" * 30 + "\n\n"
            
            for i, t in enumerate(reversed(trades), 1):
                symbol = t.get('symbol', '?')
                side = t.get('side', '?')
                style = t.get('style', '?')
                pnl_pct = t.get('pnl_pct', 0)
                strategy = t.get('strategy_tag', 'N/A')
                
                emoji = "✅" if pnl_pct > 0 else "❌"
                msg += f"{i}. {symbol} {side} ({style}) {emoji} {pnl_pct:+.2f}%\n"
                msg += f"   Estratégia: {strategy}\n"
                
                reason = t.get('reason_summary', '')
                if reason and len(reason) < 80:
                    msg += f"   Motivo: {reason}\n"
                msg += "\n"
            
            self.bot.send_message(chat_id, msg, parse_mode=None)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar journal: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)[:100]}", parse_mode=None)
    
    def _send_performance(self, chat_id: int):
        """Envia análise de performance"""
        try:
            perf_engine = getattr(self.main_bot, 'performance_engine', None)
            if not perf_engine:
                self.bot.send_message(chat_id, "⚠️ Performance Engine não disponível", parse_mode=None)
                return
            
            best_worst = perf_engine.get_best_worst_pairs(limit=3)
            
            if not best_worst.get('best') and not best_worst.get('worst'):
                self.bot.send_message(chat_id, "📊 Ainda não há dados suficientes", parse_mode=None)
                return
            
            msg = "📊 PERFORMANCE ANALYSIS\n"
            msg += "=" * 30 + "\n\n"
            
            # Top 3
            if best_worst.get('best'):
                msg += "🏆 TOP 3 PARES:\n"
                for sym, stats in best_worst['best']:
                    msg += f"  {sym}: WR {stats['win_rate']:.1f}% | Exp {stats['expectancy']:.2f}%\n"
                msg += "\n"
            
            # Piores 3
            if best_worst.get('worst'):
                msg += "⚠️ PIORES 3 PARES:\n"
                for sym, stats in best_worst['worst']:
                    msg += f"  {sym}: WR {stats['win_rate']:.1f}% | Exp {stats['expectancy']:.2f}%\n"
            
            self.bot.send_message(chat_id, msg, parse_mode=None)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar performance: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)[:100]}", parse_mode=None)
    
    def _send_weekly_summary(self, chat_id: int):
        """Envia resumo semanal"""
        try:
            perf_engine = getattr(self.main_bot, 'performance_engine', None)
            if not perf_engine:
                self.bot.send_message(chat_id, "⚠️ Performance Engine não disponível", parse_mode=None)
                return
            
            summary = perf_engine.get_weekly_summary()
            
            if 'error' in summary:
                self.bot.send_message(chat_id, f"🏆 {summary['error']}", parse_mode=None)
                return
            
            msg = "🏆 RESUMO DA SEMANA\n"
            msg += "=" * 30 + "\n\n"
            msg += f"📊 Trades: {summary['trades']}\n"
            msg += f"✅ Win Rate: {summary['win_rate']:.1f}%\n"
            msg += f"💰 PnL Médio: {summary['avg_pnl']:.2f}%\n\n"
            
            if 'best_trade' in summary:
                best = summary['best_trade']
                msg += f"🏆 Melhor Trade:\n"
                msg += f"   {best.get('symbol')} {best.get('side')} {best.get('pnl_pct', 0):+.2f}%\n\n"
            
            if 'worst_trade' in summary:
                worst = summary['worst_trade']
                msg += f"📉 Pior Trade:\n"
                msg += f"   {worst.get('symbol')} {worst.get('side')} {worst.get('pnl_pct', 0):+.2f}%\n"
            
            self.bot.send_message(chat_id, msg, parse_mode=None)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar semana: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)[:100]}", parse_mode=None)
    
    def _send_coach_insights(self, chat_id: int):
        """Envia insights do IA Coach"""
        try:
            coach = getattr(self.main_bot, 'ia_coach', None)
            if not coach:
                self.bot.send_message(chat_id, "⚠️ IA Coach não disponível", parse_mode=None)
                return
            
            insights = coach.generate_insights()
            
            if not insights:
                msg = "🧠 IA COACH\n\n"
                msg += "Ainda não há trades suficientes para gerar insights.\n"
                msg += "Continue operando e volte em breve!"
                self.bot.send_message(chat_id, msg, parse_mode=None)
                return
            
            self.bot.send_message(chat_id, insights, parse_mode=None)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar coach: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)[:100]}", parse_mode=None)
    
    # ========== PHASE 8: PAPER TRADING & SHADOW MODE ==========
    
    def _send_execution_menu(self, chat_id: int, user_id: int = None):
        """Envia menu de execução com verificação de permissão"""
        try:
            # PATCH: Verificação de permissão
            allowed_chat_id = os.getenv('TELEGRAM_CHAT_ID')
            if allowed_chat_id:
                try:
                    allowed_chat_id = int(allowed_chat_id)
                    if chat_id != allowed_chat_id:
                        self.bot.send_message(chat_id, "⛔ Você não tem permissão para acessar este menu.", parse_mode=None)
                        logger.warning(f"[EXECUTION_MODE] Acesso negado para chat_id={chat_id}")
                        return
                except ValueError:
                    pass
            
            exec_manager = getattr(self.main_bot, 'execution_manager', None)
            if not exec_manager:
                self.bot.send_message(chat_id, "⚠️ Execution Manager não disponível", parse_mode=None)
                return
            
            status = exec_manager.get_status()
            current_mode = status['mode']
            
            # Descrições dos modos
            mode_desc = {
                "LIVE": "🟢 Ordens reais na Hyperliquid",
                "PAPER_ONLY": "📝 Apenas simulação (sem ordens reais)",
                "SHADOW": "👥 Ordens reais + experimentos paper"
            }
            
            msg = "⚙️ *MODO DE EXECUÇÃO*\n"
            msg += "━" * 28 + "\n\n"
            msg += f"*Estado atual:* `{current_mode}`\n"
            msg += f"{mode_desc.get(current_mode, '')}\n\n"
            msg += "━" * 28 + "\n"
            msg += "*Modos disponíveis:*\n\n"
            msg += "🟢 *LIVE* — Envia ordens reais\n"
            msg += "📝 *PAPER* — Apenas simula\n"
            msg += "👥 *SHADOW* — Live + paper paralelo\n\n"
            msg += "Selecione um modo:"
            
            from telebot import types
            markup = types.InlineKeyboardMarkup(row_width=3)
            
            # Botões com indicação visual do modo ativo
            btn_live = types.InlineKeyboardButton(
                text="✅ LIVE" if current_mode == "LIVE" else "LIVE",
                callback_data="exec_mode_live"
            )
            btn_paper = types.InlineKeyboardButton(
                text="✅ PAPER" if current_mode == "PAPER_ONLY" else "PAPER",
                callback_data="exec_mode_paper"
            )
            btn_shadow = types.InlineKeyboardButton(
                text="✅ SHADOW" if current_mode == "SHADOW" else "SHADOW",
                callback_data="exec_mode_shadow"
            )
            
            markup.add(btn_live, btn_paper, btn_shadow)
            
            self.bot.send_message(chat_id, msg, reply_markup=markup)
            logger.info(f"[EXECUTION_MODE] Menu exibido para chat_id={chat_id}, modo atual={current_mode}")
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar execution menu: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)[:100]}", parse_mode=None)
    
    def _set_execution_mode(self, chat_id: int, mode: str, user_id: int = None):
        """Altera modo de execução com verificação de permissão"""
        try:
            # PATCH: Verificação de permissão
            allowed_chat_id = os.getenv('TELEGRAM_CHAT_ID')
            if allowed_chat_id:
                try:
                    allowed_chat_id = int(allowed_chat_id)
                    if chat_id != allowed_chat_id:
                        self.bot.send_message(chat_id, "⛔ Você não tem permissão para alterar o modo de execução.", parse_mode=None)
                        logger.warning(f"[EXECUTION_MODE] Tentativa de alteração negada para chat_id={chat_id}, user_id={user_id}")
                        return
                except ValueError:
                    pass
            
            exec_manager = getattr(self.main_bot, 'execution_manager', None)
            if not exec_manager:
                self.bot.send_message(chat_id, "⚠️ Execution Manager não disponível", parse_mode=None)
                return
            
            # Obtém modo anterior para log
            old_mode = exec_manager.execution_mode.value
            
            from bot.phase8.execution_config import ExecutionMode
            new_mode = ExecutionMode[mode]
            
            success = exec_manager.set_mode(new_mode, source=f"telegram_user_{user_id or chat_id}")
            
            if success:
                # Log detalhado
                logger.info(f"[EXECUTION_MODE] Alterado de {old_mode} para {mode} por user_id={user_id or chat_id}")
                
                msg = f"✅ *Modo de execução alterado*\n\n"
                msg += f"*Anterior:* `{old_mode}`\n"
                msg += f"*Novo:* `{mode}`\n\n"
                
                if mode == "LIVE":
                    msg += "⚠️ *ATENÇÃO:* O bot enviará ordens REAIS na Hyperliquid!"
                elif mode == "PAPER_ONLY":
                    msg += "📝 O bot NÃO enviará ordens reais. Apenas simulação."
                else:  # SHADOW
                    msg += "👥 O bot enviará ordens reais + experimentos paper em paralelo."
                
                self.bot.send_message(chat_id, msg)
                
                # Reenvia menu atualizado
                self._send_execution_menu(chat_id, user_id)
            else:
                self.bot.send_message(chat_id, "❌ Erro ao alterar modo", parse_mode=None)
                
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao alterar execution mode: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)[:100]}", parse_mode=None)
    
    def _send_real_vs_paper(self, chat_id: int):
        """Envia comparação REAL vs PAPER"""
        try:
            perf_engine = getattr(self.main_bot, 'performance_engine', None)
            if not perf_engine:
                self.bot.send_message(chat_id, "⚠️ Performance Engine não disponível", parse_mode=None)
                return
            
            summary = perf_engine.get_real_vs_paper_summary(days=30)
            
            if 'error' in summary:
                self.bot.send_message(chat_id, f"📊 {summary['error']}", parse_mode=None)
                return
            
            msg = "📊 REAL vs PAPER — 30 dias\n"
            msg += "=" * 30 + "\n\n"
            
            real = summary.get('real')
            paper = summary.get('paper')
            
            if real:
                msg += "🟢 REAL:\n"
                msg += f"  • Trades: {real['trades']}\n"
                msg += f"  • Win Rate: {real['win_rate']:.1f}%\n"
                msg += f"  • Expectancy: {real['expectancy']:+.2f}%\n\n"
            else:
                msg += "🟢 REAL: Sem trades\n\n"
            
            if paper:
                msg += "📝 PAPER:\n"
                msg += f"  • Trades: {paper['trades']}\n"
                msg += f"  • Win Rate: {paper['win_rate']:.1f}%\n"
                msg += f"  • Expectancy: {paper['expectancy']:+.2f}%\n"
            else:
                msg += "📝 PAPER: Sem trades"
            
            self.bot.send_message(chat_id, msg, parse_mode=None)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar comparação: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)[:100]}", parse_mode=None)
    
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
    
    # ========== MODO GLOBAL_IA ==========
    
    def _handle_ia_chat(self, chat_id: int, question: str):
        """Processa pergunta para o Trader IA"""
        try:
            from bot.global_ia_mode import get_global_ia_mode
            
            global_ia = get_global_ia_mode(logger_instance=logger)
            
            # Monta state atual
            state = self._build_current_state()
            
            # Chama IA
            response = global_ia.chat_with_trader(state, question)
            
            # Envia resposta usando safe_send (evita erro 400 de parse)
            if len(response) > 4000:
                chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
                for chunk in chunks:
                    self._safe_send_message(chat_id, chunk, parse_mode=None)
            else:
                self._safe_send_message(chat_id, f"🧠 *Trader IA:*\n\n{response}", parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro no chat IA: {e}")
            self._safe_send_message(chat_id, f"❌ Erro: {str(e)}", parse_mode=None)
    
    def _safe_send_message(self, chat_id: int, text: str, parse_mode: str = 'Markdown'):
        """
        Envia mensagem com fallback para texto puro se der erro de parse.
        Evita erro 400: can't parse entities
        """
        try:
            self.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        except Exception as e:
            error_str = str(e).lower()
            if "can't parse entities" in error_str or "bad request" in error_str:
                logger.warning(f"[TELEGRAM] Fallback para texto puro: {e}")
                try:
                    # Remove caracteres problemáticos de Markdown
                    clean_text = text.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')
                    self.bot.send_message(chat_id=chat_id, text=clean_text, parse_mode=None)
                except Exception as e2:
                    logger.error(f"[TELEGRAM] Erro mesmo sem parse_mode: {e2}")
            else:
                logger.error(f"[TELEGRAM] Erro ao enviar mensagem: {e}")
    
    def _build_current_state(self) -> Dict:
        """Monta state atual para a IA"""
        try:
            from bot.global_ia_mode import get_global_ia_mode
            
            global_ia = get_global_ia_mode(logger_instance=logger)
            
            # Equity e margem
            risk_manager = getattr(self.main_bot, 'risk_manager', None)
            equity = risk_manager.current_equity if risk_manager else 1000
            free_margin = equity * 0.8  # Estimativa
            day_pnl = risk_manager.daily_pnl_pct if risk_manager else 0
            
            # Posições
            position_manager = getattr(self.main_bot, 'position_manager', None)
            positions = []
            if position_manager:
                try:
                    all_prices = self.main_bot.client.get_all_mids()
                except:
                    all_prices = {}
                positions = position_manager.get_all_positions(current_prices=all_prices)
            
            # Market snapshot
            market_snapshot = []
            last_contexts = getattr(self.main_bot, 'last_market_contexts', [])
            if last_contexts:
                market_snapshot = last_contexts
            
            # Monta state
            state = global_ia.build_global_state(
                equity=equity,
                free_margin=free_margin,
                day_pnl_pct=day_pnl,
                positions=positions,
                market_snapshot=market_snapshot
            )
            
            return state
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao montar state: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}
    
    def _set_global_mode(self, chat_id: int, enable: bool):
        """Ativa/desativa modo GLOBAL_IA"""
        try:
            from bot.phase5 import TradingMode, TradingModeManager
            
            mode_manager = getattr(self.main_bot, 'mode_manager', None)
            if not mode_manager:
                mode_manager = TradingModeManager()
            
            if enable:
                success = mode_manager.set_mode(TradingMode.GLOBAL_IA, source="telegram")
                if success:
                    msg = (
                        "🧠 *MODO GLOBAL\\_IA ATIVADO*\n\n"
                        "A IA agora é 100% responsável pelas decisões de trading.\n\n"
                        "• Filtros tradicionais: *BYPASS*\n"
                        "• Cooldowns: *IGNORADOS*\n"
                        "• Quality Gate: *MÍNIMO*\n\n"
                        "Use `/ia <pergunta>` para conversar com o trader.\n"
                        "Use `/modo_global off` para desativar."
                    )
                else:
                    msg = "❌ Erro ao ativar modo GLOBAL\\_IA"
            else:
                success = mode_manager.set_mode(TradingMode.BALANCEADO, source="telegram")
                if success:
                    msg = (
                        "⚖️ *MODO GLOBAL\\_IA DESATIVADO*\n\n"
                        "Voltando para modo BALANCEADO.\n"
                        "Filtros e proteções reativados."
                    )
                else:
                    msg = "❌ Erro ao desativar modo GLOBAL\\_IA"
            
            self.bot.send_message(chat_id, msg, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao alterar modo global: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)}", parse_mode=None)
    
    def _send_ia_menu(self, chat_id: int):
        """Envia menu de interação com a IA"""
        try:
            from bot.phase5 import TradingMode
            
            mode_manager = getattr(self.main_bot, 'mode_manager', None)
            current_mode = mode_manager.current_mode if mode_manager else TradingMode.BALANCEADO
            is_global = current_mode == TradingMode.GLOBAL_IA
            
            msg = "🧠 *TRADER IA - Menu*\n\n"
            
            if is_global:
                msg += "✅ *Modo GLOBAL\\_IA ATIVO*\n"
                msg += "A IA está 100% no controle das operações.\n\n"
            else:
                msg += f"📊 Modo atual: *{current_mode.value}*\n\n"
            
            msg += "*Comandos disponíveis:*\n\n"
            msg += "💬 `/ia <pergunta>` - Conversar com o trader\n"
            msg += "_Exemplo: /ia O que você está vendo no mercado?_\n\n"
            msg += "📊 `/state` - Ver dados que a IA enxerga\n\n"
            
            if is_global:
                msg += "🔴 `/modo_global off` - Desativar modo autônomo\n"
            else:
                msg += "🟢 `/modo_global on` - Ativar modo 100% autônomo\n"
            
            msg += "\n*Perguntas que você pode fazer:*\n"
            msg += "• _Por que você abriu BTC long?_\n"
            msg += "• _Qual sua visão do mercado agora?_\n"
            msg += "• _Devo fechar minha posição em SOL?_\n"
            msg += "• _O que você faria com $500?_\n"
            msg += "• _Quais oportunidades você vê?_\n"
            
            # Botões inline para ações rápidas
            markup = types.InlineKeyboardMarkup(row_width=2)
            
            if is_global:
                markup.add(
                    types.InlineKeyboardButton("🔴 Desativar GLOBAL_IA", callback_data="global_ia_off"),
                    types.InlineKeyboardButton("📊 Ver State", callback_data="global_ia_state")
                )
            else:
                markup.add(
                    types.InlineKeyboardButton("🟢 Ativar GLOBAL_IA", callback_data="global_ia_on"),
                    types.InlineKeyboardButton("📊 Ver State", callback_data="global_ia_state")
                )
            
            markup.add(
                types.InlineKeyboardButton("💬 Perguntar: Visão do mercado?", callback_data="ia_ask_market")
            )
            
            self.bot.send_message(chat_id, msg, parse_mode='Markdown', reply_markup=markup)
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar menu IA: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)}", parse_mode=None)
    
    def _show_global_mode_status(self, chat_id: int):
        """Mostra status do modo GLOBAL_IA"""
        try:
            from bot.phase5 import TradingMode
            
            mode_manager = getattr(self.main_bot, 'mode_manager', None)
            current_mode = mode_manager.current_mode if mode_manager else TradingMode.BALANCEADO
            
            is_global = current_mode == TradingMode.GLOBAL_IA
            
            msg = "🧠 *Status do Modo GLOBAL\\_IA*\n\n"
            
            if is_global:
                msg += "✅ *ATIVO*\n\n"
                msg += "A IA está 100% no controle.\n"
                msg += "Filtros tradicionais estão em BYPASS.\n\n"
                msg += "Comandos:\n"
                msg += "• `/ia <pergunta>` - Conversar com trader\n"
                msg += "• `/state` - Ver estado atual\n"
                msg += "• `/modo_global off` - Desativar"
            else:
                msg += f"❌ *INATIVO* (modo atual: {current_mode.value})\n\n"
                msg += "Comandos:\n"
                msg += "• `/modo_global on` - Ativar modo GLOBAL\\_IA\n"
                msg += "• `/ia <pergunta>` - Conversar com trader (funciona sempre)"
            
            self.bot.send_message(chat_id, msg, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao mostrar status global: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)}", parse_mode=None)
    
    def _send_global_state(self, chat_id: int):
        """Envia o STATE atual que a IA vê"""
        try:
            import json
            
            state = self._build_current_state()
            
            # Formata como JSON bonito
            state_json = json.dumps(state, indent=2, ensure_ascii=False)
            
            msg = "🧠 *STATE Atual (visão da IA)*\n\n"
            msg += f"```json\n{state_json[:3500]}\n```"  # Limita tamanho
            
            if len(state_json) > 3500:
                msg += "\n\n_(truncado por limite de tamanho)_"
            
            self.bot.send_message(chat_id, msg, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro ao enviar state: {e}")
            self.bot.send_message(chat_id, f"❌ Erro: {str(e)}", parse_mode=None)
