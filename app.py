from flask import Flask, jsonify, send_file, render_template
import ccxt
import pandas as pd
import time
from fpdf import FPDF
from datetime import datetime
import threading
import urllib.parse
import jdatetime
import pytz
import requests

app = Flask(__name__)

# وضعیت اسکنرها
futures_status = {"running": False, "progress": 0, "results": [], "error": None, "total": 0}
spot_status = {"running": False, "progress": 0, "results": [], "error": None, "total": 0}

# ==========================================
# تنظیمات API کوین مارکت کپ
# ==========================================
CMC_API_KEY = '39478549b7c94ee093d0f3cbe43a39e9'
CMC_HEADERS = {
    'Accepts': 'application/json',
    'X-CMC_PRO_API_KEY': CMC_API_KEY,
}

# ==========================================
# توابع کمکی
# ==========================================

def calculate_ema(data, period):
    """محاسبه EMA"""
    return data.ewm(span=period, adjust=False).mean().iloc[-1]

def get_iran_datetime():
    """دریافت تاریخ و ساعت فعلی ایران به صورت شمسی"""
    tehran_tz = pytz.timezone('Asia/Tehran')
    now_tehran = datetime.now(tehran_tz)
    jalali_date = jdatetime.date.fromgregorian(
        year=now_tehran.year,
        month=now_tehran.month,
        day=now_tehran.day
    )
    formatted_date = jalali_date.strftime('%Y/%m/%d')
    formatted_time = now_tehran.strftime('%H:%M:%S')
    return f"{formatted_date} - {formatted_time}"

def get_tradingview_link(symbol):
    """ساخت لینک TradingView برای هر ارز"""
    base = symbol.split('/')[0]
    tv_symbol = f":{base}USDT"
    encoded_symbol = urllib.parse.quote(tv_symbol)
    return f"https://www.tradingview.com/chart/?symbol={encoded_symbol}"

def get_market_caps_from_cmc(symbols):
    """دریافت مارکت کپ ارزها از API کوین مارکت کپ"""
    market_caps = {}
    try:
        url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
        parameters = {'start': '1', 'limit': '5000', 'convert': 'USD'}
        response = requests.get(url, headers=CMC_HEADERS, params=parameters, timeout=30).json()
        if response.get('status', {}).get('error_code') == 0:
            for coin in response['data']:
                sym = coin['symbol']
                if sym not in market_caps:
                    market_caps[sym] = coin['quote']['USD']['market_cap']
    except Exception as e:
        print(f"خطا در دریافت لیست CMC: {e}")

    missing_symbols = [s for s in symbols if s not in market_caps]
    if missing_symbols:
        for i in range(0, len(missing_symbols), 100):
            batch = missing_symbols[i:i+100]
            try:
                url = 'https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest'
                parameters = {'symbol': ','.join(batch), 'convert': 'USD'}
                response = requests.get(url, headers=CMC_HEADERS, params=parameters, timeout=30).json()
                if response.get('status', {}).get('error_code') == 0:
                    for sym, data_list in response['data'].items():
                        if data_list and sym not in market_caps:
                            market_caps[sym] = data_list[0]['quote']['USD']['market_cap']
            except Exception as e:
                print(f"خطا در دریافت CMC برای بچ {i}: {e}")
            time.sleep(1)
    return market_caps

def format_market_cap(mcap):
    """تبدیل مارکت کپ به فرمت میلیون دلار"""
    if mcap is None or mcap == 0:
        return "N/A"
    mcap_millions = mcap / 1_000_000
    return f"{mcap_millions:.2f}M$"

# ==========================================
# FUTURES SCANNER
# ==========================================

