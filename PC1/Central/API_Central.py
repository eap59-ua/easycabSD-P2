from flask import Flask, jsonify
from map_reader import DatabaseManager, get_db_params
import logging
from flask_cors import CORS


app = Flask(__name__)
CORS(app)
# Inicializar conexión a BD
db_params = get_db_params()
db = DatabaseManager(db_params)

# Configurar logging
logger = logging.getLogger('api_central')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

@app.route("/state", methods=["GET"])
def get_state():
    """
    Devuelve el estado actual del sistema:
    - Lista de taxis con su posición, estado y cliente asignado
    - Lista de clientes con su estado y posición
    - Lista de locations disponibles en el mapa
    - Info del ctc_status
    """
    try:
        taxis = db.obtener_taxis()       #Lista de diccionarios: [{id, estado, coord_x, coord_y, ...}, ...]
        clientes = db.obtener_clientes() #Lista de diccionarios: [{id, status, coord_x, coord_y, destination_id}, ...]
        locations = db.obtener_locations() #Lista de diccionarios: [{id, coord_x, coord_y}, ...]
        ctc = db.get_ctc_status()

        # Convertir a listas "serializables"
        taxis_list = [dict(t) for t in taxis] if taxis else []
        clients_list = [dict(c) for c in clientes] if clientes else []
        locations_list = [dict(l) for l in locations] if locations else []

        response = {
            "taxis": taxis_list,
            "clients": clients_list,
            "locations": locations_list,
            "ctc": ctc,
            "message": "Estado del sistema devuelto correctamente."
        }
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Error obteniendo estado: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Lanzar la API en el puerto 5000 (se puede cambiar)
    app.run(host="0.0.0.0", port=5005, debug=True)
