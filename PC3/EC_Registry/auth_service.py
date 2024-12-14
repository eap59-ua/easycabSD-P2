import jwt
import ssl
from datetime import datetime, timedelta

class AuthService:
    def __init__(self):
        self.secret_key = "your-secret-key"  # En producción usar variable de entorno
        self.ssl_context = self.setup_ssl()

    def setup_ssl(self):
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile="server.crt", keyfile="server.key")
        return context

    def authenticate_taxi(self, taxi_id, credentials):
        # Verificar credenciales del taxi
        if self.verify_credentials(taxi_id, credentials):
            token = self.generate_token(taxi_id)
            return {"status": "OK", "token": token}
        return {"status": "ERROR", "message": "Authentication failed"}

    def generate_token(self, taxi_id):
        payload = {
            "taxi_id": taxi_id,
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")