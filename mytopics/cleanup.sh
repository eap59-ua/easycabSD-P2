#!/bin/bash
# NO borrar __consumer_offsets, es creado automaticamente por kafka

KAFKA_TOPICS="/opt/kafka/bin/kafka-topics.sh"
echo "Limpiando topics de Kafka..."

# Topics de clientes
$KAFKA_TOPICS --bootstrap-server localhost:9092 --delete --topic ride_requests
$KAFKA_TOPICS --bootstrap-server localhost:9092 --delete --topic customer_responses

# Topics de taxis
$KAFKA_TOPICS --bootstrap-server localhost:9092 --delete --topic taxi_status
for i in {1..3}; do
    $KAFKA_TOPICS --bootstrap-server localhost:9092 --delete --topic taxi_orders_$i
done

echo "Esperando 2 segundos..."
sleep 2

echo "Recreando topics..."
# Recrear topics de clientes
$KAFKA_TOPICS --create --topic ride_requests --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
$KAFKA_TOPICS --create --topic customer_responses --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1

# Recrear topics de taxis
$KAFKA_TOPICS --create --topic taxi_status --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
for i in {1..3}; do
    $KAFKA_TOPICS --create --topic taxi_orders_$i --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
done

echo "Topics recreados correctamente"

# Listar todos los topics para verificar
echo "Topics actualmente existentes:"
$KAFKA_TOPICS --bootstrap-server localhost:9092 --list