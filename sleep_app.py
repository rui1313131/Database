import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import time
import hashlib
from supabase import create_client, Client

# --- 1. Supabase接続設定 ---
# Streamlit CloudのSecretsから読み込みます
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# --- 2. UI設定（テーマ切り替え対応） ---
st.set_page_config(page_title="Sleep Tracker Ultra", layout="wide")

with st.sidebar:
    st.title("⚙️ アプリ設定")
    display_mode = st.radio("表示モード", ["ダークモード", "通常モード"], horizontal=True)
    if st.session_state.get('user_auth'):
        if st.sidebar.button("ログアウト"):
            st.session_state.user_auth = None
            st.rerun()

# CSSの動的適用
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

# セッション状態の初期化
for k, v in {'user_auth': None, 'is_sleeping': False, 'save_ready': False, 'alarm_on': False, 'alarm_volume': 0.5}.items():
    if k not in st.session_state: st.session_state[k] = v

# --- 3. 認証画面 ---
if st.session_state.user_auth is None:
    st.title("🌙 Sleep Tracker Pro")
    auth_tab = st.radio("メニュー", ["ログイン", "新規登録"], horizontal=True)
    with st.form(key="auth_form_supabase"):
        u = st.text_input("ユーザー名")
        p = st.text_input("パスワード", type="password")
        if st.form_submit_button("実行"):
            hp = hash_pw(p)
            if auth_tab == "ログイン":
                res = supabase.table("users").select("*").eq("username", u).eq("password", hp).execute()
                if res.data:
                    st.session_state.user_auth = {"id": res.data[0]['id'], "name": res.data[0]['username']}
                    st.rerun()
                else: st.error("ログイン情報が正しくありません")
            else:
                try:
                    supabase.table("users").insert({"username": u, "password": hp}).execute()
                    st.success("登録完了！ログインしてください")
                except Exception as e:
                    st.error("登録エラー。その名前は既に使用されている可能性があります。")
else:
    # --- 4. メイン画面 (全機能復活) ---
    user = st.session_state.user_auth
    tabs = st.tabs(["睡眠記録", "データ分析", "アラーム"])

    # 【睡眠記録】
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
                if st.button("クラウドに保存", use_container_width=True):
                    supabase.table("sleep_records").insert({
                        "user_id": user['id'],
                        "start_time": st.session_state.start_time.isoformat(),
                        "end_time": st.session_state.end_time.isoformat(),
                        "duration": total_sec,
                        "satisfaction": sat
                    }).execute()
                    st.session_state.save_ready = False; st.balloons(); st.rerun()
            else:
                if st.button("🛌 睡眠開始", type="primary", use_container_width=True):
                    st.session_state.start_time = datetime.now()
                    st.session_state.is_sleeping = True
                    st.rerun()

    # 【データ分析】期間切り替え & 精密グラフ
    with tabs[1]:
        st.header("📊 睡眠データの精密分析")
        res = supabase.table("sleep_records").select("*").eq("user_id", user['id']).order("start_time").execute()
        
        if res.data:
            df = pd.DataFrame(res.data)
            df['dt'] = pd.to_datetime(df['start_time'])
            
            period_choice = st.selectbox("📅 分析範囲を選択", ["今日のみ", "過去1週間", "過去1か月"])
            
            # 日本時間などを考慮したフィルタリング
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if period_choice == "今日のみ":
                df_f = df[df['dt'] >= today_start].copy()
                x_scale = alt.X('dt:T', title='記録時刻 (時:分)', axis=alt.Axis(format='%H:%M'))
                bar_size = 40
            elif period_choice == "過去1週間":
                limit = today_start - timedelta(days=7)
                df_f = df[df['dt'] >= limit].copy()
                x_scale = alt.X('dt:T', title='日付 (月/日)', axis=alt.Axis(format='%m/%d'))
                bar_size = 20
            else:
                limit = today_start - timedelta(days=30)
                df_f = df[df['dt'] >= limit].copy()
                x_scale = alt.X('dt:T', title='日付 (月/日)', axis=alt.Axis(format='%m/%d'))
                bar_size = 10

            if not df_f.empty:
                st.metric("期間中の平均睡眠時間", f"{df_f['duration'].mean():.1f} 秒")
                
                # 睡眠時間の推移
                sleep_chart = alt.Chart(df_f).mark_bar(color=accent, size=bar_size).encode(
                    x=x_scale,
                    y=alt.Y('duration:Q', title='睡眠時間 [秒]'),
                    tooltip=[alt.Tooltip('dt:T', format='%Y/%m/%d %H:%M'), 'duration']
                ).properties(height=400).interactive()
                st.altair_chart(sleep_chart, use_container_width=True)
                
                # 満足度の推移
                sat_chart = alt.Chart(df_f).mark_bar(color="#FFA500", size=bar_size).encode(
                    x=x_scale,
                    y=alt.Y('satisfaction:Q', title='満足度 [1-5]', scale=alt.Scale(domain=[0, 5])),
                ).properties(height=300)
                st.altair_chart(sat_chart, use_container_width=True)
            else: st.warning("選択した期間にデータがありません。")
        else: st.info("睡眠を記録するとここに分析が表示されます。")

    # 【アラーム】機能復活
    with tabs[2]:
        st.header("⏰ アラーム設定")
        st.session_state.alarm_volume = st.slider("音量調節", 0.0, 1.0, st.session_state.alarm_volume)
        c_h, c_m = st.columns(2)
        h = c_h.number_input("⏰ 時", 0, 23, 7)
        m = c_m.number_input("⏰ 分", 0, 59, 0)
        
        if st.session_state.alarm_on:
            if st.button("🔕 アラームを止める", type="primary", use_container_width=True):
                st.session_state.alarm_on = False; st.rerun()
            st.markdown(f'<audio src="https://www.soundjay.com/buttons/beep-01a.mp3" autoplay loop></audio><script>document.querySelector("audio").volume={st.session_state.alarm_volume}</script>', unsafe_allow_html=True)
            st.error("⏰ 起きる時間です！！")
        else:
            if st.button("この時間でアラームをセット"):
                target = f"{h:02d}:{m:02d}"
                st.info(f"{target} にセットしました。このタブを開いたままにしておいてください。")
                while True:
                    if datetime.now().strftime("%H:%M") == target:
                        st.session_state.alarm_on = True; st.rerun()
                    time.sleep(10)
