import streamlit as st
import sqlite3
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import time
import hashlib

# --- 1. データベース・セキュリティ関数 ---
def get_db():
    return sqlite3.connect('sleep_tracker.db')

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def save_record(u_id, start, end, sec, sat):
    conn = get_db()
    cur = conn.cursor()
    # 秒単位の数値をデータベースに保存
    cur.execute("INSERT INTO sleep_records (user_id, start_time, end_time, duration, satisfaction) VALUES (?, ?, ?, ?, ?)",
                (u_id, start, end, sec, sat))
    conn.commit()
    conn.close()

# --- 2. UI設定（モード切り替え対応） ---
st.set_page_config(page_title="Sleep Tracker Ultra", layout="wide")

# サイドバーに設定とログアウトを集約
with st.sidebar:
    st.title("⚙️ アプリ設定")
    display_mode = st.radio("表示モード", ["ダークモード", "通常モード"], horizontal=True)
    if st.session_state.get('user_auth'):
        if st.sidebar.button("ログアウト"):
            st.session_state.user_auth = None
            st.rerun()

# CSSでデザインを動的に変更
bg, text, accent = ("#050505", "#E0E0E0", "#00E5FF") if display_mode == "ダークモード" else ("#FFFFFF", "#333333", "#007BFF")
st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg}; color: {text}; }}
    .big-timer {{
        font-family: 'Courier New', Courier; font-size: 100px; font-weight: bold; color: {accent};
        text-align: center; padding: 40px; border: 3px solid {accent}; border-radius: 20px;
        background: rgba(0, 229, 255, 0.05); margin: 20px 0;
        box-shadow: 0 0 20px {accent}44;
    }}
    </style>
    """, unsafe_allow_html=True)

# セッション状態の一括初期化
for k, v in {'user_auth': None, 'is_sleeping': False, 'save_ready': False, 'alarm_on': False, 'alarm_volume': 0.5}.items():
    if k not in st.session_state: st.session_state[k] = v

# --- 3. 認証画面 ---
if st.session_state.user_auth is None:
    st.title("🌙 Sleep Tracker Pro")
    auth_tab = st.radio("メニュー", ["ログイン", "新規登録"], horizontal=True)
    with st.form(key="auth_form_v3"):
        u = st.text_input("ユーザー名")
        p = st.text_input("パスワード", type="password")
        if st.form_submit_button("実行"):
            conn = get_db(); cur = conn.cursor()
            hp = hash_pw(p)
            if auth_tab == "ログイン":
                cur.execute("SELECT id, username FROM users WHERE username=? AND password=?", (u, hp))
                res = cur.fetchone()
                if res:
                    st.session_state.user_auth = {"id": res[0], "name": res[1]}
                    st.rerun()
                else: st.error("ログイン情報が正しくありません")
            else:
                try:
                    cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (u, hp))
                    conn.commit(); st.success("登録完了！ログインしてください")
                except: st.error("そのユーザー名は既に使用されています")
            conn.close()
else:
    # --- 4. メイン画面 (タブ構築) ---
    user = st.session_state.user_auth
    tabs = st.tabs(["睡眠記録", "データ分析", "アラーム"]) # 'tabs' 変数をここで定義

    # 【睡眠記録】秒単位の巨大タイマー
    with tabs[0]:
        st.markdown("<h1 style='text-align: center;'>睡眠計測</h1>", unsafe_allow_html=True)
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            if st.session_state.is_sleeping:
                if st.button("☀️ 起きた（計測停止）", type="primary", use_container_width=True):
                    st.session_state.end_time = datetime.now()
                    st.session_state.is_sleeping = False
                    st.session_state.save_ready = True
                    st.rerun()
                
                timer_place = st.empty()
                while st.session_state.is_sleeping:
                    elapsed = datetime.now() - st.session_state.start_time
                    h, r = divmod(int(elapsed.total_seconds()), 3600)
                    m, s = divmod(r, 60)
                    timer_place.markdown(f"<div class='big-timer'>{h:02d}:{m:02d}:{s:02d}</div>", unsafe_allow_html=True)
                    time.sleep(1)
            
            elif st.session_state.save_ready:
                total_sec = (st.session_state.end_time - st.session_state.start_time).total_seconds()
                st.markdown(f"<h2 style='text-align: center;'>睡眠時間: {int(total_sec)} 秒</h2>", unsafe_allow_html=True)
                
                icons = {1: "😭", 2: "😕", 3: "😐", 4: "🙂", 5: "🤩"}
                sat = st.select_slider("満足度を選択", options=list(icons.keys()), format_func=lambda x: f"{icons[x]} {x}", value=3)
                
                if st.button("データベースに保存", use_container_width=True):
                    save_record(user['id'], st.session_state.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                                st.session_state.end_time.strftime('%Y-%m-%d %H:%M:%S'), total_sec, sat)
                    st.session_state.save_ready = False; st.balloons(); st.rerun()
            else:
                if st.button("🛌 睡眠開始", type="primary", use_container_width=True):
                    st.session_state.start_time = datetime.now()
                    st.session_state.is_sleeping = True
                    st.rerun()

    # 【データ分析】期間切り替え & 軸ラベル付き棒グラフ
    with tabs[1]:
        st.header("📊 睡眠データの精密分析")
        conn = get_db()
        df = pd.read_sql_query("SELECT start_time, duration, satisfaction FROM sleep_records WHERE user_id=? ORDER BY start_time ASC", 
                               conn, params=(user['id'],))
        conn.close()

        if not df.empty:
            df['dt'] = pd.to_datetime(df['start_time'])
            
            # 期間選択セレクトボックス
            period_choice = st.selectbox("📅 分析範囲を選択", ["今日のみ", "過去1週間", "過去1か月"])
            
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if period_choice == "今日のみ":
                df_filtered = df[df['dt'] >= today].copy()
                x_scale = alt.X('dt:T', title='記録時刻 (時:分)', axis=alt.Axis(format='%H:%M'))
                bar_size = 40
            elif period_choice == "過去1週間":
                limit = today - timedelta(days=7)
                df_filtered = df[df['dt'] >= limit].copy()
                x_scale = alt.X('dt:T', title='日付 (月/日)', scale=alt.Scale(domain=[limit, datetime.now()]), axis=alt.Axis(format='%m/%d'))
                bar_size = 20
            else:
                limit = today - timedelta(days=30)
                df_filtered = df[df['dt'] >= limit].copy()
                x_scale = alt.X('dt:T', title='日付 (月/日)', scale=alt.Scale(domain=[limit, datetime.now()]), axis=alt.Axis(format='%m/%d'))
                bar_size = 10

            if not df_filtered.empty:
                st.metric("期間中の平均睡眠", f"{df_filtered['duration'].mean():.1f} 秒")

                # 睡眠時間の棒グラフ (縦軸・横軸の単位を明記)
                st.subheader(f"📈 睡眠時間の推移 ({period_choice})")
                sleep_chart = alt.Chart(df_filtered).mark_bar(color=accent, size=bar_size).encode(
                    x=x_scale,
                    y=alt.Y('duration:Q', title='睡眠時間 [秒] (縦軸)'),
                    tooltip=[alt.Tooltip('dt:T', title='開始', format='%Y/%m/%d %H:%M'), alt.Tooltip('duration:Q', title='秒数')]
                ).properties(height=400).interactive()
                st.altair_chart(sleep_chart, use_container_width=True)

                # 満足度の棒グラフ
                st.subheader("📊 満足度の推移")
                sat_chart = alt.Chart(df_filtered).mark_bar(color="#FFA500", size=bar_size).encode(
                    x=x_scale,
                    y=alt.Y('satisfaction:Q', title='満足度 [1-5] (縦軸)', scale=alt.Scale(domain=[0, 5])),
                    tooltip=['dt', 'satisfaction']
                ).properties(height=300)
                st.altair_chart(sat_chart, use_container_width=True)
            else: st.warning("選択した期間にデータがありません。")
        else: st.info("睡眠を記録するとここに分析が表示されます。")

    # 【アラーム】音量調整・時分個別設定
    with tabs[2]:
        st.header("⏰ アラーム設定")
        st.session_state.alarm_volume = st.slider("音量調節", 0.0, 1.0, st.session_state.alarm_volume)
        c_h, c_m = st.columns(2)
        h = c_h.number_input("⏰ 時", 0, 23, 7)
        m = c_m.number_input("⏰ 分", 0, 59, 0)
        
        if st.session_state.alarm_on:
            if st.button("🔕 アラームを止める", type="primary", use_container_width=True):
                st.session_state.alarm_on = False; st.rerun()
            # 音声再生用HTML/JS
            st.markdown(f'<audio src="https://www.soundjay.com/buttons/beep-01a.mp3" autoplay loop></audio><script>document.querySelector("audio").volume={st.session_state.alarm_volume}</script>', unsafe_allow_html=True)
            st.error("⏰ 起きる時間です！！")
        else:
            if st.button("この時間でアラームをセット"):
                target = f"{h:02d}:{m:02d}"
                st.info(f"{target} にセットしました。")
                while True:
                    if datetime.now().strftime("%H:%M") == target:
                        st.session_state.alarm_on = True; st.rerun()
                    time.sleep(10)