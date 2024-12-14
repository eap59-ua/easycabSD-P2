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
        """Obtener un taxi disponible para servicio"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                # Primero obtener un taxi usando FOR UPDATE para bloquear la fila
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
                    # Actualizar estado del taxi seleccionado
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