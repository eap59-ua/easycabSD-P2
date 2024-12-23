// Funciones de fetch
async function fetchStatus() {
    const response = await fetch('/api/map-status');
    return response.json();
}

// Sistema de alertas
class AlertSystem {
    constructor() {
        this.container = document.getElementById('alerts-container');
        this.alerts = new Set();
    }

    addAlert(message, type = 'info', timeout = 5000) {
        const alertId = Date.now();
        const alert = document.createElement('div');
        alert.className = `alert ${type}`;
        alert.innerHTML = `
            <span>${message}</span>
            <button onclick="this.parentElement.remove()">×</button>
        `;
        this.container.prepend(alert);
        
        setTimeout(() => alert.remove(), timeout);
    }
}

const alertSystem = new AlertSystem();

// Función principal de actualización
async function updateSystem() {
    try {
        const [data] = await fetchStatus();
        drawMap(data);
        updateStatusPanel(data);
        updateTaxiList(data.taxis);
        updateClientList(data.clients);
        
    } catch (error) {
        console.error('Error updating system:', error);
        alertSystem.addAlert('Error actualizando el sistema', 'error');
    }
}

function updateStatusPanel(data) {
    const trafficStatus = document.getElementById('traffic-status');
    
    if (!data.ctc) {
        trafficStatus.innerHTML = "Sin información de tráfico";
        return;
    }
    
    const { traffic_ok, temp, city } = data.ctc;  // Ajusta según tus claves reales
    const isOk = traffic_ok; // true -> OK, false -> KO
    
    trafficStatus.innerHTML = `
        <span class="status-dot ${isOk ? 'green' : 'red'}"></span>
        ${isOk ? 'Tráfico Normal' : 'Tráfico Interrumpido'}
        <br>
        Ciudad actual: ${city}
        <br>
        Temperatura: ${temp} °C
    `;
}

function updateTaxiList(taxis) {
    const tbody = document.getElementById('taxi-tbody');
    tbody.innerHTML = '';
    
    taxis.forEach(taxi => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${taxi.id}</td>
            <td class="status ${taxi.estado === 'disponible' ? 'available' : ''}">
                ${getStatusEmoji(taxi.estado)} ${taxi.estado}
            </td>
            <td>${taxi.cliente_asignado || '-'}</td>
            <td>${taxi.token ? '✓' : '✗'}</td>
        `;
        tbody.appendChild(row);
    });
}

function updateClientList(clients) {
    const tbody = document.getElementById('client-tbody');
    tbody.innerHTML = '';
    
    clients.forEach(client => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${client.id}</td>
            <td>${client.status}</td>
            <td>${client.destination_id || '-'}</td>
        `;
        tbody.appendChild(row);
    });
}

function getStatusEmoji(status) {
    const emojis = {
        'disponible': '🟢',
        'en_movimiento': '🚕',
        'no_disponible': '🔴'
    };
    return emojis[status] || '⚪';
}

// Tu función drawMap modificada para incluir índices
// main.js
async function drawMap(data) {
    console.log('Drawing map with data:', data);
    const mapContainer = document.getElementById('map-container');
    if (!mapContainer) {
        console.error('Map container not found!');
        return;
    }
    
    mapContainer.innerHTML = '';
    const size = 20;

    // Debug logs
    console.log('Grid size:', size);
    console.log('Taxis:', data.taxis);
    console.log('Clients:', data.clients);
    console.log('Locations:', data.locations);

    // Configurar grid
    mapContainer.style.gridTemplateColumns = `35px repeat(${size}, 35px)`;
    mapContainer.style.gridTemplateRows = `35px repeat(${size}, 35px)`;

    // Celda vacía en la esquina superior izquierda
    mapContainer.appendChild(createCell(''));

    // Índices superiores (1-20)
    for (let i = 1; i <= size; i++) {
        mapContainer.appendChild(createCell(i, true));
    }

    // Grid principal con índices laterales
    for (let i = 1; i <= size; i++) {
        // Índice lateral
        mapContainer.appendChild(createCell(i, true));

        // Celdas del mapa
        for (let j = 1; j <= size; j++) {
            const cell = createCell('');
            
            // Buscar elementos en esta posición
            const taxi = data.taxis?.find(t => t.coord_x === i && t.coord_y === j);
            const client = data.clients?.find(c => 
                c.coord_x === i && 
                c.coord_y === j && 
                c.status !== 'picked_up'
            );
            const location = data.locations?.find(l => l.coord_x === i && l.coord_y === j);

            // Aplicar estilos según el elemento
            if (taxi) {
                cell.style.backgroundColor = taxi.esta_parado ? '#ff4444' : '#44ff44';
                cell.textContent = String(taxi.id);
            } else if (client) {
                cell.style.backgroundColor = '#ffff44';
                cell.textContent = client.id.toLowerCase();
            } else if (location) {
                cell.style.backgroundColor = '#4444ff';
                cell.style.color = 'white';
                cell.textContent = location.id;
            }

            mapContainer.appendChild(cell);
        }
    }
}

function createCell(content, isHeader = false) {
    const cell = document.createElement('div');
    cell.className = 'cell';
    
    if (isHeader) {
        cell.style.backgroundColor = '#f0f0f0';
        cell.style.fontWeight = 'bold';
    }
    
    cell.textContent = content;
    return cell;
}

// Evento para cambiar ciudad
document.getElementById('changeCityBtn').addEventListener('click', async () => {
    const city = document.getElementById('cityInput').value;
    if (!city) {
        alertSystem.addAlert('Por favor, introduce una ciudad', 'warning');
        return;
    }
    
    // Mostramos un aviso de "Procesando..."
    alertSystem.addAlert(`Iniciando cambio de ciudad a "${city}"...`, 'info', 3000);

    try {
        const response = await fetch('/api/city', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({city})
        });
        const data = await response.json();
        
        if (data.status === 'PENDING') {
            // Reemplazar 'OK' por 'PENDING'
            alertSystem.addAlert(`Comando de cambio de ciudad enviado. Espera que la Central lo procese...`, 'info', 5000);
            document.getElementById('cityInput').value = '';
        } 
        else if (data.status === 'ERROR') {
            alertSystem.addAlert('Error cambiando la ciudad', 'error');
        } else {
            alertSystem.addAlert('Error cambiando la ciudad', 'error');
        }
    } catch (error) {
        console.error('Error changing city:', error);
        alertSystem.addAlert('Error en la conexión', 'error');
    }
});

// Añadir algunos estilos dinámicos
const style = document.createElement('style');
style.textContent = `
    .status-dot {
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin-right: 5px;
    }
    .status-dot.green { background-color: #52c41a; }
    .status-dot.red { background-color: #f5222d; }
    .status.available { color: #52c41a; }
`;
document.head.appendChild(style);

// Iniciar el sistema de actualización
setInterval(updateSystem, 3000);
updateSystem();