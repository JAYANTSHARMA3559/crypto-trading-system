# Live Crypto Trading System

A real-time cryptocurrency trading system that ingests live market data from Binance Testnet, aggregates ticks into 1-Minute OHLC candles, runs SMA/EMA trading strategies, and executes sample orders.

## Features

- **Live Market Data**: WebSocket connection to Binance Testnet for real-time price updates
- **OHLC Aggregation**: Builds 1-minute candles from tick data with proper minute-boundary closing
- **Trading Strategy**: SMA/EMA crossover strategy with two risk variants
  - **Variant A**: 15% Stop Loss (tighter, exits faster on loss)
  - **Variant B**: 10% Stop Loss (looser, allows more drawdown)
- **Order Execution**: Market orders via Binance Testnet REST API
- **REST API**: Access trading data via HTTP endpoints
- **WebSocket Server**: Real-time candle and signal broadcasting
- **Trade Logging**: Persistent trade history in JSON format

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Binance Testnet                                  │
│  ┌──────────────────┐              ┌──────────────────┐                 │
│  │ WebSocket Stream │              │    REST API      │                 │
│  └────────┬─────────┘              └────────▲─────────┘                 │
└───────────┼─────────────────────────────────┼───────────────────────────┘
            │                                 │
            ▼                                 │
┌───────────────────┐                         │
│ BinanceStreamClient│                         │
└─────────┬─────────┘                         │
          │                                   │
          ▼                                   │
┌───────────────────┐     ┌─────────────────┐ │
│    TickStore      │────▶│  OHLCAggregator │ │
└───────────────────┘     └────────┬────────┘ │
                                   │          │
                                   ▼          │
                          ┌─────────────────┐ │
                          │ StrategyManager │ │
                          │  ├─ Variant A   │ │
                          │  └─ Variant B   │ │
                          └────────┬────────┘ │
                                   │          │
                                   ▼          │
                          ┌─────────────────┐ │
                          │  OrderExecutor  │─┘
                          │  └─ TradeLogger │
                          └─────────────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │    REST API     │◀──── Clients
                          │  WebSocket API  │◀────
                          └─────────────────┘
```

## Installation

### 1. Clone and navigate to the project
```bash
cd C:\Users\LENOVO\.gemini\antigravity\scratch\crypto_trading_system
```

### 2. Create a virtual environment (recommended)
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure API credentials

1. Get your Binance Testnet API keys from: https://testnet.binance.vision/
2. Copy the environment template:
   ```bash
   copy .env.example .env
   ```
3. Edit `.env` and add your keys:
   ```
   BINANCE_API_KEY=your_api_key_here
   BINANCE_API_SECRET=your_secret_key_here
   ```

## Running the System

```bash
python main.py
```

The system will:
1. Connect to Binance Testnet WebSocket
2. Start streaming BTCUSDT and ETHUSDT prices
3. Aggregate 1-minute OHLC candles
4. Run SMA/EMA strategies for both variants
5. Execute orders when signals occur
6. Start REST API at `http://localhost:8000`
7. Start WebSocket server at `ws://localhost:8001`

## API Documentation

### REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/symbols` | GET | List active symbols |
| `/symbols/{symbol}` | POST | Add a symbol |
| `/symbols/{symbol}` | DELETE | Remove a symbol |
| `/candles/{symbol}` | GET | Get OHLC candle history |
| `/candles` | GET | Get all candles |
| `/positions` | GET | Get all positions |
| `/positions/{symbol}` | GET | Get symbol positions |
| `/trades` | GET | Get trade history |
| `/ticks` | GET | Get latest ticks |
| `/strategy` | GET | Get strategy configuration |

### Interactive API Docs

Visit `http://localhost:8000/docs` for Swagger UI documentation.

### WebSocket Server

Connect to `ws://localhost:8001` to receive real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8001');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'candle') {
        console.log('New candle:', data.data);
    } else if (data.type === 'signal') {
        console.log('Signal:', data.data);
    }
};
```

## Strategy Logic

### SMA/EMA Crossover

The strategy uses a combination of Simple Moving Average (SMA) and Exponential Moving Average (EMA):

- **SMA Period**: 10 (configurable)
- **EMA Period**: 5 (configurable)

**Signals:**
- **BUY**: When EMA crosses above SMA (bullish crossover)
- **SELL**: When EMA crosses below SMA (bearish crossover) OR Stop Loss is triggered

### Risk Variants

| Variant | Stop Loss | Description |
|---------|-----------|-------------|
| A | 15% | Tighter SL - exits faster to limit losses |
| B | 10% | Looser SL - allows more drawdown before exit |

## Configuration

Environment variables (set in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `BINANCE_API_KEY` | - | Binance Testnet API key |
| `BINANCE_API_SECRET` | - | Binance Testnet API secret |
| `SYMBOLS` | BTCUSDT,ETHUSDT | Comma-separated symbols |
| `SMA_PERIOD` | 10 | SMA lookback period |
| `EMA_PERIOD` | 5 | EMA lookback period |
| `VARIANT_A_SL` | 0.15 | Variant A stop loss (15%) |
| `VARIANT_B_SL` | 0.10 | Variant B stop loss (10%) |

## Project Structure

```
crypto_trading_system/
├── main.py                 # Application entry point
├── config.py               # Configuration management
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── trades.json            # Trade history log
│
├── data_ingestion/        # Market data streaming
│   ├── __init__.py
│   ├── binance_stream_client.py
│   └── tick_store.py
│
├── aggregation/           # OHLC candle building
│   ├── __init__.py
│   ├── models.py
│   └── ohlc_aggregator.py
│
├── strategy/              # Trading strategies
│   ├── __init__.py
│   ├── base_strategy.py
│   ├── sma_ema_strategy.py
│   └── strategy_manager.py
│
├── execution/             # Order execution
│   ├── __init__.py
│   ├── binance_order_client.py
│   ├── order_executor.py
│   └── trade_logger.py
│
└── api/                   # REST & WebSocket APIs
    ├── __init__.py
    ├── rest_api.py
    └── websocket_server.py
```

## Testing

### Manual Testing

1. Start the system:
   ```bash
   python main.py
   ```

2. View candles:
   ```bash
   curl http://localhost:8000/candles/BTCUSDT
   ```

3. View positions:
   ```bash
   curl http://localhost:8000/positions
   ```

4. View trade history:
   ```bash
   curl http://localhost:8000/trades
   ```

### WebSocket Test

Use a WebSocket client (like wscat) to connect:
```bash
npx wscat -c ws://localhost:8001
```

## Important Notes

1. **Testnet Only**: This system is configured for Binance Testnet. Do NOT use production API keys.

2. **Sample Order Sizes**: Orders use small dummy sizes:
   - BTC pairs: 0.001 BTC
   - ETH pairs: 0.01 ETH

3. **API Credentials**: Never commit your `.env` file with real credentials.

4. **Graceful Shutdown**: Press `Ctrl+C` to stop the system gracefully.

## License

This project is for educational and testing purposes only.
