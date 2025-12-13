"""
Telegram Notifier
Sistema de notificações em tempo real via Telegram
"""
import os
import logging
import requests
from typing import Optional, Dict, Any, List
from datetime import datetime
from functools import wraps

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Envia notificações do bot de trading para o Telegram.
    
    Notifica sobre:
    - Abertura/fechamento de posições
    - Atingimento de SL/TP
    - Erros críticos
    - Resumo periódico
    """
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Inicializa o notificador do Telegram.
        
        Args:
            bot_token: Token do bot do Telegram (de @BotFather)
            chat_id: ID do chat para enviar mensagens
        """
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = bool(self.bot_token and self.chat_id)
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        
        # Controle de rate limit
        self.last_message_time = 0
        self.min_interval_seconds = 1  # Mínimo 1 segundo entre mensagens
        
        # Configurações de notificação
        self.notify_on_open = True
        self.notify_on_close = True
        self.notify_on_sl_tp = True
        self.notify_on_error = True
        self.notify_on_summary = True
        
        if self.enabled:
            logger.info("✅ Telegram Notifier ativado")
            self._send_startup_message()
        else:
            logger.warning("⚠️ Telegram Notifier desativado (TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados)")
    
    def _send_startup_message(self):
        """Envia mensagem de inicialização"""
        msg = (
            "🤖 *HYPERLIQUID BOT INICIADO*\n\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "✅ Sistema de notificações ativo\n\n"
            "Você receberá alertas sobre:\n"
            "• 🟢 Abertura de posições\n"
            "• 🔴 Fechamento de posições\n"
            "• 🎯 Atingimento de TP/SL\n"
            "• ⚠️ Erros críticos\n"
            "• 📊 Resumos periódicos"
        )
        self.send_message(msg)
    
    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Envia mensagem para o Telegram com fallback automático.
        
        Args:
            text: Texto da mensagem (suporta Markdown)
            parse_mode: Modo de parse ("Markdown" ou "HTML")
            
        Returns:
            True se enviou com sucesso
        """
        if not self.enabled:
            return False
        
        try:
            # Rate limiting simples
            import time
            now = time.time()
            if now - self.last_message_time < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - (now - self.last_message_time))
            
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            self.last_message_time = time.time()
            
            if response.status_code == 200:
                logger.debug("Mensagem Telegram enviada com sucesso")
                return True
            
            # ===== FALLBACK: Se erro de parse, tenta sem formatação =====
            error_text = response.text.lower()
            if "can't parse entities" in error_text or "bad request" in error_text:
                logger.warning(f"[TELEGRAM] Fallback sem parse_mode: {response.text}")
                
                # Remove caracteres problemáticos
                clean_text = text.replace('*', '').replace('_', '').replace('`', '')
                clean_text = clean_text.replace('[', '').replace(']', '')
                
                payload["text"] = clean_text
                payload["parse_mode"] = None
                
                retry_response = requests.post(url, json=payload, timeout=10)
                if retry_response.status_code == 200:
                    logger.debug("Mensagem Telegram enviada (fallback)")
                    return True
                else:
                    logger.warning(f"[TELEGRAM] Falha mesmo no fallback: {retry_response.text}")
                    return False
            
            logger.warning(f"Falha ao enviar Telegram: {response.status_code} - {response.text}")
            return False
                
        except Exception as e:
            # NUNCA derrubar o bot por erro de Telegram
            logger.error(f"Erro ao enviar mensagem Telegram: {e}")
            return False
    
    # ==================== NOTIFICAÇÕES DE TRADING ====================
    
    def notify_position_opened(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        size: float,
        leverage: int,
        strategy: str,
        confidence: float,
        reason: str = "",
        source: str = "claude_swing",
        margin_type: str = "ISOLATED"
    ):
        """Notifica abertura de posição"""
        if not self.notify_on_open:
            return
        
        emoji = "🟢" if side.lower() == "long" else "🔴"
        side_text = "LONG 📈" if side.lower() == "long" else "SHORT 📉"
        
        # Formata origem
        source_display = "Claude (SWING)"
        if "openai" in source.lower():
            source_display = "OpenAI (SCALP)"
            
        # Formata confiança
        conf_display = "N/A"
        if confidence is not None:
             conf_display = f"{int(confidence * 100)}%"
        
        msg = (
            f"{emoji} *POSIÇÃO ABERTA*\n\n"
            f"*{symbol}* {side_text}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🧠 Origem IA: `{source_display}`\n"
            f"💰 Entry: `${entry_price:,.4f}`\n"
            f"📦 Size: `{size:.4f}`\n"
            f"⚡ Leverage: `{leverage}x` ({margin_type})\n"
            f"🎯 Estratégia: `{strategy.upper()}`\n"
            f"📊 Confiança: `{conf_display}`\n"
        )
        
        if reason:
            msg += f"\n💡 _{reason}_"
        
        self.send_message(msg)
    
    def notify_position_closed(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl_pct: float,
        pnl_usd: float,
        reason: str = "manual"
    ):
        """Notifica fechamento de posição"""
        if not self.notify_on_close:
            return
        
        # Emoji baseado no resultado
        if pnl_pct > 0:
            emoji = "✅"
            result = "LUCRO"
        else:
            emoji = "❌"
            result = "PREJUÍZO"
        
        side_text = "LONG" if side.lower() == "long" else "SHORT"
        
        msg = (
            f"{emoji} *POSIÇÃO FECHADA - {result}*\n\n"
            f"*{symbol}* {side_text}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📥 Entry: `${entry_price:,.4f}`\n"
            f"📤 Exit: `${exit_price:,.4f}`\n"
            f"📊 PnL: `{pnl_pct:+.2f}%` (`${pnl_usd:+.2f}`)\n"
            f"📝 Motivo: `{reason}`"
        )
        
        self.send_message(msg)
    
    def notify_sl_hit(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        sl_price: float,
        pnl_pct: float
    ):
        """Notifica que Stop Loss foi atingido"""
        if not self.notify_on_sl_tp:
            return
        
        msg = (
            f"🛑 *STOP LOSS ATINGIDO*\n\n"
            f"*{symbol}* {side.upper()}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📥 Entry: `${entry_price:,.4f}`\n"
            f"🛑 Stop: `${sl_price:,.4f}`\n"
            f"📊 PnL: `{pnl_pct:+.2f}%`\n\n"
            f"⚠️ _Posição fechada automaticamente_"
        )
        
        self.send_message(msg)
    
    def notify_tp_hit(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        tp_price: float,
        pnl_pct: float
    ):
        """Notifica que Take Profit foi atingido"""
        if not self.notify_on_sl_tp:
            return
        
        msg = (
            f"🎯 *TAKE PROFIT ATINGIDO*\n\n"
            f"*{symbol}* {side.upper()}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📥 Entry: `${entry_price:,.4f}`\n"
            f"🎯 TP: `${tp_price:,.4f}`\n"
            f"📊 PnL: `{pnl_pct:+.2f}%`\n\n"
            f"🎉 _Lucro realizado!_"
        )
        
        self.send_message(msg)
    
    def notify_position_adjusted(
        self,
        symbol: str,
        action: str,  # "increase" ou "decrease"
        old_size: float,
        new_size: float,
        price: float,
        reason: str = ""
    ):
        """Notifica ajuste de posição (increase/decrease)"""
        if action == "increase":
            emoji = "➕"
            action_text = "AUMENTADA"
        else:
            emoji = "➖"
            action_text = "REDUZIDA"
        
        change = new_size - old_size
        change_pct = (change / old_size * 100) if old_size > 0 else 0
        
        msg = (
            f"{emoji} *POSIÇÃO {action_text}*\n\n"
            f"*{symbol}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📦 Size: `{old_size:.4f}` → `{new_size:.4f}`\n"
            f"📊 Variação: `{change_pct:+.1f}%`\n"
            f"💰 Preço: `${price:,.4f}`\n"
        )
        
        if reason:
            msg += f"\n💡 _{reason}_"
        
        self.send_message(msg)
    
    def notify_error(self, error_type: str, details: str):
        """Notifica erro crítico"""
        if not self.notify_on_error:
            return
        
        msg = (
            f"⚠️ *ERRO NO BOT*\n\n"
            f"*Tipo:* `{error_type}`\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📝 {details}\n\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        
        self.send_message(msg)
    
    def notify_summary(
        self,
        equity: float,
        daily_pnl_pct: float,
        open_positions: List[Dict],
        total_pnl_usd: float = 0
    ):
        """Envia resumo do status atual"""
        if not self.notify_on_summary:
            return
        
        # Emoji baseado no PnL
        if daily_pnl_pct > 0:
            pnl_emoji = "🟢"
        elif daily_pnl_pct < -1:
            pnl_emoji = "🔴"
        else:
            pnl_emoji = "🟡"
        
        msg = (
            f"📊 *RESUMO DO BOT*\n\n"
            f"💰 Equity: `${equity:,.2f}`\n"
            f"{pnl_emoji} PnL Hoje: `{daily_pnl_pct:+.2f}%`\n"
            f"📈 Posições: `{len(open_positions)}`\n"
            f"━━━━━━━━━━━━━━━\n"
        )
        
        if open_positions:
            msg += "\n*Posições Abertas:*\n"
            for pos in open_positions[:10]:  # Aumentado limite para 10
                symbol = pos.get('symbol', '?')
                side = pos.get('side', '?')
                size = pos.get('size', 0)
                entry_price = pos.get('entry_price', 0)
                pnl_pct = pos.get('unrealized_pnl_pct', 0)
                pnl_usd = pos.get('unrealized_pnl', 0)
                
                # Correção de Leverage
                leverage = pos.get('leverage')
                if not leverage:
                    # Tenta inferir
                    margin_used = pos.get('margin_used', 0)
                    notional = size * entry_price
                    if margin_used > 0:
                        leverage = int(notional / margin_used)
                    else:
                        leverage = "Cross"
                
                lev_str = f"{leverage}x" if isinstance(leverage, (int, float)) else str(leverage)
                
                side_emoji = "📈" if str(side).lower() == 'long' else "📉"
                pnl_indicator = "🟢" if pnl_pct > 0 else "🔴" if pnl_pct < 0 else "⚪"
                
                msg += (
                    f"{side_emoji} *{symbol}* ({lev_str})\n"
                    f"   Entry: `${entry_price:,.4f}` | Size: `{size:.4f}`\n"
                    f"   PnL: `{pnl_pct:+.2f}%` (`${pnl_usd:+.2f}`) {pnl_indicator}\n"
                )
        else:
            msg += "\n_Nenhuma posição aberta_\n"
        
        msg += f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        self.send_message(msg)
    
    def notify_iteration(self, iteration: int, decisions_count: int, filtered_count: int):
        """Notifica fim de iteração (opcional, pode ser muito spam)"""
        # Por padrão desabilitado para não spammar
        pass
    
    def send_custom(self, message: str):
        """Envia mensagem customizada"""
        self.send_message(message)


# ==================== HELPER FUNCTION ====================

def get_notifier() -> TelegramNotifier:
    """
    Factory function para obter instância do notificador.
    Usa variáveis de ambiente por padrão.
    """
    return TelegramNotifier(
        bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
        chat_id=os.getenv('TELEGRAM_CHAT_ID')
    )
