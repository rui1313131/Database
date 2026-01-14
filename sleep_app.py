import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta, timezone
import time
import hashlib
from supabase import create_client, Client

# --- 1. Supabase接続設定 ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# 日本時間(JST)の設定
JST = timezone(timedelta(hours=9))

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

# --- 2. UI設定 ---
st.set_page_config(page_title="Sleep Tracker Ultra", layout="wide")

for k, v in {'user_auth': None, 'is_sleeping': False, 'save_ready': False, 'alarm_active': False}.items():
    if k not in st.session_state: st.session_state[k] = v

with st.sidebar:
    st.title("⚙️ 設定")
    if st.session_state.user_auth:
        if st.sidebar.button("ログアウト"): st.session_state.user_auth = None; st.rerun()

# --- 3. 認証画面 ---
if st.session_state.user_auth is None:
    st.title("🌙 Sleep Tracker Pro")
    u, p = st.text_input("ユーザー名"), st.text_input("パスワード", type="password")
    if st.button("ログイン/新規登録"):
        hp = hash_pw(p)
        res = supabase.table("users").select("*").eq("username", u).eq("password", hp).execute()
        if res.data:
            st.session_state.user_auth = {"id": res.data[0]['id'], "name": res.data[0]['username']}; st.rerun()
        else:
            try:
                supabase.table("users").insert({"username": u, "password": hp}).execute()
                st.success("新規登録しました！もう一度ボタンを押してログインしてください")
            except: st.error("ログイン情報が違うか、名前が使われています")
else:
    user = st.session_state.user_auth
    tabs = st.tabs(["睡眠記録", "データ分析", "アラーム"])

    # 【睡眠記録】
    with tabs[0]:
        if st.session_state.is_sleeping:
            if st.button("☀️ 起きた", type="primary", use_container_width=True):
                st.session_state.end_t = datetime.now(timezone.utc); st.session_state.is_sleeping, st.session_state.save_ready = False, True; st.rerun()
            t_place = st.empty()
            while st.session_state.is_sleeping:
                diff = datetime.now(timezone.utc) - st.session_state.start_t
                h, r = divmod(int(diff.total_seconds()), 3600); m, s = divmod(r, 60)
                t_place.markdown(f"<div class='big-timer'>{h:02d}:{m:02d}:{s:02d}</div>", unsafe_allow_html=True); time.sleep(1)
        elif st.session_state.save_ready:
            sec = (st.session_state.end_t - st.session_state.start_t).total_seconds()
            sat = st.select_slider("満足度", options=[1,2,3,4,5], value=3)
            if st.button("保存"):
                supabase.table("sleep_records").insert({"user_id": user['id'], "start_time": st.session_state.start_t_str, "end_time": st.session_state.end_t.isoformat(), "duration": sec, "satisfaction": sat}).execute()
                st.session_state.save_ready = False; st.balloons(); st.rerun()
        else:
            if st.button("🛌 睡眠開始", type="primary"):
                n = datetime.now(timezone.utc); st.session_state.start_t, st.session_state.start_t_str = n, n.isoformat(); st.session_state.is_sleeping = True; st.rerun()

    # 【データ分析】期間の幅を完全に固定
    with tabs[1]:
        res = supabase.table("sleep_records").select("*").eq("user_id", user['id']).order("start_time").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df['dt'] = pd.to_datetime(df['start_time'], utc=True).dt.tz_convert(JST)
            period = st.selectbox("📅 範囲", ["今日のみ", "過去1週間", "過去1か月"])
            now = datetime.now(JST); start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if period == "今日のみ": limit, fmt, lbl = start, '%H:%M', '時刻'
            elif period == "過去1週間": limit, fmt, lbl = start - timedelta(days=7), '%m/%d', '日付'
            else: limit, fmt, lbl = start - timedelta(days=30), '%m/%d', '日付'
            
            x_ax = alt.X('dt:T', title=lbl, axis=alt.Axis(format=fmt), scale=alt.Scale(domain=[limit.isoformat(), now.isoformat()]))
            st.altair_chart(alt.Chart(df[df['dt'] >= limit]).mark_bar(color="#00E5FF", size=15).encode(x=x_ax, y=alt.Y('duration:Q', title='秒数')), use_container_width=True)

    # 【アラーム】日本時間・強制発火システム
    with tabs[2]:
        st.header("⏰ アラーム設定")
        SOUND_URL = "https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3"
        
        if st.button("▶️ 音が出るかテスト（まずこれを押してください）"):
            st.components.v1.html(f'<audio src="{SOUND_URL}" autoplay></audio>', height=0)

        c1, c2 = st.columns(2)
        h = c1.number_input("時", 0, 23, 7)
        m = c2.number_input("分", 0, 59, 0)
        
        if st.button("✅ アラームをセット"):
            st.session_state.alarm_time = f"{h:02d}:{m:02d}"
            st.session_state.alarm_active = True
            st.success(f"{st.session_state.alarm_time} にセットしました。")

        if st.session_state.alarm_active:
            # 日本時間(JST)で現在時刻を取得
            current_t = datetime.now(JST).strftime("%H:%M")
            st.info(f"現在、日本時間 {current_t} です。{st.session_state.alarm_time} になると鳴ります。")
            
            if current_t == st.session_state.alarm_time:
                # 指定時間になったらHTMLで音を強制再生
                st.components.v1.html(f"""
                    <div style="background:#ff4b4b;color:white;padding:20px;border-radius:10px;text-align:center;">
                        <h2>⏰ 起きる時間です！ ({current_t})</h2>
                        <audio src="{SOUND_URL}" autoplay loop></audio>
                    </div>
                """, height=150)
                if st.button("🔕 止める"):
                    st.session_state.alarm_active = False; st.rerun()
            else:
                time.sleep(10); st.rerun() # 10秒ごとに再チェック
