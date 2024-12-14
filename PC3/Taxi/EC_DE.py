# EC_DE.py (Digital Engine)
import sys
import socket
import json
import threading
import logging
from kafka import KafkaConsumer, KafkaProducer
import time

class DigitalEngine:
    def __init__(self, central_ip, central_port, kafka_broker, sensor_port, taxi_id):
        # Configurar logging
        self.logger = logging.getLogger(f'taxi_{taxi_id}')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # Atributos del taxi
        self.taxi_id = taxi_id
        self.position = [1, 1]  # Posición inicial
        self.state = "no_disponible"  # Inicialmente no disponible hasta autenticación
        self.esta_parado = True  # Inicialmente parado
        self.destination = None
        self.is_authenticated = False
        self.sensor_status = "OK"
        
        # Datos de conexión
        self.central_ip = central_ip
        self.central_port = central_port
        self.kafka_broker = kafka_broker
        self.sensor_port = sensor_port
        # Inicializar servidor de sensores
        self.setup_sensor_server()  # <-- Añadir esta línea
        # Nuevos atributos para manejar el servicio
        self.client_id = None
        self.final_destination = None
        self.auth_token = None  # Para almacenar el token
        



        
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
                # Crear contexto SSL
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.load_verify_locations("shared/security/certificates/server.crt")
                # Crear socket base
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(5.0)
                    self.logger.info(f"Intentando conectar a {self.central_ip}:{self.central_port}")
                    
                    # Envolver el socket con SSL
                    with context.wrap_socket(sock, server_hostname=self.central_ip) as ssl_sock:
                        # Conectar con el socket seguro
                        ssl_sock.connect((self.central_ip, self.central_port))
                        self.logger.info("Conexión SSL establecida")
                        
                        # Preparar mensaje de autenticación
                        auth_message = {
                            "type": "auth",
                            "taxi_id": self.taxi_id,
                            "position": self.position,
                            "credentials": {
                                "cert_id": "taxi_cert_1",  # Identificador del certificado
                                "timestamp": int(time.time())
                            }
                        }
                        
                        # Enviar mensaje cifrado
                        message_str = json.dumps(auth_message)
                        ssl_sock.send(message_str.encode())
                        
                        # Recibir respuesta cifrada
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
        
        self.consumer = KafkaConsumer(
            f'taxi_orders_{self.taxi_id}',
            bootstrap_servers=[self.kafka_broker],
            group_id=f'taxi_group_{self.taxi_id}',
            auto_offset_reset='earliest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
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
                self.position = command.get("current_position")  # Última posición conocida
                self.destination = command.get("destination")  # Destino real del cliente
                
                if command.get("client_picked_up"):
                    self.state = "en_movimiento"
                    self.esta_parado = False
                    self.logger.info(f"Reanudando servicio con cliente {self.client_id} hacia destino {self.destination}")
                else:
                    self.state = "en_movimiento"
                    self.esta_parado = False
                    self.logger.info(f"Reanudando viaje para recoger al cliente {self.client_id}")
                
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
            
    def run(self):
        """Método principal del taxi"""
        if not self.authenticate_with_central():
            return
            
        self.setup_kafka()
        
        # Iniciar thread para sensores
        sensor_thread = threading.Thread(target=self.handle_sensors)
        sensor_thread.daemon = True
        sensor_thread.start()
        
        # Bucle principal
        movement_delay = 1.0  # 1 segundo entre movimientos
        last_movement = time.time()
        
        try:
            while True:
                # Procesar mensajes de Kafka
                messages = self.consumer.poll(timeout_ms=100)
                for tp, msgs in messages.items():
                    for msg in msgs:
                        self.process_command(msg.value)
                
                # Mover si es tiempo
                current_time = time.time()
                if current_time - last_movement >= movement_delay:
                    if self.state == "en_movimiento" and not self.esta_parado:
                        self.move_towards_destination()
                    last_movement = current_time
                
                time.sleep(0.1)  # Evitar consumo excesivo de CPU
                
        except KeyboardInterrupt:
            self.logger.info("Cerrando taxi...")
            # Enviar última actualización de estado antes de cerrar
            message = {
                "type": "disconnect",
                "taxi_id": self.taxi_id,
                "position": self.position,
                "state": "no_disponible",
                "esta_parado": True
            }
            try:
                self.producer.send('taxi_status', value=message)
                self.producer.flush()  # Asegurarnos de que se envía
            except:
                pass  # Si falla el envío, la central lo detectará por timeout
            sys.exit(0)
        except Exception as e:
            self.logger.error(f"Error en bucle principal: {e}")

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