// Funciones de fetch separadas (buena práctica de tu código)
async function fetchStatus() {
    const response = await fetch('/api/map-status');
    return response.json();
}

async function fetchTraffic() {
    const response = await fetch('/api/traffic');
    return response.json();
}

// Función principal de actualización
async function updateSystem() {
    try {
        const [data, trafficData] = await Promise.all([
            fetchStatus(),
            fetchTraffic()
        ]);

        drawMap(data);
        updateStatusPanel(data);
        updateTrafficStatus(trafficData.status);
    } catch (error) {
        console.error('Error updating system:', error);
    }
}

// Tu función drawMap modificada para incluir índices
function drawMap(data) {
    const mapContainer = document.getElementById('map-container');
    mapContainer.innerHTML = '';
    const size = 20;

    // Configurar grid con espacio para índices
    mapContainer.style.gridTemplateColumns = `35px repeat(${size}, 35px)`;
    mapContainer.style.gridTemplateRows = `35px repeat(${size}, 35px)`;

    // Añadir índices superiores
    mapContainer.appendChild(createCell(''));
    for (let i = 1; i <= size; i++) {
        mapContainer.appendChild(createCell(i, true));
    }

    // Crear grid con índices laterales
    for (let i = 1; i <= size; i++) {
        // Índice lateral
        mapContainer.appendChild(createCell(i, true));

        // Celdas del mapa
        for (let j = 1; j <= size; j++) {
            const cell = createCell('');
            
            // Buscar elementos en esta posición
            const taxi = data.taxis.find(t => t.coord_x === i && t.coord_y === j);
            const client = data.clients.find(c => 
                c.coord_x === i && 
                c.coord_y === j && 
                c.status !== 'picked_up'
            );
            const location = data.locations.find(l => l.coord_x === i && l.coord_y === j);

            // Aplicar estilo según el elemento
            if (taxi) {
                cell.style.backgroundColor = (taxi.estado === 'en_movimiento' && !taxi.esta_parado) ? 'green' : 'red';
                let display_text = String(taxi.id);
                if (taxi.cliente_asignado) {
                    const assignedClient = data.clients.find(c => c.id === taxi.cliente_asignado);
                    if (assignedClient && assignedClient.status === 'picked_up') {
                        display_text += assignedClient.id.toLowerCase();
                    }
                }
                cell.textContent = display_text;
            } else if (client) {
                cell.style.backgroundColor = 'yellow';
                cell.textContent = client.id.toLowerCase();
            } else if (location) {
                cell.style.backgroundColor = 'blue';
                cell.style.color = 'white';
                cell.textContent = location.id;
            }

            mapContainer.appendChild(cell);
        }
    }
}

// Funciones auxiliares (mantener las que te proporcioné antes)
function createCell(content, isHeader = false) {
    const cell = document.createElement('div');
    cell.className = 'cell';
    cell.textContent = content;
    if (isHeader) {
        cell.style.backgroundColor = '#f0f0f0';
        cell.style.fontWeight = 'bold';
    }
    return cell;
}

function updateStatusPanel(data) {
    // [Mantener el código de actualización de tablas que te proporcioné]
}

function updateTrafficStatus(status) {
    // [Mantener el código de actualización de tráfico que te proporcioné]
}

// Evento para cambiar ciudad (tu versión)
document.getElementById('changeCityBtn').addEventListener('click', async () => {
    const city = document.getElementById('cityInput').value;
    if (!city) return;
    
    try {
        const response = await fetch('http://localhost:5001/city', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({city})
        });
        const data = await response.json();
        console.log(data);
        document.getElementById('cityInput').value = '';
    } catch (error) {
        console.error('Error changing city:', error);
    }
});

// Actualizar cada 3 segundos (como en tu código)
setInterval(updateSystem, 3000);
updateSystem();