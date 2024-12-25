import sys
import socket
import json
import time
import logging
import threading

class Sensors:
    def __init__(self, de_ip, de_port):
        # Configurar logging
        self.logger = logging.getLogger('sensors')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        self.de_ip = de_ip
        self.de_port = de_port
        self.status = "OK"
        self.socket = None
        self.connected = False
        self.running = True
        
    def connect_to_de(self):
        """Conectar al Digital Engine"""
        while not self.connected and self.running:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.de_ip, self.de_port))
                self.connected = True
                self.logger.info(f"Conectado al Digital Engine en {self.de_ip}:{self.de_port}")
            except Exception as e:
                self.logger.error(f"Error conectando al DE: {e}")
                time.sleep(5)  # Esperar antes de reintentar
                
    def send_status(self):
        """Enviar estado actual al Digital Engine"""
        while self.running:
            if self.connected:
                try:
                    message = json.dumps({
                        "type": "sensor_status",
                        "status": self.status,
                        "timestamp": time.time()
                    })
                    self.socket.sendall(message.encode())
                    self.logger.debug(f"Estado enviado: {self.status}")
                except Exception as e:
                    self.logger.error(f"Error enviando estado: {e}")
                    self.connected = False
                    self.connect_to_de()
            time.sleep(1)
            
    def send_final_status(self):
        """Enviar el estado final antes de cerrar la conexión"""
        if self.connected:
            try:
                message = json.dumps({
                    "type": "sensor_status",
                    "status": self.status,
                    "timestamp": time.time()
                })
                self.socket.sendall(message.encode())
                self.logger.info(f"Estado final enviado: {self.status}")
            except Exception as e:
                self.logger.error(f"Error enviando estado final: {e}")

    def handle_user_input(self):
        """Manejar entrada del usuario para cambiar estado"""
        while self.running:
            command = input("Presiona ENTER para cambiar el estado del sensor (o 'q' para salir): ")
            if command.lower() == 'q':
                self.status = "KO"
                self.send_final_status()
                self.running = False
                break
            self.status = "KO" if self.status == "OK" else "OK"
            self.logger.info(f"Estado cambiado a: {self.status}")
        
    def run(self):
        """Método principal de los sensores"""
        self.connect_to_de()
        
        # Iniciar thread para enviar estados
        send_thread = threading.Thread(target=self.send_status)
        send_thread.daemon = True
        send_thread.start()
        
        # Manejar entrada del usuario en el thread principal
        try:
            self.handle_user_input()
        except KeyboardInterrupt:
            self.logger.info("Cerrando sensores...")
        finally:
            self.running = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket.close()

def main():
    if len(sys.argv) != 3:
        print("Usage: python EC_S.py <de_ip> <de_port>")
        sys.exit(1)
        
    de_ip = sys.argv[1]
    de_port = int(sys.argv[2])
    
    sensors = Sensors(de_ip, de_port)
    sensors.run()

if __name__ == "__main__":
    main()