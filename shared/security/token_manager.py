# shared/security/token_manager.py
import uuid

class TokenManager:
    def __init__(self):
        self.active_tokens = {}  # {taxi_id: token}
    
    def generate_token(self, taxi_id):
        token = str(uuid.uuid4())
        self.active_tokens[taxi_id] = token
        return token
    
    def validate_token(self, taxi_id, token):
        return self.active_tokens.get(taxi_id) == token