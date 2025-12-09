"""
Patch: Rate Limiting para Hyperliquid API
Resolve erro 429 (Too Many Requests)
"""

# INSTRUÇÕES DE APLICAÇÃO:
# 
# 1. No arquivo bot_hyperliquid.py, localizar o método get_user_state() (linha ~152)
# 
# 2. ADICIONAR no início do método:
#
#    import time
#    
#    # Rate limiting: aguarda entre chamadas
#    time.sleep(0.5)  # 500ms entre chamadas
#
# 3. ADICIONAR try/except com retry:
#
#    max_retries = 3
#    for attempt in range(max_retries):
#        try:
#            response = requests.post(...)
#            response.raise_for_status()
#            return response.json()
#        except requests.exceptions.HTTPError as e:
#            if e.response.status_code == 429:
#                # Rate limited, aguarda e tenta novamente
#                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
#                self.logger.warning(f"[HYPERLIQUID] Rate limited, aguardando {wait_time}s...")
#                time.sleep(wait_time)
#                continue
#            raise
#
# 4. NO LOOP PRINCIPAL (método run()), AUMENTAR INTERVALO:
#
#    # Linha ~715 (aproximadamente)
#    # ANTES:
#    time.sleep(5)  # 5 segundos
#    
#    # DEPOIS:
#    time.sleep(10)  # 10 segundos (reduz chamadas pela metade)

# CÓDIGO COMPLETO DO MÉTODO get_user_state() COM RATE LIMITING:

def get_user_state(self):
    """
    Obtém estado do usuário com rate limiting
    """
    import time
    
    # Rate limiting entre chamadas
    time.sleep(0.5)
    
    try:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{self.base_url}/info",
                    json={
                        "type": "clearinghouseState",
                        "user": self.address
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    # Rate limited
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    self.logger.warning(
                        f"[HYPERLIQUID] Rate limited (tentativa {attempt+1}/{max_retries}), "
                        f"aguardando {wait_time}s..."
                    )
                    time.sleep(wait_time)
                    
                    if attempt == max_retries - 1:
                        # Última tentativa falhou
                        self.logger.error("[HYPERLIQUID] Rate limit persistente após retries")
                        return None
                    continue
                else:
                    # Outro erro HTTP
                    raise
            
            except requests.exceptions.Timeout:
                self.logger.warning(f"[HYPERLIQUID] Timeout na tentativa {attempt+1}")
                if attempt == max_retries - 1:
                    return None
                time.sleep(1)
                continue
        
        return None
        
    except Exception as e:
        self.logger.error(f"[HYPERLIQUID] Erro ao obter user state: {e}")
        return None


# ALTERNATIVA: Se o problema persistir, adicione um cache simples:

class HyperliquidRateLimiter:
    """Rate limiter simples com cache"""
    
    def __init__(self, min_interval=1.0):
        self.min_interval = min_interval
        self.last_call = {}
        self.cache = {}
        self.cache_ttl = 5  # 5 segundos de cache
    
    def wait_if_needed(self, endpoint):
        """Aguarda se necessário antes de fazer chamada"""
        import time
        
        now = time.time()
        last = self.last_call.get(endpoint, 0)
        
        elapsed = now - last
        if elapsed < self.min_interval:
            wait = self.min_interval - elapsed
            time.sleep(wait)
        
        self.last_call[endpoint] = time.time()
    
    def get_cached(self, key):
        """Retorna do cache se disponível"""
        import time
        
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return data
        return None
    
    def set_cache(self, key, data):
        """Salva no cache"""
        import time
        self.cache[key] = (data, time.time())

# USO:
# No __init__ do bot:
# self.rate_limiter = HyperliquidRateLimiter(min_interval=1.0)
#
# No get_user_state():
# cached = self.rate_limiter.get_cached('user_state')
# if cached:
#     return cached
#
# self.rate_limiter.wait_if_needed('info')
# response = requests.post(...)
# data = response.json()
# self.rate_limiter.set_cache('user_state', data)
# return data
