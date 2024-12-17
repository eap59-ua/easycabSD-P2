from flask import Flask, request, jsonify
import ssl
import logging
from datetime import datetime
import secrets
import sys
import os
# Añadir el directorio raíz del proyecto al path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(project_root)
from PC1.Central.map_reader import DatabaseManager

class RegistryService:
    def __init__(self, db_params):
        # Configuración básica
        self.app = Flask(__name__)
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
        """Configurar contexto SSL"""
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(
                certfile="shared/security/certificates/server.crt",
                keyfile="shared/security/certificates/server.key"
            )
            return context
        except Exception as e:
            self.logger.error(f"Error configurando SSL: {e}")
            raise

    def setup_routes(self):
        @self.app.route('/registry/taxi', methods=['POST'])
        def register_taxi():
            try:
                # Verificar headers de seguridad
                if not request.headers.get('X-Taxi-Auth'):
                    self.db.log_audit_event(
                        source='REGISTRY',
                        source_id='unknown',
                        ip_address=request.remote_addr,
                        event_type='AUTH',
                        action='MISSING_AUTH_HEADER',
                        details='Intento de registro sin header de autenticación'
                    )
                    return jsonify({
                        'status': 'error',
                        'message': 'Falta header de autenticación'
                    }), 401

                data = request.get_json()
                taxi_id = data.get('taxi_id')
                
                if not taxi_id:
                    return jsonify({
                        'status': 'error',
                        'message': 'taxi_id es requerido'
                    }), 400

                ip_address = request.remote_addr
                
                # Generar token de registro único
                cert_token = secrets.token_hex(32)
                
                # Registrar en la BD y auditoría
                success = self.db.register_taxi(taxi_id, cert_token, ip_address)
                if not success:
                    raise Exception("Error registrando taxi en BD")

                # Registrar evento en auditoría
                self.db.log_audit_event(
                    source='REGISTRY',
                    source_id=str(taxi_id),
                    ip_address=ip_address,
                    event_type='AUTH',
                    action='TAXI_REGISTRATION',
                    details=f"Taxi {taxi_id} registrado exitosamente"
                )

                return jsonify({
                    'status': 'success',
                    'cert_token': cert_token,
                    'message': 'Taxi registrado correctamente'
                })

            except Exception as e:
                self.logger.error(f"Error en registro de taxi: {e}")
                # Registrar error en auditoría
                self.db.log_audit_event(
                    source='REGISTRY',
                    source_id=str(taxi_id) if taxi_id else 'unknown',
                    ip_address=request.remote_addr,
                    event_type='ERROR',
                    action='REGISTRATION_ERROR',
                    details=str(e)
                )
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500

        @self.app.route('/registry/taxi/<int:taxi_id>', methods=['DELETE'])
        def unregister_taxi(taxi_id):
            try:
                # Verificar header de autenticación
                if not request.headers.get('X-Taxi-Auth'):
                    return jsonify({
                        'status': 'error',
                        'message': 'Falta header de autenticación'
                    }), 401

                ip_address = request.remote_addr
                
                # Dar de baja al taxi
                success = self.db.unregister_taxi(taxi_id)
                if not success:
                    raise Exception("Error dando de baja al taxi")

                # Registrar evento en auditoría
                self.db.log_audit_event(
                    source='REGISTRY',
                    source_id=str(taxi_id),
                    ip_address=ip_address,
                    event_type='AUTH',
                    action='TAXI_UNREGISTRATION',
                    details=f"Taxi {taxi_id} dado de baja"
                )

                return jsonify({
                    'status': 'success',
                    'message': 'Taxi dado de baja correctamente'
                })

            except Exception as e:
                self.logger.error(f"Error dando de baja taxi: {e}")
                # Registrar error en auditoría
                self.db.log_audit_event(
                    source='REGISTRY',
                    source_id=str(taxi_id),
                    ip_address=request.remote_addr,
                    event_type='ERROR',
                    action='UNREGISTRATION_ERROR',
                    details=str(e)
                )
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500

    def run(self, host='0.0.0.0', port=5000):
        # Usar SSL context para HTTPS
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