def scan_futures():
    global futures_status
    futures_status = {"running": True, "progress": 0, "results": [], "error": None, "total": 0}
    
    try:
        exchange = ccxt.xt({
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        
        markets = exchange.load_markets()
        futures_pairs = [symbol for symbol, market in markets.items()
                         if market['swap'] and market['active']]
        
        total = len(futures_pairs)
        futures_status['total'] = total
        results = []
        
        for i, symbol in enumerate(futures_pairs):
            if not futures_status['running']:
                break
            
            futures_status['progress'] = int((i / total) * 100)
            
            try:
                # فیلتر 1: تایم‌فریم روزانه
                ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                if len(ohlcv_1d) < 50:
                    continue
                
                df_1d = pd.DataFrame(ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                current_price = df_1d['close'].iloc[-1]
                ema50_1d = calculate_ema(df_1d['close'], 50)
                
                if current_price <= ema50_1d:
                    continue
                
                # فیلتر 2: تایم‌فریم ساعتی
                ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
                if len(ohlcv_1h) < 200:
                    continue
                
                df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                ema50_1h = calculate_ema(df_1h['close'], 50)
                ema200_1h = calculate_ema(df_1h['close'], 200)
                
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
        
        # مرتب‌سازی
        results.sort(key=lambda x: x['Distance %'], reverse=True)
        futures_status['results'] = results
        futures_status['progress'] = 100
        
    except Exception as e:
        futures_status['error'] = str(e)
    finally:
        futures_status['running'] = False

# ==========================================
# SPOT SCANNER
# ==========================================

def scan_spot():
    global spot_status
    spot_status = {"running": True, "progress": 0, "results": [], "error": None, "total": 0}
    
    try:
        exchange = ccxt.xt({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        
        markets = exchange.load_markets()
        spot_pairs = [symbol for symbol in markets.keys()
                      if markets[symbol]['spot'] and
                      markets[symbol]['active'] and
                      symbol.endswith('/USDT')]
        
        total = len(spot_pairs)
        spot_status['total'] = total
        results = []
        
        for i, symbol in enumerate(spot_pairs):
            if not spot_status['running']:
                break
            
            spot_status['progress'] = int((i / total) * 50)  # 50% اول برای اسکن
            
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
                
                if len(ohlcv) >= 50:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    current_price = df['close'].iloc[-1]
                    ema_50 = calculate_ema(df['close'], 50)
                    
                    if current_price > ema_50:
                        distance_pct = ((current_price - ema_50) / ema_50) * 100
                        tv_link = get_tradingview_link(symbol)
                        
                        results.append({
                            'Symbol': symbol,
                            'Price ($)': round(current_price, 8),
                            'EMA(50)': round(ema_50, 8),
                            'Distance %': round(distance_pct, 2),
                            'TradingView Link': tv_link
                        })
                
                time.sleep(0.15)
            except Exception:
                continue
        
        # دریافت مارکت کپ از CoinMarketCap
        if results:
            spot_status['progress'] = 60
            base_symbols = [res['Symbol'].split('/')[0] for res in results]
            cmc_caps = get_market_caps_from_cmc(base_symbols)
            
            for res in results:
                base = res['Symbol'].split('/')[0]
                mcap = cmc_caps.get(base)
                res['Market Cap'] = format_market_cap(mcap)
        
        # مرتب‌سازی
        results.sort(key=lambda x: x['Distance %'], reverse=True)
        spot_status['results'] = results
        spot_status['progress'] = 100
        
    except Exception as e:
        spot_status['error'] = str(e)
    finally:
        spot_status['running'] = False

# ==========================================
# ساخت PDF - Futures
# ==========================================

def create_futures_pdf(results):
    iran_datetime_str = get_iran_datetime()
    
    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 16)
            self.cell(0, 10, 'XT.com Futures Scanner Report', 0, 1, 'C')
            self.set_font('Helvetica', '', 10)
            self.cell(0, 8, f'Generated: {iran_datetime_str}', 0, 1, 'C')
            self.set_font('Helvetica', 'I', 9)
            self.set_text_color(0, 0, 200)
            self.cell(0, 6, 'Click on any Symbol to open its chart in TradingView', 0, 1, 'C')
            self.set_text_color(0, 0, 0)
            self.ln(3)
        
        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')
    
    pdf = PDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, f'Total Futures Coins Found: {len(results)}', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, 'Filter 1 (Daily 1D): Price > EMA(50)', 0, 1, 'L')
    pdf.cell(0, 8, 'Filter 2 (Hourly 1H): Price > EMA(50) > EMA(200)', 0, 1, 'L')
    pdf.cell(0, 8, 'Sorted by: Distance % (High to Low)', 0, 1, 'L')
    pdf.ln(5)
    
    pdf.set_draw_color(0, 0, 0)
    pdf.line(10, pdf.get_y(), 287, pdf.get_y())
    pdf.ln(5)
    
    if len(results) > 0:
        col_widths = [60, 70, 70, 77]
        headers = ['Symbol', 'Price ($)', 'EMA(50)', 'Distance %']
        
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_fill_color(192, 57, 43)
        pdf.set_text_color(255, 255, 255)
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, 1, 0, 'C', True)
        pdf.ln()
        
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(0, 0, 0)
        
        for idx, row in enumerate(results):
            if idx % 2 == 0:
                pdf.set_fill_color(245, 245, 245)
                fill = True
            else:
                fill = False
            
            tv_link = row['TradingView Link']
            pdf.set_text_color(0, 0, 200)
            pdf.set_font('Helvetica', 'U', 10)
            pdf.cell(col_widths[0], 8, str(row['Symbol']), 1, 0, 'L', fill, link=tv_link)
            
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(col_widths[1], 8, f"${row['Price ($)']:.8f}", 1, 0, 'R', fill)
            pdf.cell(col_widths[2], 8, f"${row['EMA(50)']:.8f}", 1, 0, 'R', fill)
            pdf.cell(col_widths[3], 8, f"{row['Distance %']:.2f}%", 1, 0, 'R', fill)
            pdf.ln()
    
    filename = f'XT_Futures_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    pdf.output(filename)
    return filename

# ==========================================
# ساخت PDF - Spot
# ==========================================

def create_spot_pdf(results):
    iran_datetime_str = get_iran_datetime()
    
    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 16)
            self.cell(0, 10, 'XT.com Spot Scanner Report', 0, 1, 'C')
            self.set_font('Helvetica', '', 10)
            self.cell(0, 8, f'Generated: {iran_datetime_str}', 0, 1, 'C')
            self.set_font('Helvetica', 'I', 9)
            self.set_text_color(0, 0, 200)
            self.cell(0, 6, 'Click on any Symbol to open its chart in TradingView', 0, 1, 'C')
            self.set_text_color(0, 0, 0)
            self.ln(3)
        
        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')
    
    pdf = PDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, f'Total Spot Coins Found: {len(results)}', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, 'Filter (Daily 1D): Price > EMA(50)', 0, 1, 'L')
    pdf.cell(0, 8, 'Sorted by: Distance % (High to Low)', 0, 1, 'L')
    pdf.ln(5)
    
    pdf.set_draw_color(0, 0, 0)
    pdf.line(10, pdf.get_y(), 287, pdf.get_y())
    pdf.ln(5)
    
    if len(results) > 0:
        col_widths = [50, 60, 60, 45, 62]
        headers = ['Symbol', 'Price ($)', 'EMA(50)', 'Distance %', 'Market Cap']
        
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_fill_color(41, 128, 185)
        pdf.set_text_color(255, 255, 255)
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, 1, 0, 'C', True)
        pdf.ln()
        
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(0, 0, 0)
        
        for idx, row in enumerate(results):
            if idx % 2 == 0:
                pdf.set_fill_color(245, 245, 245)
                fill = True
            else:
                fill = False
            
            tv_link = row['TradingView Link']
            pdf.set_text_color(0, 0, 200)
            pdf.set_font('Helvetica', 'U', 10)
            pdf.cell(col_widths[0], 8, str(row['Symbol']), 1, 0, 'L', fill, link=tv_link)
            
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(col_widths[1], 8, f"${row['Price ($)']:.8f}", 1, 0, 'R', fill)
            pdf.cell(col_widths[2], 8, f"${row['EMA(50)']:.8f}", 1, 0, 'R', fill)
            pdf.cell(col_widths[3], 8, f"{row['Distance %']:.2f}%", 1, 0, 'R', fill)
            pdf.cell(col_widths[4], 8, str(row.get('Market Cap', 'N/A')), 1, 0, 'R', fill)
            pdf.ln()
    
    filename = f'XT_Spot_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    pdf.output(filename)
    return filename

# ==========================================
# ROUTES
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

# ===== Futures Routes =====
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
    filename = create_futures_pdf(futures_status['results'])
    return send_file(filename, as_attachment=True, download_name=filename)

# ===== Spot Routes =====
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
    filename = create_spot_pdf(spot_status['results'])
    return send_file(filename, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
