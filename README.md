# Flujo del programa EC_Customer

## Inicialización
1. El programa comienza en la función `main()`.
2. Se crea una instancia de `ECCustomer` con la dirección del broker Kafka y el ID del cliente.
3. Durante la inicialización (`__init__`):
   - Se configura el productor y consumidor Kafka.
   - Se cargan las ubicaciones y solicitudes desde archivos JSON.

## Procesamiento de solicitudes
4. El `main()` itera sobre las solicitudes del cliente:
   - Llama a `request_ride()` para cada destino.
   - Espera la respuesta con `listen_for_responses()`.
   - Pausa 4 segundos entre solicitudes exitosas.

## Desglose de métodos

### load_locations() y load_requests()
- Leen y parsean archivos JSON.
- Manejan errores como archivo no encontrado o JSON inválido.
- Estructuran los datos para su uso en el programa.

### request_ride(destination_id)
- Verifica si el destino es válido.
- Obtiene la posición actual del cliente.
- Envía una solicitud de viaje a través de Kafka.

### get_current_position()
- Interactúa con el usuario para obtener su ubicación actual.
- Valida las entradas para asegurar coordenadas válidas.

### listen_for_responses()
- Escucha las respuestas de la central a través de Kafka.
- Procesa diferentes tipos de mensajes (confirmación, completado, rechazado).

## Conceptos clave

### Kafka
- Sistema de mensajería distribuido.
- Productor: Envía mensajes a un topic (`ride_requests`).
- Consumidor: Recibe mensajes de un topic específico para el cliente.
- Permite comunicación asíncrona entre el cliente y la central.

### Archivos JSON
- Formato de datos estructurado y legible.
- `EC_locations.json`: Almacena información sobre ubicaciones.
- `EC_Requests.json`: Contiene las solicitudes de viaje del cliente.

### Comunicación con la central
- Asíncrona a través de Kafka.
- El cliente envía solicitudes y escucha respuestas en topics diferentes.
- La central procesa las solicitudes y envía respuestas al topic del cliente.
