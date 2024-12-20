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
        temp = data['main']['temp']
        if temp < 0:
            return "KO"  # No viable
        else:
            return "OK"  # Viable
    else:
        return "KO"  # Si no podemos obtener datos, mejor devolver KO o algún error

if __name__ == '__main__':
    #Iniciar el servidor Flask, en el puerto 5001, por ejemplo
    app.run(host='0.0.0.0', port=5002, debug=False)