# Turtle Trading Bot - Full-Stack Application

A modern, full-stack trading bot implementing the Turtle Trading methodology with FastAPI backend and React frontend.

## 🏗️ Architecture

```
turtle-trading-platform/
├── api/                              # FastAPI Backend
│   ├── app/
│   │   ├── routers/                  # API endpoints
│   │   ├── models/                   # Pydantic models
│   │   ├── services/                 # Business logic
│   │   ├── core/                     # Core utilities
│   │   └── main.py                   # FastAPI app
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                         # React Frontend
│   ├── src/
│   │   ├── components/               # React components
│   │   ├── services/                 # API clients
│   │   ├── stores/                   # State management
│   │   ├── types/                    # TypeScript types
│   │   └── App.tsx
│   ├── package.json
│   └── Dockerfile
├── data/                             # Data storage
├── docker-compose.yml               # Development setup
└── README-fullstack.md
```

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Node.js 18+ (for local development)
- Python 3.11+ (for local development)

### Development with Docker

1. **Clone and setup**
   ```bash
   cd turtle-trading-platform
   cp .env.example .env
   ```

2. **Start all services**
   ```bash
   docker-compose up -d
   ```

3. **Access the application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/api/docs

### Local Development

#### Backend (FastAPI)
```bash
cd api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

#### Frontend (React)
```bash
cd frontend
npm install
npm run dev
```

## 🔧 Technology Stack

### Backend
- **FastAPI** - Modern, fast web framework
- **Pydantic** - Data validation and serialization
- **SQLAlchemy** - Database ORM
- **WebSockets** - Real-time communication
- **Pandas** - Data analysis

### Frontend
- **React 18** with TypeScript
- **Vite** - Build tool and dev server
- **Zustand** - State management
- **React Query** - API state management
- **Tailwind CSS** - Styling
- **Chart.js** - Data visualization

## 📡 API Endpoints

### Charts
- `GET /api/charts` - List chart files
- `GET /api/charts/{filename}` - Get chart data
- `POST /api/charts/download` - Download new data
- `POST /api/charts/resample` - Resample timeframe

### Strategies
- `GET /api/strategies` - List strategies
- `POST /api/strategies` - Create strategy
- `POST /api/strategies/{name}/backtest` - Run backtest

### Trading
- `GET /api/trading/trades` - Get trades
- `POST /api/trading/trades` - Create trade
- `WebSocket /api/trading/ws` - Real-time updates

### Portfolio
- `GET /api/portfolio` - Get portfolios
- `GET /api/portfolio/{id}/summary` - Portfolio metrics
- `GET /api/portfolio/{id}/performance` - Performance data

### Market Data
- `GET /api/market-data/pairs/crypto` - Crypto pairs
- `POST /api/market-data/download/crypto` - Download crypto data
- `POST /api/market-data/download/forex` - Download forex data

## 🔄 Real-time Features

The application supports real-time updates via WebSockets:
- Live trading signals
- Portfolio updates
- Trade execution notifications
- Price updates

## 🛠️ Development

### Adding New Features

1. **Backend**: Add models, services, and routers
2. **Frontend**: Create components and connect to API
3. **Types**: Update TypeScript types to match Pydantic models

### Database Migrations

```bash
cd api
alembic revision --autogenerate -m "Description"
alembic upgrade head
```

### Testing

```bash
# Backend
cd api
pytest

# Frontend
cd frontend
npm test
```

## 🐳 Docker Services

- **api**: FastAPI backend service
- **frontend**: React frontend service
- **redis**: Caching and WebSocket management
- **postgres**: Production database (optional)

## 📊 Features

### Data Management
- Historical data download (Crypto/Forex)
- Multiple timeframe support
- Data resampling and validation

### Portfolio Management
- Multi-portfolio support
- Real-time P&L tracking
- Risk management metrics
- Performance analytics

### Trading Strategies
- Turtle Trading implementation
- Strategy backtesting
- Custom strategy creation
- Signal generation and tracking

### User Interface
- Interactive charts
- Real-time dashboard
- Trading interface
- Portfolio analytics

## 🔐 Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# Database
DATABASE_URL=sqlite:///./data/turtle_trading.db

# API Keys
ALPHA_VANTAGE_API_KEY=your_key_here

# CORS
ALLOWED_ORIGINS=http://localhost:3000

# Portfolio Defaults
DEFAULT_PORTFOLIO_BALANCE=100000.0
DEFAULT_PORTFOLIO_CURRENCY=USD
```

## 📈 Migration from Legacy

This full-stack version replaces the Streamlit monolith with:
- Separated backend/frontend architecture
- RESTful API design
- Modern React UI
- Real-time WebSocket communication
- Better state management
- Improved performance and scalability

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## 📝 License

This project is licensed under the MIT License.