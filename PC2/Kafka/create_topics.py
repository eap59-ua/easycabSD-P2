# create_topics.py
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

def setup_taxi_topics(broker_url="localhost:9092", num_taxis=3):
    admin_client = KafkaAdminClient(bootstrap_servers=broker_url)
    
    topics = [
        # Topic para estados de todos los taxis
        NewTopic(name="taxi_status", num_partitions=1, replication_factor=1),
    ]
    
    # Topics individuales para cada taxi
    for i in range(num_taxis):
        topics.append(
            NewTopic(name=f"taxi_orders_{i}", num_partitions=1, replication_factor=1)
        )

    for topic in topics:
        try:
            admin_client.create_topics([topic])
            print(f"✓ Topic {topic.name} creado correctamente")
        except TopicAlreadyExistsError:
            print(f"! Topic {topic.name} ya existe")
        except Exception as e:
            print(f"✗ Error creando topic {topic.name}: {e}")

if __name__ == "__main__":
    print("Creando topics para EasyCab...")
    setup_taxi_topics()
    print("Finalizado!")