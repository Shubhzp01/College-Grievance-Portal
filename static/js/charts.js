/**
 * Chart.js Visualizations for Admin Dashboard
 */

document.addEventListener('DOMContentLoaded', function () {
    const statusCanvas = document.getElementById('statusChart');
    const categoryCanvas = document.getElementById('categoryChart');
    const priorityCanvas = document.getElementById('priorityChart');

    if (!statusCanvas || !categoryCanvas) {
        return; // Not on the dashboard page
    }

    // Fetch live dashboard metrics from API endpoint
    fetch('/admin/api/chart-data')
        .then(response => response.json())
        .then(data => {
            // 1. Status Distribution Doughnut Chart
            new Chart(statusCanvas, {
                type: 'doughnut',
                data: {
                    labels: data.status.labels,
                    datasets: [{
                        data: data.status.data,
                        backgroundColor: [
                            '#f59e0b', // Pending (Yellow)
                            '#06b6d4', // Under Review (Cyan)
                            '#3b82f6', // In Progress (Blue)
                            '#10b981', // Resolved (Green)
                            '#ef4444'  // Rejected (Red)
                        ],
                        borderWidth: 2,
                        borderColor: '#ffffff',
                        hoverOffset: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                padding: 15,
                                font: { size: 12, family: "'Segoe UI', sans-serif" }
                            }
                        }
                    },
                    cutout: '65%'
                }
            });

            // 2. Category Breakdown Horizontal Bar Chart
            new Chart(categoryCanvas, {
                type: 'bar',
                data: {
                    labels: data.category.labels,
                    datasets: [{
                        label: 'Total Complaints',
                        data: data.category.data,
                        backgroundColor: '#6366f1',
                        borderRadius: 6,
                        maxBarThickness: 28
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: {
                            beginAtZero: true,
                            ticks: { precision: 0, stepSize: 1 },
                            grid: { color: '#f1f5f9' }
                        },
                        y: {
                            grid: { display: false }
                        }
                    }
                }
            });

            // 3. Priority Breakdown Chart (if canvas present)
            if (priorityCanvas && data.priority) {
                new Chart(priorityCanvas, {
                    type: 'pie',
                    data: {
                        labels: data.priority.labels,
                        datasets: [{
                            data: data.priority.data,
                            backgroundColor: [
                                '#94a3b8', // Low
                                '#38bdf8', // Medium
                                '#f59e0b', // High
                                '#dc2626'  // Urgent
                            ],
                            borderWidth: 2,
                            borderColor: '#ffffff'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: { padding: 12, font: { size: 11 } }
                            }
                        }
                    }
                });
            }
        })
        .catch(error => {
            console.error('Error fetching dashboard chart data:', error);
        });
});
