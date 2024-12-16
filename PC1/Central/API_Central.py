from flask import Flask, jsonify

def create_api(central):
    app = Flask(__name__)

    @app.route('/status', methods=['GET'])
    def get_status():
        taxis = central.db.obtener_taxis()
        clients = central.active_clients
        traffic = "OK" if getattr(central, 'traffic_status', True) else "KO"
        return jsonify({"taxis": [dict(t) for t in taxis], "clients": clients, "traffic": traffic})

    return app

# Luego desde main o desde EC_Central:
# api_app = create_api(central)
# api_app.run(host='0.0.0.0', port=5002)
