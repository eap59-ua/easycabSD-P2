from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

API_KEY = '32c1c0c19dd2b6dff37ac4e4f177840d'
current_city = "Alicante"  #Ciudad por defecto

@app.route('/city', methods=['POST'])
def set_city():
    global current_city
    data = request.get_json()
    if 'city' in data:
        current_city = data['city']
        return jsonify({"status": "OK", "city": current_city})
    else:
        return jsonify({"status": "ERROR", "message": "No city provided"}), 400

@app.route('/traffic', methods=['GET'])
def get_traffic_status():
    # Llamar a OpenWeather
    url = f"https://api.openweathermap.org/data/2.5/weather?q={current_city}&appid={API_KEY}&units=metric"
    r = requests.get(url)
    if r.status_code == 200:
        data = r.json()
        
        #Si no encuentra información (se ha producido un error), devolvemos KO
        if data.get("cod") != 200:
            return jsonify({
                "status": "KO",
                "city": current_city,
                "temp": None
            }), 200
        
        #Si la consulta ha funcionado, extraemos la información correspondiente
        city_name = data.get("name", "")
        temp = data["main"]["temp"]
        
        status = "KO" if temp < 0 else "OK"
        
        #Devolvemos un JSON con la información extraída y el estado del tráfico según la temperatura
        return jsonify({
            "status": status,           #OK/KO, según temp
            "city": city_name,          #Nombre de la ciudad
            "temp": temp                #Temperatura en °C
        }), 200
    
    else:
        return jsonify({
                "status": "KO",
                "city": current_city,       #Devuelve la ciudad por defecto o la última que estaba
                "temp": None
            }), r.status_code

if __name__ == '__main__':
    #Iniciar el servidor Flask, en el puerto 5002
    app.run(host='0.0.0.0', port=5002, debug=False)