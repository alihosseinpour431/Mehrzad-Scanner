from flask import Flask, jsonify, render_template
import ccxt
import pandas as pd
import time
import urllib.parse
import threading

app = Flask(__name__)

# ==========================================
# وضعیت دو اسکنر (هر کدام مستقل)
# ==========================================
futures_trend_status = {
    "running": False, "progress": 0, "results": [], "error": None, "total": 0
}
futures_pullback_status = {
    "running": False, "progress": 0, "results": [], "error": None, "total": 0
}

# ==========================================
# توابع کمکی
# ==========================================

def calculate_ema(data, period):
    """محاسبه EMA"""
    return data.ewm(span=period, adjust=False).mean().iloc[-1]


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


# ==========================================
# STRATEGY 1: BULLISH TREND
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
                # --- فیلتر 1: تایم‌فریم روزانه (D1) ---
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                if len(ohlcv_1d) < 50:
                    continue

                df_1d = pd.DataFrame(
                    ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                current_price = df_1d['close'].iloc[-1]
                ema50_1d = calculate_ema(df_1d['close'], 50)

                # شرط D1: Price > EMA(50)
                if current_price <= ema50_1d:
                    continue

                # --- فیلتر 2: تایم‌فریم ساعتی (H1) ---
                ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
                if len(ohlcv_1h) < 200:
                    continue

                df_1h = pd.DataFrame(
                    ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                ema50_1h = calculate_ema(df_1h['close'], 50)
                ema200_1h = calculate_ema(df_1h['close'], 200)

                # شرط H1: Price > EMA(50) > EMA(200)
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

        # مرتب‌سازی بر اساس Distance % (نزولی)
        results.sort(key=lambda x: x['Distance %'], reverse=True)
        futures_trend_status['results'] = results
        futures_trend_status['progress'] = 100

    except Exception as e:
        futures_trend_status['error'] = str(e)
    finally:
        futures_trend_status['running'] = False


# ==========================================
# STRATEGY 2: PULLBACK ENTRY
# D1: Price > EMA(50)
# H1: Price < EMA(50)  AND  EMA(50) > EMA(200)
# ==========================================

def scan_futures_pullback():
    global futures_pullback_status
    futures_pullback_status = {
        "running": True, "progress": 0, "results": [], "error": None, "total": 0
    }

    try:
        exchange, futures_pairs = get_futures_pairs()
        total = len(futures_pairs)
        futures_pullback_status['total'] = total
        results = []

        for i, symbol in enumerate(futures_pairs):
            if not futures_pullback_status['running']:
                break

            futures_pullback_status['progress'] = int((i / total) * 100)

            try:
                # --- فیلتر 1: تایم‌فریم روزانه (D1) ---
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                if len(ohlcv_1d) < 50:
                    continue

                df_1d = pd.DataFrame(
                    ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                current_price = df_1d['close'].iloc[-1]
                ema50_1d = calculate_ema(df_1d['close'], 50)

                # شرط D1: Price > EMA(50)
                if current_price <= ema50_1d:
                    continue

                # --- فیلتر 2: تایم‌فریم ساعتی (H1) ---
                ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
                if len(ohlcv_1h) < 200:
                    continue

                df_1h = pd.DataFrame(
                    ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                ema50_1h = calculate_ema(df_1h['close'], 50)
                ema200_1h = calculate_ema(df_1h['close'], 200)

                # شرط H1: Price < EMA(50)  AND  EMA(50) > EMA(200)
                # یعنی پولبک به EMA50 در یک روند صعودی
                if current_price < ema50_1h and ema50_1h > ema200_1h:
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

        # مرتب‌سازی بر اساس Distance % (نزولی)
        results.sort(key=lambda x: x['Distance %'], reverse=True)
        futures_pullback_status['results'] = results
        futures_pullback_status['progress'] = 100

    except Exception as e:
        futures_pullback_status['error'] = str(e)
    finally:
        futures_pullback_status['running'] = False


# ==========================================
# ROUTES
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')


# ===== Strategy 1: Bullish Trend =====
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


# ===== Strategy 2: Pullback Entry =====
@app.route('/start_futures_pullback')
def start_futures_pullback():
    if futures_pullback_status['running']:
        return jsonify({"status": "already_running"})
    thread = threading.Thread(target=scan_futures_pullback)
    thread.daemon = True
    thread.start()
    return jsonify({"status": "started"})


@app.route('/futures_status_pullback')
def futures_status_pullback_endpoint():
    return jsonify(futures_pullback_status)


# ==========================================
# RUN
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
