# EC_DE.py (Digital Engine)
import sys
import socket
import json
import threading
import logging
from kafka import KafkaConsumer, KafkaProducer
import time
import pygame
import ssl
from datetime import datetime, timedelta
import requests
import secrets
import os
import queue
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Primero añadir las constantes necesarias al inicio de la clase
TILE_SIZE = 35
MAP_SIZE = 21
WINDOW_SIZE = MAP_SIZE * TILE_SIZE

# Colores
BACKGROUND_COLOR = (255, 255, 255)
GRID_COLOR = (200, 200, 200)
TAXI_COLOR = (0, 255, 0)
TAXI_END_COLOR = (255, 0, 0)
LOCATION_COLOR = (0, 0, 255)
CUSTOMER_COLOR = (255, 255, 0)
TEXT_COLOR = (0, 0, 0)
INDEX_BG_COLOR = (240, 240, 240)

class TaxiVisualization:
    def __init__(self, taxi_id, window_size):
        pygame.init()
        # Configurar logging
        self.logger = logging.getLogger(f'taxi_viz_{taxi_id}')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # Cola para la comunicación entre hilos
        self.update_queue = queue.Queue(maxsize=10)
        
        # Configuración de pygame
        self.screen = pygame.display.set_mode((window_size, window_size), 
                                            pygame.HWSURFACE | pygame.DOUBLEBUF)
        pygame.display.set_caption(f"Taxi {taxi_id} View")
        self.font = pygame.font.SysFont('Arial', 16)
        self.running = True
        self.taxi_id = taxi_id
        self.clock = pygame.time.Clock()
        self.map_state = None
        self._grid_surface = self._create_grid(window_size)

    def update(self, map_state):
        """Poner actualización en la cola de manera no bloqueante"""
        if map_state:
            try:
                # Usar put_nowait para evitar bloqueos
                self.update_queue.put_nowait(map_state.copy())
            except queue.Full:
                # Si la cola está llena, descartar el mensaje más antiguo
                try:
                    self.update_queue.get_nowait()
                    self.update_queue.put_nowait(map_state.copy())
                except (queue.Empty, queue.Full):
                    pass


    def _draw_dynamic_elements(self, surface):
        """Dibujar elementos dinámicos del mapa"""
        if not self.map_state:
            return

        for elem in self.map_state.get('grid_state', []):
            x_pixel = elem['pos'][1] * TILE_SIZE
            y_pixel = elem['pos'][0] * TILE_SIZE
            
            if 0 <= x_pixel < WINDOW_SIZE and 0 <= y_pixel < WINDOW_SIZE:
                color = self._get_element_color(elem)
                pygame.draw.rect(surface, color, (x_pixel, y_pixel, TILE_SIZE, TILE_SIZE))
                text = self._get_element_text(elem)
                text_surface = self.font.render(text, True, TEXT_COLOR)
                surface.blit(text_surface, (x_pixel + TILE_SIZE//4, y_pixel + TILE_SIZE//4))
                
                # Resaltar el taxi actual
                if elem['type'] == 'taxi' and elem['id'] == self.taxi_id:
                    pygame.draw.rect(surface, (255,255,255), 
                                  (x_pixel, y_pixel, TILE_SIZE, TILE_SIZE), 2)

    def draw(self):
        """Dibujar el mapa actual desde la cola"""
        if not self.running:
            return

        try:
            # Procesar eventos pygame
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    return
                elif event.type == pygame.WINDOWMINIMIZED:
                    time.sleep(0.1)
                    continue

            # Obtener última actualización disponible
            try:
                while not self.update_queue.empty():
                    self.map_state = self.update_queue.get_nowait()
            except queue.Empty:
                pass

            # Crear surface temporal
            temp_surface = pygame.Surface((WINDOW_SIZE, WINDOW_SIZE))
            temp_surface.fill(BACKGROUND_COLOR)
            
            # Dibujar elementos base
            if self._grid_surface:
                temp_surface.blit(self._grid_surface, (0, 0))
            
            # Dibujar elementos dinámicos si hay estado
            if self.map_state:
                self._draw_dynamic_elements(temp_surface)

            # Actualizar pantalla
            self.screen.blit(temp_surface, (0, 0))
            pygame.display.flip()
            self.clock.tick(30)

        except Exception as e:
            self.logger.error(f"Error en visualización: {e}")

    def _draw_element(self, surface, elem):
        """Dibujar un elemento individual de manera optimizada"""
        x_pixel = elem['pos'][1] * TILE_SIZE
        y_pixel = elem['pos'][0] * TILE_SIZE
        
        if 0 <= x_pixel < WINDOW_SIZE and 0 <= y_pixel < WINDOW_SIZE:
            color = self._get_element_color(elem)
            pygame.draw.rect(surface, color, (x_pixel, y_pixel, TILE_SIZE, TILE_SIZE))
            text = self._get_element_text(elem)
            text_surface = self.font.render(text, True, TEXT_COLOR)
            surface.blit(text_surface, (x_pixel + TILE_SIZE//4, y_pixel + TILE_SIZE//4))
    def _create_grid(self, window_size):
        """Crear una superficie con el grid básico"""
        surface = pygame.Surface((window_size, window_size))
        surface.fill(BACKGROUND_COLOR)
        
        # Dibujar área de índices
        pygame.draw.rect(surface, INDEX_BG_COLOR, (0, 0, window_size, TILE_SIZE))
        pygame.draw.rect(surface, INDEX_BG_COLOR, (0, 0, TILE_SIZE, window_size))
        
        # Dibujar líneas de la cuadrícula
        for i in range(MAP_SIZE):
            pygame.draw.line(surface, GRID_COLOR, 
                        (i * TILE_SIZE, 0), 
                        (i * TILE_SIZE, window_size))
            pygame.draw.line(surface, GRID_COLOR, 
                        (0, i * TILE_SIZE), 
                        (window_size, i * TILE_SIZE))
        
        # Dibujar números de índices
        for i in range(1, MAP_SIZE):
            num_text = self.font.render(str(i), True, TEXT_COLOR)
            surface.blit(num_text, (i * TILE_SIZE + TILE_SIZE//4, TILE_SIZE//4))
            surface.blit(num_text, (TILE_SIZE//4, i * TILE_SIZE + TILE_SIZE//4))
        
        return surface
    def _get_element_color(self, elem):
        """Obtener color para un elemento"""
        if elem['type'] == 'taxi':
            return TAXI_COLOR if elem['color'] == 'green' else TAXI_END_COLOR
        elif elem['type'] == 'client':
            return CUSTOMER_COLOR
        elif elem['type'] == 'location':
            return LOCATION_COLOR
        return BACKGROUND_COLOR

    def _get_element_text(self, elem):
        """Obtener texto para un elemento"""
        if elem['type'] == 'taxi':
            return str(elem['id'])
        elif elem['type'] == 'client':
            return elem['id'].lower()
        elif elem['type'] == 'location':
            return elem['id']
        return ""
    def cleanup(self):
        """Limpiar recursos de pygame"""
        self.running = False
        pygame.quit()



class DigitalEngine:
    def __init__(self, central_ip, central_port, kafka_broker, sensor_port, taxi_id):
        # Primero asignar el taxi_id
        self.taxi_id = taxi_id
        
        # Configurar logging
        self.logger = logging.getLogger(f'taxi_{taxi_id}')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # Inicializar pygame
        #pygame.init()
        #self.WINDOW_SIZE = 735  # 21 * 35 (MAP_SIZE * TILE_SIZE)
        #self.screen = pygame.display.set_mode((self.WINDOW_SIZE, self.WINDOW_SIZE))
        #pygame.display.set_caption(f"EasyCab Taxi {self.taxi_id}")
        # Configuración optimizada para el consumidor de mapa
        self.map_consumer = KafkaConsumer(
            'map_state',
            bootstrap_servers=[kafka_broker],
            group_id=f'taxi_map_{self.taxi_id}',
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            fetch_min_bytes=1,
            fetch_max_wait_ms=100,
            consumer_timeout_ms=100,
            max_poll_records=1,  # Limitar registros por poll
            session_timeout_ms=30000,  # Aumentar timeout de sesión
            heartbeat_interval_ms=10000
        )
        # Resto de las inicializaciones...
        self.position = [1, 1]
        self.state = "no_disponible"
        self.esta_parado = True
        self.destination = None
        self.is_authenticated = False
        self.sensor_status = "OK"
        
        # Datos de conexión
        self.central_ip = central_ip
        self.central_port = central_port
        self.kafka_broker = kafka_broker
        self.sensor_port = sensor_port
        
        # Otros atributos
        self.client_id = None
        self.final_destination = None
        self.auth_token = None
        self.ssl_context = self.setup_ssl()
        self.cert_token = None
        self.running = True
        self.viz_thread = None

        self.map_queue = queue.Queue(maxsize=10)  # Limitar tamaño para evitar memory leaks
        self.visualization = TaxiVisualization(taxi_id, WINDOW_SIZE)
        self.kafka_thread = None
        # Inicializar servidor de sensores
        self.setup_sensor_server()

    def start_visualization(self):
        if self.viz_thread is None or not self.viz_thread.is_alive():
            self.running = True
            self.viz_thread = threading.Thread(target=self.run_visualization)
            self.viz_thread.daemon = True
            self.viz_thread.start()
            
            try:
                # Esperar primer estado
                start = time.time()
                while time.time() - start < 5:  # Timeout de 5 segundos
                    messages = self.map_consumer.poll(timeout_ms=100)
                    if messages:
                        for tp, msgs in messages.items():
                            for msg in msgs:
                                if msg.value:
                                    self.logger.info("Estado inicial del mapa recibido")
                                    self.visualization.update(msg.value)
                                    return
                    time.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error iniciando visualización: {e}")
    def consume_map_data(self):
        """Hilo dedicado para consumir datos del mapa desde Kafka"""
        try:
            while self.running:
                try:
                    messages = self.map_consumer.poll(timeout_ms=100)
                    if messages:
                        for tp, msgs in messages.items():
                            for msg in msgs:
                                if msg.value:
                                    # Usar put_nowait para evitar bloqueos
                                    try:
                                        self.map_queue.put_nowait(msg.value)
                                    except queue.Full:
                                        # Si la cola está llena, descartar el mensaje más antiguo
                                        try:
                                            self.map_queue.get_nowait()
                                            self.map_queue.put_nowait(msg.value)
                                        except (queue.Empty, queue.Full):
                                            pass
                    time.sleep(0.01)  # Pequeña pausa para no saturar CPU
                except Exception as e:
                    self.logger.error(f"Error en consumidor Kafka: {e}")
                    time.sleep(0.1)
        except Exception as e:
            self.logger.error(f"Error fatal en consumidor: {e}")

    
    def register_with_registry(self):
            """Registrarse con el Registry primero"""
            try:
                headers = {
                    'X-Taxi-Auth': 'Basic ' + secrets.token_hex(16),
                    'Content-Type': 'application/json'
                }
                
                data = {
                    'taxi_id': self.taxi_id
                }
                
                # Usar HTTPS sin verificar certificado (solo para desarrollo)
                response = requests.post(
                    'https://localhost:5000/registry/taxi',
                    headers=headers,
                    json=data,
                    verify=False  # Solo para desarrollo
                )
                
                if response.status_code == 200:
                    result = response.json()
                    self.cert_token = result['cert_token']
                    self.logger.info("Registro exitoso con Registry")
                    return True
                else:
                    self.logger.error(f"Error en registro: {response.text}")
                    return False
                    
            except Exception as e:
                self.logger.error(f"Error conectando con Registry: {e}")
                return False

    
        
    def setup_sensor_server(self):
        """Inicializar servidor socket para sensores"""
        self.sensor_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sensor_server.bind(('0.0.0.0', self.sensor_port))
        self.sensor_server.listen(1)
        self.logger.info(f"Servidor de sensores iniciado en puerto {self.sensor_port}")
        
    def authenticate_with_central(self):
        """Autenticación inicial con la central mediante sockets seguros"""
        while not self.is_authenticated:
            try:
                context = self.ssl_context
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(10.0)
                    self.logger.info(f"Intentando conectar a {self.central_ip}:{self.central_port}")
                    
                    with context.wrap_socket(sock, server_hostname=self.central_ip) as ssl_sock:
                        self.logger.debug("Socket seguro creado, intentando conectar...")
                        ssl_sock.connect((self.central_ip, self.central_port))
                        self.logger.info("Conexión SSL establecida")
                        
                        auth_message = {
                            "type": "auth",
                            "taxi_id": self.taxi_id,
                            "position": self.position,
                            "cert_token": self.cert_token,  # Token del Registry
                            "credentials": {
                                "cert_id": "taxi_cert_1",
                                "timestamp": int(time.time())
                            }
                        }
                        
                        message_str = json.dumps(auth_message)
                        ssl_sock.send(message_str.encode())
                        
                        data = ssl_sock.recv(1024)
                        if not data:
                            self.logger.error("No se recibieron datos del servidor")
                            time.sleep(2)
                            continue
                        
                        # Procesar respuesta
                        try:
                            response = json.loads(data.decode())
                            self.logger.debug(f"Respuesta recibida: {response}")
                            
                            if response.get("status") == "OK":
                                # Guardar el token recibido
                                self.auth_token = response.get("token")
                                if not self.auth_token:
                                    self.logger.error("No se recibió token de autenticación")
                                    time.sleep(2)
                                    continue
                                    
                                self.is_authenticated = True
                                self.state = "disponible"
                                restored = response.get("restore", False)
                                
                                if restored:
                                    self.logger.info("Reconexión exitosa con nuevo token de seguridad")
                                else:
                                    self.logger.info("Autenticación exitosa, token recibido")
                                return True
                            else:
                                self.logger.error(f"Autenticación rechazada: {response}")
                                time.sleep(2)
                                
                        except json.JSONDecodeError as e:
                            self.logger.error(f"Error decodificando respuesta JSON: {e}")
                            self.logger.debug(f"Datos recibidos: {data}")
                            time.sleep(2)
                            
            except ssl.SSLError as e:
                self.logger.error(f"Error SSL: {e}")
                time.sleep(2)
            except socket.timeout:
                self.logger.error("Timeout en la conexión SSL")
                time.sleep(2)
            except ConnectionRefusedError:
                self.logger.error(f"Conexión rechazada por {self.central_ip}:{self.central_port}")
                time.sleep(2)
            except Exception as e:
                self.logger.error(f"Error en autenticación: {e}")
                time.sleep(2)
                
        return False
            
    def setup_kafka(self):
        """Configurar conexiones Kafka después de autenticación"""
        self.producer = KafkaProducer(
            bootstrap_servers=[self.kafka_broker],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        # Consumidor para órdenes específicas del taxi
        self.consumer = KafkaConsumer(
            f'taxi_orders_{self.taxi_id}',
            bootstrap_servers=[self.kafka_broker],
            group_id=f'taxi_group_{self.taxi_id}',
            auto_offset_reset='earliest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        self.map_consumer = KafkaConsumer(
            'map_state',
            bootstrap_servers=[self.kafka_broker],
            group_id=f'taxi_map_{self.taxi_id}',
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            fetch_min_bytes=1,
            fetch_max_wait_ms=50,  # Reducido para mejor respuesta
            consumer_timeout_ms=50,  # Reducido para mejor respuesta
            max_poll_records=1,
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000,
            enable_auto_commit=True,
            auto_commit_interval_ms=1000
        )
    def setup_ssl(self):
        """Configurar contexto SSL para el cliente"""
        # Obtener el directorio del script actual
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Subir dos niveles para llegar a la raíz del proyecto
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        cert_path = os.path.join(project_root, 'shared', 'security', 'certificates')
        cert_file = os.path.join(cert_path, 'server.crt')
        
        # Verificar que el certificado existe
        if not os.path.exists(cert_file):
            self.logger.error(f"Certificado no encontrado en: {cert_file}")
            raise FileNotFoundError(f"Certificado no encontrado en: {cert_file}")
        
        # Crear contexto SSL para cliente
        context = ssl.create_default_context()
        context.load_verify_locations(cert_file)
        
        return context
    


    def handle_sensors(self):
        """Manejar conexiones de sensores"""
        while True:
            try:
                client_socket, addr = self.sensor_server.accept()
                self.logger.info(f"Sensor conectado desde {addr}")
                
                sensor_thread = threading.Thread(
                    target=self.handle_sensor_messages,
                    args=(client_socket,)
                )
                sensor_thread.daemon = True
                sensor_thread.start()
                
            except Exception as e:
                self.logger.error(f"Error aceptando sensor: {e}")
                time.sleep(5)
                
    def handle_sensor_messages(self, sensor_socket):
        """Manejar mensajes de un sensor específico"""
        while True:
            try:
                data = sensor_socket.recv(1024)
                if not data:
                    break
                    
                sensor_data = json.loads(data.decode())
                new_status = sensor_data.get("status")
                
                if new_status != self.sensor_status:
                    self.sensor_status = new_status
                    self.handle_sensor_status_change()
                    
            except Exception as e:
                self.logger.error(f"Error leyendo sensor: {e}")
                break
                
        sensor_socket.close()
        
    def handle_sensor_status_change(self):
        """Manejar cambios en el estado del sensor"""
        self.logger.info(f"Estado del sensor cambiado a: {self.sensor_status}")
        
        if self.sensor_status == "KO":
            self.esta_parado = True
            self.send_status_update("stopped_by_sensor")
        elif self.sensor_status == "OK" and self.destination:
            self.esta_parado = False
            self.state = "en_movimiento"  # Cambiado de "MOVING"
            self.send_status_update("resumed_by_sensor")
            
    def send_status_update(self, update_type):
        if not self.is_authenticated or not self.auth_token:
            return
            
        message = {
            "type": update_type,
            "taxi_id": self.taxi_id,
            "position": self.position,
            "state": self.state,
            "esta_parado": self.esta_parado,
            "token": self.auth_token  # Añadir token a cada mensaje
        }
        
        self.producer.send('taxi_status', value=message)
        
    @staticmethod
    def calculate_toroidal_distance(coord1, coord2, size):
        """Calcular la distancia más corta entre dos puntos en un espacio toroidal"""
        # Calcular la distancia directa
        direct_distance = coord2 - coord1
        # Calcular la distancia wrapping around
        wrap_distance = coord2 - coord1
        if abs(direct_distance) > size // 2:
            if direct_distance > 0:
                wrap_distance = direct_distance - size
            else:
                wrap_distance = direct_distance + size
        return wrap_distance

    def move_towards_destination(self):
        """Mover el taxi hacia su destino en un mapa toroidal"""
        if not self.destination or self.state != "en_movimiento" or self.sensor_status == "KO":
            return
                
        old_position = self.position.copy()
        MAP_SIZE = 20  # Tamaño del mapa (20x20)
        
        # Calcular el movimiento necesario en cada eje usando el método estático
        dx = self.calculate_toroidal_distance(self.position[0], self.destination[0], MAP_SIZE)
        dy = self.calculate_toroidal_distance(self.position[1], self.destination[1], MAP_SIZE)

        # Realizar el movimiento
        if dx != 0:
            # Mover en X
            step_x = 1 if dx > 0 else -1
            new_x = (self.position[0] + step_x) % MAP_SIZE
            if new_x == 0:
                new_x = MAP_SIZE  # Mantener en rango 1-20
            self.position[0] = new_x

        if dy != 0:
            # Mover en Y
            step_y = 1 if dy > 0 else -1
            new_y = (self.position[1] + step_y) % MAP_SIZE
            if new_y == 0:
                new_y = MAP_SIZE  # Mantener en rango 1-20
            self.position[1] = new_y
                
        # Si la posición cambió
        if old_position != self.position:
            self.send_status_update("moving")
                
        # Verificar si hemos llegado al destino
        if self.position == self.destination:
            # Si tenemos destino final pendiente
            if hasattr(self, 'final_destination') and self.final_destination:
                self.logger.info("Cliente recogido, iniciando viaje al destino final")
                self.destination = self.final_destination
                self.final_destination = None
                self.send_status_update("passenger_picked")
            else:
                # Hemos llegado al destino final
                self.state = "disponible"
                self.esta_parado = True
                self.destination = None
                self.client_id = None
                self.send_status_update("arrived")
    def cleanup(self, is_temporary=False):
        """
        Limpiar recursos del taxi
        is_temporary: True si es una desconexión temporal que permite reconexión
        """
        try:
            self.running = False
            if hasattr(self, 'visualization'):
                self.visualization.running = False
                self.visualization.cleanup()

            if not hasattr(self, '_cleanup_called'):

                disconnect_message = {
                    "type": "disconnect",
                    "taxi_id": self.taxi_id,
                    "position": self.position,
                    "state": "no_disponible",
                    "esta_parado": True,
                    "token": self.auth_token,
                    "is_temporary": is_temporary  # Indicar si es temporal
                }
                
                try:
                    self.producer.send('taxi_status', value=disconnect_message)
                    self.producer.flush(timeout=5)
                    if is_temporary:
                        self.logger.info("Mensaje de desconexión temporal enviado - esperando reconexión")
                    else:
                        self.logger.info("Mensaje de cierre enviado - finalizando taxi")
                except Exception as e:
                    self.logger.error(f"Error enviando mensaje de desconexión: {e}")
                
                if not is_temporary:
                    # Solo cerrar conexiones si es cierre definitivo
                    if hasattr(self, 'producer'):
                        self.producer.close()
                    if hasattr(self, 'consumer'):
                        self.consumer.close()
                    if hasattr(self, 'sensor_server'):
                        self.sensor_server.close()
                pygame.quit()
            
                self._cleanup_called = True
            
                
        except Exception as e:
            self.logger.error(f"Error en cleanup: {e}")  
    def process_command(self, command):
        """
        Procesar comandos recibidos de la central
        Tipos de comandos:
        - pickup: Recoger cliente
        - stop: Parar taxi
        - resume: Reanudar movimiento
        - return_to_base: Volver a la base
        - resume_service: Restaurar servicio después de reconexión
        """
        command_type = command.get("type")
        
        try:
            if command_type == "pickup":
                # Primero vamos a por el cliente
                pickup_location = command.get("pickup_location")
                final_destination = command.get("destination")
                self.client_id = command.get("client_id")
                
                # Guardamos el destino final para usarlo después
                self.final_destination = final_destination
                # Primero vamos a por el cliente
                self.destination = pickup_location
                
                if self.sensor_status == "OK":
                    self.state = "en_movimiento"
                    self.esta_parado = False
                    self.logger.info(f"Iniciando recogida del cliente en {pickup_location}")

            elif command_type == "resume_service":
                # Restaurar estado del servicio
                self.client_id = command.get("client_id")
                self.position = command.get("current_position")
                
                # Usar el destino correcto
                if command.get("is_pickup_phase"):
                    self.destination = command.get("client_position")
                    self.final_destination = command.get("final_destination")
                else:
                    self.destination = command.get("destination")
                
                self.state = "en_movimiento"
                self.esta_parado = False
                self.logger.info(f"Reanudando servicio desde posición {self.position} hacia {self.destination}")
                
                # Notificar estado actual
                self.send_status_update("service_resumed")

            elif command_type == "stop":
                self.esta_parado = True
                self.logger.info("Taxi parado por comando de la central")

            elif command_type == "resume":
                if self.sensor_status == "OK" and self.destination:
                    self.esta_parado = False
                    self.state = "en_movimiento"
                    self.logger.info("Reanudando movimiento")

            elif command_type == "return_to_base":
                self.destination = [1, 1]
                if self.sensor_status == "OK":
                    self.state = "en_movimiento"
                    self.esta_parado = False
                    self.logger.info("Volviendo a la base")
            # En EC_DE.py, dentro del método process_command
            elif command_type == "go_to":
                # Similar a return_to_base pero con destino específico
                new_destination = command.get("destination")
                if new_destination:
                    self.destination = new_destination
                    if self.sensor_status == "OK":
                        self.state = "en_movimiento"
                        self.esta_parado = False
                        self.logger.info(f"Cambiando destino a: {new_destination}")
                        # Notificar el cambio de estado a la central
                        self.send_status_update("command_processed")
            
        except Exception as e:
            self.logger.error(f"Error procesando comando {command_type}: {e}")
    def run_visualization(self):
        """Thread dedicado a la visualización"""
        try:
            while self.running and self.visualization.running:
                try:
                    # Procesar mensajes de Kafka
                    messages = self.map_consumer.poll(timeout_ms=50)
                    if messages:
                        for tp, msgs in messages.items():
                            for msg in msgs:
                                if msg.value:
                                    self.visualization.update(msg.value)

                    # Actualizar visualización si pygame sigue activo
                    if pygame.get_init():
                        self.visualization.draw()
                    else:
                        break
                    
                    # Pequeña pausa para no saturar CPU
                    time.sleep(0.01)

                except Exception as e:
                    self.logger.error(f"Error en visualización: {e}")
                    time.sleep(0.1)

        except Exception as e:
            self.logger.error(f"Error fatal en visualización: {e}")
        finally:
            if hasattr(self, 'visualization'):
                self.visualization.cleanup()

    def run(self):
        try:
            # Registrarse primero
            if not self.register_with_registry():
                self.logger.error("No se pudo registrar con Registry")
                return
                
            # Luego autenticarse
            if not self.authenticate_with_central():
                return
                
            # Configurar Kafka
            self.setup_kafka()
            
            self.start_visualization()
            # Iniciar thread de sensores
            sensor_thread = threading.Thread(target=self.handle_sensors)
            sensor_thread.daemon = True
            sensor_thread.start()
            
            # Iniciar thread de Kafka
            self.kafka_thread = threading.Thread(target=self.consume_map_data)
            self.kafka_thread.daemon = True
            self.kafka_thread.start()
            # Bucle principal
            movement_delay = 1.0
            last_movement = time.time()
            
            while self.running:
                # Procesar eventos Pygame y actualizar visualización
                if not self.map_queue.empty():
                    try:
                        new_state = self.map_queue.get_nowait()
                        self.visualization.update(new_state)
                    except queue.Empty:
                        pass
                
                self.visualization.draw()


                messages = self.consumer.poll(timeout_ms=100)
                for tp, msgs in messages.items():
                    for msg in msgs:
                        self.process_command(msg.value)
                
                current_time = time.time()
                if current_time - last_movement >= movement_delay:
                    if self.state == "en_movimiento" and not self.esta_parado:
                        self.move_towards_destination()
                    last_movement = current_time
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            self.logger.info("Cerrando taxi...")
            self.cleanup(is_temporary=False)
        except Exception as e:
            self.logger.error(f"Error en bucle principal: {e}")
            self.cleanup(is_temporary=True)

def main():
    if len(sys.argv) != 6:
        print("Usage: python EC_DE.py <central_ip> <central_port> <kafka_broker> <sensor_port> <taxi_id>")
        sys.exit(1)
        
    central_ip = sys.argv[1]
    central_port = int(sys.argv[2])
    kafka_broker = sys.argv[3]
    sensor_port = int(sys.argv[4])
    taxi_id = int(sys.argv[5])
    
    taxi = DigitalEngine(central_ip, central_port, kafka_broker, sensor_port, taxi_id)
    taxi.run()

if __name__ == "__main__":
    main()