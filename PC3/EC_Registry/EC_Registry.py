from flask import Flask, request, jsonify
import ssl
import logging
from datetime import datetime
import secrets
import sys
import os
from flask_cors import CORS
# Añadir el directorio raíz del proyecto al path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(project_root)
from PC1.Central.map_reader import DatabaseManager

class RegistryService:
    def __init__(self, db_params):
        # Inicialización de Flask
        self.app = Flask(__name__)
        CORS(self.app)
        
        # Configuración de BD y SSL
        self.db = DatabaseManager(db_params)
        self.ssl_context = self.setup_ssl()
        
        # Configurar logging
        self.logger = logging.getLogger('registry')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # Configurar rutas
        self.setup_routes()

    def setup_ssl(self):
        """Configurar contexto SSL para el servidor"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        cert_path = os.path.join(project_root, 'shared', 'security', 'certificates')
        
        cert_file = os.path.join(cert_path, 'server.crt')
        key_file = os.path.join(cert_path, 'server.key')
        
        if not os.path.exists(cert_file):
            raise FileNotFoundError(f"Certificado no encontrado en: {cert_file}")
        if not os.path.exists(key_file):
            raise FileNotFoundError(f"Clave privada no encontrada en: {key_file}")
        
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        return context

    def setup_routes(self):
        @self.app.route('/registry/taxi', methods=['POST'])
        def register_taxi():
            try:
                # Verificar headers de seguridad
                auth_header = request.headers.get('X-Taxi-Auth')
                if not auth_header:
                    self.db.log_audit_event(
                        source="REGISTRY",
                        source_id="unknown",
                        ip_address=request.remote_addr,
                        event_type="security",
                        action="MISSING_AUTH_HEADER",
                        details="Intento de registro sin header de autenticación"
                    )
                    return jsonify({
                        'status': 'error',
                        'message': 'Falta header de autenticación'
                    }), 401

                data = request.get_json()
                taxi_id = data.get('taxi_id')
                
                if not taxi_id:
                    self.db.log_audit_event(
                        source="REGISTRY",
                        source_id="unknown",
                        ip_address=request.remote_addr,
                        event_type="error",
                        action="INVALID_REQUEST",
                        details="Intento de registro sin taxi_id"
                    )
                    return jsonify({
                        'status': 'error',
                        'message': 'taxi_id es requerido'
                    }), 400

                cert_token = secrets.token_hex(32)
                success = self.db.register_taxi(taxi_id, cert_token, request.remote_addr)
                
                if not success:
                    self.db.log_audit_event(
                        source="REGISTRY",
                        source_id=str(taxi_id),
                        ip_address=request.remote_addr,
                        event_type="error",
                        action="REGISTRATION_FAILED",
                        details="Error en proceso de registro"
                    )
                    raise Exception("Error registrando taxi en BD")

                self.db.log_audit_event(
                    source="REGISTRY",
                    source_id=str(taxi_id),
                    ip_address=request.remote_addr,
                    event_type="auth",
                    action="TAXI_REGISTERED",
                    details=f"Taxi {taxi_id} registrado exitosamente"
                )

                return jsonify({
                    'status': 'success',
                    'cert_token': cert_token,
                    'message': 'Taxi registrado correctamente'
                })

            except Exception as e:
                self.logger.error(f"Error en registro: {e}")
                self.db.log_audit_event(
                    source="REGISTRY",
                    source_id=str(taxi_id) if taxi_id else "unknown",
                    ip_address=request.remote_addr,
                    event_type="error",
                    action="REGISTRATION_ERROR",
                    details=f"Error en registro: {str(e)}"
                )
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500

        @self.app.route('/registry/taxi/<int:taxi_id>', methods=['DELETE'])
        def unregister_taxi(taxi_id):
            try:
                if not request.headers.get('X-Taxi-Auth'):
                    self.db.log_audit_event(
                        source="REGISTRY",
                        source_id=str(taxi_id),
                        ip_address=request.remote_addr,
                        event_type="security",
                        action="MISSING_AUTH_HEADER",
                        details="Intento de baja sin autenticación"
                    )
                    return jsonify({
                        'status': 'error',
                        'message': 'Falta header de autenticación'
                    }), 401

                success = self.db.unregister_taxi(taxi_id)
                if not success:
                    raise Exception("Error dando de baja al taxi")

                self.db.log_audit_event(
                    source="REGISTRY",
                    source_id=str(taxi_id),
                    ip_address=request.remote_addr,
                    event_type="auth",
                    action="TAXI_UNREGISTERED",
                    details=f"Taxi {taxi_id} dado de baja correctamente"
                )

                return jsonify({
                    'status': 'success',
                    'message': 'Taxi dado de baja correctamente'
                })

            except Exception as e:
                self.logger.error(f"Error en baja de taxi: {e}")
                self.db.log_audit_event(
                    source="REGISTRY",
                    source_id=str(taxi_id),
                    ip_address=request.remote_addr,
                    event_type="error",
                    action="UNREGISTER_ERROR",
                    details=f"Error dando de baja: {str(e)}"
                )
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500

    def run(self, host='0.0.0.0', port=5000):
        self.app.run(
            host=host, 
            port=port, 
            ssl_context=self.ssl_context
        )

def main():
    db_params = {
        'dbname': 'central_db',
        'user': 'postgres',
        'password': 'postgres',
        'host': 'localhost',
        'port': '5432'
    }
    registry = RegistryService(db_params)
    registry.run()

if __name__ == '__main__':
    main()