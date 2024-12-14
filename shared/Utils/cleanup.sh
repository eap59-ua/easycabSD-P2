#!/bin/bash
# NO borrar __consumer_offsets, es creado automaticamente por kafka
echo "Limpiando topics de Kafka..."

# Topics de clientes
kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic ride_requests
kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic customer_responses

# Topics de taxis
kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic taxi_status
for i in {1..3}; do
    kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic taxi_orders_$i
done

echo "Esperando 2 segundos..."
sleep 2

echo "Recreando topics..."
# Recrear topics de clientes
kafka-topics.sh --create --topic ride_requests --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
kafka-topics.sh --create --topic customer_responses --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1

# Recrear topics de taxis
kafka-topics.sh --create --topic taxi_status --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
for i in {1..3}; do
    kafka-topics.sh --create --topic taxi_orders_$i --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
done

echo "Topics recreados correctamente"

# Listar todos los topics para verificar
echo "Topics actualmente existentes:"
kafka-topics.sh --bootstrap-server localhost:9092 --list