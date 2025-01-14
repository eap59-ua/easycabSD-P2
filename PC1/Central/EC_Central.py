import pygame
import sys
from map_reader import DatabaseManager, get_db_params
from kafka import KafkaConsumer, KafkaProducer
import json
import logging
import argparse
import socket
import threading
import time
import ssl
import jwt
import os
import datetime
import requests
import threading 

# Constantes ajustadas
TILE_SIZE = 35  # Aumentado de 30 a 35
MAP_SIZE = 21  # 20x20 + índices
WINDOW_WIDTH = MAP_SIZE * TILE_SIZE + 450  # Aumentado de 400 a 450 para la tabla
WINDOW_HEIGHT = MAP_SIZE * TILE_SIZE  # Añadido +200 para dar espacio al panel
MAP_SECTION_WIDTH = MAP_SIZE * TILE_SIZE

# Colores
TAXI_COLOR = (0, 255, 0)
TAXI_END_COLOR = (255, 0, 0)
LOCATION_COLOR = (0, 0, 255)
CUSTOMER_COLOR = (255, 255, 0)
BACKGROUND_COLOR = (255, 255, 255)
GRID_COLOR = (200, 200, 200)
TEXT_COLOR = (0, 0, 0)
INDEX_BG_COLOR = (240, 240, 240)
#nuevos campos para la pantalla divida
TABLE_HEADER_COLOR = (200, 200, 200)
TABLE_ROW_COLOR = (240, 240, 240)
TABLE_BORDER_COLOR = (100, 100, 100)
STATUS_OK_COLOR = (0, 200, 0)
STATUS_KO_COLOR = (200, 0, 0)

#botones
# Colores para los botones del panel de control
BUTTON_STOP_COLOR = (255, 80, 80)    # Rojo
BUTTON_RESUME_COLOR = (80, 255, 80)  # Verde
BUTTON_BASE_COLOR = (80, 80, 255)    # Azul
BUTTON_GOTO_COLOR = (255, 255, 80)   # Amarillo

