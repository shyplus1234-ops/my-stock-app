import sys
import subprocess

# 1. 필수 라이브러리 체크 및 설치
required_libraries = ['finance-datareader', 'pandas', 'beautifulsoup4', 'requests', 'lxml', 'html5lib', 'streamlit']
for lib in required_libraries:
    try:
        __import__(lib.replace('-', '_'))
    except ImportError:
        print(f"[안내] {lib} 라이브러리를 자동으로 설치합니다...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

import FinanceDataReader as fdr
import pandas as pd
import requests
from bs4 import BeautifulSoup
import io
import streamlit as st

# --- 웹페이지 화면 구성 ---
st.set_page_config(page_title="국내 주식 전종목 재무제표 검색 대시보드", layout="wide")
st.title("🔍 국내 주식 전종목 5개년 재무제표 검색기")
st.write("시총 100대 기업뿐만 아니라 국내 상장된 모든 업체의 재무제표를 실시간으로 검색하고 분석할 수 있습니다.")

# 한국거래소 전체 상장 기업 리스트 수집 함수 (캐싱 처리로 최초 1회만 로딩하여 속도 향상)
@st.cache_data
def load_all_krx_data():
    df_krx = fdr.StockListing('KRX')
    # 기본 정렬은 시가총액 순으로 정렬해 둡니다.
    return df_krx.sort_values(by='Marcap', ascending=False).copy()

try:
    # 2. 국내 상장 전체 기업 데이터 로드
    df_all = load_all_krx_data()
    all_tickers = df_all['Code'].tolist()
    all_names = df_all['Name'].tolist()
    
    # 3. 시총 상위 100개 요약 정보판 (기존 화면 유지용)
    df_top100 = df_all.head(100)
    summary_df = pd.DataFrame({
        '종목코드': df_top100['Code'].tolist(),
        '기업명': df_top100['Name'].tolist(),
        '시장구분': df_top100['Market'].tolist(),
        '시가총액(억)': (df_top100['Marcap'] / 100000000).round(0).astype(int).tolist(),
        '현재가': df_top100['Close'].tolist()
    })
    summary_df.index = range(1, 101)
    
    # 4. 웹화면 레이아웃 나누기
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🏆 현재 시가총액 상위 100대 기업 목록")
        st.dataframe(summary_df, height=650)
        
    with col2:
        st.subheader("🔎 국내 상장 기업 통합 검색")
        
        # [핵심 변경 포인트] 100개 고정이 아닌, 전체 상장기업 리스트(all_names)에서 선택/검색 가능하게 변경!
        # 글자를 타이핑하면 해당 글자가 들어간 기업들만 아래에 자동으로 필터링되어 나타납니다.
        selected_name = st.selectbox(
            "조회하고 싶은 기업명을 입력하거나 선택하세요 (전체 상장사 대상):", 
            all_names,
            index=0, # 기본값은 시총 1위인 삼성전자
            help="여기에 원하시는 기업명을 직접 타이핑하시면 검색이 됩니다."
        )
        
        # 선택된 기업의 정보 추출
        idx = all_names.index(selected_name)
        ticker = all_tickers[idx]
        market_type = df_all.iloc[idx]['Market']
        current_price = df_all.iloc[idx]['Close']
        
        # 간단한 기업 기본 정보 표시
        st.info(f"📌 **{selected_name}** ({ticker}) | 시장: {market_type} | 현재가: {current_price:,}원")
        
        # 네이버 금융에서 선택된 기업 데이터 실시간 크롤링
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'}
        
        with st.spinner(f'네이버 금융에서 {selected_name}의 5년치 재무제표를 가져오는 중...'):
            res = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            finance_div = soup.find('div', class_='section cop_analysis')
            
            if finance_div:
                html_stream = io.StringIO(str(finance_div.find('table')))
                tables = pd.read_html(html_stream, flavor='lxml')
                
                if tables:
                    financial_table = tables[0]
                    
                    # 멀티인덱스 컬럼 정리 (중복 에러 방지)
                    if isinstance(financial_table.columns, pd.MultiIndex):
                        new_cols = []
                        for col in financial_table.columns:
                            main_cat = str(col[0]).strip()
                            sub_cat = str(col[1]).strip()
                            
                            if '연간' in main_cat:
                                new_cols.append(f"{sub_cat}(연간)")
                            elif '분기' in main_cat:
                                new_cols.append(f"{sub_cat}(분기)")
                            else:
                                new_cols.append(sub_cat)
                        financial_table.columns = new_cols
                    
                    # 첫 번째 열을 인덱스로 지정
                    financial_table = financial_table.set_index(financial_table.columns[0])
                    financial_table.index.name = "주요재무지표"
                    
                    # 연간 데이터 컬럼만 추출
                    annual_cols = [col for col in financial_table.columns if '(연간)' in col]
                    
                    if annual_cols:
                        financial_table = financial_table[annual_cols]
                        financial_table.columns = [col.replace('(연간)', '') for col in financial_table.columns]
                    
                    # 깔끔하게 완성된 재무제표 화면에 출력
                    st.dataframe(financial_table.fillna('-'), use_container_width=True, height=400)
                    st.success(f"✨ {selected_name} 연간 실적 데이터 조회가 완료되었습니다!")
                else:
                    st.warning("재무제표 표를 해석할 수 없습니다.")
            else:
                st.warning("이 종목은 연간 재무제표(IFRS/GAAP) 정보가 제공되지 않는 종목이거나 일시적 오류입니다.")

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")
