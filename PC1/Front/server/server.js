// En server.js
const path = require('path');
const express = require('express');
const app = express();
const cors = require('cors');

// Ajusta la ruta para servir archivos estáticos desde el directorio correcto
app.use(express.static(path.join(__dirname, '../public')));
app.use(express.json());
app.use(cors());
// Endpoints
app.get('/api/map-status', async (req, res) => {
    try {
        const response = await fetch('http://localhost:5005/state');
        const data = await response.json();
        res.json(data);
    } catch (error) {
        console.error('Error fetching map status:', error);
        res.status(500).json({ error: 'Error fetching map status' });
    }
});

// Endpoint para obtener estado del tráfico
app.get('/api/traffic', async (req, res) => {
  try {
    const response = await fetch('http://localhost:5002/traffic');
    const data = await response.text();
    res.json({ status: data });
  } catch (error) {
    console.error('Error fetching traffic status:', error);
    res.status(500).json({ error: 'Error fetching traffic status' });
  }
});

// Endpoint para cambiar ciudad
app.post('/api/city', async (req, res) => {
  try {
    const response = await fetch('http://localhost:5002/city', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    });
    const data = await response.json();
    res.json(data);
  } catch (error) {
    console.error('Error changing city:', error);
    res.status(500).json({ error: 'Error changing city' });
  }
});

const PORT = 8080;
app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});