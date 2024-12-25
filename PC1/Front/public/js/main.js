// Funciones de fetch
async function fetchStatus() {
    try {
        const response = await fetch('http://localhost:5005/state');
        const data = await response.json();
        console.log("Datos recibidos:", data); // Para debug
        return data;
    } catch (error) {
        console.error("Error fetching status:", error);
        throw error;
    }
}

// Sistema de alertas mejorado
class AlertSystem {
    constructor() {
        this.container = document.getElementById('alerts-container');
        this.alerts = new Set();
    }

    addAlert(message, type = 'info', timeout = 5000) {
        const alertId = `${type}-${message}`;
        if (this.alerts.has(alertId)) return;
        
        this.alerts.add(alertId);
        const alert = document.createElement('div');
        alert.className = `alert ${type}`;
        alert.innerHTML = `
            <span>${message}</span>
            <button onclick="this.parentElement.remove()">×</button>
        `;
        
        this.container.prepend(alert);
        
        setTimeout(() => {
            alert.remove();
            this.alerts.delete(alertId);
        }, timeout);
    }
}

const alertSystem = new AlertSystem();

// Función principal de actualización
async function updateSystem() {
    try {
        const data = await fetchStatus();
        console.log("Actualizando sistema con datos:", data);
        
        // Dibujar el mapa
        drawMap(data);
        
        // Actualizar tablas
        updateTables(data);

        // Actualizar estado del tráfico
        updateTrafficStatus(data.traffic);

    } catch (error) {
        console.error('Error updating system:', error);
        alertSystem.addAlert('Error actualizando el sistema', 'error');
    }
}

// Función para actualizar estado del tráfico
function updateTrafficStatus(trafficData) {
    const trafficStatus = document.getElementById('traffic-status');
    if (!trafficStatus) return;

    const isOk = trafficData.status === 'OK';
    trafficStatus.innerHTML = `
        <span class="status-dot ${isOk ? 'green' : 'red'}"></span>
        ${isOk ? 'Tráfico Normal' : 'Tráfico Interrumpido'}
    `;
}

// Función para actualizar las tablas
function updateTables(data) {
    console.log("Actualizando tablas con:", data);
    
    // Actualizar tabla de taxis
    const taxiTbody = document.getElementById('taxi-tbody');
    if (taxiTbody) {
        taxiTbody.innerHTML = '';
        data.taxis?.forEach(taxi => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${taxi.id}</td>
                <td class="${taxi.esta_parado ? 'status-stopped' : 'status-moving'}">
                    ${getStatusEmoji(taxi.estado)} ${taxi.estado}
                </td>
                <td>${taxi.cliente_asignado || '-'}</td>
                <td>${taxi.has_token ? '✅' : '❌'}</td>
            `;
            taxiTbody.appendChild(row);
        });
    }
    
    // Actualizar tabla de clientes
    const clientTbody = document.getElementById('client-tbody');
    if (clientTbody) {
        clientTbody.innerHTML = '';
        data.clients?.forEach(client => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${client.id}</td>
                <td class="status-${client.status}">
                    ${getClientStatusEmoji(client.status)} ${client.status}
                </td>
                <td>${client.destination_id || '-'}</td>
            `;
            clientTbody.appendChild(row);
        });
    }
}

function getStatusEmoji(status) {
    return {
        'disponible': '🟢',
        'en_movimiento': '🚕',
        'no_disponible': '⚫️'
    }[status] || '⚪️';
}

function getClientStatusEmoji(status) {
    return {
        'waiting': '⌛️',
        'picked_up': '🚖',
        'finished': '✅'
    }[status] || '⚪️';
}

// Función para dibujar el mapa
async function drawMap(data) {
    console.log('Drawing map with data:', data);
    const mapContainer = document.getElementById('map-container');
    if (!mapContainer) {
        console.error('Map container not found!');
        return;
    }
    
    mapContainer.innerHTML = '';
    const size = 20;

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
    
    cell.style.transition = 'all 0.1s linear';
    cell.textContent = content;
    return cell;
}

// Iniciar actualizaciones cuando se carga la página
document.addEventListener('DOMContentLoaded', () => {
    updateSystem();
    setInterval(updateSystem, 50);
});