class CentralSystem:
    def __init__(self, listen_port, kafka_broker, db_params):
        # Inicialización de Pygame
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("EasyCab Central")
        self.font = pygame.font.SysFont('Arial', 16)  # Reducimos un poco el tamaño
        self.header_font = pygame.font.SysFont('Arial', 18, bold=True)
        
        # Configurar logging
        self.logger = logging.getLogger('central')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        #locations
        
        # Atributos de la central
        self.listen_port = listen_port
        self.kafka_broker = kafka_broker
        self.db = DatabaseManager(db_params)
        self.active_clients = {}  # {client_id: {position, status}}
        self.active_taxis = {}    # {taxi_id: client_id} - Para saber qué taxi sirve a qué cliente
        #para taxi_tokens:
        self.taxi_tokens = {} 
        # Inicializar servidor socket para autenticación
        self.ssl_context = self.setup_ssl()
        self.setup_socket_server()
        #lock para los threads
        self.taxis_lock = threading.Lock()
        # Cargar locations desde la BD
        self.locations = {}  # diccionario para almacenar las locations
        self.load_locations()
        # Inicializar Kafka
        self.setup_kafka()
        self.disconnected_taxis = {}  # {taxi_id: (timer, last_position, client_id)}
        self.reconnection_window = 10 # para la reconexión del taxi antes de los 10 segundos, resiliencia
        self.logger.info(f"Central iniciada en puerto {listen_port}, conectada a Kafka en {kafka_broker}")
        self.running = True
        # En __init__, después de inicializar pygame
        # Estado para los inputs y botones
        self.selected_input = None  # Para saber qué input está activo ('taxi_id' o 'destination')
        self.taxi_id_input = ""     # Texto del input de taxi ID
        self.destination_input = "" # Texto del input de destino
        #Cifrado SSL: la secret key es un string random
        self.secret_key = "EasyCab2024SecureKey"  # O cualquier string aleatorio complejo
        

        self.current_city = "Alicante"
        self.current_temp = None
        #Hilo para consultar a EC_CTC
        self.traffic_status=True
        self.running=True
        traffic_thread=threading.Thread(target=self.check_traffic)
        traffic_thread.daemon=True
        traffic_thread.start()

        #Hilo para procesar comandos de la BD cada 1s
        commands_thread = threading.Thread(target=self.check_commands)
        commands_thread.daemon = True
        commands_thread.start()

        # que se muestre el mapa en todos los taxis:
        self.map_producer = KafkaProducer(
            bootstrap_servers=[self.kafka_broker],
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            #compression_type='gzip'  # Comprimir datos
        )


        
    def setup_socket_server(self):
        """Inicializar servidor socket seguro para autenticación"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Envolver el socket con SSL antes del bind
        self.ssl_server = self.ssl_context.wrap_socket(
            self.server_socket, 
            server_side=True
        )
        
        self.ssl_server.bind(('0.0.0.0', self.listen_port))
        self.ssl_server.listen(5)
        self.logger.info(f"Servidor SSL escuchando en puerto {self.listen_port}")
        
        # Thread para manejar autenticaciones
        auth_thread = threading.Thread(target=self.handle_auth_connections)
        auth_thread.daemon = True
        auth_thread.start()


    # En CentralSystem
    def get_current_map_state(self):
        """Optimizado para enviar solo lo esencial"""
        try:
            map_state = {
                'timestamp': time.time(),
                'grid_state': []
            }
            
            # Siempre enviar locations
            locations = self.db.obtener_locations()
            for loc in locations:
                map_state['grid_state'].append({
                    'type': 'location',
                    'pos': [loc['coord_x'], loc['coord_y']],
                    'id': loc['id']
                })
                
            # Resto del estado...
            taxis = self.db.obtener_taxis()
            for taxi in taxis:
                if taxi['estado'] != 'no_disponible':
                    map_state['grid_state'].append({
                        'type': 'taxi',
                        'pos': [taxi['coord_x'], taxi['coord_y']],
                        'id': taxi['id'],
                        'color': 'green' if (taxi['estado'] == 'en_movimiento' and not taxi['esta_parado']) else 'red'
                    })
            
            # Añadir clientes activos
            for client_id, client in self.active_clients.items():
                if client.get('status') != 'picked_up':
                    map_state['grid_state'].append({
                        'type': 'client',
                        'pos': client['position'],
                        'id': client_id
                    })
                    
            return map_state
                
        except Exception as e:
            self.logger.error(f"Error generando estado del mapa: {e}")
            return None
    def cleanup(self):
        """Liberar recursos sin afectar la resiliencia"""
        if not hasattr(self, '_cleanup_called'):
            try:
                # Marcar el flag de finalización
                self.running = False
                
                # Cerrar el socket del servidor de manera segura
                if hasattr(self, 'server_socket'):
                    try:
                        self.server_socket.shutdown(socket.SHUT_RDWR)
                    except:
                        pass
                    finally:
                        self.server_socket.close()
                
                # Liberamos pygame pero no afecta a datos
                pygame.quit()
                
                self.logger.info("Recursos de sistema liberados")
                
            except Exception as e:
                self.logger.error(f"Error en cleanup: {e}")
            finally:
                # Marcar que ya se ha llamado al cleanup
                self._cleanup_called = True
    def load_locations(self):
        """Cargar locations desde la BD"""
        try:
            locations = self.db.obtener_locations()
            for loc in locations:
                self.locations[loc['id']] = [loc['coord_x'], loc['coord_y']]
            self.logger.info(f"Locations cargadas: {self.locations}")
        except Exception as e:
            self.logger.error(f"Error cargando locations: {e}")
            raise
    
    def process_command(self, command):
        """Procesar comandos de taxis"""
        if command.get('type') == 'return_to_base':
            taxi_id = command.get('taxi_id')
            # Invalidar token
            self.db.invalidate_taxi_token(taxi_id)
            # Enviar comando de vuelta a base
            self.send_taxi_order(taxi_id, {
                'type': 'return_to_base',
                'destination': [1, 1]
            })
    
    def setup_kafka(self):
        """Configurar productores y consumidores de Kafka"""
        self.producer = KafkaProducer(
            bootstrap_servers=[self.kafka_broker],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        # Consumidor para solicitudes de clientes
        self.consumer = KafkaConsumer(
            'ride_requests',
            bootstrap_servers=[self.kafka_broker],
            auto_offset_reset='latest',  # Solo mensajes nuevos
            enable_auto_commit=True,
            group_id='central_group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        # Consumidor para estados de taxis
        self.taxi_consumer = KafkaConsumer(
            'taxi_status',
            bootstrap_servers=[self.kafka_broker],
            auto_offset_reset='latest',  # Solo mensajes nuevos
            enable_auto_commit=True,
            group_id='central_taxi_group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
    def setup_ssl(self):
        """Configurar contexto SSL para el servidor"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        cert_path = os.path.join(project_root, 'shared', 'security', 'certificates')
        
        cert_file = os.path.join(cert_path, 'server.crt')
        key_file = os.path.join(cert_path, 'server.key')
        
        # Verificar que los archivos existen
        if not os.path.exists(cert_file):
            raise FileNotFoundError(f"Certificado no encontrado en: {cert_file}")
        if not os.path.exists(key_file):
            raise FileNotFoundError(f"Clave privada no encontrada en: {key_file}")
        
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(
            certfile=cert_file,
            keyfile=key_file
        )
        return context


    def verify_taxi_message(self, message):
        taxi_id = message.get('taxi_id')
        token = message.get('token')
        
        if not token:
            self.logger.warning(f"Mensaje sin token del taxi {taxi_id}")
            return False
            
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            if payload["taxi_id"] != taxi_id:
                self.logger.warning(f"Token no coincide con taxi_id {taxi_id}")
                return False
            return True
        except jwt.ExpiredSignatureError:
            self.logger.warning(f"Token expirado para taxi {taxi_id}")
            return False
        except Exception as e:
            self.logger.error(f"Error verificando token: {e}")
            return False
        
    def verify_taxi_token(self, taxi_id, token):
        """Verificar validez del token de un taxi"""
        if not token:
            return False
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return payload["taxi_id"] == taxi_id
        except jwt.ExpiredSignatureError:
            return False
        except Exception as e:
            self.logger.error(f"Error verificando token: {e}")
            return False
    def handle_auth_connections(self):
        while True:
            try:
                self.logger.info("Esperando conexiones entrantes...")
                client_socket, addr = self.ssl_server.accept()  
                self.logger.info(f"Nueva conexión desde {addr}")
                try:
                    self.logger.info("Iniciando handshake SSL...")
                    data = client_socket.recv(1024)
                    if not data:
                        self.logger.warning("No se recibieron datos")
                        continue

                    self.logger.info(f"Datos recibidos: {data}")
                    message = json.loads(data.decode())
                    if message.get('type') == 'auth':
                        response = self.handle_taxi_auth(message)
                        self.logger.info(f"Enviando respuesta: {response}")
                        client_socket.send(json.dumps(response).encode())
                        
                except Exception as e:
                    self.logger.error(f"Error procesando conexión: {e}", exc_info=True)
                finally:
                    client_socket.close()
                    
            except Exception as e:
                self.logger.error(f"Error en conexión SSL: {e}", exc_info=True)
    
    def log_audit_event(self, event_type, action, details, source_id=None):
        """Registrar evento de auditoría"""
        try:
            self.db.log_audit_event(
                source="CENTRAL",
                source_id=source_id,
                ip_address=self.get_local_ip(),
                event_type=event_type,
                action=action,
                details=details
            )
        except Exception as e:
            self.logger.error(f"Error registrando evento de auditoría: {e}")
    def handle_taxi_auth(self, message):
        """Manejar autenticación de taxi"""
        taxi_id = message.get('taxi_id')
        self.logger.info(f"Procesando autenticación para taxi {taxi_id}")

        try:
            # Verificar si es una reconexión dentro de los 10 segundos
            if taxi_id in self.disconnected_taxis:
                info = self.disconnected_taxis[taxi_id]
                info['timer'].cancel()  # Cancelar el timer
                
                # Restaurar estado del taxi
                if info['client_id']:
                    # Determinar el destino correcto basado en la fase del servicio
                    current_destination = info['current_destination']
                    
                    order = {
                        'type': 'resume_service',
                        'taxi_id': taxi_id,
                        'client_id': info['client_id'],
                        'current_position': info['position'],
                        'destination': current_destination,  # Usar el destino actual guardado
                        'final_destination': info['final_destination'],
                        'is_pickup_phase': info['is_pickup_phase'],
                        'client_position': info['client_position']
                    }
                    
                    # Restaurar estado en BD
                    self.db.restore_taxi_state(
                        taxi_id=taxi_id,
                        position=info['position'],
                        client_id=info['client_id'],
                        estado='en_movimiento',
                        destino=current_destination
                    )
                    
                    # Enviar orden al taxi
                    self.send_taxi_order(taxi_id, order)
                    
                    # Notificar al cliente
                    response = {
                        'type': 'service_resumed',
                        'client_id': info['client_id'],
                        'message': 'El taxi se ha reconectado y continúa el servicio'
                    }
                    self.producer.send('customer_responses', value=response)
                    
                del self.disconnected_taxis[taxi_id]
                # para auditoria
                self.log_audit_event(
                    event_type="auth",
                    action="TAXI_RECONNECT_SUCCESS",
                    details=f"Taxi {taxi_id} reconectado correctamente",
                    source_id=str(taxi_id)
                )
                return {'status': 'OK', 'restore': True, 'token': self.generate_token(taxi_id)}  

            # Si no es reconexión
            if self.db.verificar_taxi(taxi_id):
                # Aquí sí podemos usar posición inicial [1,1] porque es nueva autenticación
                self.db.actualizar_taxi_autenticado(taxi_id, 1, 1)
                token = self.generate_token(taxi_id)
                # Registrar evento de autenticación exitosa
                self.log_audit_event(
                    event_type="auth",
                    action="TAXI_AUTH_SUCCESS",
                    details=f"Nueva autenticación exitosa del taxi {taxi_id}",
                    source_id=str(taxi_id)
                )
                self.logger.info(f"Nueva autenticación exitosa del taxi {taxi_id}")
                
                return {'status': 'OK', 'restore': False, 'token': token}
            else:
                self.log_audit_event(
                    event_type="auth",
                    action="TAXI_AUTH_FAILED",
                    details=f"Autenticación fallida para taxi {taxi_id} - Taxi no verificado",
                    source_id=str(taxi_id)
                )
                self.logger.warning(f"Autenticación fallida para taxi {taxi_id}")
                return {'status': 'ERROR'}
            
        except Exception as e:
            self.log_audit_event(
                event_type="error",
                action="TAXI_AUTH_ERROR",
                details=f"Error en autenticación del taxi {taxi_id}: {str(e)}",
                source_id=str(taxi_id)
            )
            self.logger.error(f"Error en autenticación del taxi {taxi_id}: {e}")
            return {'status': 'ERROR'}
        
    # para generar token de autenciacion, de sesion, expirara en un tiempo
    def generate_token(self, taxi_id):
        """Generar un token JWT para el taxi"""
        payload = {
            'taxi_id': taxi_id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }
        return jwt.encode(payload, self.secret_key, algorithm='HS256')
    def mark_taxi_as_incident(self, taxi_id):
        """Marcar taxi como incidencia después de 10 segundos"""
        if taxi_id in self.disconnected_taxis:
            info = self.disconnected_taxis.pop(taxi_id)
            client_id = info['client_id']
            
            if client_id:
                # Actualizar el estado del cliente y su posición
                if client_id in self.active_clients:
                    # Determinar la posición final del cliente
                    if info['is_pickup_phase']:
                        # Si el taxi no había recogido al cliente aún, 
                        # el cliente se queda en su posición original
                        final_position = info['client_position']
                    else:
                        # Si el taxi ya había recogido al cliente,
                        # el cliente se queda en la última posición del taxi
                        final_position = info['position']
                    
                    self.active_clients[client_id].update({
                        'status': 'waiting',
                        'position': final_position
                    })
                    
                    # Actualizar el estado del cliente en la BD
                    self.db.actualizar_estado_cliente(
                        client_id=client_id,
                        status='waiting',
                        coord_x=final_position[0],
                        coord_y=final_position[1]
                    )
                    
                    # Notificar al cliente
                    response = {
                        'type': 'service_terminated',
                        'client_id': client_id,
                        'final_position': final_position,
                        'reason': 'taxi_disconnected',
                        'message': ('El servicio ha sido interrumpido por desconexión permanente del taxi' +
                                (' - Manteniéndote en tu posición original' if info['is_pickup_phase'] else ''))
                    }
                    self.producer.send('customer_responses', value=response)
                    self.logger.info(f"Cliente {client_id} notificado de la pérdida definitiva del taxi {taxi_id}")
                    
                    # Limpiar la asignación taxi-cliente
                    if taxi_id in self.active_taxis:
                        del self.active_taxis[taxi_id]
            
            # Actualizar BD - taxi vuelve a base y queda no disponible
            self.db.update_taxi_disconnected(taxi_id)
            self.logger.info(f"Taxi {taxi_id} marcado como no disponible por desconexión permanente") 
    
    def process_ride_request(self, request):
        """Procesar solicitud de viaje de un cliente"""
        request_type = request.get('type')
        client_id = request.get('client_id')
        
        # Si es un mensaje de finalización
        if request_type == 'customer_finished':
            if client_id in self.active_clients:
                self.logger.info(f"Cliente {client_id} ha terminado todos sus servicios")
                
                # Buscar si hay algún taxi que tenga asignado este cliente
                try:
                    taxi_info = self.db.get_taxi_by_client(client_id)
                    if taxi_info:
                        # Limpiar la asignación del taxi en la BD
                        self.db.actualizar_posicion_taxi(
                            taxi_id=taxi_info['id'],
                            x=taxi_info['coord_x'],
                            y=taxi_info['coord_y'],
                            estado='disponible',
                            esta_parado=True,
                            clear_client=True  # Nuevo parámetro
                        )
                        # Si el taxi estaba en nuestro registro de taxis activos, limpiarlo
                        if taxi_info['id'] in self.active_taxis:
                            del self.active_taxis[taxi_info['id']]
                except Exception as e:
                    self.logger.error(f"Error limpiando estado del taxi para cliente {client_id}: {e}")
                
                # Finalmente eliminar el cliente de nuestro registro
                del self.active_clients[client_id]
                
                self.db.borrar_cliente(
                    client_id=client_id
                )

                return

        # Para solicitudes de servicio
        elif request_type == 'ride_request':
            current_position = request.get('current_position')
            destination_id = request.get('destination_id')
            
            # PROBLEMA: No se valida que destination_id sea válido
            if destination_id is None or destination_id not in self.locations:
                self.logger.warning(f"Destino inválido para cliente {client_id}")
                response = {
                    'type': 'ride_rejected',
                    'client_id': client_id,
                    'reason': 'invalid_destination'
                }
                self.producer.send('customer_responses', value=response)
                return
            if client_id in self.active_clients:
                # Actualizar posición del cliente si ya existe
                self.active_clients[client_id].update({
                    'id': client_id,
                    'position': current_position,
                    'status': 'waiting',
                    'destination_id': destination_id  # Importante guardar el destination_id
                })

                #Actualizar el estado y el destino del cliente en la base de datos
                self.db.actualizar_estado_cliente(
                    client_id=client_id,
                    status='waiting',
                    coord_x=current_position[0],
                    coord_y=current_position[1],
                    destination_id=destination_id
                )
            else:
                # Crear nuevo registro de cliente
                self.active_clients[client_id] = {
                    'id': client_id,
                    'position': current_position,
                    'status': 'waiting',
                    'destination_id': destination_id  # Importante guardar el destination_id
                }

                #Añadir también el cliente a la BD
                self.db.insertar_cliente(
                    client_id=client_id,
                    coord_x=current_position[0],
                    coord_y=current_position[1],
                    destination_id=destination_id
                )
            
            # Intentar asignar un taxi
            if self.assign_taxi_to_service(client_id, destination_id):
                response = {
                    'type': 'ride_confirmation',
                    'client_id': client_id
                }
                self.logger.info(f"Servicio asignado para cliente {client_id}")
            else:
                response = {
                    'type': 'ride_rejected',
                    'client_id': client_id
                }
                self.logger.warning(f"No hay taxis disponibles para cliente {client_id}")

            self.producer.send('customer_responses', value=response)
            self.producer.flush()
    
    def is_taxi_with_client(self, taxi_id):
        """Determinar si el taxi ya recogió al cliente"""
        taxi = self.db.get_taxi_info(taxi_id)
        if not taxi or not taxi['cliente_asignado']:
            return False
        
        client_id = taxi['cliente_asignado']
        if client_id not in self.active_clients:
            return False

        # El taxi está con el cliente solo si está en la posición original del cliente
        # o si ya lo recogió (indicado por passenger_picked)
        client_pos = self.active_clients[client_id]['position']
        taxi_pos = [taxi['coord_x'], taxi['coord_y']]
        
        return taxi_pos == client_pos

    def handle_taxi_status(self, message):
        """Manejar actualizaciones de estado de los taxis"""
        # Primero verificar el mensaje completo
        if not self.verify_taxi_message(message):
            self.logger.warning("Mensaje rechazado por fallo en verificación")
            return

        try:
            taxi_id = message.get('taxi_id')
            message_type = message.get('type')
            position = message.get('position')
            state = message.get('state')
            is_parado = message.get('esta_parado', True)

            # Logging de auditoría para cada mensaje recibido
            self.logger.info(f"Mensaje recibido de taxi {taxi_id}: tipo={message_type}, posición={position}")

            # Si es mensaje de desconexión
            if message_type == 'disconnect':
                self.handle_taxi_disconnect(taxi_id)
                return

            # Verificar llegada a base y gestionar token
            if position == [1, 1]:
                self.db.invalidate_taxi_token(taxi_id)
                self.logger.info(f"Token invalidado para taxi {taxi_id} en base")
                # Notificar al taxi que debe reautenticarse
                self.send_taxi_order(taxi_id, {
                    'type': 'reauth_required',
                    'message': 'Token invalidado por llegada a base'
                })

            # Actualizar posición y estado en BD
            self.db.actualizar_posicion_taxi(
                taxi_id=taxi_id,
                x=position[0],
                y=position[1],
                estado=state,
                esta_parado=is_parado
            )

            # Procesar eventos específicos
            if message_type == 'arrived':
                self.notify_customer_service_completed(taxi_id)
            elif message_type == 'passenger_picked':
                client_id = self.active_taxis.get(taxi_id)
                if client_id in self.active_clients:
                    self.logger.info(f"Taxi {taxi_id} ha recogido al cliente {client_id}")
                    self.active_clients[client_id].update({
                        'status': 'picked_up',
                        'position': position
                    })

                    #Actualizar el estado del cliente en la base de datos
                    self.db.actualizar_estado_cliente(
                        client_id=client_id,
                        status='picked_up',
                        coord_x=position[0],
                        coord_y=position[1]
                    )

                    self.logger.debug(f"Estado del cliente actualizado: {self.active_clients[client_id]}")

        except Exception as e:
            self.logger.error(f"Error procesando mensaje de taxi {taxi_id}: {e}")
            # Registrar el error en el sistema de auditoría
            self.db.log_audit_event(
                event_type='error',
                taxi_id=taxi_id,
                details=str(e)
            )    
    def is_client_picked_up(self, client_id):
        """Verificar si el cliente ya ha sido recogido por algún taxi"""
        for taxi_id, assigned_client in self.active_taxis.items():
            if assigned_client == client_id:
                taxi = self.db.get_taxi_info(taxi_id)
                if taxi and self.has_taxi_reached_client(taxi_id):
                    return True
        return False

    def has_taxi_reached_client(self, taxi_id):
        """Verificar si el taxi ha llegado físicamente a la posición del cliente"""
        taxi = self.db.get_taxi_info(taxi_id)
        if not taxi or not taxi['cliente_asignado']:
            return False
        
        client_id = taxi['cliente_asignado']
        if client_id not in self.active_clients:
            return False
        
        # Verificar si el taxi está exactamente en la posición del cliente
        client_pos = self.active_clients[client_id]['position']
        taxi_pos = [taxi['coord_x'], taxi['coord_y']]
        
        # El taxi ha llegado al cliente si está en la misma posición
        has_reached = taxi_pos == client_pos
        
        self.logger.debug(f"Taxi {taxi_id}: posición={taxi_pos}, cliente={client_pos}, ha_llegado={has_reached}")
        
        return has_reached
    
    def assign_taxi_to_service(self, client_id, destination_id):
        """Asignar un taxi a un servicio"""
        
        with self.taxis_lock:  # Usar lock para hacer la asignación atómica
        # Verificar si el cliente ya tiene un taxi asignado
            for taxi_id, assigned_client in self.active_taxis.items():
                if assigned_client == client_id:
                    self.logger.warning(f"Cliente {client_id} ya tiene el taxi {taxi_id} asignado")
                    return False
            
        available_taxi = self.db.get_available_taxi()
        if available_taxi:
            taxi_id = available_taxi['id']
            # Verificar que el taxi no esté ya asignado (doble verificación)
            if taxi_id in self.active_taxis:
                self.logger.warning(f"Taxi {taxi_id} ya está asignado a otro cliente")
                return False
            
            # Registrar asignación
            self.active_taxis[taxi_id] = client_id
            
            pickup_location = self.active_clients[client_id]['position']
            
            try:
                # Actualizar BD con el destino y cliente
                self.db.assign_taxi_service(
                    taxi_id=taxi_id,
                    dest_x=pickup_location[0],
                    dest_y=pickup_location[1],
                    client_id=client_id
                )
                
                # Enviar orden al taxi
                order = {
                    'type': 'pickup',
                    'taxi_id': taxi_id,
                    'client_id': client_id,
                    'pickup_location': pickup_location,
                    'destination': self.locations[destination_id]
                }
                
                if self.send_taxi_order(taxi_id, order):
                    # Actualizar respuesta al cliente incluyendo el taxi_id
                    response = {
                        'type': 'ride_confirmation',
                        'client_id': client_id,
                        'taxi_id': taxi_id
                    }
                    self.producer.send('customer_responses', value=response)
                    self.producer.flush()
                    self.logger.info(f"Taxi {taxi_id} asignado al cliente {client_id}")
                    return True
                else:
                    # Si falla el envío de la orden, liberar la asignación
                    del self.active_taxis[taxi_id]
                    self.db.actualizar_posicion_taxi(
                        taxi_id=taxi_id,
                        x=available_taxi['coord_x'],
                        y=available_taxi['coord_y'],
                        estado='disponible',
                        esta_parado=True
                    )
            except Exception as e:
                self.logger.error(f"Error en asignación de taxi: {e}")
                # Limpiar asignación en caso de error
                if taxi_id in self.active_taxis:
                    del self.active_taxis[taxi_id]
                return False
                
        return False
    def handle_taxi_disconnect(self, taxi_id):
        """Manejar desconexión de taxi"""
        self.logger.info(f"Detectada desconexión del taxi {taxi_id}")
        
        try:
            taxi_info = self.db.get_taxi_info(taxi_id)
            if not taxi_info:
                return

            client_id = taxi_info['cliente_asignado']
            
            # Crear timer para todos los taxis
            timer = threading.Timer(
                self.reconnection_window, 
                self.mark_taxi_as_incident, 
                args=[taxi_id]
            )
            timer.start()
            
            # Si tiene cliente asignado, manejar toda la lógica del cliente
            if client_id and client_id in self.active_clients:
                # Determinar el destino actual y el tipo de destino
                current_destination = None
                final_destination = None
                is_pickup_phase = True  # Por defecto asumimos que va a recoger al cliente
                
                if self.has_taxi_reached_client(taxi_id):
                    # Si ya recogió al cliente, el destino actual es el destino final
                    is_pickup_phase = False
                    current_destination = self.locations[self.active_clients[client_id]['destination_id']]
                    final_destination = current_destination
                else:
                    # Si no recogió al cliente, el destino actual es la posición del cliente
                    current_destination = self.active_clients[client_id]['position']
                    final_destination = self.locations[self.active_clients[client_id]['destination_id']]

                # Guardar estado completo con info del cliente
                self.disconnected_taxis[taxi_id] = {
                    'timer': timer,
                    'position': [taxi_info['coord_x'], taxi_info['coord_y']],
                    'client_id': client_id,
                    'estado': taxi_info['estado'],
                    'current_destination': current_destination,  # Guardar destino actual
                    'final_destination': final_destination,
                    'is_pickup_phase': is_pickup_phase,  # Indicar si va a recoger o a destino final
                    'client_position': self.active_clients[client_id]['position'],
                    'destination_id': self.active_clients[client_id]['destination_id']  # Guardar ID del destino
                }
                
                # Notificar al cliente
                response = {
                    'type': 'service_interrupted',
                    'client_id': client_id,
                    'message': 'El taxi se ha desconectado temporalmente. Esperando reconexión...',
                    'is_temporary': True
                }
                self.producer.send('customer_responses', value=response)
                self.logger.info(f"Cliente {client_id} notificado de desconexión temporal")
            else:
                # Si no tiene cliente, guardar solo info básica del taxi
                self.disconnected_taxis[taxi_id] = {
                    'timer': timer,
                    'position': [taxi_info['coord_x'], taxi_info['coord_y']],
                    'client_id': None,
                    'estado': taxi_info['estado']
                }
            
            # Marcar temporalmente como no disponible
            self.db.update_taxi_status(taxi_id, 'no_disponible', True)
            self.logger.info(f"Estado del taxi {taxi_id} guardado para posible reconexión")
            
        except Exception as e:
            self.logger.error(f"Error al manejar desconexión del taxi {taxi_id}: {e}")
    def send_taxi_order(self, taxi_id, order):
        """Enviar orden a un taxi específico"""
        try:
            self.producer.send(f'taxi_orders_{taxi_id}', value=order)
            self.producer.flush()
            self.logger.info(f"Orden enviada al taxi {taxi_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error enviando orden al taxi {taxi_id}: {e}")
            return False
    
    # En Central, añadir método para detectar desconexión de taxi
    def monitor_taxi_connection(self, taxi_id):
        """Monitor para detectar desconexión de taxi"""
        time.sleep(10)  # Esperar 10 segundos
        # Si después de 10 segundos el taxi sigue en el mismo estado, considerar desconectado
        with self.taxis_lock:  # Usar un lock para thread safety
            if taxi_id in self.active_taxis:
                client_id = self.active_taxis[taxi_id]
                self.db.update_taxi_disconnected(taxi_id)
                self.notify_client_taxi_disconnected(client_id)
                del self.active_taxis[taxi_id]

    def notify_client_taxi_disconnected(self, client_id):
        """Notificar al cliente que su taxi se ha desconectado"""
        if client_id:
            response = {
                'type': 'service_interrupted',
                'client_id': client_id,
                'message': 'El servicio se ha interrumpido por desconexión del taxi'
            }
            self.producer.send('customer_responses', value=response)
    def notify_customer_service_completed(self, taxi_id):
        """Notificar al cliente que su servicio ha sido completado"""
        client_id = self.active_taxis.get(taxi_id)
        if client_id:
            # Obtener información del taxi y destino
            taxi_info = self.db.get_taxi_info(taxi_id)
            
            response = {
                'type': 'ride_completed',
                'client_id': client_id,
                'final_position': [taxi_info['coord_x'], taxi_info['coord_y']]
            }
            self.producer.send('customer_responses', value=response)
            self.producer.flush()
            
            # Actualizar estado del taxi
            self.db.actualizar_posicion_taxi(
                taxi_id=taxi_id,
                x=taxi_info['coord_x'],
                y=taxi_info['coord_y'],
                estado='disponible',
                esta_parado=True,
                clear_client=True #se envia tambien para cambiar el cliente a off
            )
            
            # Limpiar asignaciones
            del self.active_taxis[taxi_id]
            if client_id in self.active_clients:
                self.active_clients[client_id]['position'] = [taxi_info['coord_x'], taxi_info['coord_y']]
            
            self.db.actualizar_estado_cliente(
                client_id=client_id,
                status='finished',
                coord_x=taxi_info['coord_x'],
                coord_y=taxi_info['coord_y'],
            )

            self.logger.info(f"Servicio completado para cliente {client_id}")
    def handle_mouse_click(self, pos):
        """Manejar clicks del mouse"""
        # Verificar click en inputs
        if hasattr(self, 'taxi_input_rect') and self.taxi_input_rect.collidepoint(pos):
            self.selected_input = 'taxi_id'
        elif hasattr(self, 'dest_input_rect') and self.dest_input_rect.collidepoint(pos):
            self.selected_input = 'destination'
        else:
            self.selected_input = None
            
        # Verificar click en botones
        if hasattr(self, 'button_rects'):
            for i, rect in enumerate(self.button_rects):
                if rect.collidepoint(pos):
                    self.handle_button_click(i)

    def handle_key_press(self, event):
        """Manejar teclas presionadas"""
        if self.selected_input == 'taxi_id':
            if event.key == pygame.K_BACKSPACE:
                self.taxi_id_input = self.taxi_id_input[:-1]
            elif event.key in [pygame.K_RETURN, pygame.K_TAB]:
                self.selected_input = 'destination'
            elif event.unicode.isdigit() and len(self.taxi_id_input) < 2:
                self.taxi_id_input += event.unicode
                
        elif self.selected_input == 'destination':
            if event.key == pygame.K_BACKSPACE:
                self.destination_input = self.destination_input[:-1]
            elif event.key in [pygame.K_RETURN, pygame.K_TAB]:
                self.selected_input = None
            elif event.unicode.isalpha() and len(self.destination_input) < 1:
                self.destination_input += event.unicode.upper()
    def handle_button_click(self, button_index):
        """Manejar clicks en los botones"""
        if not self.taxi_id_input:
            self.logger.warning("Por favor, introduce un ID de taxi")
            return
            
        try:
            taxi_id = int(self.taxi_id_input)
            # Verificar que el taxi existe y está autenticado
            taxi_info = self.db.get_taxi_info(taxi_id)
            if not taxi_info or taxi_info['estado'] == 'no_disponible':
                self.logger.warning(f"Taxi {taxi_id} no disponible o no existe")
                return

            if button_index == 0:  # PARAR
                order = {
                    'type': 'stop',
                    'taxi_id': taxi_id
                }
                self.logger.info(f"Enviando orden de PARAR al taxi {taxi_id}")
                
            elif button_index == 1:  # REANUDAR
                order = {
                    'type': 'resume',
                    'taxi_id': taxi_id
                }
                self.logger.info(f"Enviando orden de REANUDAR al taxi {taxi_id}")
                
            elif button_index == 2:  # BASE
                order = {
                    'type': 'return_to_base',
                    'taxi_id': taxi_id,
                    'destination': [1, 1]
                }
                self.logger.info(f"Enviando orden de VOLVER A BASE al taxi {taxi_id}")
                
            elif button_index == 3:  # IR A
                if not self.destination_input or self.destination_input not in self.locations:
                    self.logger.warning("Destino inválido o no especificado")
                    return
                    
                destination = self.locations[self.destination_input]
                order = {
                    'type': 'go_to',
                    'taxi_id': taxi_id,
                    'destination': destination
                }
                self.logger.info(f"Enviando orden IR A {self.destination_input} al taxi {taxi_id}")

            # Enviar la orden al taxi
            if self.send_taxi_order(taxi_id, order):
                # Actualizar estado en BD según la orden
                if button_index == 0:  # PARAR
                    self.db.actualizar_posicion_taxi(
                        taxi_id=taxi_id,
                        x=taxi_info['coord_x'],
                        y=taxi_info['coord_y'],
                        esta_parado=True
                    )
                elif button_index == 1:  # REANUDAR
                    self.db.actualizar_posicion_taxi(
                        taxi_id=taxi_id,
                        x=taxi_info['coord_x'],
                        y=taxi_info['coord_y'],
                        esta_parado=False,
                        estado='en_movimiento'
                    )
                elif button_index in [2, 3]:  # BASE o IR A
                    self.db.actualizar_posicion_taxi(
                        taxi_id=taxi_id,
                        x=taxi_info['coord_x'],
                        y=taxi_info['coord_y'],
                        esta_parado=False,
                        estado='en_movimiento'
                    )
                    
        except ValueError:
            self.logger.error("ID de taxi inválido")
        except Exception as e:
            self.logger.error(f"Error procesando orden: {e}")
    def run(self):
        """Bucle principal de la central"""
        try:
            while True:
                # Procesar eventos de Pygame
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                    # Manejar clicks en inputs y botones
                        self.handle_mouse_click(event.pos)
                    elif event.type == pygame.KEYDOWN:
                    # Manejar entrada de texto
                        self.handle_key_press(event)

                # Procesar mensajes de clientes
                messages = self.consumer.poll(timeout_ms=100)
                for tp, msgs in messages.items():
                    for msg in msgs:
                        self.process_ride_request(msg.value)

                # Procesar mensajes de taxis (con más logs)
                taxi_messages = self.taxi_consumer.poll(timeout_ms=100)
                if taxi_messages:  # Solo si hay mensajes
                    self.logger.debug(f"Mensajes de taxis recibidos: {len(taxi_messages)}")
                    for tp, msgs in taxi_messages.items():
                        for msg in msgs:
                            self.logger.debug(f"Procesando mensaje: {msg.value}")
                            self.handle_taxi_status(msg.value)

                # Actualizar visualización
                self.draw_map()
                pygame.time.delay(100)
        except KeyboardInterrupt:
            self.logger.info("Cerrando central...")
        except Exception as e:
            self.logger.error(f"Error en bucle principal: {e}")
        finally:
            self.cleanup()  # Se llama aquí al cerrar
    
    def has_picked_up_client(self, taxi_id):
        """
        Verificar si el taxi ya ha recogido al cliente.
        Ahora usa el estado explícito 'picked_up' del cliente.
        """
        try:
            taxi = self.db.get_taxi_info(taxi_id)
            if not taxi or not taxi['cliente_asignado']:
                return False
            
            client_id = taxi['cliente_asignado']
            if client_id not in self.active_clients:
                return False
            client = self.active_clients[client_id]
        
            # Verificar si el cliente está marcado como recogido
            if client.get('status') == 'picked_up':
                return True
                
            return False
        
        except Exception as e:
            self.logger.error(f"Error en has_picked_up_client para taxi {taxi_id}: {e}")
            return False
    # Añadir nuevo método para dibujar la tabla de estado
    def draw_status_table(self):
        # Posición inicial de la tabla
        table_x = MAP_SECTION_WIDTH + 10
        table_y = 10
        table_width = 380
        row_height = 30
        col_widths = [60, 100, 220]  # Ajustados los anchos
        
        # Dibujar título principal
        title_height = 40
        pygame.draw.rect(self.screen, (220, 220, 220), 
                        (table_x, table_y, table_width, title_height))
        pygame.draw.rect(self.screen, TABLE_BORDER_COLOR,
                        (table_x, table_y, table_width, title_height), 2)
        
        title_font = pygame.font.SysFont('Arial', 20, bold=True)
        title_text = title_font.render("*** EASY CAB Release 1 ***", True, TEXT_COLOR)
        title_rect = title_text.get_rect(center=(table_x + table_width//2, table_y + title_height//2))
        self.screen.blit(title_text, title_rect)
        
        current_y = table_y + title_height + 10
        
        # Sección de Taxis
        section_title = self.header_font.render("Taxis", True, TEXT_COLOR)
        section_bg = pygame.Surface((table_width, 30))
        section_bg.fill((200, 200, 200))
        self.screen.blit(section_bg, (table_x, current_y))
        self.screen.blit(section_title, (table_x + 5, current_y + 5))
        current_y += 30
        
        # Encabezados de columnas para taxis
        headers = ['ID', 'Destino', 'Estado']
        x = table_x
        for i, header in enumerate(headers):
            pygame.draw.rect(self.screen, TABLE_HEADER_COLOR,
                            (x, current_y, col_widths[i], row_height))
            pygame.draw.rect(self.screen, TABLE_BORDER_COLOR,
                            (x, current_y, col_widths[i], row_height), 1)
            text = self.header_font.render(header, True, TEXT_COLOR)
            self.screen.blit(text, (x + 5, current_y + 5))
            x += col_widths[i]
        
        current_y += row_height
        
        # Datos de taxis
        taxis = self.db.obtener_taxis()
        for taxi in taxis:
            x = table_x
            
            # Mejorar la visualización del destino del taxi
            destino_mostrado = '-'
            if taxi['cliente_asignado']:
                client_id = taxi['cliente_asignado']
                if client_id in self.active_clients:
                    client = self.active_clients[client_id]
                    if client.get('status') == 'picked_up':
                        # Si ya recogió al cliente, mostrar el destino final
                        destino_mostrado = client.get('destination_id', '-')
                    else:
                        # Si va a recoger al cliente, mostrar el ID del cliente
                        destino_mostrado = f"→{client_id}"

            row_data = [
                str(taxi['id']),
                destino_mostrado,
                taxi['estado']
            ]
            # Color de texto y fondo según estado
            text_color = TEXT_COLOR
            if taxi['estado'] == 'no_disponible':
                text_color = (200, 0, 0)  # Rojo para no disponible
            elif taxi['estado'] == 'en_movimiento' and not taxi['esta_parado']:
                text_color = (0, 150, 0)  # Verde para en movimiento
            
            for i, data in enumerate(row_data):
                # Fondo alternado para mejor legibilidad
                bg_color = (245, 245, 245) if taxis.index(taxi) % 2 == 0 else (255, 255, 255)
                pygame.draw.rect(self.screen, bg_color,
                            (x, current_y, col_widths[i], row_height))
                pygame.draw.rect(self.screen, TABLE_BORDER_COLOR,
                            (x, current_y, col_widths[i], row_height), 1)
                text = self.font.render(data, True, text_color)
                self.screen.blit(text, (x + 5, current_y + 5))
                x += col_widths[i]
            current_y += row_height
        
        current_y += 20  # Espacio entre secciones
        
        # Sección de Clientes
        if self.active_clients:  # Solo mostrar si hay clientes activos
            section_title = self.header_font.render("Clientes", True, TEXT_COLOR)
            section_bg = pygame.Surface((table_width, 30))
            section_bg.fill((200, 200, 200))
            self.screen.blit(section_bg, (table_x, current_y))
            self.screen.blit(section_title, (table_x + 5, current_y + 5))
            current_y += 30
            
            # Encabezados de columnas para clientes
            x = table_x
            for i, header in enumerate(headers):
                pygame.draw.rect(self.screen, TABLE_HEADER_COLOR,
                            (x, current_y, col_widths[i], row_height))
                pygame.draw.rect(self.screen, TABLE_BORDER_COLOR,
                            (x, current_y, col_widths[i], row_height), 1)
                text = self.header_font.render(header, True, TEXT_COLOR)
                self.screen.blit(text, (x + 5, current_y + 5))
                x += col_widths[i]
            
            current_y += row_height
            
            # Datos de clientes
            for client_id, client in self.active_clients.items():
                x = table_x
                
                # Mejorar la visualización del destino del cliente
                destino_mostrado = client.get('destination_id', '-')
                if client.get('status') == 'picked_up':
                    # Si está siendo transportado, mostrar hacia dónde va
                    destino_mostrado = f"→{client.get('destination_id', '-')}"
                
                row_data = [
                    client_id,
                    destino_mostrado,
                    client.get('status', 'waiting')
                ]
                
                # Color según estado del cliente
                text_color = TEXT_COLOR
                if client.get('status') == 'waiting':
                    text_color = (200, 150, 0)  # Amarillo oscuro para waiting
                elif client.get('status') == 'picked_up':
                    text_color = (0, 150, 0)  # Verde para picked_up
                
                for i, data in enumerate(row_data):
                    bg_color = (245, 245, 245) if list(self.active_clients.keys()).index(client_id) % 2 == 0 else (255, 255, 255)
                    pygame.draw.rect(self.screen, bg_color,
                                (x, current_y, col_widths[i], row_height))
                    pygame.draw.rect(self.screen, TABLE_BORDER_COLOR,
                                (x, current_y, col_widths[i], row_height), 1)
                    text = self.font.render(str(data), True, text_color)
                    self.screen.blit(text, (x + 5, current_y + 5))
                    x += col_widths[i]
                current_y += row_height
    def draw_map(self):
        self.screen.fill(BACKGROUND_COLOR)
        
        # Dibujar área de índices
        pygame.draw.rect(self.screen, INDEX_BG_COLOR, (0, 0, MAP_SECTION_WIDTH, TILE_SIZE))  # Fila superior
        pygame.draw.rect(self.screen, INDEX_BG_COLOR, (0, 0, TILE_SIZE, MAP_SECTION_WIDTH))  # Columna izquierda
        
        # Dibujar cuadrícula
        for i in range(MAP_SIZE):
            # Líneas verticales
            pygame.draw.line(self.screen, GRID_COLOR, 
                            (i * TILE_SIZE, 0), 
                            (i * TILE_SIZE, MAP_SECTION_WIDTH))
            # Líneas horizontales
            pygame.draw.line(self.screen, GRID_COLOR, 
                            (0, i * TILE_SIZE), 
                            (MAP_SECTION_WIDTH, i * TILE_SIZE))
        
        # Dibujar números de índices
        for i in range(1, MAP_SIZE):
            # Números horizontales (1-20)
            num_text = self.font.render(str(i), True, TEXT_COLOR)
            self.screen.blit(num_text, 
                            (i * TILE_SIZE + TILE_SIZE//4, TILE_SIZE//4))
            # Números verticales (1-20)
            self.screen.blit(num_text, 
                            (TILE_SIZE//4, i * TILE_SIZE + TILE_SIZE//4))

        # Dibujar locations
        locations = self.db.obtener_locations()
        for loc in locations:
            x_pixel = (loc['coord_y']) * TILE_SIZE
            y_pixel = (loc['coord_x']) * TILE_SIZE
            pygame.draw.rect(self.screen, LOCATION_COLOR, 
                            (x_pixel, y_pixel, TILE_SIZE, TILE_SIZE))
            text = self.font.render(loc['id'], True, TEXT_COLOR)
            self.screen.blit(text, (x_pixel + TILE_SIZE//4, 
                                    y_pixel + TILE_SIZE//4))
        # Primero dibujar los clientes que están esperando
        for client_id, client in self.active_clients.items():
            if client.get('status') in ['waiting', None]:  # Incluir clientes sin estado o en espera
                x_pixel = (client['position'][1]) * TILE_SIZE
                y_pixel = (client['position'][0]) * TILE_SIZE
                pygame.draw.rect(self.screen, CUSTOMER_COLOR,
                            (x_pixel, y_pixel, TILE_SIZE, TILE_SIZE))
                text = self.font.render(str(client_id).lower(), True, TEXT_COLOR)
                self.screen.blit(text, (x_pixel + TILE_SIZE//4,
                                    y_pixel + TILE_SIZE//4))
        # Dibujar taxis y clientes que están siendo transportados
        taxis = self.db.obtener_taxis()
        for taxi in taxis:
            if taxi['estado'] != 'no_disponible':
                # Verde si está en movimiento y no parado, rojo en cualquier otro caso
                color = TAXI_COLOR if (taxi['estado'] == 'en_movimiento' and not taxi['esta_parado']) else TAXI_END_COLOR
                
                # Calcular posición en pantalla
                x_pixel = (taxi['coord_y']) * TILE_SIZE
                y_pixel = (taxi['coord_x']) * TILE_SIZE
                
                # Dibujar rectángulo del taxi
                pygame.draw.rect(self.screen, color,
                            (x_pixel, y_pixel, TILE_SIZE, TILE_SIZE))
                
                # Preparar el texto a mostrar
                display_text = str(taxi['id'])
                
                # Si el taxi tiene un cliente y está en estado picked_up, mostrarlos juntos
                if (taxi['cliente_asignado'] and 
                    taxi['cliente_asignado'] in self.active_clients and 
                    self.active_clients[taxi['cliente_asignado']]['status'] == 'picked_up'):
                    
                    display_text = f"{taxi['id']}{taxi['cliente_asignado']}"
                    # Actualizar la posición del cliente
                    self.active_clients[taxi['cliente_asignado']]['position'] = [taxi['coord_x'], taxi['coord_y']]
                
                text = self.font.render(display_text, True, TEXT_COLOR)
                self.screen.blit(text, (x_pixel + TILE_SIZE//4, y_pixel + TILE_SIZE//4))

        # Dibujar clientes que no están siendo transportados
        for client_id, client in self.active_clients.items():
            # Solo dibujar el cliente si NO está en estado picked_up
            if client.get('status') != 'picked_up':
                x_pixel = (client['position'][1]) * TILE_SIZE
                y_pixel = (client['position'][0]) * TILE_SIZE
                pygame.draw.rect(self.screen, CUSTOMER_COLOR,
                            (x_pixel, y_pixel, TILE_SIZE, TILE_SIZE))
                text = self.font.render(str(client_id).lower(), True, TEXT_COLOR)
                self.screen.blit(text, (x_pixel + TILE_SIZE//4,
                                    y_pixel + TILE_SIZE//4))
        
        self.draw_status_table()
        self.draw_control_panel()  # Añadir esta línea
        current_time = time.time()
        if not hasattr(self, 'last_map_update') or current_time - self.last_map_update >= 0.1:
            map_state = self.get_current_map_state()
            if map_state:
                self.map_producer.send('map_state', value=map_state)
                self.last_map_update = current_time
    
        pygame.display.flip()
    def draw_control_panel(self):
        """Dibujar panel de control para enviar órdenes a los taxis"""
        # Posición inicial del panel (debajo de las tablas actuales)
        panel_x = MAP_SECTION_WIDTH + 10
        panel_y = WINDOW_HEIGHT - 150
        panel_width = 380
        panel_height = 140
        
        # Fondo del panel
        pygame.draw.rect(self.screen, (240, 240, 240),
                        (panel_x, panel_y, panel_width, panel_height))
        pygame.draw.rect(self.screen, TABLE_BORDER_COLOR,
                        (panel_x, panel_y, panel_width, panel_height), 2)
        
        # Título del panel
        title_height = 30
        pygame.draw.rect(self.screen, TABLE_HEADER_COLOR, 
                        (panel_x, panel_y, panel_width, title_height))
        title_text = self.header_font.render("Panel de Control", True, TEXT_COLOR)
        self.screen.blit(title_text, (panel_x + 5, panel_y + 5))
        
        # Input para ID del taxi
        input_y = panel_y + title_height + 10  # <- Esta línea faltaba
        
        # Label "Taxi ID:"
        taxi_id_text = self.font.render("Taxi ID:", True, TEXT_COLOR)
        self.screen.blit(taxi_id_text, (panel_x + 5, input_y + 5))
        
        # Campo de entrada Taxi ID
        taxi_input_rect = pygame.Rect(panel_x + 70, input_y, 40, 30)
        pygame.draw.rect(self.screen, (255, 255, 255), taxi_input_rect, 0)
        pygame.draw.rect(self.screen, TABLE_BORDER_COLOR, taxi_input_rect, 1)
        if self.selected_input == 'taxi_id':
            pygame.draw.rect(self.screen, (200, 200, 255), taxi_input_rect, 3)
        taxi_text = self.font.render(self.taxi_id_input, True, TEXT_COLOR)
        self.screen.blit(taxi_text, (taxi_input_rect.x + 5, taxi_input_rect.y + 5))

        # Input para Destino
        dest_label = self.font.render("Destino:", True, TEXT_COLOR)
        self.screen.blit(dest_label, (panel_x + 130, input_y + 5))
        
        # Campo de entrada Destino
        dest_input_rect = pygame.Rect(panel_x + 200, input_y, 40, 30)
        pygame.draw.rect(self.screen, (255, 255, 255), dest_input_rect, 0)
        pygame.draw.rect(self.screen, TABLE_BORDER_COLOR, dest_input_rect, 1)
        if self.selected_input == 'destination':
            pygame.draw.rect(self.screen, (200, 200, 255), dest_input_rect, 3)
        dest_text = self.font.render(self.destination_input, True, TEXT_COLOR)
        self.screen.blit(dest_text, (dest_input_rect.x + 5, dest_input_rect.y + 5))

        # Botones de control
        button_y = input_y + 40
        buttons = [
            {"text": "PARAR", "color": BUTTON_STOP_COLOR},
            {"text": "REANUDAR", "color": BUTTON_RESUME_COLOR},
            {"text": "BASE", "color": BUTTON_BASE_COLOR},
            {"text": "IR A", "color": BUTTON_GOTO_COLOR}
        ]
        
        # Guardamos las rect de los botones para detectar clicks
        self.button_rects = []
        
        button_width = 85
        for i, btn in enumerate(buttons):
            x = panel_x + (i * (button_width + 10))
            button_rect = pygame.Rect(x, button_y, button_width, 30)
            self.button_rects.append(button_rect)
            
            pygame.draw.rect(self.screen, btn["color"], button_rect)
            pygame.draw.rect(self.screen, TABLE_BORDER_COLOR, button_rect, 1)
            text = self.font.render(btn["text"], True, TEXT_COLOR)
            text_rect = text.get_rect(center=button_rect.center)
            self.screen.blit(text, text_rect)

        # Guardar las rect de los inputs para detectar clicks
        self.taxi_input_rect = taxi_input_rect
        self.dest_input_rect = dest_input_rect

    def order_all_taxis_to_base(self):
        try:
            taxis = self.db.obtener_taxis()
            for taxi in taxis:
                taxi_id = taxi['id']
                order = {
                    'type': 'return_to_base',
                    'taxi_id': taxi_id,
                    'destination': [1, 1]
                }
                self.send_taxi_order(taxi_id, order)
                # Invalidate token if any
                if taxi_id in self.taxi_tokens:
                    del self.taxi_tokens[taxi_id]
            
            self.logger.info("Todos los taxis han sido enviados a la base (order_all_taxis_to_base)")
        except Exception as e:
            self.logger.error(f"Error enviando a todos los taxis a la base: {e}")

    def check_traffic(self):
        while self.running:
            try:
                response = requests.get("http://localhost:5002/traffic", timeout=5)
                if response.status_code == 200:
                    data=response.json()
                    
                    city = data["city"]
                    temp = data["temp"]
                    traffic_ok = (data["status"] == "OK")
                    
                    self.current_city = city
                    self.current_temp = temp
                    prev_status = self.traffic_status
                    self.traffic_status = traffic_ok

                    #Guardamos la información en la BD
                    self.db.update_ctc_status(city, temp, traffic_ok)
                    
                    # Solo enviar órdenes si el estado cambió a KO
                    if prev_status and not self.traffic_status:
                        self.order_all_taxis_to_base()
                else:
                    self.traffic_status = False
                    self.db.update_ctc_status(self.current_city, self.current_temp or 0.0, False)

            except Exception as e:
                self.traffic_status = False
                # Guardar en BD (KO)
                self.db.update_ctc_status(self.current_city, self.current_temp or 0.0, False)
                print(f"Error en check_traffic: {e}")
            
            time.sleep(10)

    def check_commands(self):
        """
        Hilo que revisa cada 1s la tabla ctc_commands, 
        y si encuentra un 'change_city', llama a self.change_city(...) 
        y marca el comando como processed.
        """
        while self.running:
            try:
                commands = self.db.get_unprocessed_ctc_commands()
                for cmd in commands:
                    cmd_id = cmd["id"]
                    cmd_type = cmd["command_type"]
                    cmd_data = cmd["command_data"]
                    
                    if cmd_type == "change_city":
                        # Llama a tu método local
                        result = self.change_city(cmd_data)  # city
                        # Podrías hacer logging, o guardar la respuesta en algún lado
                        self.logger.info(f"Resultado al cambiar ciudad: {result}")
                    
                    # tras ejecutar la acción, marcar como processed
                    self.db.mark_command_processed(cmd_id)

            except Exception as e:
                self.logger.error(f"Error en check_commands: {e}")
            
            # Esperamos 2 seg para no saturar
            time.sleep(2)


    def change_city(self, new_city):
        """
        Llama a la CTC para cambiar la ciudad y devuelve el resultado: "OK" o "ERROR", la ciudad y la temp.
        """
        try:
            payload = {"city": new_city}
            r = requests.post("http://localhost:5002/city", json=payload, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data["status"] == "OK":
                    #Hacemos la petición inmediatamente para poder mostrar rápido el cambio de ciudad y la nueva temperatura, así como el estado del tráfico
                    traffic_resp = requests.get("http://localhost:5002/traffic", timeout=5).json()
                    if r.status_code == 200:
                        city = traffic_resp["city"]
                        temp = traffic_resp["temp"]
                        traffic_ok = (traffic_resp["status"] == "OK")

                        self.current_city = city
                        self.current_temp = temp
                        self.traffic_status = traffic_ok

                        #Guardamos la nueva información con la nueva ciudad en la base de datos
                        self.db.update_ctc_status(city, temp, traffic_ok)

                        #Devolvemos el "status" en base a la temperatura
                        return {
                            "status": traffic_resp["status"], 
                            "city": city, 
                            "temp": temp
                        }
                    else:
                        self.db.update_ctc_status(new_city, 0.0, False)
                        return {"status": "ERROR", "city": new_city, "temp": None}
                    
                else:
                    return {"status": "ERROR", "city": new_city, "temp": None}
            
            else:
                return {"status": "ERROR", "city": new_city, "temp": None}
        except Exception as e:
            self.logger.error(f"Error cambiando ciudad: {e}")
            return {"status": "ERROR", "city": new_city, "temp": None}

def main():
    parser = argparse.ArgumentParser(description='EasyCab Central Server')
    parser.add_argument('listen_port', type=int, help='Puerto de escucha')
    parser.add_argument('kafka_broker', help='IP:Puerto del broker Kafka')
    parser.add_argument('--db-host', default='localhost', help='Host de la BD')
    parser.add_argument('--db-port', type=int, default=5432, help='Puerto de la BD')
    
    args = parser.parse_args()
    
    # Configuración de la BD
    db_params = {
        'dbname': 'central_db',
        'user': 'postgres',
        'password': 'postgres',
        'host': args.db_host,
        'port': args.db_port
    }
    central = None
    try:
        central = CentralSystem(args.listen_port, args.kafka_broker, db_params)
        central.run()
    except KeyboardInterrupt:
        print("\nCentral terminada por el usuario")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if central:
            central.cleanup()  # También se llama aquí por seguridad

if __name__ == "__main__":
    main()