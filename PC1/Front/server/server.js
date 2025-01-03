// En server.js
const path = require('path');
const express = require('express');
const app = express();
const cors = require('cors');

// Ajusta la ruta para servir archivos estáticos desde el directorio correcto
app.use(express.static(path.join(__dirname, '../public')));
app.use(express.json());
app.use(cors());

// Ruta para la página principal (ya existe)
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '../public/index.html'));
});

// Nueva ruta para la página de auditorías
app.get('/audit', (req, res) => {
  res.sendFile(path.join(__dirname, '../public/audit.html'));
});

// Nuevo endpoint para obtener datos de auditoría
app.get('/api/audit-log', async (req, res) => {
  try {
      const queryParams = new URLSearchParams({
          page: req.query.page || '1',
          limit: req.query.limit || '10',
          eventType: req.query.eventType || '',
          source: req.query.source || '',
          date: req.query.date || ''
      });

      console.log('Attempting to fetch audit data from:', `http://127.0.0.1:5005/audit?${queryParams}`);

      const response = await fetch(`http://127.0.0.1:5005/audit?${queryParams}`, {
          method: 'GET',
          headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json'
          },
          // Añadir timeout
          timeout: 5000
      });

      if (!response.ok) {
          const errorText = await response.text();
          console.error('Response not OK:', response.status, errorText);
          throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('Successfully received audit data:', data);
      res.json(data);

  } catch (error) {
      console.error('Detailed error in /api/audit-log:', {
          message: error.message,
          cause: error.cause,
          stack: error.stack
      });

      res.status(500).json({ 
          error: 'Error accessing audit log',
          details: error.message,
          cause: error.cause ? error.cause.message : null
      });
  }
});
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
    const response = await fetch('http://127.0.0.1:5002/ctc/city', {
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