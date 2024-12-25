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

// Sistema de caché mejorado
const cache = {
    lastMapData: null,
    lastSystemData: null,
    lastMapUpdate: 0,
    lastSystemUpdate: 0
};
// Nueva función solo para actualizar el mapa
async function updateMapOnly() {
    try {
        const data = await fetchStatus();
        
        // Solo actualizar mapa si los datos relevantes han cambiado
        const mapData = {
            taxis: data.taxis,
            clients: data.clients,
            locations: data.locations
        };

        if (JSON.stringify(mapData) !== JSON.stringify(cache.lastMapData)) {
            drawMap(data);
            cache.lastMapData = mapData;
            cache.lastMapUpdate = Date.now();
        }
    } catch (error) {
        console.error('Error updating map:', error);
    }
}
// Nueva función para actualizar el resto del sistema
async function updateSystemStatus() {
    try {
        const data = await fetchStatus();
        
        // Solo actualizar si los datos del sistema han cambiado
        const systemData = {
            traffic: data.traffic,
            taxis: data.taxis?.map(t => ({ 
                id: t.id, 
                estado: t.estado, 
                cliente_asignado: t.cliente_asignado,
                has_token: t.has_token 
            })),
            clients: data.clients
        };

        if (JSON.stringify(systemData) !== JSON.stringify(cache.lastSystemData)) {
            updateTables(data);
            updateTrafficStatus(data.traffic);
            
            cache.lastSystemData = systemData;
            cache.lastSystemUpdate = Date.now();
        }
    } catch (error) {
        console.error('Error updating system status:', error);
        alertSystem.addAlert('Error actualizando el estado del sistema', 'error');
    }
}

// Mejorar el sistema de alertas
class AlertSystem {
    constructor() {
        this.container = document.getElementById('alerts-container');
        this.alerts = new Map();
    }

    addAlert(message, type = 'info', timeout = 5000) {
        const id = `${type}-${message}`;
        
        // Evitar duplicados
        if (this.alerts.has(id)) {
            clearTimeout(this.alerts.get(id).timer);
        }

        const alert = document.createElement('div');
        alert.className = `alert ${type}`;
        alert.innerHTML = `
            <span>${message}</span>
            <button onclick="this.parentElement.remove()">×</button>
        `;
        
        const timer = setTimeout(() => {
            alert.remove();
            this.alerts.delete(id);
        }, timeout);

        this.alerts.set(id, { alert, timer });
        this.container.prepend(alert);
    }
}
const alertSystem = new AlertSystem();


// En main.js, modificar la función updateTrafficStatus
function updateTrafficStatus(data) {
    const trafficStatus = document.getElementById('traffic-status');
    if (!trafficStatus) return;

    // Si no hay datos de tráfico
    if (!data || (!data.status && !data.city && !data.temp)) {
        trafficStatus.innerHTML = "Sin información de tráfico";
        return;
    }

    // Obtener valores directamente del objeto data
    const isOk = data.status === 'OK';
    const city = data.city || 'No disponible';
    const temp = data.temp !== undefined ? data.temp.toFixed(2) : 'No disponible';

    // Crear el HTML con la información
    trafficStatus.innerHTML = `
        <div class="traffic-info">
            <div class="status-row">
                <span class="status-dot ${isOk ? 'green' : 'red'}"></span>
                <span>${isOk ? 'Tráfico Normal' : 'Tráfico Interrumpido'}</span>
            </div>
            <div class="city-row">
                <strong>Ciudad actual:</strong> ${city}
            </div>
            <div class="temp-row">
                <strong>Temperatura:</strong> ${temp !== 'No disponible' ? `${temp}°C` : temp}
            </div>
        </div>
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
        'no_disponible': '🔴'
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
        const response = await fetch('http://127.0.0.1:5005/ctc/city', {
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
// En el style que ya tienes en main.js, añadir:
style.textContent += `
    .traffic-info {
        padding: 10px;
        background: #f5f5f5;
        border-radius: 4px;
        margin: 10px 0;
    }
    .status-row, .city-row, .temp-row {
        margin: 5px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .status-dot {
        margin-right: 8px;
    }
`;


document.head.appendChild(style);
// Iniciar actualizaciones cuando se carga la página
// Modificar el inicializador al final del archivo
document.addEventListener('DOMContentLoaded', () => {
    // Primera carga
    updateMapOnly();
    updateSystemStatus();
    
    // Configurar intervalos diferentes
    setInterval(updateMapOnly, 1000);     // Actualización rápida del mapa
    setInterval(updateSystemStatus, 5000); // Actualización más lenta del resto
});