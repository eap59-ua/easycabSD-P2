async function fetchStatus() {
    let response = await fetch('/api/map-status');
    let data = await response.json();
    return data;
}

function drawMap(data) {
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

    // Dibujar taxis
    data.taxis.forEach(taxi => {
        let x = taxi.coord_x;
        let y = taxi.coord_y;
        let index = (x - 1) * size + (y - 1);
        cells[index].style.background = 'green';
    });

    // Dibujar clientes
    for (let client_id in data.clients) {
        let client = data.clients[client_id];
        let x = client.position[0];
        let y = client.position[1];
        let index = (x - 1)*size + (y - 1);
        cells[index].style.background = 'yellow';
    }

    // Estado del tráfico
    document.getElementById('traffic').textContent = data.traffic;
}

// Botón para cambiar la ciudad en EC_CTC
document.getElementById('changeCityBtn').addEventListener('click', async () => {
    const city = document.getElementById('cityInput').value;
    // Aquí asumiendo que quieras llamar directamente a EC_CTC
    // Ajusta la IP/puerto de EC_CTC
    let response = await fetch('http://IP_DEL_EC_CTC:5001/city', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({city})
    });
    let data = await response.json();
    console.log(data);
});

async function update() {
    let data = await fetchStatus();
    drawMap(data);
}

setInterval(update, 3000);
update();
