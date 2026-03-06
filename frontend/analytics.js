/**
 * Analytics Page - JavaScript
 * 
 * Handles data fetching, chart rendering, and statistics display
 * for the trading analytics page.
 */

// Configuration
const CONFIG = {
    API_BASE: window.location.origin,
    REFRESH_INTERVAL: 30000  // 30 seconds
};

// Charts
let pnlChart = null;
let distributionChart = null;

// =====================================================
// UTILITY FUNCTIONS
// =====================================================

function formatPrice(price) {
    if (!price && price !== 0) return '$0.00';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(price);
}

function formatPercent(value) {
    if (!value && value !== 0) return '0%';
    return `${(value * 100).toFixed(1)}%`;
}

// =====================================================
// API FUNCTIONS
// =====================================================

async function fetchAPI(endpoint) {
    try {
        const response = await fetch(`${CONFIG.API_BASE}${endpoint}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`API Error [${endpoint}]:`, error);
        return null;
    }
}

async function fetchTrades() {
    return await fetchAPI('/trades?limit=500');
}

async function fetchHealth() {
    const data = await fetchAPI('/health');
    updateConnectionStatus(data && data.status === 'healthy');
}

// =====================================================
// UI UPDATE FUNCTIONS
// =====================================================

function updateConnectionStatus(connected) {
    const indicator = document.getElementById('status-indicator');
    const text = indicator.querySelector('.status-text');

    if (connected) {
        indicator.classList.add('connected');
        indicator.classList.remove('disconnected');
        text.textContent = 'Connected';
    } else {
        indicator.classList.remove('connected');
        indicator.classList.add('disconnected');
        text.textContent = 'Disconnected';
    }
}

function updateTime() {
    const timeElement = document.getElementById('time-display');
    const now = new Date();
    timeElement.textContent = now.toLocaleTimeString();
}

function calculateStats(trades) {
    if (!trades || trades.length === 0) {
        return {
            totalTrades: 0,
            totalPnl: 0,
            winRate: 0,
            avgTrade: 0,
            buyCount: 0,
            sellCount: 0,
            winCount: 0,
            lossCount: 0,
            bestTrade: 0,
            worstTrade: 0,
            variantA: { trades: 0, pnl: 0, wins: 0 },
            variantB: { trades: 0, pnl: 0, wins: 0 },
            btc: { trades: 0, pnl: 0, wins: 0 },
            eth: { trades: 0, pnl: 0, wins: 0 },
            pnlHistory: []
        };
    }

    const pnlTrades = trades.filter(t => t.pnl !== null && t.pnl !== undefined);
    const totalPnl = pnlTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
    const winCount = pnlTrades.filter(t => t.pnl > 0).length;
    const lossCount = pnlTrades.filter(t => t.pnl < 0).length;
    const winRate = pnlTrades.length > 0 ? winCount / pnlTrades.length : 0;
    const avgTrade = pnlTrades.length > 0 ? totalPnl / pnlTrades.length : 0;

    const buyCount = trades.filter(t => t.side === 'BUY').length;
    const sellCount = trades.filter(t => t.side === 'SELL').length;

    const bestTrade = pnlTrades.length > 0 ? Math.max(...pnlTrades.map(t => t.pnl)) : 0;
    const worstTrade = pnlTrades.length > 0 ? Math.min(...pnlTrades.map(t => t.pnl)) : 0;

    // Variant stats
    const variantATrades = trades.filter(t => t.variant === 'A');
    const variantBTrades = trades.filter(t => t.variant === 'B');
    const variantAPnl = variantATrades.filter(t => t.pnl).reduce((sum, t) => sum + (t.pnl || 0), 0);
    const variantBPnl = variantBTrades.filter(t => t.pnl).reduce((sum, t) => sum + (t.pnl || 0), 0);
    const variantAWins = variantATrades.filter(t => t.pnl && t.pnl > 0).length;
    const variantBWins = variantBTrades.filter(t => t.pnl && t.pnl > 0).length;

    // Symbol stats
    const btcTrades = trades.filter(t => t.symbol === 'BTCUSDT');
    const ethTrades = trades.filter(t => t.symbol === 'ETHUSDT');
    const btcPnl = btcTrades.filter(t => t.pnl).reduce((sum, t) => sum + (t.pnl || 0), 0);
    const ethPnl = ethTrades.filter(t => t.pnl).reduce((sum, t) => sum + (t.pnl || 0), 0);
    const btcWins = btcTrades.filter(t => t.pnl && t.pnl > 0).length;
    const ethWins = ethTrades.filter(t => t.pnl && t.pnl > 0).length;

    // Cumulative P&L history
    let cumPnl = 0;
    const pnlHistory = trades.map((t, i) => {
        if (t.pnl) cumPnl += t.pnl;
        return { index: i + 1, pnl: cumPnl, timestamp: t.timestamp };
    });

    return {
        totalTrades: trades.length,
        totalPnl,
        winRate,
        avgTrade,
        buyCount,
        sellCount,
        winCount,
        lossCount,
        bestTrade,
        worstTrade,
        variantA: {
            trades: variantATrades.length,
            pnl: variantAPnl,
            wins: variantAWins,
            pnlTrades: variantATrades.filter(t => t.pnl).length
        },
        variantB: {
            trades: variantBTrades.length,
            pnl: variantBPnl,
            wins: variantBWins,
            pnlTrades: variantBTrades.filter(t => t.pnl).length
        },
        btc: {
            trades: btcTrades.length,
            pnl: btcPnl,
            wins: btcWins,
            pnlTrades: btcTrades.filter(t => t.pnl).length
        },
        eth: {
            trades: ethTrades.length,
            pnl: ethPnl,
            wins: ethWins,
            pnlTrades: ethTrades.filter(t => t.pnl).length
        },
        pnlHistory
    };
}

function updateDashboard(stats) {
    // Summary cards
    const totalPnlEl = document.getElementById('total-pnl');
    totalPnlEl.textContent = formatPrice(stats.totalPnl);
    totalPnlEl.style.color = stats.totalPnl >= 0 ? '#10b981' : '#ef4444';

    document.getElementById('total-trades').textContent = stats.totalTrades;
    document.getElementById('win-rate').textContent = formatPercent(stats.winRate);
    document.getElementById('avg-trade').textContent = formatPrice(stats.avgTrade);

    // Trade breakdown
    document.getElementById('buy-count').textContent = stats.buyCount;
    document.getElementById('sell-count').textContent = stats.sellCount;
    document.getElementById('win-count').textContent = stats.winCount;
    document.getElementById('loss-count').textContent = stats.lossCount;
    document.getElementById('best-trade').textContent = formatPrice(stats.bestTrade);
    document.getElementById('worst-trade').textContent = formatPrice(stats.worstTrade);

    // Variant A
    document.getElementById('va-trades').textContent = stats.variantA.trades;
    document.getElementById('va-pnl').textContent = formatPrice(stats.variantA.pnl);
    const vaWinrate = stats.variantA.pnlTrades > 0 ? stats.variantA.wins / stats.variantA.pnlTrades : 0;
    document.getElementById('va-winrate').textContent = formatPercent(vaWinrate);

    // Variant B
    document.getElementById('vb-trades').textContent = stats.variantB.trades;
    document.getElementById('vb-pnl').textContent = formatPrice(stats.variantB.pnl);
    const vbWinrate = stats.variantB.pnlTrades > 0 ? stats.variantB.wins / stats.variantB.pnlTrades : 0;
    document.getElementById('vb-winrate').textContent = formatPercent(vbWinrate);

    // Symbol performance
    document.getElementById('btc-trades').textContent = stats.btc.trades;
    document.getElementById('btc-pnl').textContent = formatPrice(stats.btc.pnl);
    const btcWinrate = stats.btc.pnlTrades > 0 ? stats.btc.wins / stats.btc.pnlTrades : 0;
    document.getElementById('btc-winrate').textContent = formatPercent(btcWinrate);

    document.getElementById('eth-trades').textContent = stats.eth.trades;
    document.getElementById('eth-pnl').textContent = formatPrice(stats.eth.pnl);
    const ethWinrate = stats.eth.pnlTrades > 0 ? stats.eth.wins / stats.eth.pnlTrades : 0;
    document.getElementById('eth-winrate').textContent = formatPercent(ethWinrate);
}

// =====================================================
// CHART FUNCTIONS
// =====================================================

function initCharts() {
    initPnlChart();
    initDistributionChart();
}

function initPnlChart() {
    const ctx = document.getElementById('pnl-chart').getContext('2d');

    pnlChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Cumulative P&L',
                data: [],
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleColor: '#f9fafb',
                    bodyColor: '#9ca3af',
                    borderColor: '#374151',
                    borderWidth: 1,
                    callbacks: {
                        label: function (context) {
                            return `P&L: ${formatPrice(context.raw)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(55, 65, 81, 0.5)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6b7280',
                        maxTicksLimit: 10
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(55, 65, 81, 0.5)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6b7280',
                        callback: function (value) {
                            return formatPrice(value);
                        }
                    }
                }
            }
        }
    });
}

