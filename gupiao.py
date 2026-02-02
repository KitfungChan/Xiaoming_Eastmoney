import requests
import pandas as pd
import time
import sys

# ==========================================
# 0. 全局设置与美化
# ==========================================
# 设置 Pandas 显示选项，确保终端表格整齐
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)

# 定义终端颜色代码，让交互更漂亮
class Color:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_step(text):
    print(f"\n{Color.BOLD}{Color.CYAN}>>> {text}{Color.ENDC}")

# ==========================================
# 1. 基础数据获取函数 (API逻辑)
# ==========================================

def get_secid(stock_code):
    return f"1.{stock_code}" if str(stock_code).startswith('6') else f"0.{stock_code}"

def get_k_history_fixed(code, secid_override=None, limit=20):
    """获取K线数据"""
    secid = secid_override if secid_override else get_secid(code)
    url = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid, "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61", 
        "klt": "101", "fqt": "1", "end": "20500101", "lmt": limit,
    }
    try:
        res = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}).json()
        if not (res and res.get('data') and res['data'].get('klines')): return None
        rows = [line.split(',') for line in res['data']['klines']]
        df = pd.DataFrame(rows, columns=['日期', '开盘', '收盘', '最高', '最低', '成交量', '成交额', '振幅', '涨跌幅', '涨跌额', '换手率'])
        df['日期'] = pd.to_datetime(df['日期'])
        df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce')
        return df
    except: return None

# ==========================================
# 2. 核心功能模块
# ==========================================

def show_market_turnover(days):
    """显示全市场成交额"""
    print(f"{Color.BLUE}正在拉取沪深北三市数据...{Color.ENDC}")
    
    # 获取三大指数数据
    sh = get_k_history_fixed('000001', '1.000001', limit=days+5) 
    sz = get_k_history_fixed('399001', '0.399001', limit=days+5)
    bj = get_k_history_fixed('899050', '0.899050', limit=days+5)
    
    if sh is None or sz is None or bj is None:
        print(f"{Color.FAIL}数据获取失败，请检查网络。{Color.ENDC}")
        return

    # 合并处理
    df = pd.merge(sh[['日期','成交额']], sz[['日期','成交额']], on='日期', suffixes=('_sh','_sz'))
    df = pd.merge(df, bj[['日期','成交额']], on='日期')
    df.rename(columns={'成交额':'成交额_bj'}, inplace=True)
    
    # 计算
    df['沪市(亿)'] = (df['成交额_sh'] / 1e8).round(2)
    df['深市(亿)'] = (df['成交额_sz'] / 1e8).round(2)
    df['北证(亿)'] = (df['成交额_bj'] / 1e8).round(2)
    df['总成交(亿)'] = (df['沪市(亿)'] + df['深市(亿)'] + df['北证(亿)']).round(2)
    
    # 情绪打标签
    def get_sentiment(v):
        if v < 6000: return "🥶 冷清"
        if v < 8000: return "😐 温和"
        if v < 10000: return "😃 活跃"
        return "🔥 火爆"
    
    df['热度'] = df['总成交(亿)'].apply(get_sentiment)
    
    # 展示
    final = df.tail(days).copy()
    final['日期'] = final['日期'].dt.strftime('%Y-%m-%d')
    cols = ['日期', '沪市(亿)', '深市(亿)', '北证(亿)', '总成交(亿)', '热度']
    
    print(f"\n{Color.GREEN}--- 近 {days} 天全市场（修正版）成交数据 ---{Color.ENDC}")
    print(final[cols].to_string(index=False))

def show_sector_and_stocks(sector_num, stock_num):
    """显示板块分布和个股详情"""
    print(f"{Color.BLUE}正在扫描今日资金战场 (Top 100)...{Color.ENDC}")
    
    url = "http://82.push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f6", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "fields": "f12,f14,f6,f100,f3"
    }
    
    try:
        res = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}).json()
        df = pd.DataFrame(res['data']['diff'])
        df = df.rename(columns={'f12':'代码', 'f14':'名称', 'f6':'成交额', 'f100':'所属板块', 'f3':'涨跌幅'})
        df['成交额(亿)'] = df['成交额'] / 1e8
        df['所属板块'] = df['所属板块'].replace('', '其他')
        
        # --- 板块统计 ---
        sector_stats = df.groupby('所属板块').agg({
            '代码': 'count',
            '成交额(亿)': 'sum',
            '涨跌幅': 'mean'
        }).rename(columns={'代码':'入围数量', '成交额(亿)':'聚合成交', '涨跌幅':'平均涨跌'})
        
        sector_stats = sector_stats.sort_values(by=['入围数量', '聚合成交'], ascending=False)
        
        # 展示板块
        print(f"\n{Color.GREEN}--- 📊 今日资金战场：前 {sector_num} 个板块分布 ---{Color.ENDC}")
        show_sec = sector_stats.head(sector_num).copy()
        show_sec['聚合成交'] = show_sec['聚合成交'].map('{:,.2f}亿'.format)
        show_sec['平均涨跌'] = show_sec['平均涨跌'].map('{:+.2f}%'.format)
        print(show_sec)
        
        # 展示个股
        print(f"\n{Color.GREEN}--- 🔍 龙头详情：成交额排名 前 {stock_num} 个股 ---{Color.ENDC}")
        show_stk = df[['代码', '名称', '所属板块', '成交额(亿)', '涨跌幅']].head(stock_num).copy()
        show_stk['成交额(亿)'] = show_stk['成交额(亿)'].map('{:,.2f}'.format)
        show_stk['涨跌幅'] = show_stk['涨跌幅'].map('{:+.2f}%'.format)
        print(show_stk.to_string(index=False))
        
    except Exception as e:
        print(f"{Color.FAIL}分析失败: {e}{Color.ENDC}")

# ==========================================
# 3. 交互主逻辑
# ==========================================

def main():
    print(f"{Color.HEADER}{'='*50}")
    print(f"   📈 A股市场 交互式资金分析终端")
    print(f"{'='*50}{Color.ENDC}")

    while True:
        try:
            # --- 步骤 1: 市场总成交 ---
            print_step("【步骤 1/3】您想获得近几天的数据？")
            days_input = input("请输入天数 (默认7，输入0退出): ").strip()
            
            if days_input == '0': break
            days = int(days_input) if days_input else 7
            
            show_market_turnover(days)
            
            # --- 步骤 2: 板块分布 ---
            print_step("【步骤 2/3】想看今天资金战场前多少个股板块统计？")
            sec_input = input("请输入板块数量 (默认5): ").strip()
            sec_num = int(sec_input) if sec_input else 5
            
            # --- 步骤 3: 龙头详情 ---
            print_step("【步骤 3/3】想获得今天龙头详情成交额排名前几个股？")
            stk_input = input("请输入个股数量 (默认10): ").strip()
            stk_num = int(stk_input) if stk_input else 10
            
            # 执行分析 (步骤2和3合并执行以减少请求次数)
            show_sector_and_stocks(sec_num, stk_num)
            
            print(f"\n{Color.HEADER}{'-'*50}")
            print("分析完成！按回车键重新开始，或按 Ctrl+C 退出。")
            input(f"{'-'*50}{Color.ENDC}")
            
        except ValueError:
            print(f"{Color.FAIL}请输入有效的数字！{Color.ENDC}")
        except KeyboardInterrupt:
            print("\n程序已退出。")
            sys.exit()

if __name__ == "__main__":
    main()