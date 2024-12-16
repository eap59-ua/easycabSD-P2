// server/server.js
const express = require('express');
const app = express();

// Servir archivos estáticos desde 'public'
app.use(express.static('public'));

// API para obtener estado del mapa
app.get('/api/map-status', async (req, res) => {
    try {
        const response = await fetch('http://central-api:3000/status'); //Cambiar a http://<ip de api_central:5002/status
        const data = await response.json();
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: 'Error fetching map status' });
    }
});

app.listen(8080, () => {
    console.log('Frontend server running on port 8080');
});