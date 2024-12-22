import sys
import json
from json.decoder import JSONDecodeError
from kafka import KafkaProducer, KafkaConsumer
import time
import logging
from enum import Enum

class CustomerState(Enum):
    WAITING_CONNECTION = 1
    CONNECTED_WAITING_SERVICE = 2
    SERVICE_ASSIGNED_WAITING_PICKUP = 3
    TRAVELING = 4

class ECCustomer:
    def __init__(self, broker_address, client_id):
        # Configurar logging
        self.logger = logging.getLogger(f'customer_{client_id}')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        self.broker_address = broker_address
        self.client_id = client_id
        self.state = CustomerState.WAITING_CONNECTION
        self.current_position = None
        self.assigned_taxi = None
        self.current_destination_id = None
        self.last_processed_message_time=0
        self.waiting_for_next_request=False
        
        # Productor Kafka
        self.producer = KafkaProducer(
            bootstrap_servers=[broker_address],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        # Consumidor Kafka
        self.consumer = KafkaConsumer(
            'customer_responses',
            bootstrap_servers=[broker_address],
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id=f'customer_group_{client_id}',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            consumer_timeout_ms=1000
        )
        
        self.locations = self.load_locations()
        self.requests = self.load_requests()
        self.logger.info(f"Cliente {client_id} inicializado. Conectado a broker: {broker_address}")
        self.get_current_position()
        self.state = CustomerState.CONNECTED_WAITING_SERVICE
        
    def get_current_position(self):
        if self.current_position is None:
            print("Hola cliente, ¿cuál es su punto de recogida?")
            while True:
                try:
                    x = int(input("Enter your current X coordinate (1-20): "))
                    y = int(input("Enter your current Y coordinate (1-20): "))
                    if 1 <= x <= 20 and 1 <= y <= 20:
                        self.current_position = [x, y]
                        return self.current_position
                    else:
                        print("Las coordenadas deben estar entre 1 y 20. Inténtalo de nuevo.")
                except ValueError:
                    print("Por favor, ingrese números enteros válidos.")
        return self.current_position

    def load_locations(self):
        try:
            with open('EC_locations.json', 'r') as file:
                data = json.load(file)
            return {loc['Id']: tuple(map(int, loc['POS'].split(','))) for loc in data['locations']}
        except FileNotFoundError:
            self.logger.error("Error: El archivo 'EC_locations.json' no se encontró.")
            return {}
        except JSONDecodeError:
            self.logger.error("Error: El archivo 'EC_locations.json' no contiene JSON válido.")
            return {}
        except KeyError:
            self.logger.error("Error: El archivo 'EC_locations.json' no tiene el formato esperado.")
            return {}

    def load_requests(self):
        requests_filename = f"EC_Requests_{self.client_id}.json"
        
        try:
            with open(requests_filename, 'r') as file:
                data = json.load(file)
            return [req['Id'] for req in data['Requests']]
        except FileNotFoundError:
            self.logger.error("Error: El archivo '{requests_filename}' no se encontró.")
            return []
        except JSONDecodeError:
            self.logger.error("Error: El archivo '{requests_filename}' no contiene JSON válido.")
            return []
        except KeyError:
            self.logger.error("Error: El archivo '{requests_filename}' no tiene el formato esperado.")
            return []

    def request_ride(self, destination_id):
        if self.state != CustomerState.CONNECTED_WAITING_SERVICE:
            self.logger.debug(f"No se puede solicitar servicio en estado: {self.state}")
            return True  # Retornamos True para no interrumpir el bucle principal
            
        if destination_id not in self.locations:
            self.logger.error(f"Destino inválido: {destination_id}")
            return False

        message = {
            'type': 'ride_request',
            'client_id': self.client_id,
            'current_position': self.current_position,
            'destination_id': destination_id,
            'timestamp': time.time()
        }
        
        try:
            self.producer.send('ride_requests', value=message)
            self.current_destination_id = destination_id
            self.waiting_for_next_request = False
            self.logger.info(f"Solicitud de viaje enviada - Destino: {destination_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error al enviar solicitud: {e}")
            return False

    def process_response(self, response):
        """Procesar respuesta recibida de la central"""
        if response.get('client_id') != self.client_id:
            return False
            
        # Evitar procesar mensajes duplicados o muy cercanos en el tiempo
        current_time = time.time()
        if current_time - self.last_processed_message_time < 0.1:
            return True
            
        response_type = response.get('type')
        self.logger.debug(f"Procesando respuesta tipo: {response_type} en estado: {self.state}")
        
        if response_type == 'ride_confirmation':
            if self.state == CustomerState.CONNECTED_WAITING_SERVICE:
                new_taxi_id = response.get('taxi_id')
                if new_taxi_id is not None:
                    self.assigned_taxi = new_taxi_id
                    self.state = CustomerState.SERVICE_ASSIGNED_WAITING_PICKUP
                    self.logger.info(f"Viaje confirmado. Taxi {self.assigned_taxi} en camino.")
                    self.last_processed_message_time = current_time
            return True
            
        elif response_type == 'ride_completed':
            if self.state in [CustomerState.TRAVELING, CustomerState.SERVICE_ASSIGNED_WAITING_PICKUP]:
                if 'final_position' in response:
                    self.current_position = response['final_position']
                    self.logger.info(f"Viaje completado. Nueva posición: {self.current_position}")
                self.state = CustomerState.CONNECTED_WAITING_SERVICE
                self.assigned_taxi = None
                self.current_destination_id = None
                self.last_processed_message_time = current_time
                self.waiting_for_next_request = True
                return 'completed'
            return True
            
        elif response_type == 'ride_rejected':
            if self.state == CustomerState.CONNECTED_WAITING_SERVICE:
                self.logger.warning("No hay taxis disponibles.")
                self.last_processed_message_time = current_time
                self.waiting_for_next_request = False  # Importante: resetear este flag
                return 'rejected'
            return True
            
        elif response_type == 'passenger_picked_up':
            if self.state == CustomerState.SERVICE_ASSIGNED_WAITING_PICKUP:
                self.state = CustomerState.TRAVELING
                self.logger.info("El taxi ha recogido al cliente. Iniciando viaje.")
                self.last_processed_message_time = current_time
            return True
            
        elif response_type == 'service_terminated':
            if self.state in [CustomerState.TRAVELING, CustomerState.SERVICE_ASSIGNED_WAITING_PICKUP]:
                if 'final_position' in response:
                    self.current_position = response.get('final_position')
                    self.logger.info(f"Servicio interrumpido: {response.get('message', 'Sin detalles')}")
                    self.logger.info(f"Posición final: {self.current_position}")
                
                self.state = CustomerState.CONNECTED_WAITING_SERVICE
                self.assigned_taxi = None
                self.current_destination_id = None
                self.last_processed_message_time = current_time
                self.waiting_for_next_request = True
                
                if response.get('reason') == 'taxi_disconnected':
                    self.logger.warning("El taxi se ha desconectado permanentemente")
                return 'terminated'
            return True
        
        return True

    def listen_for_responses(self):
        """Escuchar respuestas de la central"""
        try:
            messages = self.consumer.poll(timeout_ms=1000)
            for tp, msgs in messages.items():
                sorted_msgs = sorted(msgs, 
                                   key=lambda m: m.value.get('timestamp', 0) 
                                   if isinstance(m.value, dict) else 0)
                for msg in sorted_msgs:
                    result = self.process_response(msg.value)
                    if result == 'completed' or result == 'rejected':
                        return result
            return True
        except Exception as e:
            self.logger.error(f"Error al procesar respuestas: {e}")
            return False
    def cleanup(self):
        """Limpiar recursos del cliente"""
        try:
            if not hasattr(self, '_cleanup_called'):
                # Enviar mensaje de despedida una sola vez
                try:
                    farewell_message = {
                        'type': 'customer_finished',
                        'client_id': self.client_id,
                        'timestamp': time.time()
                    }
                    self.producer.send('ride_requests', value=farewell_message)
                    self.producer.flush(timeout=5)  # Esperar máximo 5 segundos
                    self.logger.info("Cliente terminando, mensaje de despedida enviado")
                except Exception as e:
                    self.logger.error(f"Error enviando mensaje de despedida: {e}")
                
                self._cleanup_called = True
        except Exception as e:
            self.logger.error(f"Error en cleanup: {e}")
def main():
    if len(sys.argv) != 3:
        print("Usage: python EC_Customer.py <broker_address:port> <client_id>")
        sys.exit(1)

    broker_address = sys.argv[1]
    client_id = sys.argv[2].lower()

    if len(client_id) != 1 or not client_id.isalpha():
        print("Error: El ID del cliente debe ser una letra")
        sys.exit(1)
    customer = None
    try:
        customer = ECCustomer(broker_address, client_id)
        # Registrar manejador de señales
        def signal_handler(signum, frame):
            if customer:
                customer.cleanup()
            sys.exit(0)
        
        # Registrar para SIGINT (Ctrl+C) y SIGTERM
        import signal
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        current_request_index = 0

        while current_request_index < len(customer.requests):
            destination_id = customer.requests[current_request_index]
            
            # Si estamos esperando servicio y no estamos esperando el siguiente request
            if (customer.state == CustomerState.CONNECTED_WAITING_SERVICE and 
                not customer.waiting_for_next_request):
                if not customer.request_ride(destination_id):
                    time.sleep(4)
                    continue

            # Escuchar respuestas continuamente
            response = customer.listen_for_responses()
            
            if response == 'completed':
                current_request_index += 1
                if current_request_index < len(customer.requests):
                    customer.logger.info("Esperando 4 segundos antes del siguiente servicio...")
                    time.sleep(4)
                    customer.waiting_for_next_request = False
                continue
            elif response == 'rejected':
                customer.logger.info("Esperando 4 segundos antes de reintentar...")
                time.sleep(4)
                customer.waiting_for_next_request = False  # Asegurarnos de resetear el flag
                continue
                    # Enviar mensaje de finalización
            
            time.sleep(0.1)  # Pequeña pausa para no saturar el CPU
        #fuera del bucle enviamos un adios a la central
        farewell_message = {
                'type': 'customer_finished',
                'client_id': client_id,
                'timestamp': time.time()
            }
        customer.producer.send('ride_requests', value=farewell_message)
        customer.producer.flush()
        customer.logger.info("Todos los servicios completados. Cliente terminando...")
        time.sleep(1) 
    except KeyboardInterrupt:
        print("\nCliente terminado por el usuario")
        if customer:
            customer.cleanup()
    except Exception as e:
        print(f"Error: {e}")
        if customer:
            customer.cleanup()
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main()