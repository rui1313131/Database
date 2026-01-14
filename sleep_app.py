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

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# --- 2. UI設定 ---
st.set_page_config(page_title="Sleep Tracker Ultra", layout="wide")

for k, v in {'user_auth': None, 'is_sleeping': False, 'save_ready': False, 'alarm_on': False, 'audio_unlocked': False}.items():
    if k not in st.session_state: st.session_state[k] = v

with st.sidebar:
    st.title("⚙️ 設定")
    display_mode = st.radio("表示モード", ["ダークモード", "通常モード"], horizontal=True)
    if st.session_state.user_auth:
        if st.sidebar.button("ログアウト"):
            st.session_state.user_auth = None; st.rerun()

bg, text, accent = ("#050505", "#E0E0E0", "#00E5FF") if display_mode == "ダークモード" else ("#FFFFFF", "#333333", "#007BFF")
st.markdown(f"<style>.stApp {{ background-color: {bg}; color: {text}; }} .big-timer {{ font-family: 'Courier New'; font-size: 100px; font-weight: bold; color: {accent}; text-align: center; padding: 40px; border: 3px solid {accent}; border-radius: 20px; background: rgba(0, 229, 255, 0.05); margin: 20px 0; }}</style>", unsafe_allow_html=True)

# --- 3. 認証画面 ---
if st.session_state.user_auth is None:
    st.title("🌙 Sleep Tracker Pro")
    auth_tab = st.radio("メニュー", ["ログイン", "新規登録"], horizontal=True)
    with st.form(key="auth_final_v7"):
        u, p = st.text_input("ユーザー名"), st.text_input("パスワード", type="password")
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
                    st.success("完了！ログインしてください")
                except: st.error("その名前は使用されています")
else:
    user = st.session_state.user_auth
    tabs = st.tabs(["睡眠記録", "データ分析", "アラーム"])

    with tabs[0]:
        st.markdown("<h1 style='text-align: center;'>睡眠計測</h1>", unsafe_allow_html=True)
        if st.session_state.is_sleeping:
            if st.button("☀️ 起きた", type="primary", use_container_width=True):
                st.session_state.end_time = datetime.now(timezone.utc)
                st.session_state.is_sleeping, st.session_state.save_ready = False, True
                st.rerun()
            t_place = st.empty()
            while st.session_state.is_sleeping:
                diff = datetime.now(timezone.utc) - st.session_state.start_time
                h, r = divmod(int(diff.total_seconds()), 3600); m, s = divmod(r, 60)
                t_place.markdown(f"<div class='big-timer'>{h:02d}:{m:02d}:{s:02d}</div>", unsafe_allow_html=True)
                time.sleep(1)
        elif st.session_state.save_ready:
            sec = (st.session_state.end_time - st.session_state.start_time).total_seconds()
            st.subheader(f"睡眠時間: {int(sec)} 秒")
            sat = st.select_slider("満足度", options=[1,2,3,4,5], value=3)
            if st.button("クラウドに保存", use_container_width=True):
                supabase.table("sleep_records").insert({
                    "user_id": user['id'], "start_time": st.session_state.start_t_str,
                    "end_time": st.session_state.end_time.isoformat(), "duration": sec, "satisfaction": sat
                }).execute()
                st.session_state.save_ready = False; st.balloons(); st.rerun()
        else:
            if st.button("🛌 睡眠開始", type="primary", use_container_width=True):
                now = datetime.now(timezone.utc)
                st.session_state.start_time, st.session_state.start_t_str = now, now.isoformat()
                st.session_state.is_sleeping = True; st.rerun()

    # 【分析タブ】横軸の正確な表示修正
    with tabs[1]:
        st.header("📊 精密分析")
        res = supabase.table("sleep_records").select("*").eq("user_id", user['id']).order("start_time").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df['dt'] = pd.to_datetime(df['start_time'], utc=True)
            period = st.radio("📅 表示範囲を選択", ["今日のみ", "過去1週間", "過去1か月"], horizontal=True)
            
            now_utc = datetime.now(timezone.utc)
            today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

            # 範囲に応じた軸設定
            if period == "今日のみ":
                limit = today_start
                # 今日のみ：横軸は「時:分」表示
                x_scale = alt.X('dt:T', title='時刻', axis=alt.Axis(format='%H:%M', labelAngle=0), 
                                scale=alt.Scale(domain=[limit.isoformat(), now_utc.isoformat()]))
            elif period == "過去1週間":
                limit = today_start - timedelta(days=7)
                # 1週間：横軸は「月/日」表示
                x_scale = alt.X('dt:T', title='日付', axis=alt.Axis(format='%m/%d', tickCount=7), 
                                scale=alt.Scale(domain=[limit.isoformat(), now_utc.isoformat()]))
            else:
                limit = today_start - timedelta(days=30)
                # 1か月：横軸は「月/日」表示
                x_scale = alt.X('dt:T', title='日付', axis=alt.Axis(format='%m/%d', tickCount=10), 
                                scale=alt.Scale(domain=[limit.isoformat(), now_utc.isoformat()]))

            df_f = df[df['dt'] >= limit].copy()

            st.metric("平均睡眠時間", f"{df_f['duration'].mean() if not df_f.empty else 0:.1f} 秒")
            # 棒グラフの描画
            chart = alt.Chart(df_f).mark_bar(color=accent, size=15).encode(
                x=x_scale, 
                y=alt.Y('duration:Q', title='睡眠時間 [秒]'),
                tooltip=[alt.Tooltip('dt:T', title='記録日時', format='%Y/%m/%d %H:%M'), alt.Tooltip('duration:Q', title='秒数')]
            ).properties(height=400).interactive()
            st.altair_chart(chart, use_container_width=True)
        else: st.info("データを保存するとここに表示されます")

    # 【アラームタブ】
    with tabs[2]:
        st.header("⏰ アラーム")
        if not st.session_state.audio_unlocked:
            st.warning("⚠️ ブラウザの音ブロックを解除するため、まず下のボタンを1度クリックしてください。")
            if st.button("🔔 音声機能をアンロック"):
                st.session_state.audio_unlocked = True
                st.markdown(f'<audio src="https://www.soundjay.com/buttons/beep-01a.mp3" autoplay></audio>', unsafe_allow_html=True)
                st.rerun()
        
        if st.session_state.audio_unlocked:
            vol = st.slider("音量", 0.0, 1.0, 0.5)
            c1, c2 = st.columns(2)
            h, m = c1.number_input("時", 0, 23, 7), c2.number_input("分", 0, 59, 0)
            
            if st.session_state.alarm_on:
                if st.button("🔕 アラーム停止", type="primary", use_container_width=True):
                    st.session_state.alarm_on = False; st.rerun()
                st.markdown(f'<audio src="https://www.soundjay.com/buttons/beep-01a.mp3" autoplay loop id="ring"></audio><script>document.getElementById("ring").volume={vol}</script>', unsafe_allow_html=True)
                st.error("⏰ 起きる時間です！！")
            elif st.button("アラームをセット", use_container_width=True):
                st.session_state.target = f"{h:02d}:{m:02d}"; st.info(f"{st.session_state.target} にセット。このままにしてください。")
                while True:
                    if datetime.now().strftime("%H:%M") == st.session_state.target:
                        st.session_state.alarm_on = True; st.rerun()
                    time.sleep(1)