function initDistributionChart() {
    const ctx = document.getElementById('distribution-chart').getContext('2d');

    distributionChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Wins', 'Losses'],
            datasets: [{
                data: [0, 0],
                backgroundColor: ['#10b981', '#ef4444'],
                borderColor: '#111827',
                borderWidth: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#9ca3af',
                        padding: 20,
                        usePointStyle: true
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleColor: '#f9fafb',
                    bodyColor: '#9ca3af',
                    borderColor: '#374151',
                    borderWidth: 1
                }
            }
        }
    });
}

function updateCharts(stats) {
    // Update P&L chart
    if (pnlChart && stats.pnlHistory.length > 0) {
        pnlChart.data.labels = stats.pnlHistory.map((_, i) => `Trade ${i + 1}`);
        pnlChart.data.datasets[0].data = stats.pnlHistory.map(h => h.pnl);

        // Change color based on final P&L
        const finalPnl = stats.pnlHistory[stats.pnlHistory.length - 1]?.pnl || 0;
        const color = finalPnl >= 0 ? '#10b981' : '#ef4444';
        const bgColor = finalPnl >= 0 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)';
        pnlChart.data.datasets[0].borderColor = color;
        pnlChart.data.datasets[0].backgroundColor = bgColor;

        pnlChart.update('none');
    }

    // Update distribution chart
    if (distributionChart) {
        distributionChart.data.datasets[0].data = [stats.winCount, stats.lossCount];
        distributionChart.update('none');
    }
}

// =====================================================
// MAIN
// =====================================================

async function loadData() {
    const data = await fetchTrades();
    if (data && data.trades) {
        const stats = calculateStats(data.trades);
        updateDashboard(stats);
        updateCharts(stats);
    }
}

async function init() {
    // Initial data load
    await fetchHealth();
    await loadData();

    // Initialize charts
    initCharts();

    // Load data again after charts init
    await loadData();

    // Start time updates
    updateTime();
    setInterval(updateTime, 1000);

    // Periodic data refresh
    setInterval(loadData, CONFIG.REFRESH_INTERVAL);
    setInterval(fetchHealth, 10000);
}

// Start application
document.addEventListener('DOMContentLoaded', init);
