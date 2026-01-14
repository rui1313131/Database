import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import time
import hashlib
from supabase import create_client, Client

# --- 1. Supabase接続設定 ---
# StreamlitのSecretsから情報を取得します
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# --- 2. UI設定 ---
st.set_page_config(page_title="Sleep Tracker Pro", layout="wide")

with st.sidebar:
    st.title("⚙️ 設定")
    display_mode = st.radio("表示モード", ["ダーク", "通常"], horizontal=True)
    if st.session_state.get('user_auth'):
        if st.button("ログアウト"):
            st.session_state.user_auth = None
            st.rerun()

bg, text, accent = ("#050505", "#E0E0E0", "#00E5FF") if display_mode == "ダーク" else ("#FFFFFF", "#333333", "#007BFF")
st.markdown(f"<style>.stApp {{ background-color: {bg}; color: {text}; }} .big-timer {{ font-family: 'Courier New'; font-size: 100px; font-weight: bold; color: {accent}; text-align: center; padding: 40px; border: 3px solid {accent}; border-radius: 20px; background: rgba(0, 229, 255, 0.05); margin: 20px 0; }}</style>", unsafe_allow_html=True)

for k, v in {'user_auth': None, 'is_sleeping': False, 'save_ready': False}.items():
    if k not in st.session_state: st.session_state[k] = v

# --- 3. 認証画面 ---
if st.session_state.user_auth is None:
    st.title("🌙 Sleep Tracker Pro")
    auth_tab = st.radio("メニュー", ["ログイン", "新規登録"], horizontal=True)
    with st.form(key="auth_v4"):
        u, p = st.text_input("ユーザー名"), st.text_input("パスワード", type="password")
        if st.form_submit_button("実行"):
            hp = hash_pw(p)
            if auth_tab == "ログイン":
                res = supabase.table("users").select("*").eq("username", u).eq("password", hp).execute()
                if res.data:
                    st.session_state.user_auth = {"id": res.data[0]['id'], "name": res.data[0]['username']}
                    st.rerun()
                else: st.error("情報が正しくありません")
            else:
                try:
                    supabase.table("users").insert({"username": u, "password": hp}).execute()
                    st.success("登録完了！ログインしてください")
                except: st.error("その名前は既に使用されています")
else:
    # --- 4. メイン画面 ---
    user = st.session_state.user_auth
    tabs = st.tabs(["睡眠記録", "データ分析"])

    with tabs[0]:
        if st.session_state.is_sleeping:
            if st.button("☀️ 起きた", type="primary", use_container_width=True):
                st.session_state.end_t, st.session_state.is_sleeping, st.session_state.save_ready = datetime.now(), False, True
                st.rerun()
            t_place = st.empty()
            while st.session_state.is_sleeping:
                diff = datetime.now() - st.session_state.start_t
                h, r = divmod(int(diff.total_seconds()), 3600)
                m, s = divmod(r, 60)
                t_place.markdown(f"<div class='big-timer'>{h:02d}:{m:02d}:{s:02d}</div>", unsafe_allow_html=True)
                time.sleep(1)
        elif st.session_state.save_ready:
            sec = (st.session_state.end_t - st.session_state.start_t).total_seconds()
            sat = st.select_slider("満足度", options=[1,2,3,4,5], value=3)
            if st.button("保存する"):
                supabase.table("sleep_records").insert({
                    "user_id": user['id'], "start_time": st.session_state.start_t.isoformat(),
                    "end_time": st.session_state.end_t.isoformat(), "duration": sec, "satisfaction": sat
                }).execute()
                st.session_state.save_ready = False; st.balloons(); st.rerun()
        else:
            if st.button("🛌 睡眠開始", type="primary"):
                st.session_state.start_t, st.session_state.is_sleeping = datetime.now(), True
                st.rerun()

    with tabs[1]:
        st.header("📊 分析結果")
        res = supabase.table("sleep_records").select("*").eq("user_id", user['id']).order("start_time").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df['dt'] = pd.to_datetime(df['start_time'])
            st.metric("平均睡眠時間", f"{df['duration'].mean():.1f} 秒")
            chart = alt.Chart(df).mark_bar(color=accent).encode(
                x=alt.X('dt:T', title='日付'), y=alt.Y('duration:Q', title='秒数')
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
        else: st.info("データがありません")
