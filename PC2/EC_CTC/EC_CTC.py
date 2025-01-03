from flask import Flask, request, jsonify
import requests
import os
import sys
# Añadir el directorio raíz del proyecto al path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(project_root)

# Ahora podemos importar desde PC1.Central
from PC1.Central.map_reader import DatabaseManager, get_db_params
app = Flask(__name__)
API_KEY = '32c1c0c19dd2b6dff37ac4e4f177840d'
current_city = "Alicante"  # Ciudad por defecto

# Inicializar conexión a BD para auditoría
db = DatabaseManager(get_db_params())

@app.route('/city', methods=['POST'])
def set_city():
    global current_city
    try:
        data = request.get_json()
        if 'city' in data:
            old_city = current_city
            current_city = data['city']
            
            # Registrar el cambio de ciudad
            db.log_audit_event(
                source="CTC",
                source_id="system",
                ip_address=request.remote_addr,
                event_type="traffic",
                action="CITY_CHANGE",
                details=f"Ciudad cambiada de {old_city} a {current_city}"
            )
            
            return jsonify({"status": "OK", "city": current_city})
        else:
            # Registrar error
            db.log_audit_event(
                source="CTC",
                source_id="system",
                ip_address=request.remote_addr,
                event_type="error",
                action="CITY_CHANGE_ERROR",
                details="Intento de cambio de ciudad sin especificar ciudad"
            )
            return jsonify({"status": "ERROR", "message": "No city provided"}), 400
    except Exception as e:
        db.log_audit_event(
            source="CTC",
            source_id="system",
            ip_address=request.remote_addr,
            event_type="error",
            action="CTC_ERROR",
            details=f"Error cambiando ciudad: {str(e)}"
        )
        return jsonify({"status": "ERROR", "message": str(e)}), 500

@app.route('/traffic', methods=['GET'])
def get_traffic_status():
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={current_city}&appid={API_KEY}&units=metric"
        r = requests.get(url)
        
        if r.status_code == 200:
            data = r.json()
            
            if data.get("cod") != 200:
                db.log_audit_event(
                    source="CTC",
                    source_id="system",
                    ip_address=request.remote_addr,
                    event_type="error",
                    action="WEATHER_DATA_ERROR",
                    details="Error en datos de OpenWeather"
                )
                return jsonify({
                    "status": "KO",
                    "city": current_city,
                    "temp": None
                }), 200

            city_name = data.get("name", "")
            temp = data["main"]["temp"]
            status = "KO" if temp < 0 else "OK"
            
            # Registrar estado del tráfico
            db.log_audit_event(
                source="CTC",
                source_id="system",
                ip_address=request.remote_addr,
                event_type="traffic",
                action="TRAFFIC_STATUS",
                details=f"Estado del tráfico: {status}, Ciudad: {city_name}, Temperatura: {temp}°C"
            )
            
            return jsonify({
                "status": status,
                "city": city_name,
                "temp": temp
            }), 200
        
        else:
            db.log_audit_event(
                source="CTC",
                source_id="system",
                ip_address=request.remote_addr,
                event_type="error",
                action="OPENWEATHER_ERROR",
                details=f"Error consultando OpenWeather: {r.status_code}"
            )
            return jsonify({
                "status": "KO",
                "city": current_city,
                "temp": None
            }), r.status_code

    except Exception as e:
        db.log_audit_event(
            source="CTC",
            source_id="system",
            ip_address=request.remote_addr,
            event_type="error",
            action="CTC_ERROR",
            details=f"Error en CTC: {str(e)}"
        )
        return jsonify({
            "status": "KO",
            "city": current_city,
            "temp": None
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False)