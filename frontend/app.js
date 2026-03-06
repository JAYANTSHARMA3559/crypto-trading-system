/**
 * Crypto Trading Dashboard - Main Application
 * 
 * Handles API integration, real-time updates, and chart rendering
 * for the crypto trading system frontend.
 */

// Configuration
const CONFIG = {
    API_BASE: window.location.origin,
    // Use /ws endpoint on same host - works for both local dev and production
    WS_URL: `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`,
    REFRESH_INTERVAL: 2000,  // 2 seconds
    CHART_CANDLES: 50
};

// State
const state = {
    selectedSymbol: 'BTCUSDT',
    prices: {},
    previousPrices: {},
    positions: {},
    chart: null,
    wsConnected: false
};

// =====================================================
// UTILITY FUNCTIONS
// =====================================================

function formatPrice(price) {
    if (!price || price === 0) return '--,---.--';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(price);
}

function formatPriceNumber(price) {
    if (!price || price === 0) return '--,---.--';
    return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(price);
}

function formatQuantity(qty) {
    if (!qty) return '0.000';
    return qty.toFixed(6);
}

function formatPercent(value) {
    if (!value && value !== 0) return '0.00%';
    const sign = value >= 0 ? '+' : '';
    return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatTime(isoString) {
    if (!isoString) return '--:--:--';
    const date = new Date(isoString);
    return date.toLocaleTimeString();
}

function formatDate(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleString();
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

async function fetchTicks() {
    const data = await fetchAPI('/ticks');
    if (data) {
        state.previousPrices = { ...state.prices };

        for (const [symbol, tick] of Object.entries(data)) {
            state.prices[symbol] = tick.price;
        }
        updatePriceTickers();
    }
}

async function fetchCandles(symbol) {
    const data = await fetchAPI(`/candles/${symbol}?limit=${CONFIG.CHART_CANDLES}`);
    if (data && data.history) {
        updateChart(data.history, data.current);
    }
}

async function fetchPositions() {
    const data = await fetchAPI('/positions');
    if (data && data.positions) {
        state.positions = data.positions;
        updatePositionCards(data);
        updateIndicators(data);
    }
}

async function fetchTrades() {
    const symbolFilter = document.getElementById('filter-symbol').value;
    const variantFilter = document.getElementById('filter-variant').value;

    let endpoint = '/trades?limit=50';
    if (symbolFilter) endpoint += `&symbol=${symbolFilter}`;
    if (variantFilter) endpoint += `&variant=${variantFilter}`;

    const data = await fetchAPI(endpoint);
    if (data) {
        updateTradeHistory(data.trades, data.summary);
    }
}

async function fetchSystemHealth() {
    const data = await fetchAPI('/health');
    if (data && data.status === 'healthy') {
        updateConnectionStatus(true);
    } else {
        updateConnectionStatus(false);
    }
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

function updatePriceTickers() {
    // BTC
    const btcPrice = state.prices['BTCUSDT'];
    const prevBtcPrice = state.previousPrices['BTCUSDT'];
    const btcElement = document.getElementById('btc-price');

    if (btcPrice) {
        btcElement.textContent = formatPriceNumber(btcPrice);

        // Flash animation
        if (prevBtcPrice && btcPrice !== prevBtcPrice) {
            btcElement.classList.remove('flash-up', 'flash-down');
            btcElement.classList.add(btcPrice > prevBtcPrice ? 'flash-up' : 'flash-down');
            setTimeout(() => btcElement.classList.remove('flash-up', 'flash-down'), 500);
        }
    }

    // ETH
    const ethPrice = state.prices['ETHUSDT'];
    const prevEthPrice = state.previousPrices['ETHUSDT'];
    const ethElement = document.getElementById('eth-price');

    if (ethPrice) {
        ethElement.textContent = formatPriceNumber(ethPrice);

        if (prevEthPrice && ethPrice !== prevEthPrice) {
            ethElement.classList.remove('flash-up', 'flash-down');
            ethElement.classList.add(ethPrice > prevEthPrice ? 'flash-up' : 'flash-down');
            setTimeout(() => ethElement.classList.remove('flash-up', 'flash-down'), 500);
        }
    }
}

function updatePositionCards(data) {
    const symbol = state.selectedSymbol;
    const symbolPositions = data.positions[symbol] || {};

    // Update Variant A
    updatePositionCard('a', symbolPositions['A'], symbol);

    // Update Variant B
    updatePositionCard('b', symbolPositions['B'], symbol);
}

function updatePositionCard(variant, posData, symbol) {
    const prefix = `pos-${variant}`;
    const card = document.getElementById(`position-${variant}`);

    if (!posData || !posData.position) {
        document.getElementById(`${prefix}-symbol`).textContent = symbol;
        document.getElementById(`${prefix}-side`).textContent = 'FLAT';
        document.getElementById(`${prefix}-side`).className = 'position-side flat';
        return;
    }

    const pos = posData.position;

    document.getElementById(`${prefix}-symbol`).textContent = pos.symbol || symbol;

    const sideElement = document.getElementById(`${prefix}-side`);
    sideElement.textContent = pos.side || 'FLAT';
    sideElement.className = `position-side ${(pos.side || 'flat').toLowerCase()}`;

    document.getElementById(`${prefix}-entry`).textContent = formatPrice(pos.entry_price);
    document.getElementById(`${prefix}-current`).textContent = formatPrice(pos.current_price);
    document.getElementById(`${prefix}-sl`).textContent = formatPrice(pos.stop_loss_price);
    document.getElementById(`${prefix}-qty`).textContent = formatQuantity(pos.quantity);

    // P&L
    const pnlContainer = document.getElementById(`${prefix}-pnl`);
    const pnlValue = pnlContainer.querySelector('.pnl-value');
    const pnl = pos.unrealized_pnl || 0;

    pnlValue.textContent = formatPrice(pnl);
    pnlContainer.classList.remove('positive', 'negative');
    if (pnl > 0) pnlContainer.classList.add('positive');
    else if (pnl < 0) pnlContainer.classList.add('negative');
}

function updateIndicators(data) {
    const symbol = state.selectedSymbol;
    const symbolPositions = data.positions[symbol] || {};

    // Get indicators from Variant A (same for both)
    const variantA = symbolPositions['A'];
    if (variantA && variantA.indicators) {
        const sma = variantA.indicators.sma;
        const ema = variantA.indicators.ema;

        document.getElementById('sma-value').textContent = sma ? formatPriceNumber(sma) : '--';
        document.getElementById('ema-value').textContent = ema ? formatPriceNumber(ema) : '--';

        // Determine signal based on EMA vs SMA
        const signalElement = document.getElementById('signal-value');
        if (sma && ema) {
            if (ema > sma) {
                signalElement.textContent = 'BUY';
                signalElement.className = 'signal-badge buy';
            } else if (ema < sma) {
                signalElement.textContent = 'SELL';
                signalElement.className = 'signal-badge sell';
            } else {
                signalElement.textContent = 'HOLD';
                signalElement.className = 'signal-badge';
            }
        }
    }
}

function updateTradeHistory(trades, summary) {
    const tbody = document.getElementById('trades-body');

    if (!trades || trades.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="6">No trades yet</td>
            </tr>
        `;
    } else {
        tbody.innerHTML = trades.reverse().map(trade => `
            <tr>
                <td>${formatTime(trade.timestamp)}</td>
                <td>${trade.symbol}</td>
                <td class="${trade.side.toLowerCase()}">${trade.side}</td>
                <td>${formatQuantity(trade.size)}</td>
                <td>${formatPrice(trade.price)}</td>
                <td class="${trade.pnl > 0 ? 'buy' : trade.pnl < 0 ? 'sell' : ''}">${trade.pnl ? formatPrice(trade.pnl) : '-'}</td>
            </tr>
        `).join('');
    }

    // Update summary
    if (summary) {
        document.getElementById('total-trades').textContent = summary.total_trades || 0;
        document.getElementById('win-rate').textContent = `${((summary.win_rate || 0) * 100).toFixed(0)}%`;
        document.getElementById('total-pnl').textContent = formatPrice(summary.total_pnl || 0);
    }
}

function updateTime() {
    const timeElement = document.getElementById('time-display');
    const now = new Date();
    timeElement.textContent = now.toLocaleTimeString() + ' UTC' + (now.getTimezoneOffset() / -60);
}

// =====================================================
// CHART FUNCTIONS
// =====================================================

function initChart() {
    const ctx = document.getElementById('price-chart').getContext('2d');

    state.chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Close Price',
                    data: [],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.1,
                    pointRadius: 0,
                    pointHoverRadius: 4
                },
                {
                    label: 'High',
                    data: [],
                    borderColor: 'rgba(16, 185, 129, 0.5)',
                    borderWidth: 1,
                    fill: false,
                    tension: 0.1,
                    pointRadius: 0,
                    borderDash: [5, 5]
                },
                {
                    label: 'Low',
                    data: [],
                    borderColor: 'rgba(239, 68, 68, 0.5)',
                    borderWidth: 1,
                    fill: false,
                    tension: 0.1,
                    pointRadius: 0,
                    borderDash: [5, 5]
                }
            ]
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
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#8b949e',
                        usePointStyle: true
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(22, 27, 34, 0.9)',
                    titleColor: '#f0f6fc',
                    bodyColor: '#8b949e',
                    borderColor: 'rgba(48, 54, 61, 0.8)',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(48, 54, 61, 0.5)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6e7681',
                        maxTicksLimit: 8
                    }
                },
                y: {
                    position: 'right',
                    grid: {
                        color: 'rgba(48, 54, 61, 0.5)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6e7681',
                        callback: value => '$' + value.toLocaleString()
                    }
                }
            }
        }
    });
}

function updateChart(history, current) {
    if (!state.chart || !history) return;

    const allCandles = [...history];
    if (current) allCandles.push(current);

    const labels = allCandles.map(c => {
        const date = new Date(c.timestamp);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });

    const closes = allCandles.map(c => c.close);
    const highs = allCandles.map(c => c.high);
    const lows = allCandles.map(c => c.low);

    state.chart.data.labels = labels;
    state.chart.data.datasets[0].data = closes;
    state.chart.data.datasets[1].data = highs;
    state.chart.data.datasets[2].data = lows;

    state.chart.update('none');
}

// =====================================================
// WEBSOCKET
// =====================================================

function connectWebSocket() {
    try {
        const ws = new WebSocket(CONFIG.WS_URL);

        ws.onopen = () => {
            console.log('WebSocket connected');
            state.wsConnected = true;
            document.getElementById('ws-status').textContent = 'WebSocket: Connected';
            document.getElementById('ws-status').classList.add('connected');
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (e) {
                console.error('WebSocket message parse error:', e);
            }
        };

        ws.onclose = () => {
            console.log('WebSocket disconnected');
            state.wsConnected = false;
            document.getElementById('ws-status').textContent = 'WebSocket: Disconnected';
            document.getElementById('ws-status').classList.remove('connected');

            // Reconnect after 5 seconds
            setTimeout(connectWebSocket, 5000);
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    } catch (e) {
        console.error('WebSocket connection failed:', e);
        setTimeout(connectWebSocket, 5000);
    }
}

function handleWebSocketMessage(data) {
    if (data.type === 'candle') {
        // Real-time candle update
        if (data.symbol === state.selectedSymbol) {
            fetchCandles(state.selectedSymbol);
        }
    } else if (data.type === 'signal') {
        // Trading signal
        console.log('Signal received:', data);
        fetchTrades();
        fetchPositions();
    }
}

// =====================================================
// EVENT HANDLERS
// =====================================================

function setupEventListeners() {
    // Chart symbol buttons
    document.querySelectorAll('.tab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.selectedSymbol = btn.dataset.symbol;
            fetchCandles(state.selectedSymbol);
            fetchPositions();
        });
    });

    // Trade filters
    document.getElementById('filter-symbol').addEventListener('change', fetchTrades);
    document.getElementById('filter-variant').addEventListener('change', fetchTrades);

    // Trading buttons
    document.getElementById('btn-buy').addEventListener('click', () => executeTrade('BUY'));
    document.getElementById('btn-sell').addEventListener('click', () => executeTrade('SELL'));
}

// =====================================================
// MANUAL TRADING
// =====================================================

async function executeTrade(side) {
    const symbol = document.getElementById('trade-symbol').value;
    const variant = document.getElementById('trade-variant').value;
    const quantity = parseFloat(document.getElementById('trade-quantity').value);

    const statusEl = document.getElementById('trading-status');
    const buyBtn = document.getElementById('btn-buy');
    const sellBtn = document.getElementById('btn-sell');

    // Disable buttons during trade
    buyBtn.disabled = true;
    sellBtn.disabled = true;

    // Show loading state
    statusEl.textContent = `Placing ${side} order...`;
    statusEl.className = 'trading-status loading';

    try {
        const response = await fetch(`${CONFIG.API_BASE}/trade?symbol=${symbol}&side=${side}&variant=${variant}&quantity=${quantity}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok && data.success) {
            statusEl.textContent = `✅ ${side} ${quantity} ${symbol} @ ${formatPrice(data.trade.price)} (Variant ${variant})`;
            statusEl.className = 'trading-status success';

            // Refresh data
            await fetchPositions();
            await fetchTrades();
        } else {
            statusEl.textContent = `❌ Error: ${data.detail || 'Trade failed'}`;
            statusEl.className = 'trading-status error';
        }
    } catch (error) {
        console.error('Trade error:', error);
        statusEl.textContent = `❌ Error: ${error.message}`;
        statusEl.className = 'trading-status error';
    } finally {
        // Re-enable buttons
        buyBtn.disabled = false;
        sellBtn.disabled = false;

        // Clear status after 5 seconds
        setTimeout(() => {
            statusEl.textContent = '';
            statusEl.className = 'trading-status';
        }, 5000);
    }
}

// =====================================================
// INITIALIZATION
// =====================================================

async function init() {
    console.log('Initializing Crypto Trading Dashboard...');

    // Setup event listeners
    setupEventListeners();

    // Initialize chart
    initChart();

    // Initial data fetch
    await fetchSystemHealth();
    await fetchTicks();
    await fetchCandles(state.selectedSymbol);
    await fetchPositions();
    await fetchTrades();

    // Update time
    updateTime();
    setInterval(updateTime, 1000);

    // Start refresh loop
    setInterval(async () => {
        await fetchTicks();
        await fetchPositions();
    }, CONFIG.REFRESH_INTERVAL);

    // Fetch candles less frequently
    setInterval(() => fetchCandles(state.selectedSymbol), 5000);

    // Fetch trades less frequently
    setInterval(fetchTrades, 10000);

    // Health check
    setInterval(fetchSystemHealth, 30000);

    // Connect WebSocket
    connectWebSocket();

    console.log('Dashboard initialized!');
}

// Start the application
document.addEventListener('DOMContentLoaded', init);
