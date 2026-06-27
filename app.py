from flask import Flask, send_file, render_template_string
import ccxt
import pandas as pd
import io
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# ==========================================
# توابع کمکی
# ==========================================
def calculate_ema(data, period):
    """محاسبه EMA"""
    return data.ewm(span=period, adjust=False).mean()

def get_tradingview_link(symbol):
    """ساخت لینک TradingView"""
    # فرمت نماد در تریدینگ ویو برای صرافی XT
    base = symbol.split('/')[0]
    tv_symbol = f"XT:{base}USDT"
    encoded_symbol = urllib.parse.quote(tv_symbol)
    return f"https://www.tradingview.com/chart/?symbol={encoded_symbol}"

# ==========================================
# منطق اصلی اسکن و تولید اکسل
# ==========================================
def scan_market_to_excel(market_type):
    """
    market_type: 'spot' برای اسپات | 'swap' برای فیوچرز
    """
    # 1. اتصال به صرافی XT
    exchange = ccxt.xt({
        'enableRateLimit': True,
        'options': {'defaultType': market_type}
    })
    markets = exchange.load_markets()
    
    # 2. فیلتر کردن جفت‌ارزهای فعال تتر (USDT)
    if market_type == 'swap':
        pairs = [s for s, m in markets.items() if m.get('swap') and m.get('active') and s.endswith('/USDT:USDT')]
    else:
        pairs = [s for s, m in markets.items() if not m.get('swap') and m.get('active') and s.endswith('/USDT')]

    results = []

    # 3. تابع پردازش هر ارز
    def process_symbol(symbol):
        try:
            # --- بررسی تایم‌فریم روزانه (1D) ---
            ohlcv_1d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=100)
            if len(ohlcv_1d) < 50: return None
            
            df_1d = pd.DataFrame(ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            price_1d = df_1d['close'].iloc[-1]
            ema50_1d = calculate_ema(df_1d['close'], 50).iloc[-1]
            
            # شرط اول: Price > EMA(50) در روزانه
            if price_1d <= ema50_1d: return None
            
            # --- بررسی تایم‌فریم ساعتی (1H) ---
            ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
            if len(ohlcv_1h) < 200: return None
            
            df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            price_1h = df_1h['close'].iloc[-1]
            ema50_1h = calculate_ema(df_1h['close'], 50).iloc[-1]
            ema200_1h = calculate_ema(df_1h['close'], 200).iloc[-1]
            
            # شرط دوم: Price > EMA(50) > EMA(200) در ساعتی
            if price_1h > ema50_1h > ema200_1h:
                # محاسبه شاخص Distance طبق فرمول شما
                distance = ((ema50_1h - ema200_1h) / ema50_1h) * 100
                
                return {
                    'Symbol': symbol.split('/')[0],
                    'Price': round(price_1h, 8),
                    'EMA50_H1': round(ema50_1h, 8),
                    'EMA200_H1': round(ema200_1h, 8),
                    'Distance(%)': round(distance, 2),
                    'TradingView': get_tradingview_link(symbol)
                }
            return None
        except Exception:
            return None

    # 4. اجرای موازی برای سرعت بالاتر
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(process_symbol, sym): sym for sym in pairs}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
                
    # 5. تبدیل به دیتافریم و مرتب‌سازی (بیشترین Distance در بالا)
    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values(by='Distance(%)', ascending=False)
        
    return df

# ==========================================
# اندپوینت‌های دانلود اکسل
# ==========================================
@app.route('/scan/spot')
def scan_spot():
    df = scan_market_to_excel('spot')
    return export_to_excel(df, 'Spot_Scanner_Result.xlsx')

@app.route('/scan/futures')
def scan_futures():
    df = scan_market_to_excel('swap')
    return export_to_excel(df, 'Futures_Scanner_Result.xlsx')

def export_to_excel(df, filename):
    """تبدیل دیتافریم به فایل اکسل و ارسال برای دانلود"""
    if df.empty:
        return "هیچ ارزی با این شرایط پیدا نشد!", 404
        
    output = io.BytesIO()
    # استفاده از openpyxl برای نوشتن در حافظه
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Scan Results')
        
    output.seek(0)
    
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# ==========================================
# رابط کاربری ساده (دو دکمه)
# ==========================================
@app.route('/')
def index():
    html = """
    <!DOCTYPE html>
    <html dir="rtl" lang="fa">
    <head>
        <meta charset="UTF-8">
        <title>اسکنر بازار XT</title>
        <style>
            body { font-family: Tahoma, sans-serif; text-align: center; margin-top: 100px; background: #f4f4f9; }
            h1 { color: #333; }
            .btn {
                display: inline-block; padding: 15px 30px; margin: 20px;
                font-size: 18px; font-weight: bold; color: white; text-decoration: none;
                border-radius: 8px; transition: 0.3s; cursor: pointer; border: none;
            }
            .btn-spot { background: #28a745; }
            .btn-spot:hover { background: #218838; }
            .btn-futures { background: #dc3545; }
            .btn-futures:hover { background: #c82333; }
            .note { margin-top: 30px; color: #666; font-size: 14px; }
        </style>
    </head>
    <body>
        <h1>اسکنر روند صعودی (EMA Strategy)</h1>
        <p>برای اسکن و دانلود فایل اکسل، روی دکمه مورد نظر کلیک کنید:</p>
        
        <a href="/scan/spot" class="btn btn-spot">اسکن بازار اسپات (Spot)</a>
        <a href="/scan/futures" class="btn btn-futures">اسکن بازار فیوچرز (Futures)</a>
        
        <p class="note">
            * شرایط: قیمت بالای EMA50 روزانه | قیمت و EMA50 بالای EMA200 ساعتی<br>
            * مرتب‌سازی بر اساس شاخص Distance (فاصله EMA50 تا EMA200 در تایم ۱ ساعته)
        </p>
    </body>
    </html>
    """
    return render_template_string(html)

# ==========================================
# اجرای سرور
# ==========================================
if __name__ == '__main__':
    # سرور روی پورت 5000 اجرا می‌شود
    app.run(host='0.0.0.0', port=5000, debug=True)
