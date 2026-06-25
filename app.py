from flask import Flask, jsonify, render_template, request
import ccxt
import pandas as pd
import time
import urllib.parse
import threading

app = Flask(__name__)

# ==========================================
# وضعیت ۲ اسکنر (فقط Trend)
# ==========================================
futures_trend_status = {
    "running": False, "progress": 0, "results": [], "error": None, "total": 0
}
spot_trend_status = {
    "running": False, "progress": 0, "results": [], "error": None, "total": 0
}

# ==========================================
# توابع کمکی
# ==========================================

def calculate_ema(data, period):
    """محاسبه EMA"""
    return data.ewm(span=period, adjust=False).mean()

def get_tradingview_link(symbol):
    """ساخت لینک TradingView برای هر ارز"""
    base = symbol.split('/')[0]
    tv_symbol = f":{base}USDT"
    encoded_symbol = urllib.parse.quote(tv_symbol)
    return f"https://www.tradingview.com/chart/?symbol={encoded_symbol}"

def get_futures_pairs():
    """دریافت لیست تمام جفت‌ارزهای فعال فیوچرز XT"""
    exchange = ccxt.xt({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    markets = exchange.load_markets()
    futures_pairs = [
        symbol for symbol, market in markets.items()
        if market['swap'] and market['active']
    ]
    return exchange, futures_pairs

def get_spot_pairs():
    """دریافت لیست تمام جفت‌ارزهای فعال اسپات XT"""
    exchange = ccxt.xt({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    markets = exchange.load_markets()
    spot_pairs = [
        symbol for symbol, market in markets.items()
        if market['spot'] and market['active'] and symbol.endswith('/USDT')
    ]
    return exchange, spot_pairs

# ==========================================
# STRATEGY 1: FUTURES BULLISH TREND
# D1: Price > EMA(50)
# H1: Price > EMA(50) > EMA(200)
# ==========================================

def scan_futures_trend():
    global futures_trend_status
    futures_trend_status = {
        "running": True, "progress": 0, "results": [], "error": None, "total": 0
    }

    try:
        exchange, futures_pairs = get_futures_pairs()
        total = len(futures_pairs)
        futures_trend_status['total'] = total
        results = []

        for i, symbol in enumerate(futures_pairs):
            if not futures_trend_status['running']:
                break

            futures_trend_status['progress'] = int((i / total) * 100)

            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                if len(ohlcv_1d) < 50:
                    continue

                df_1d = pd.DataFrame(
                    ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                current_price = df_1d['close'].iloc[-1]
                ema50_1d = calculate_ema(df_1d['close'], 50).iloc[-1]

                if current_price <= ema50_1d:
                    continue

                ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
                if len(ohlcv_1h) < 200:
                    continue

                df_1h = pd.DataFrame(
                    ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                ema50_1h = calculate_ema(df_1h['close'], 50).iloc[-1]
                ema200_1h = calculate_ema(df_1h['close'], 200).iloc[-1]

                if current_price > ema50_1h > ema200_1h:
                    distance_pct = ((current_price - ema50_1d) / ema50_1d) * 100
                    tv_link = get_tradingview_link(symbol)

                    results.append({
                        'Symbol': symbol,
                        'Price ($)': round(current_price, 8),
                        'EMA(50)': round(ema50_1d, 8),
                        'Distance %': round(distance_pct, 2),
                        'TradingView Link': tv_link
                    })

                time.sleep(0.2)
            except Exception:
                continue

        results.sort(key=lambda x: x['Distance %'], reverse=True)
        futures_trend_status['results'] = results
        futures_trend_status['progress'] = 100

    except Exception as e:
        futures_trend_status['error'] = str(e)
    finally:
        futures_trend_status['running'] = False

# ==========================================
# STRATEGY 2: SPOT BULLISH TREND
# D1: Price > EMA(50)
# H1: Price > EMA(50) > EMA(200)
# ==========================================

def scan_spot_trend():
    global spot_trend_status
    spot_trend_status = {
        "running": True, "progress": 0, "results": [], "error": None, "total": 0
    }

    try:
        exchange, spot_pairs = get_spot_pairs()
        total = len(spot_pairs)
        spot_trend_status['total'] = total
        results = []

        for i, symbol in enumerate(spot_pairs):
            if not spot_trend_status['running']:
                break

            spot_trend_status['progress'] = int((i / total) * 100)

            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                if len(ohlcv_1d) < 50:
                    continue

                df_1d = pd.DataFrame(
                    ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                current_price = df_1d['close'].iloc[-1]
                ema50_1d = calculate_ema(df_1d['close'], 50).iloc[-1]

                if current_price <= ema50_1d:
                    continue

                ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
                if len(ohlcv_1h) < 200:
                    continue

                df_1h = pd.DataFrame(
                    ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                ema50_1h = calculate_ema(df_1h['close'], 50).iloc[-1]
                ema200_1h = calculate_ema(df_1h['close'], 200).iloc[-1]

                if current_price > ema50_1h > ema200_1h:
                    distance_pct = ((current_price - ema50_1d) / ema50_1d) * 100
                    tv_link = get_tradingview_link(symbol)

                    results.append({
                        'Symbol': symbol,
                        'Price ($)': round(current_price, 8),
                        'EMA(50)': round(ema50_1d, 8),
                        'Distance %': round(distance_pct, 2),
                        'TradingView Link': tv_link
                    })

                time.sleep(0.2)
            except Exception:
                continue

        results.sort(key=lambda x: x['Distance %'], reverse=True)
        spot_trend_status['results'] = results
        spot_trend_status['progress'] = 100

    except Exception as e:
        spot_trend_status['error'] = str(e)
    finally:
        spot_trend_status['running'] = False

# ==========================================
# EMA CROSSOVER DETECTION (5m Timeframe)
# برای Futures و Spot - فقط ارزهای ارسالی از n8n
# ==========================================

def detect_ema_crossovers(symbols, market_type='futures'):
    """
    بررسی تقاطع EMA50 و EMA200 در تایم‌فریم 5 دقیقه
    فقط برای ارزهای مشخص‌شده
    
    Parameters:
    - symbols: لیست symbols به فرمت ['BTC/USDT:USDT', 'ETH/USDT:USDT', ...]
    - market_type: 'futures' یا 'spot'
    """
    try:
        if market_type == 'futures':
            exchange = ccxt.xt({
                'enableRateLimit': True,
                'options': {'defaultType': 'swap'}
            })
        else:
            exchange = ccxt.xt({
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            })
        
        crossovers = []
        total = len(symbols)
        
        for i, symbol in enumerate(symbols):
            try:
                # دریافت OHLCV 5 دقیقه (250 کندل برای محاسبه EMA200)
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=250)
                
                if len(ohlcv) < 200:
                    continue
                
                df = pd.DataFrame(
                    ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                
                # محاسبه EMA
                ema50 = calculate_ema(df['close'], 50)
                ema200 = calculate_ema(df['close'], 200)
                
                # بررسی crossover در 2 کندل آخر
                current_ema50 = ema50.iloc[-1]
                current_ema200 = ema200.iloc[-1]
                prev_ema50 = ema50.iloc[-2]
                prev_ema200 = ema200.iloc[-2]
                
                # Bullish crossover: EMA50 crosses above EMA200
                bullish_cross = prev_ema50 <= prev_ema200 and current_ema50 > current_ema200
                
                # Bearish crossover: EMA50 crosses below EMA200
                bearish_cross = prev_ema50 >= prev_ema200 and current_ema50 < current_ema200
                
                if bullish_cross or bearish_cross:
                    current_price = df['close'].iloc[-1]
                    cross_type = 'BULLISH' if bullish_cross else 'BEARISH'
                    
                    crossovers.append({
                        'symbol': symbol,
                        'cross_type': cross_type,
                        'price': round(current_price, 8),
                        'ema50': round(current_ema50, 8),
                        'ema200': round(current_ema200, 8),
                        'timestamp': pd.Timestamp.now().isoformat(),
                        'tradingview_link': get_tradingview_link(symbol)
                    })
                
                time.sleep(0.15)  # Rate limiting
                
            except Exception as e:
                print(f"Error checking {symbol}: {e}")
                continue
        
        return crossovers
        
    except Exception as e:
        return {'error': str(e)}

# ==========================================
# ROUTES
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

# ===== Strategy 1: Futures Bullish Trend =====
@app.route('/start_futures_trend')
def start_futures_trend():
    if futures_trend_status['running']:
        return jsonify({"status": "already_running"})
    thread = threading.Thread(target=scan_futures_trend)
    thread.daemon = True
    thread.start()
    return jsonify({"status": "started"})

@app.route('/futures_status_trend')
def futures_status_trend_endpoint():
    return jsonify(futures_trend_status)

# ===== Strategy 2: Spot Bullish Trend =====
@app.route('/start_spot_trend')
def start_spot_trend():
    if spot_trend_status['running']:
        return jsonify({"status": "already_running"})
    thread = threading.Thread(target=scan_spot_trend)
    thread.daemon = True
    thread.start()
    return jsonify({"status": "started"})

@app.route('/spot_status_trend')
def spot_status_trend_endpoint():
    return jsonify(spot_trend_status)

# ===== API Endpoint 1: Futures Crossover (از n8n) =====
@app.route('/api/futures_crossover', methods=['POST'])
def api_futures_crossover():
    """
    بررسی تقاطع EMA برای ارزهای خاص در فیوچرز
    Input: {"symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT", ...]}
    Output: {"crossovers": [...], "count": N}
    """
    data = request.get_json()
    
    if not data or 'symbols' not in data:
        return jsonify({"error": "symbols list is required"}), 400
    
    symbols = data['symbols']
    
    if not isinstance(symbols, list) or len(symbols) == 0:
        return jsonify({"error": "symbols must be a non-empty list"}), 400
    
    print(f"Checking {len(symbols)} symbols for futures crossover...")
    crossovers = detect_ema_crossovers(symbols, market_type='futures')
    
    return jsonify({
        "crossovers": crossovers,
        "count": len(crossovers) if isinstance(crossovers, list) else 0,
        "timestamp": pd.Timestamp.now().isoformat()
    })

# ===== API Endpoint 2: Spot Crossover (از n8n) =====
@app.route('/api/spot_crossover', methods=['POST'])
def api_spot_crossover():
    """
    بررسی تقاطع EMA برای ارزهای خاص در اسپات
    Input: {"symbols": ["BTC/USDT", "ETH/USDT", ...]}
    Output: {"crossovers": [...], "count": N}
    """
    data = request.get_json()
    
    if not data or 'symbols' not in data:
        return jsonify({"error": "symbols list is required"}), 400
    
    symbols = data['symbols']
    
    if not isinstance(symbols, list) or len(symbols) == 0:
        return jsonify({"error": "symbols must be a non-empty list"}), 400
    
    print(f"Checking {len(symbols)} symbols for spot crossover...")
    crossovers = detect_ema_crossovers(symbols, market_type='spot')
    
    return jsonify({
        "crossovers": crossovers,
        "count": len(crossovers) if isinstance(crossovers, list) else 0,
        "timestamp": pd.Timestamp.now().isoformat()
    })

# ==========================================
# RUN
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
