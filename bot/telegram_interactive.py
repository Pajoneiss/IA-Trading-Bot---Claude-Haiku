"""
Telegram Interactive Bot
Módulo para interação bidirecional via Telegram
"""
import os
import threading
import logging
import time
import requests
from datetime import datetime
from typing import Optional, Dict, Any

# Tenta importar telebot, mas não falha se não estiver instalado (para não quebrar o bot principal)
try:
    import telebot
    from telebot import types
    TELEBOT_AVAILABLE = True
except ImportError:
    TELEBOT_AVAILABLE = False

logger = logging.getLogger(__name__)

class TelegramInteractive:
    """
    Gerencia comandos e interações do Telegram.
    Roda em thread separada para não bloquear o bot principal.
    Implementa Singleton para evitar múltiplas instâncias.
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(TelegramInteractive, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, main_bot, token: str):
        # Evita re-inicialização se já foi inicializado
        if hasattr(self, 'initialized') and self.initialized:
            return
            
        self.main_bot = main_bot
        self.token = token
        self.bot = None
        self.is_running = False
        self.thread = None
        self.initialized = True
        
        if not TELEBOT_AVAILABLE:
            logger.warning("⚠️ pyTelegramBotAPI não instalado. Funcionalidades interativas desativadas.")
            return
            
        if not token:
            logger.warning("⚠️ Token do Telegram não fornecido. Funcionalidades interativas desativadas.")
            return
            
        try:
            self.bot = telebot.TeleBot(token, parse_mode='Markdown')
            self._setup_handlers()
            logger.info("✅ Telegram Interactive inicializado")
        except Exception as e:
            logger.error(f"Erro ao inicializar Telegram Interactive: {e}")
    
    def start(self):
        """Inicia o listener do Telegram em background"""
        if not self.bot:
            logger.warning("[TELEGRAM] Bot não inicializado, ignorando start().")
            return
            
        if self.is_running:
            logger.warning("[TELEGRAM] start() chamado novamente, ignorando (já iniciado).")
            return
            
        self.is_running = True
        self.thread = threading.Thread(target=self._run_polling, daemon=True)
        self.thread.start()
        logger.info("🚀 [TELEGRAM] Bot iniciado (polling em background).")
        
    def _run_polling(self):
        """Loop de polling - CHAMA INFINITY_POLLING APENAS UMA VEZ"""
        try:
            logger.info("[TELEGRAM] Iniciando infinity_polling...")
            # skip_pending=True evita processar mensagens antigas ao reiniciar
            self.bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except Exception as e:
            logger.error(f"[TELEGRAM] Erro no polling: {e}")
            self.is_running = False
                
    def _setup_handlers(self):
        """Configura handlers de comandos"""
        
        @self.bot.message_handler(commands=['start', 'menu'])
        def send_welcome(message):
            self._send_menu(message.chat.id)
            
        @self.bot.message_handler(commands=['status'])
        def send_status(message):
            self._send_status(message.chat.id)
            
        @self.bot.message_handler(commands=['positions'])
        def send_positions(message):
            self._send_positions(message.chat.id)
            
        @self.bot.message_handler(commands=['balance'])
        def send_balance(message):
            self._send_balance(message.chat.id)
            
        @self.bot.message_handler(commands=['pnl'])
        def send_pnl(message):
            self._send_pnl(message.chat.id)
            
        @self.bot.message_handler(commands=['fear'])
        def send_fear(message):
            self._send_fear_index(message.chat.id)
            
        @self.bot.message_handler(commands=['news'])
        def send_news(message):
            self._send_news(message.chat.id)
            
        @self.bot.message_handler(commands=['ai'])
        def chat_ai(message):
            query = message.text.replace('/ai', '').strip()
            if not query:
                self.bot.reply_to(message, "Por favor, digite sua pergunta após /ai. Ex: `/ai O que acha do BTC?`")
                return
            self._handle_ai_chat(message.chat.id, query)
            
        @self.bot.message_handler(commands=['start_trading'])
        def start_trading(message):
            self.main_bot.paused = False
            self.bot.reply_to(message, "▶️ **Trading RETOMADO!** O bot voltará a abrir posições.")
            
        @self.bot.message_handler(commands=['stop_trading'])
        def stop_trading(message):
            self.main_bot.paused = True
            self.bot.reply_to(message, "⏸️ **Trading PAUSADO!** O bot não abrirá novas posições (mas gerenciará as existentes).")
        
        @self.bot.message_handler(commands=['force_scalp'])
        def force_scalp(message):
            self.bot.reply_to(message, "⚡ Solicitando um scalp imediato via IA SCALP (OpenAI)...")
            self._handle_force_scalp(message.chat.id)

        # Handler genérico para texto (Chat com IA se não for comando)
        @self.bot.message_handler(func=lambda message: True)
        def echo_all(message):
            if message.text.startswith('/'):
                return
            # Se o usuário falar algo, assume que é para a IA
            self._handle_ai_chat(message.chat.id, message.text)

        # Callback query handler para botões
        @self.bot.callback_query_handler(func=lambda call: True)
        def callback_query(call):
            if call.data == "status":
                self._send_status(call.message.chat.id)
            elif call.data == "positions":
                self._send_positions(call.message.chat.id)
            elif call.data == "balance":
                self._send_balance(call.message.chat.id)
            elif call.data == "pnl":
                self._send_pnl(call.message.chat.id)
            elif call.data == "fear":
                self._send_fear_index(call.message.chat.id)
            elif call.data == "news":
                self._send_news(call.message.chat.id)
            elif call.data == "toggle_trading":
                if getattr(self.main_bot, 'paused', False):
                    self.main_bot.paused = False
                    self.bot.answer_callback_query(call.id, "Trading Retomado")
                    self.bot.send_message(call.message.chat.id, "▶️ Trading RETOMADO!")
                else:
                    self.main_bot.paused = True
                    self.bot.answer_callback_query(call.id, "Trading Pausado")
                    self.bot.send_message(call.message.chat.id, "⏸️ Trading PAUSADO!")
            
            # Atualiza o menu se necessário (opcional)
            # self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=self._get_main_keyboard())

    def _get_main_keyboard(self):
        """Cria o teclado principal"""
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        
        btn_status = types.InlineKeyboardButton("📊 Status", callback_data="status")
        btn_pos = types.InlineKeyboardButton("📈 Posições", callback_data="positions")
        btn_bal = types.InlineKeyboardButton("💰 Saldo", callback_data="balance")
        btn_pnl = types.InlineKeyboardButton("📉 PnL", callback_data="pnl")
        btn_fear = types.InlineKeyboardButton("😱 Fear/Greed", callback_data="fear")
        btn_news = types.InlineKeyboardButton("📰 Notícias", callback_data="news")
        
        # Botão dinâmico de Pause/Resume
        is_paused = getattr(self.main_bot, 'paused', False)
        btn_pause = types.InlineKeyboardButton(
            "▶️ Retomar" if is_paused else "⏸️ Pausar", 
            callback_data="toggle_trading"
        )
        
        keyboard.add(btn_status, btn_pos, btn_bal, btn_pnl, btn_fear, btn_news, btn_pause)
        return keyboard

    def _send_menu(self, chat_id):
        """Envia o menu principal"""
        msg = (
            "🤖 **Hyperliquid AI Bot**\n\n"
            "Escolha uma opção abaixo ou digite sua pergunta para a IA."
        )
        self.bot.send_message(chat_id, msg, reply_markup=self._get_main_keyboard())

    def _send_status(self, chat_id):
        """Envia status geral"""
        try:
            equity = self.main_bot.risk_manager.current_equity
            dd = self.main_bot.risk_manager.daily_drawdown_pct
            pos_count = self.main_bot.position_manager.get_positions_count()
            is_paused = getattr(self.main_bot, 'paused', False)
            
            status_emoji = "⏸️ PAUSADO" if is_paused else "▶️ ATIVO"
            
            msg = (
                f"📊 **STATUS DO BOT**\n\n"
                f"Estado: {status_emoji}\n"
                f"Equity: `${equity:.2f}`\n"
                f"Drawdown Hoje: `{dd:+.2f}%`\n"
                f"Posições Abertas: `{pos_count}`"
            )
            self.bot.send_message(chat_id, msg)
        except Exception as e:
            self.bot.send_message(chat_id, f"Erro ao obter status: {e}")

    def _send_positions(self, chat_id):
        """Envia posições abertas"""
        try:
            # Precisa buscar preços atuais para PnL preciso
            try:
                prices = self.main_bot.client.get_all_mids()
            except:
                prices = {}
                
            positions = self.main_bot.position_manager.get_all_positions(current_prices=prices)
            
            if not positions:
                self.bot.send_message(chat_id, "🤷‍♂️ Nenhuma posição aberta no momento.")
                return
                
            msg = "📈 **POSIÇÕES ABERTAS**\n\n"
            for pos in positions:
                symbol = pos['symbol']
                side = pos['side'].upper()
                entry = pos['entry_price']
                pnl = pos.get('unrealized_pnl_pct', 0)
                
                emoji = "🟢" if pnl > 0 else "🔴"
                
                msg += (
                    f"{emoji} **{symbol}** {side}\n"
                    f"Entry: `${entry:.4f}`\n"
                    f"PnL: `{pnl:+.2f}%`\n"
                    f"────────────────\n"
                )
            
            self.bot.send_message(chat_id, msg)
        except Exception as e:
            self.bot.send_message(chat_id, f"Erro ao obter posições: {e}")

    def _send_balance(self, chat_id):
        """Envia saldo detalhado"""
        try:
            user_state = self.main_bot.client.get_user_state()
            equity = user_state.get('account_value', 0)
            withdrawable = user_state.get('withdrawable', 0)
            margin_used = user_state.get('total_margin_used', 0)
            
            msg = (
                f"💰 **SALDO DA CONTA**\n\n"
                f"Equity Total: `${equity:.2f}`\n"
                f"Disponível Saque: `${withdrawable:.2f}`\n"
                f"Margem Usada: `${margin_used:.2f}`"
            )
            self.bot.send_message(chat_id, msg)
        except Exception as e:
            self.bot.send_message(chat_id, f"Erro ao obter saldo: {e}")

    def _send_pnl(self, chat_id):
        """Envia PnL do dia"""
        try:
            pnl_pct = self.main_bot.risk_manager.daily_pnl_pct
            pnl_usd = self.main_bot.risk_manager.daily_pnl
            
            emoji = "🤑" if pnl_pct > 0 else "😢"
            
            msg = (
                f"{emoji} **PnL HOJE**\n\n"
                f"Percentual: `{pnl_pct:+.2f}%`\n"
                f"Dólares: `${pnl_usd:+.2f}`"
            )
            self.bot.send_message(chat_id, msg)
        except Exception as e:
            self.bot.send_message(chat_id, f"Erro ao obter PnL: {e}")

    def _send_fear_index(self, chat_id):
        """Busca e envia Fear & Greed Index"""
        try:
            r = requests.get("https://api.alternative.me/fng/?limit=1")
            data = r.json()
            item = data['data'][0]
            
            value = int(item['value'])
            classification = item['value_classification']
            
            # Emoji
            if value >= 75: emoji = "🤩 Extreme Greed"
            elif value >= 55: emoji = "🙂 Greed"
            elif value >= 45: emoji = "😐 Neutral"
            elif value >= 25: emoji = "😨 Fear"
            else: emoji = "😱 Extreme Fear"
            
            msg = (
                f"🧠 **FEAR & GREED INDEX**\n\n"
                f"Valor: `{value}/100`\n"
                f"Status: **{classification}** {emoji}\n\n"
                f"_Atualizado: {datetime.fromtimestamp(int(item['timestamp'])).strftime('%d/%m %H:%M')}_"
            )
            self.bot.send_message(chat_id, msg)
        except Exception as e:
            self.bot.send_message(chat_id, f"Erro ao buscar Fear & Greed: {e}")

    def _send_news(self, chat_id):
        """Envia notícias (Placeholder por enquanto)"""
        # TODO: Implementar API de notícias real
        msg = (
            "📰 **NOTÍCIAS DO MERCADO**\n\n"
            "⚠️ _Funcionalidade de notícias em tempo real em desenvolvimento._\n\n"
            "**Resumo Rápido (Simulado):**\n"
            "• Bitcoin mantém suporte em $90k\n"
            "• Volume de ETFs continua alto\n"
            "• FED sinaliza cautela com juros"
        )
        self.bot.send_message(chat_id, msg)

    def _handle_ai_chat(self, chat_id, query):
        """Processa chat com a IA"""
        self.bot.send_chat_action(chat_id, 'typing')
        
        try:
            # Usa o engine de IA do bot principal
            # Precisamos criar um contexto ad-hoc
            
            # 1. Busca contexto de mercado básico (BTC)
            btc_price = 0
            try:
                prices = self.main_bot.client.get_all_mids()
                btc_price = prices.get('BTC', 0)
            except:
                pass
                
            # 2. Monta prompt para conversa
            system_prompt = (
                "Você é um assistente de trading crypto experiente. "
                "Responda de forma concisa, direta e em português. "
                f"O preço atual do BTC é aproximadamente ${btc_price:.2f}. "
                "O usuário está perguntando sobre mercado ou sobre o bot."
            )
            
            # Chama Anthropic diretamente se disponível
            if self.main_bot.ai_engine.client:
                response = self.main_bot.ai_engine.client.messages.create(
                    model=self.main_bot.ai_engine.model,
                    max_tokens=500,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query}
                    ]
                )
                reply = response.content[0].text
            else:
                reply = "🤖 IA não está configurada (sem API Key)."
                
            self.bot.send_message(chat_id, reply)
            
        except Exception as e:
            logger.error(f"Erro no chat IA: {e}")
            self.bot.send_message(chat_id, "Desculpe, tive um erro ao processar sua pergunta.")
    
    def _handle_force_scalp(self, chat_id):
        """Força um scalp imediato via comando Telegram"""
        try:
            logger.info(f"[TELEGRAM] /force_scalp chamado por chat_id={chat_id}")
            result = self.main_bot.force_scalp_trade()
            logger.info(f"[TELEGRAM] force_scalp_trade retornou: {result}")
            
            if result['status'] == 'hold':
                msg = f"🤚 IA SCALP decidiu HOLD\n\n{result['reason']}"
                self.bot.send_message(chat_id, msg)
            elif result['status'] == 'blocked':
                msg = (
                    f"⚠️ SCALP FORÇADO BLOQUEADO PELO RISKMANAGER\n\n"
                    f"Motivo: {result['reason']}"
                )
                self.bot.send_message(chat_id, msg)
            elif result['status'] == 'executed':
                dec = result['decision']
                msg = (
                    f"✅ SCALP FORÇADO EXECUTADO\n\n"
                    f"• Símbolo: {dec.get('symbol')}\n"
                    f"• Direção: {dec.get('side', '').upper()}\n"
                    f"• Tamanho: ${dec.get('size_usd', 0):.2f} (mínimo de teste)\n"
                    f"• Alavancagem: {dec.get('leverage', 0)}x\n"
                    f"• SL: {dec.get('stop_loss_pct', 0):.2f}%\n"
                    f"• TP: {dec.get('take_profit_pct', 0):.2f}%\n"
                    f"• IA: OpenAI (SCALP)\n"
                    f"• Observação: operação de teste acionada via /force_scalp"
                )
                self.bot.send_message(chat_id, msg)
            else:
                msg = f"❌ Erro ao executar SCALP FORÇADO\n\n{result.get('reason', 'Erro desconhecido')}"
                self.bot.send_message(chat_id, msg)
                
        except Exception as e:
            logger.error(f"Erro em _handle_force_scalp: {e}", exc_info=True)
            try:
                self.bot.send_message(chat_id, f"❌ Erro ao processar /force_scalp: {str(e)}")
            except:
                logger.error("Falha ao enviar mensagem de erro para Telegram")
