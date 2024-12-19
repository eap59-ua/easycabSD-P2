// server/server.js
const express = require('express');
const fetch = require('node-fetch')
const app = express();

// Servir archivos estáticos desde 'public'
app.use(express.static('public'));

// API para obtener estado del mapa
app.get('/api/map-status', async (req, res) => {
    try {
        const response = await fetch('http://localhost:5000/state'); //Cambiar a http://<ip de api_central:5000/state
        const data = await response.json();
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: 'Error fetching map status' });
    }
});

app.listen(8080, () => {
    console.log('Frontend server running on port 8080');
});