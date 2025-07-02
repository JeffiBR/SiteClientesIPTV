// Dashboard JavaScript functionality

// Chart configurations
let categoryChart, revenueChart;

function initializeCharts(data) {
    // Category Distribution Chart
    const categoryCtx = document.getElementById('categoryChart');
    if (categoryCtx) {
        categoryChart = new Chart(categoryCtx, {
            type: 'doughnut',
            data: {
                labels: ['IPTV', 'VPN'],
                datasets: [{
                    data: [data.iptv_count, data.vpn_count],
                    backgroundColor: [
                        '#0dcaf0', // info color for IPTV
                        '#6c757d'  // secondary color for VPN
                    ],
                    borderColor: [
                        '#0dcaf0',
                        '#6c757d'
                    ],
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#ffffff',
                            font: {
                                size: 12
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.parsed;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((value / total) * 100).toFixed(1);
                                return `${label}: ${value} clientes (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    // Revenue Chart
    const revenueCtx = document.getElementById('revenueChart');
    if (revenueCtx) {
        revenueChart = new Chart(revenueCtx, {
            type: 'bar',
            data: {
                labels: ['IPTV', 'VPN'],
                datasets: [{
                    label: 'Receita (R$)',
                    data: [data.iptv_value, data.vpn_value],
                    backgroundColor: [
                        'rgba(13, 202, 240, 0.8)', // info color with transparency
                        'rgba(108, 117, 125, 0.8)'  // secondary color with transparency
                    ],
                    borderColor: [
                        '#0dcaf0',
                        '#6c757d'
                    ],
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `${context.label}: R$ ${context.parsed.y.toFixed(2)}`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: '#ffffff',
                            callback: function(value) {
                                return 'R$ ' + value.toFixed(2);
                            }
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    },
                    x: {
                        ticks: {
                            color: '#ffffff'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    }
                }
            }
        });
    }
}

// Auto-refresh dashboard data
function refreshDashboardData() {
    fetch('/api/dashboard-data')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error loading dashboard data:', data.error);
                return;
            }

            // Update statistics cards
            updateStatisticsCards(data);

            // Update charts
            updateCharts(data);
        })
        .catch(error => {
            console.error('Error fetching dashboard data:', error);
        });
}

function updateStatisticsCards(data) {
    // Update card values
    const totalClientsElement = document.querySelector('.card.bg-primary .card-text');
    const totalValueElement = document.querySelector('.card.bg-success .card-text');
    const iptvElement = document.querySelector('.card.bg-info .card-text');
    const vpnElement = document.querySelector('.card.bg-warning .card-text');

    if (totalClientsElement) {
        totalClientsElement.textContent = data.total_clients;
    }

    if (totalValueElement) {
        totalValueElement.textContent = `R$ ${data.total_value.toFixed(2)}`;
    }

    if (iptvElement) {
        iptvElement.textContent = data.iptv_count;
        const iptvSmall = iptvElement.parentElement.querySelector('small');
        if (iptvSmall) {
            iptvSmall.textContent = `R$ ${data.iptv_value.toFixed(2)}`;
        }
    }

    if (vpnElement) {
        vpnElement.textContent = data.vpn_count;
        const vpnSmall = vpnElement.parentElement.querySelector('small');
        if (vpnSmall) {
            vpnSmall.textContent = `R$ ${data.vpn_value.toFixed(2)}`;
        }
    }
}

function updateCharts(data) {
    // Update category chart
    if (categoryChart) {
        categoryChart.data.datasets[0].data = [data.iptv_count, data.vpn_count];
        categoryChart.update();
    }

    // Update revenue chart
    if (revenueChart) {
        revenueChart.data.datasets[0].data = [data.iptv_value, data.vpn_value];
        revenueChart.update();
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Set up auto-refresh every 30 seconds
    setInterval(refreshDashboardData, 30000);

    // Add smooth animations to cards
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
});

// Format currency values
function formatCurrency(value) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(value);
}

// Format dates
function formatDate(dateString) {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    }).format(date);
}

// Show loading state
function showLoading(element) {
    if (element) {
        element.classList.add('loading');
    }
}

// Hide loading state
function hideLoading(element) {
    if (element) {
        element.classList.remove('loading');
    }
}

// Export dashboard data (future feature)
function exportDashboardData() {
    fetch('/api/dashboard-data')
        .then(response => response.json())
        .then(data => {
            const exportData = {
                export_date: new Date().toISOString(),
                statistics: data,
                timestamp: Date.now()
            };

            const blob = new Blob([JSON.stringify(exportData, null, 2)], {
                type: 'application/json'
            });

            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `dashboard-export-${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        })
        .catch(error => {
            console.error('Error exporting data:', error);
            alert('Erro ao exportar dados');
        });
}
