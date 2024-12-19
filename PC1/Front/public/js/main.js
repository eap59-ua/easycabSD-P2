async function fetchStatus() {
    let response = await fetch('/api/map-status');
    let data = await response.json();
    return data;
}

async function fetchTraffic() {
    let response = await fetch('http://localhost:5001/traffic');
    let text = await response.text();
    return text;
}

function drawMap(data, trafficStatus) {
    const mapElement = document.getElementById('map-container');
    mapElement.innerHTML = ''; 
    let size = 20; // Por ejemplo, 20x20

    // Crear grid
    mapElement.style.display = 'grid';
    mapElement.style.gridTemplateColumns = `repeat(${size}, 20px)`;
    mapElement.style.gridTemplateRows = `repeat(${size}, 20px)`;
    mapElement.style.gap = '1px';

    let cells = [];
    for (let i = 0; i < size * size; i++) {
        let div = document.createElement('div');
        div.className = 'cell';
        div.style.width = '20px';
        div.style.height = '20px';
        div.style.background = '#fff';
        cells.push(div);
        mapElement.appendChild(div);
    }

    //Clientes que están waiting o finished
    data.clients.forEach(client => {
        if (client.status !== 'picked_up') {
            let x = client.coord_x;
            let y = client.coord_y;
            // Asumiendo que (1,1) es la esquina sup-izq y que x incrementa hacia abajo y y hacia la derecha
            let index = (x - 1) * size + (y - 1);
            if (index >= 0 && index < cells.length) {
                cells[index].style.background = 'yellow';
                cells[index].textContent = client.id.toLowerCase();
            }
        }
    });

    //Dibujar taxis. Si un taxi tiene un cliente en picked_up, se muestra taxiID+clienteID
    data.taxis.forEach(taxi => {
        let x = taxi.coord_x;
        let y = taxi.coord_y;
        let index = (x - 1) * size + (y - 1);
        if (index < 0 || index >= cells.length) return;

        // Determinar color del taxi según estado
        // Por simplicidad: verde si en_movimiento, rojo si no
        let color = (taxi.estado === 'en_movimiento' && !taxi.esta_parado) ? 'green' : 'red';
        cells[index].style.background = color;

        let display_text = String(taxi.id);

        // Si el taxi tiene un cliente asignado
        if (taxi.cliente_asignado) {
            // Buscar el cliente correspondiente
            let assignedClient = data.clients.find(c => c.id === taxi.cliente_asignado);
            if (assignedClient && assignedClient.status === 'picked_up') {
                // Mostrar taxi y cliente juntos (ej: "1a")
                display_text = display_text + assignedClient.id.toLowerCase();
            }
        }

        cells[index].textContent = display_text;
    });

    // Estado del tráfico
    document.getElementById('traffic').textContent = "Estado del tráfico: " + trafficStatus;
}

// Botón para cambiar la ciudad en EC_CTC
document.getElementById('changeCityBtn').addEventListener('click', async () => {
    const city = document.getElementById('cityInput').value;
    // Ajusta la IP/puerto de EC_CTC
    let response = await fetch('http://localhost:5001/city', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({city})
    });
    let data = await response.json();
    console.log(data);
});

async function update() {
    let data = await fetchStatus();
    let traffic = await fetchTraffic();
    drawMap(data, traffic);
}

setInterval(update, 3000);
update();
