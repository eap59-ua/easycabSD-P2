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
// GET /api/map-status -> llama a /state en API_Central
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

// POST /api/city -> llama a /ctc/city en API_Central
app.post('/api/city', async (req, res) => {
  try {
    const response = await fetch('http://localhost:5005/ctc/city', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body) // { city: "..." }
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