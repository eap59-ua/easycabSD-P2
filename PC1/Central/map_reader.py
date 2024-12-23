import psycopg2
from psycopg2.extras import DictCursor
import json
import logging

def get_db_params():
    return {
        'dbname': 'central_db',
        'user': 'postgres',
        'password': 'postgres',
        'host': 'localhost',
        'port': '5432'
    }

class DatabaseManager:
    def __init__(self, db_params):
        self.db_params = db_params
        # Configurar logging
        self.logger = logging.getLogger('database')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
    def get_connection(self):
        return psycopg2.connect(**self.db_params)
    
    # En DatabaseManager (map_reader.py)
    def verify_taxi_cert_token(self, taxi_id, cert_token):
        """Verificar token de certificación del taxi"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT token, expired 
                        FROM taxi_tokens 
                        WHERE taxi_id = %s 
                        AND token = %s
                    """, (taxi_id, cert_token))
                    
                    result = cursor.fetchone()
                    if result and not result['expired']:
                        # Actualizar último uso
                        cursor.execute("""
                            UPDATE taxi_tokens 
                            SET last_used = NOW() 
                            WHERE taxi_id = %s
                        """, (taxi_id,))
                        conn.commit()
                        return True
                    return False
        except Exception as e:
            self.logger.error(f"Error verificando cert_token: {e}")
            return False
    # verificar el token de auth_service.py 
    def verify_token(self, taxi_id, token):
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT token FROM taxi_tokens 
                    WHERE taxi_id = %s AND token = %s
                    AND NOT expired
                """, (taxi_id, token))
                return cursor.fetchone() is not None
    def log_audit_event(self, source, source_id, ip_address, event_type, action, details):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO audit_log 
                        (source, source_id, ip_address, event_type, action, details)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (source, source_id, ip_address, event_type, action, details))
                    conn.commit()
                    self.logger.debug(f"Evento de auditoría registrado: {action}")
        except Exception as e:
            self.logger.error(f"Error registrando evento de auditoría: {e}")
    def invalidate_taxi_token(self, taxi_id):
        """Invalidar token cuando el taxi vuelve a base"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Marcar token como expirado
                cursor.execute("""
                    UPDATE taxis 
                    SET token = NULL, 
                        estado = 'no_disponible'
                    WHERE id = %s
                """, (taxi_id,))
                conn.commit()


    def get_taxi_by_client(self, client_id):
        """Obtener información del taxi que tiene asignado un cliente específico"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT id, estado, esta_parado, coord_x, coord_y, 
                        dest_x, dest_y, cliente_asignado
                    FROM taxis
                    WHERE cliente_asignado = %s;
                """, (client_id,))
                return dict(cursor.fetchone()) if cursor.rowcount > 0 else None

    def actualizar_posicion_taxi(self, taxi_id, x, y, estado=None, esta_parado=None, clear_client=False): 
        """
        Actualizar posición y estado de un taxi
        
        Args:
            taxi_id (int): ID del taxi
            x (int): Coordenada X
            y (int): Coordenada Y
            estado (str, optional): Estado del taxi ('no_disponible', 'disponible', 'en_movimiento')
            esta_parado (bool, optional): Si el taxi está parado o no
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Construir la consulta SQL dinámicamente
                    query = "UPDATE taxis SET coord_x = %s, coord_y = %s"
                    params = [x, y]
                    
                    if estado is not None:
                        query += ", estado = %s"
                        params.append(estado)
                        
                    if esta_parado is not None:
                        query += ", esta_parado = %s"
                        params.append(esta_parado)
                    if clear_client:
                        query += ", cliente_asignado = NULL, dest_x = NULL, dest_y = NULL"
                    
                        
                    query += " WHERE id = %s"
                    params.append(taxi_id)
                    
                    cursor.execute(query, params)
                    conn.commit()
        except Exception as e:
            self.logger.error(f"Error actualizando posición del taxi {taxi_id}: {e}")
            raise
    def assign_taxi_service(self, taxi_id, dest_x, dest_y, client_id):
        """Actualizar destino y cliente asignado de un taxi"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE taxis 
                        SET estado = 'en_movimiento',
                            esta_parado = false,
                            dest_x = %s,
                            dest_y = %s,
                            cliente_asignado = %s
                        WHERE id = %s;
                    """, (dest_x, dest_y, client_id, taxi_id))
                    conn.commit()
        except Exception as e:
            self.logger.error(f"Error asignando servicio al taxi {taxi_id}: {e}")
            raise

    def obtener_taxis(self):
        """Obtener todos los taxis con sus estados"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT id, estado, esta_parado, coord_x, coord_y, 
                        dest_x, dest_y, cliente_asignado
                    FROM taxis
                """)
                taxis = cursor.fetchall()
                self.logger.debug(f"Estados de taxis: {[{'id': t['id'], 'estado': t['estado']} for t in taxis]}")
                return taxis

    def obtener_locations(self):
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("SELECT id, coord_x, coord_y FROM locations;")
                return cursor.fetchall()
    
    def get_available_taxi(self):
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT id, estado, esta_parado, coord_x, coord_y, 
                        dest_x, dest_y, cliente_asignado
                    FROM taxis 
                    WHERE estado = 'disponible' 
                    AND esta_parado = true
                    AND cliente_asignado IS NULL
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1;
                """)
                taxi = cursor.fetchone()
                
                if taxi:
                    # Importante: Verificar nuevamente que sigue disponible
                    cursor.execute("""
                        SELECT id FROM taxis 
                        WHERE id = %s 
                        AND estado = 'disponible'
                        AND cliente_asignado IS NULL
                    """, (taxi['id'],))
                    
                    if cursor.fetchone():
                        cursor.execute("""
                            UPDATE taxis 
                            SET estado = 'en_movimiento',
                                esta_parado = false
                            WHERE id = %s;
                        """, (taxi['id'],))
                        conn.commit()
                        return dict(taxi)
                return None
        
    def verificar_taxi(self, taxi_id):
        """Verificar si un taxi puede autenticarse"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT id, estado
                    FROM taxis 
                    WHERE id = %s;
                """, (taxi_id,))
                taxi = cursor.fetchone()
                
                if taxi is None:
                    return False  # El taxi no existe
                
                # Actualizar a no_disponible si no lo está ya
                if taxi['estado'] != 'no_disponible':
                    cursor.execute("""
                        UPDATE taxis
                        SET estado = 'no_disponible',
                            esta_parado = true
                        WHERE id = %s
                    """, (taxi_id,))
                    conn.commit()
                
                return True

    def actualizar_taxi_autenticado(self, taxi_id, x, y):
        """Actualizar estado y posición del taxi cuando se autentica"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE taxis 
                    SET estado = 'disponible',
                        esta_parado = true,
                        coord_x = %s,
                        coord_y = %s
                    WHERE id = %s;
                """, (x, y, taxi_id))
                conn.commit()
    # En DatabaseManager, añadir método
    def update_taxi_disconnected(self, taxi_id):
        """Marcar taxi como desconectado"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE taxis 
                        SET estado = 'no_disponible',
                            esta_parado = true,
                            coord_x = 1,
                            coord_y = 1,
                            dest_x = null,
                            dest_y = null,
                            cliente_asignado = null
                        WHERE id = %s;
                    """, (taxi_id,))
                    conn.commit()
            self.logger.info(f"Taxi {taxi_id} actualizado a no_disponible en BD")
        except Exception as e:
            self.logger.error(f"Error actualizando estado del taxi {taxi_id} a desconectado: {e}")
            raise
    def get_taxi_info(self, taxi_id):
        """Obtener información completa de un taxi"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT id, estado, esta_parado, coord_x, coord_y, 
                        dest_x, dest_y, cliente_asignado
                    FROM taxis
                    WHERE id = %s
                """, (taxi_id,))
                return dict(cursor.fetchone())
    def update_taxi_status(self, taxi_id, estado, esta_parado):
        """Actualizar estado del taxi"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE taxis 
                        SET estado = %s,
                            esta_parado = %s
                        WHERE id = %s;
                    """, (estado, esta_parado, taxi_id))
                    conn.commit()
            self.logger.info(f"Estado del taxi {taxi_id} actualizado a {estado}")
        except Exception as e:
            self.logger.error(f"Error actualizando estado del taxi {taxi_id}: {e}")
            raise
    def restore_taxi_state(self, taxi_id, position, client_id, estado, destino=None):
        """Restaurar el estado anterior de un taxi"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = """
                        UPDATE taxis 
                        SET estado = %s,
                            coord_x = %s,
                            coord_y = %s,
                            cliente_asignado = %s
                    """
                    params = [estado, position[0], position[1], client_id]
                    
                    if destino:
                        query += ", dest_x = %s, dest_y = %s"
                        params.extend([destino[0], destino[1]])
                        
                    query += " WHERE id = %s"
                    params.append(taxi_id)
                    
                    cursor.execute(query, params)
                    conn.commit()
                    self.logger.info(f"Estado del taxi {taxi_id} restaurado correctamente")
        except Exception as e:
            self.logger.error(f"Error restaurando estado del taxi {taxi_id}: {e}")
            raise

    def register_taxi(self, taxi_id, cert_token, ip_address):
        """Registrar un nuevo taxi"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Verificar si el taxi ya existe
                    cursor.execute("""
                        SELECT id FROM taxis WHERE id = %s
                    """, (taxi_id,))
                    
                    if cursor.fetchone() is None:
                        # Crear nuevo taxi
                        cursor.execute("""
                            INSERT INTO taxis (id, estado, esta_parado, coord_x, coord_y)
                            VALUES (%s, 'no_disponible', true, 1, 1)
                        """, (taxi_id,))
                    
                    # Registrar el token
                    cursor.execute("""
                        INSERT INTO taxi_tokens (taxi_id, token, ip_address)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (taxi_id) 
                        DO UPDATE SET token = EXCLUDED.token,
                                    ip_address = EXCLUDED.ip_address,
                                    last_used = NOW(),
                                    expired = false
                    """, (taxi_id, cert_token, ip_address))
                    
                    conn.commit()
                    return True
        except Exception as e:
            self.logger.error(f"Error en register_taxi: {e}")
            return False

    def unregister_taxi(self, taxi_id):
        """Dar de baja un taxi"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Actualizar estado del taxi
                    cursor.execute("""
                        UPDATE taxis 
                        SET estado = 'no_disponible',
                            esta_parado = true
                        WHERE id = %s
                    """, (taxi_id,))
                    
                    # Invalidar tokens
                    cursor.execute("""
                        UPDATE taxi_tokens 
                        SET expired = true 
                        WHERE taxi_id = %s
                    """, (taxi_id,))
                    
                    conn.commit()
                    return True
        except Exception as e:
            self.logger.error(f"Error en unregister_taxi: {e}")
            return False


    #Métodos para gestionar los clientes en la base de datos
    def insertar_cliente(self, client_id, coord_x, coord_y, destination_id=None):
        """
        Inserta un nuevo cliente en la BD con estado 'waiting' por defecto.
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO clients (id, status, coord_x, coord_y, destination_id)
                        VALUES (%s, 'waiting', %s, %s, %s)
                    """, (client_id, coord_x, coord_y, destination_id))
                    conn.commit()
            self.logger.info(f"Cliente {client_id} insertado con estado 'waiting' en la BD.")
        except Exception as e:
            self.logger.error(f"Error insertando cliente {client_id}: {e}")
            raise

    def obtener_clientes(self):
        """
        Obtiene todos los clientes y sus datos.
        Devuelve una lista de diccionarios: [{id, status, coord_x, coord_y, destination_id}, ...]
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT id, status, coord_x, coord_y, destination_id FROM clients;")
                    clientes = cursor.fetchall()
                    return clientes
        except Exception as e:
            self.logger.error(f"Error obteniendo clientes: {e}")
            raise

    def actualizar_estado_cliente(self, client_id, status, coord_x=None, coord_y=None, destination_id=None):
        """
        Actualiza el estado, posición  y destino de un cliente.
        No se requiere siempre coord_x y coord_y: si no se pasan, el cliente mantiene las actuales.
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = "UPDATE clients SET status = %s"
                    params = [status]

                    if coord_x is not None and coord_y is not None:
                        query += ", coord_x = %s, coord_y = %s"
                        params.extend([coord_x, coord_y])

                    if destination_id is not None:
                        query += ", destination_id = %s"
                        params.append(destination_id)

                    query += " WHERE id = %s"
                    params.append(client_id)

                    cursor.execute(query, params)
                    conn.commit()
            self.logger.info(f"Estado del cliente {client_id} actualizado a {status} con destino {destination_id}")
        except Exception as e:
            self.logger.error(f"Error actualizando estado del cliente {client_id}: {e}")
            raise

    def borrar_cliente(self, client_id):
        """
        Borra un cliente de la BD, por ejemplo cuando finaliza su viaje definitivamente
        y no es necesario mantenerlo.
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM clients WHERE id = %s", (client_id,))
                    conn.commit()
            self.logger.info(f"Cliente {client_id} eliminado de la BD.")
        except Exception as e:
            self.logger.error(f"Error eliminando cliente {client_id}: {e}")
            raise


    #Métodos para gestionar el tráfico de CTC en la base de datos
    def update_ctc_status(self, city, temp, traffic_ok):
        """
        Actualiza o inserta (en caso de no existir) el estado del CTC en la tabla ctc_status con id=1.
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Usamos un "upsert" de Postgres (ON CONFLICT)
                    cursor.execute("""
                        INSERT INTO ctc_status (id, current_city, current_temp, traffic_ok)
                        VALUES (1, %s, %s, %s)
                        ON CONFLICT (id) 
                        DO UPDATE SET current_city = EXCLUDED.current_city,
                                    current_temp = EXCLUDED.current_temp,
                                    traffic_ok = EXCLUDED.traffic_ok
                    """, (city, temp, traffic_ok))
                    conn.commit()
            self.logger.info(f"CTC status actualizado: city={city}, temp={temp}, traffic_ok={traffic_ok}")
        except Exception as e:
            self.logger.error(f"Error en update_ctc_status: {e}")
            raise

    def get_ctc_status(self):
        """
        Devuelve un dict con { "city": str, "temp": float, "traffic_ok": bool }
        desde la tabla ctc_status (id=1).
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("""
                        SELECT current_city, current_temp, traffic_ok 
                        FROM ctc_status 
                        WHERE id = 1
                    """)
                    row = cursor.fetchone()
                    if row:
                        return {
                            "city": row["current_city"],
                            "temp": row["current_temp"],
                            "traffic_ok": row["traffic_ok"]
                        }
                    else:
                        # Si no hay fila con id=1
                        return {
                            "city": None,
                            "temp": None,
                            "traffic_ok": False
                        }
        except Exception as e:
            self.logger.error(f"Error en get_ctc_status: {e}")
            raise
