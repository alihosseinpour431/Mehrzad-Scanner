from flask import render_template, jsonify, send_file
import ccxt
import pandas as pd
import time
from fpdf import FPDF
from datetime import datetime
import threading

app = Flask(__name__)

# وضعیت اسکنرها
futures_status = {"running": False, "progress": 0, "results": [], "error": None}
spot_status = {"running": False, "progress": 0, "results": [], "error": None}

def calculate_ema(data, period):
    return data.ewm(span=period, adjust=False).mean().iloc[-1]

# ========== FUTURES SCANNER ==========
def scan_futures():
    global futures_status
    futures_status = {"running": True, "progress": 0, "results": [], "error": None}
    
    try:
        exchange = ccxt.xt({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
        markets = exchange.load_markets()
        futures_pairs = [s for s, m in markets.items() if m['swap'] and m['active']]
        
        results = []
        total = len(futures_pairs)
        
        for i, symbol in enumerate(futures_pairs):
            futures_status['progress'] = int((i / total) * 100)
            
            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                if len(ohlcv_1d) < 50:
                    continue
                
                df_1d = pd.DataFrame(ohlcv_1d, columns=['timestamp','open','high','low','close','volume'])
                current_price = df_1d['close'].iloc[-1]
                ema50_1d = calculate_ema(df_1d['close'], 50)
                
                if current_price <= ema50_1d:
                    continue
                
                ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
                if len(ohlcv_1h) < 200:
                    continue
                
                df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp','open','high','low','close','volume'])
                ema50_1h = calculate_ema(df_1h['close'], 50)
                ema200_1h = calculate_ema(df_1h['close'], 200)
                
                if current_price > ema50_1h > ema200_1h:
                    distance_pct = ((current_price - ema50_1d) / ema50_1d) * 100
                    results.append({
                        'Symbol': symbol,
                        'Price': round(current_price, 8),
                        'EMA50': round(ema50_1d, 8),
                        'Distance%': round(distance_pct, 2)
                    })
                
                time.sleep(0.2)
            except:
                continue
        
        futures_status['results'] = results
        futures_status['progress'] = 100
        
    except Exception as e:
        futures_status['error'] = str(e)
    finally:
        futures_status['running'] = False

# ========== SPOT SCANNER ==========
def scan_spot():
    global spot_status
    spot_status = {"running": True, "progress": 0, "results": [], "error": None}
    
    try:
        exchange = ccxt.xt({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
        markets = exchange.load_markets()
        spot_pairs = [s for s, m in markets.items() if m['spot'] and m['active']]
        
        results = []
        total = len(spot_pairs)
        
        for i, symbol in enumerate(spot_pairs):
            spot_status['progress'] = int((i / total) * 100)
            
            try:
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                if len(ohlcv_1d) < 50:
                    continue
                
                df_1d = pd.DataFrame(ohlcv_1d, columns=['timestamp','open','high','low','close','volume'])
                current_price = df_1d['close'].iloc[-1]
                ema50_1d = calculate_ema(df_1d['close'], 50)
                
                if current_price <= ema50_1d:
                    continue
                
                ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
                if len(ohlcv_1h) < 200:
                    continue
                
                df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp','open','high','low','close','volume'])
                ema50_1h = calculate_ema(df_1h['close'], 50)
                ema200_1h = calculate_ema(df_1h['close'], 200)
                
                if current_price > ema50_1h > ema200_1h:
                    distance_pct = ((current_price - ema50_1d) / ema50_1d) * 100
                    results.append({
                        'Symbol': symbol,
                        'Price': round(current_price, 8),
                        'EMA50': round(ema50_1d, 8),
                        'Distance%': round(distance_pct, 2)
                    })
                
                time.sleep(0.2)
            except:
                continue
        
        spot_status['results'] = results
        spot_status['progress'] = 100
        
    except Exception as e:
        spot_status['error'] = str(e)
    finally:
        spot_status['running'] = False

# ========== ROUTES ==========

@app.route('/')
def index():
    return "XT Scanner API is running!"

@app.route('/start_futures')
def start_futures():
    if futures_status['running']:
        return jsonify({"status": "already_running"})
    thread = threading.Thread(target=scan_futures)
    thread.daemon = True
    thread.start()
    return jsonify({"status": "started"})

@app.route('/futures_status')
def futures_status_endpoint():
    return jsonify(futures_status)

@app.route('/download_futures_pdf')
def download_futures_pdf():
    if not futures_status['results']:
        return "No results", 404
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="XT Futures Scanner Report", ln=True, align='C')
    for result in futures_status['results']:
        pdf.cell(200, 10, txt=f"{result['Symbol']}: ${result['Price']}", ln=True)
    filename = f"Futures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(filename)
    return send_file(filename, as_attachment=True)

@app.route('/start_spot')
def start_spot():
    if spot_status['running']:
        return jsonify({"status": "already_running"})
    thread = threading.Thread(target=scan_spot)
    thread.daemon = True
    thread.start()
    return jsonify({"status": "started"})

@app.route('/spot_status')
def spot_status_endpoint():
    return jsonify(spot_status)

@app.route('/download_spot_pdf')
def download_spot_pdf():
    if not spot_status['results']:
        return "No results", 404
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="XT Spot Scanner Report", ln=True, align='C')
    for result in spot_status['results']:
        pdf.cell(200, 10, txt=f"{result['Symbol']}: ${result['Price']}", ln=True)
    filename = f"Spot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(filename)
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
