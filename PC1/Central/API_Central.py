from flask import Flask, jsonify, request
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
        # Usar tu método mejorado para taxis
        taxis = db.obtener_taxis_para_front()
        taxis_list = [dict(t) for t in taxis if t['estado'] != 'no_disponible'] if taxis else []
        
        clientes = db.obtener_clientes()
        clients_list = [dict(c) for c in clientes] if clientes else []
        
        locations = db.obtener_locations()
        locations_list = [dict(l) for l in locations] if locations else []

        # Mejorar el manejo del tráfico
        traffic_info = {}
        try:
            response = requests.get("http://localhost:5002/traffic", timeout=2)
            if response.status_code == 200:
                data = response.json()
                traffic_info = {
                    "status": data.get("status"),
                    "city": data.get("city"),
                    "temp": data.get("temp")
                }
        except requests.exceptions.RequestException:
            # Fallback a BD
            ctc_status = db.get_ctc_status()
            if ctc_status:
                traffic_info = {
                    "status": "OK" if ctc_status["traffic_ok"] else "KO",
                    "city": ctc_status["city"],
                    "temp": ctc_status["temp"]
                }

        response = {
            "taxis": taxis_list,
            "clients": clients_list,
            "locations": locations_list,
            "traffic": traffic_info,
            "timestamp": time.time()
        }
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error obteniendo estado: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/ctc/city", methods=["POST"])
def request_change_city():
    try:
        data = request.get_json()
        new_city = data.get("city")
        if not new_city:
            return jsonify({"status": "ERROR", "message": "No city provided"}), 400

        logger.info(f"Solicitando cambio de ciudad a: {new_city}")
        
        try:
            response = requests.post(
                "http://localhost:5002/city",
                json={"city": new_city},
                timeout=2
            )
            
            if response.status_code == 200:
                logger.info(f"Ciudad cambiada exitosamente a {new_city}")
                db.insert_ctc_command("change_city", new_city)
                return jsonify({"status": "OK", "city": new_city}), 200
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error en llamada directa a CTC: {e}")
            db.insert_ctc_command("change_city", new_city)
            return jsonify({"status": "PENDING", "city": new_city}), 202

    except Exception as e:
        logger.error(f"Error en request_change_city: {e}")
        return jsonify({"status": "ERROR", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=True)