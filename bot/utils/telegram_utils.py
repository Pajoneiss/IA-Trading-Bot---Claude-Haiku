"""
Telegram Utils - Sanitização de mensagens para MarkdownV2
"""
import re
import logging

logger = logging.getLogger(__name__)


def escape_markdown_v2(text: str) -> str:
    """
    Escapa caracteres especiais para MarkdownV2 do Telegram
    
    Caracteres que precisam de escape:
    _ * [ ] ( ) ~ ` > # + - = | { } . ! %
    
    Args:
        text: Texto a ser escapado
        
    Returns:
        Texto com caracteres escapados
    """
    if text is None or text == "":
        return "N/A"
    
    # Converte para string
    text = str(text)
    
    # Lista de caracteres que precisam escape
    # Ordem importa: processar \ primeiro
    escape_chars = [
        ('\\', '\\\\'),  # Backslash primeiro
        ('_', '\\_'),
        ('*', '\\*'),
        ('[', '\\['),
        (']', '\\]'),
        ('(', '\\('),
        (')', '\\)'),
        ('~', '\\~'),
        ('`', '\\`'),
        ('>', '\\>'),
        ('#', '\\#'),
        ('+', '\\+'),
        ('-', '\\-'),
        ('=', '\\='),
        ('|', '\\|'),
        ('{', '\\{'),
        ('}', '\\}'),
        ('.', '\\.'),
        ('!', '\\!'),
        ('%', '\\%'),
        ('$', '\\$')  # Dollar sign
    ]
    
    # Aplica escapes
    for char, escaped in escape_chars:
        text = text.replace(char, escaped)
    
    return text


def safe_markdown_bold(text: str) -> str:
    """
    Cria texto em negrito de forma segura
    
    Args:
        text: Texto a colocar em negrito
        
    Returns:
        Texto formatado em negrito
    """
    if not text:
        return "N/A"
    
    # Escapa o texto primeiro
    escaped = escape_markdown_v2(text)
    
    # Aplica negrito (sem escapar os asteriscos do negrito)
    return f"*{escaped}*"


def format_number(value, decimals=2, prefix="", suffix="") -> str:
    """
    Formata número de forma segura
    
    Args:
        value: Valor numérico
        decimals: Casas decimais
        prefix: Prefixo (ex: "$")
        suffix: Sufixo (ex: "%")
        
    Returns:
        Número formatado e escapado
    """
    try:
        if value is None:
            return "N/A"
        
        # Formata número
        formatted = f"{prefix}{value:.{decimals}f}{suffix}"
        
        # Escapa
        return escape_markdown_v2(formatted)
        
    except (TypeError, ValueError):
        return "N/A"


def sanitize_telegram_message(message: str) -> str:
    """
    Sanitiza mensagem completa para Telegram
    
    Remove formatações problemáticas e garante que tudo está escapado
    
    Args:
        message: Mensagem original
        
    Returns:
        Mensagem sanitizada
    """
    if not message:
        return "Mensagem vazia"
    
    # Remove markdown manual (vamos reconstruir de forma segura)
    # Remove ** (bold)
    message = message.replace('**', '')
    
    # Remove __ (underline)
    message = message.replace('__', '')
    
    # Remove ` (code)
    message = message.replace('`', '')
    
    # Escapa tudo
    sanitized = escape_markdown_v2(message)
    
    return sanitized


def build_safe_line(prefix: str, value: str, emoji: str = "") -> str:
    """
    Constrói linha de forma segura
    
    Args:
        prefix: Texto antes do valor (ex: "PnL: ")
        value: Valor a exibir
        emoji: Emoji opcional (colocado antes do prefix)
        
    Returns:
        Linha formatada e segura
    """
    try:
        # Escapa partes
        safe_prefix = escape_markdown_v2(prefix)
        safe_value = escape_markdown_v2(str(value)) if value is not None else "N/A"
        
        # Monta linha
        if emoji:
            line = f"{emoji} {safe_prefix}{safe_value}"
        else:
            line = f"{safe_prefix}{safe_value}"
        
        return line
        
    except Exception as e:
        logger.error(f"[TELEGRAM UTILS] Erro ao construir linha: {e}")
        return "Erro ao formatar linha"
