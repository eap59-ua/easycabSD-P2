class AuditSystem {
    constructor() {
        this.currentPage = 1;
        this.itemsPerPage = 10;
        this.totalPages = 1;
        this.currentFilters = {};
        
        // Elementos DOM
        this.tableBody = document.getElementById('auditTableBody');
        this.pageInfo = document.getElementById('pageInfo');
        
        // Configurar event listeners
        this.setupEventListeners();
        
        // Cargar datos iniciales
        this.loadAuditData();
    }

    setupEventListeners() {
        // Filtros
        document.getElementById('applyFilters').addEventListener('click', () => {
            this.currentPage = 1;
            this.updateFilters();
            this.loadAuditData();
        });

        // Paginación
        document.getElementById('prevPage').addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.loadAuditData();
            }
        });

        document.getElementById('nextPage').addEventListener('click', () => {
            if (this.currentPage < this.totalPages) {
                this.currentPage++;
                this.loadAuditData();
            }
        });
    }

    updateFilters() {
        this.currentFilters = {
            eventType: document.getElementById('eventTypeFilter').value,
            source: document.getElementById('sourceFilter').value,
            date: document.getElementById('dateFilter').value
        };
    }

    async loadAuditData() {
        try {
            const queryParams = new URLSearchParams({
                page: this.currentPage,
                limit: this.itemsPerPage,
                ...this.currentFilters
            });
    
            console.log('Fetching audit data with params:', queryParams.toString()); // Debug
    
            const response = await fetch(`/api/audit-log?${queryParams}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Error fetching audit data');
            }
            
            const data = await response.json();
            console.log('Received audit data:', data); // Debug
    
            if (!data.logs || !Array.isArray(data.logs)) {
                throw new Error('Invalid data format received');
            }
    
            this.renderAuditTable(data.logs);
            this.updatePagination(data.total);
            
        } catch (error) {
            console.error('Error loading audit data:', error);
            this.showError(`Error cargando datos de auditoría: ${error.message}`);
        }
    }
    
    showError(message) {
        // Mejorar la visualización del error
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;
        
        // Insertar al principio de la tabla
        const container = this.tableBody.parentElement.parentElement;
        container.insertBefore(errorDiv, container.firstChild);
        
        // Remover después de 5 segundos
        setTimeout(() => errorDiv.remove(), 5000);
    }
    renderAuditTable(logs) {
        this.tableBody.innerHTML = '';
        
        logs.forEach(log => {
            const row = document.createElement('tr');
            
            // Formatear fecha
            const date = new Date(log.timestamp);
            const formattedDate = date.toLocaleString();
            
            row.innerHTML = `
                <td>${formattedDate}</td>
                <td>${this.formatSource(log.source, log.source_id)}</td>
                <td>${log.ip_address}</td>
                <td>${this.formatEventType(log.event_type)}</td>
                <td>${log.action}</td>
                <td>${log.details}</td>
            `;
            
            this.tableBody.appendChild(row);
        });
    }

    formatSource(source, sourceId) {
        return `${source} ${sourceId ? `(${sourceId})` : ''}`;
    }

    formatEventType(type) {
        const types = {
            'auth': '🔑 Autenticación',
            'traffic': '🚦 Tráfico',
            'error': '⚠️ Error'
        };
        return types[type] || type;
    }

    updatePagination(total) {
        this.totalPages = Math.ceil(total / this.itemsPerPage);
        this.pageInfo.textContent = `Página ${this.currentPage} de ${this.totalPages}`;
        
        // Actualizar estado de botones
        document.getElementById('prevPage').disabled = this.currentPage === 1;
        document.getElementById('nextPage').disabled = this.currentPage === this.totalPages;
    }

    showError(message) {
        // Implementar mostrar error al usuario
        alert(message);
    }
}

// Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    window.auditSystem = new AuditSystem();
});