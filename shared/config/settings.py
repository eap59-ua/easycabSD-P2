# shared/config/settings.py
CONFIG = {
    'central_port': 5000,              # Tu puerto actual
    'registry_port': 5001,             # Puedes usar 5001 para el Registry
    'kafka_broker': 'localhost:9092',   # Tu broker Kafka
    'db_connection': {
        'host': 'localhost',
        'port': 5432,                  # Tu puerto PostgreSQL
        'database': 'central_db',
        'user': 'postgres',
        'password': 'postgres'
    }
}