from flask import Flask, jsonify
from map_reader import DatabaseManager, get_db_params
import logging
from flask_cors import CORS
import requests
import time
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
    try:
        # Obtener datos básicos
        taxis = db.obtener_taxis_para_front()
        taxis_list = [dict(t) for t in taxis if t['estado'] != 'no_disponible'] if taxis else []
        
        # Obtener datos de clientes
        clientes = db.obtener_clientes()
        clients_list = [dict(c) for c in clientes] if clientes else []
        
        # Obtener locations
        locations = db.obtener_locations()
        locations_list = [dict(l) for l in locations] if locations else []
        
        # Obtener datos de tráfico con mejor manejo de errores
        traffic_status = "KO"
        try:
            traffic_response = requests.get("http://localhost:5002/traffic", timeout=2)
            if traffic_response.status_code == 200:
                traffic_status = traffic_response.text.strip()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error consultando tráfico: {e}")

        # Construir respuesta completa
        response = {
            "taxis": taxis_list,
            "clients": clients_list,
            "locations": locations_list,
            "traffic": {
                "status": traffic_status
            },
            "timestamp": time.time()
        }
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Error obteniendo estado: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Lanzar la API en el puerto 5000 (se puede cambiar)
    app.run(host="0.0.0.0", port=5005, debug=True)
