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

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

# --- 2. UI設定 ---
st.set_page_config(page_title="Sleep Tracker Ultra", layout="wide")

# セッション状態
for k, v in {'user_auth': None, 'is_sleeping': False, 'save_ready': False, 'alarm_on': False}.items():
    if k not in st.session_state: st.session_state[k] = v

with st.sidebar:
    st.title("⚙️ 設定")
    display_mode = st.radio("表示モード", ["ダーク", "通常"], horizontal=True)
    if st.session_state.user_auth:
        if st.sidebar.button("ログアウト"): st.session_state.user_auth = None; st.rerun()

bg, text, accent = ("#050505", "#E0E0E0", "#00E5FF") if display_mode == "ダーク" else ("#FFFFFF", "#333333", "#007BFF")
st.markdown(f"<style>.stApp {{ background-color: {bg}; color: {text}; }} .big-timer {{ font-family: 'Courier New'; font-size: 100px; font-weight: bold; color: {accent}; text-align: center; padding: 40px; border: 3px solid {accent}; border-radius: 20px; background: rgba(0, 229, 255, 0.05); margin: 20px 0; }}</style>", unsafe_allow_html=True)

# --- 3. 認証画面 ---
if st.session_state.user_auth is None:
    st.title("🌙 Sleep Tracker Pro")
    auth_tab = st.radio("メニュー", ["ログイン", "新規登録"], horizontal=True)
    with st.form(key="auth_v9"):
        u, p = st.text_input("ユーザー名"), st.text_input("パスワード", type="password")
        if st.form_submit_button("実行"):
            hp = hash_pw(p)
            if auth_tab == "ログイン":
                res = supabase.table("users").select("*").eq("username", u).eq("password", hp).execute()
                if res.data: st.session_state.user_auth = {"id": res.data[0]['id'], "name": res.data[0]['username']}; st.rerun()
                else: st.error("情報が違います")
            else:
                try: supabase.table("users").insert({"username": u, "password": hp}).execute(); st.success("完了！")
                except: st.error("その名前は使えません")
else:
    user = st.session_state.user_auth
    tabs = st.tabs(["睡眠記録", "データ分析", "アラーム"])

    with tabs[0]:
        st.markdown("<h1 style='text-align: center;'>睡眠計測</h1>", unsafe_allow_html=True)
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
            st.subheader(f"睡眠時間: {int(sec)} 秒")
            sat = st.select_slider("満足度", options=[1,2,3,4,5], value=3)
            if st.button("保存", use_container_width=True):
                supabase.table("sleep_records").insert({"user_id": user['id'], "start_time": st.session_state.start_t_str, "end_time": st.session_state.end_t.isoformat(), "duration": sec, "satisfaction": sat}).execute()
                st.session_state.save_ready = False; st.balloons(); st.rerun()
        else:
            if st.button("🛌 睡眠開始", type="primary", use_container_width=True):
                n = datetime.now(timezone.utc); st.session_state.start_t, st.session_state.start_t_str = n, n.isoformat(); st.session_state.is_sleeping = True; st.rerun()

    # 【分析】期間表示の完全修正
    with tabs[1]:
        st.header("📊 精密分析")
        res = supabase.table("sleep_records").select("*").eq("user_id", user['id']).order("start_time").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df['dt'] = pd.to_datetime(df['start_time'], utc=True)
            period = st.radio("📅 表示範囲を選択", ["今日のみ", "過去1週間", "過去1か月"], horizontal=True)
            now = datetime.now(timezone.utc); today_s = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if period == "今日のみ": limit, fmt, lbl = today_s, '%H:%M', '時刻'
            elif period == "過去1週間": limit, fmt, lbl = today_s - timedelta(days=7), '%m/%d', '日付'
            else: limit, fmt, lbl = today_s - timedelta(days=30), '%m/%d', '日付'
            df_f = df[df['dt'] >= limit].copy()
            x_ax = alt.X('dt:T', title=lbl, axis=alt.Axis(format=fmt, labelAngle=0), scale=alt.Scale(domain=[limit.isoformat(), now.isoformat()]))
            st.metric("平均睡眠", f"{df_f['duration'].mean() if not df_f.empty else 0:.1f} 秒")
            st.altair_chart(alt.Chart(df_f).mark_bar(color=accent, size=15).encode(x=x_ax, y=alt.Y('duration:Q', title='睡眠時間 [秒]')).properties(height=400), use_container_width=True)
        else: st.info("データがありません")

    # 【アラーム】JavaScriptを使った「絶対に音を出す」ための新設計
    with tabs[2]:
        st.header("⏰ アラーム設定")
        
        # 音源URL（確実に鳴るようにパブリックなmp3を使用）
        SOUND_URL = "https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3"
        
        # --- 手動テストボタン ---
        st.subheader("🔊 サウンド確認")
        if st.button("▶️ 手動で音をテストする"):
            st.components.v1.html(f"""
                <audio id="testAudio" src="{SOUND_URL}" autoplay></audio>
                <p style="color: {accent};">音が鳴りましたか？鳴らない場合はブラウザの設定で音声を許可してください。</p>
            """, height=50)

        st.divider()

        st.subheader("⏰ アラームをセット")
        c1, c2 = st.columns(2)
        h, m = c1.number_input("時", 0, 23, 7), c2.number_input("分", 0, 59, 0)
        vol = st.slider("アラーム音量", 0.0, 1.0, 0.7)
        
        target_time = f"{h:02d}:{m:02d}"
        
        if st.button("✅ この時間でセットする"):
            st.session_state.alarm_time = target_time
            st.session_state.alarm_active = True
            st.success(f"{target_time} にアラームをセットしました！")

        if st.session_state.get('alarm_active'):
            st.info(f"現在 {st.session_state.alarm_time} にセット中。画面を閉じないでください。")
            
            # 正確な時間チェック
            current_t = datetime.now().strftime("%H:%M")
            if current_t == st.session_state.alarm_time:
                # 指定時刻にJavaScriptで音をループ再生
                st.components.v1.html(f"""
                    <div style="background-color: #ff4b4b; color: white; padding: 20px; text-align: center; border-radius: 10px;">
                        <h1>⏰ 起きる時間です！！ ({current_t})</h1>
                        <audio src="{SOUND_URL}" autoplay loop id="alarmAudio"></audio>
                        <script>document.getElementById("alarmAudio").volume = {vol};</script>
                    </div>
                """, height=150)
                if st.button("🔕 アラームを止める"):
                    st.session_state.alarm_active = False
                    st.rerun()
            else:
                # 10秒ごとに自動更新して時間をチェックさせる
                time.sleep(10)
                st.rerun()
