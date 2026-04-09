import pandas as pd
import streamlit as st
from datetime import datetime
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re

st.set_page_config(page_title="Мониторинг выплавки и затрат", layout="wide")

DB_FILE = "furnace_data.xlsx"

# --- ЗАГРУЗКА ДАННЫХ ---
def load_data():
    if os.path.exists(DB_FILE):
        try:
            df = pd.read_excel(DB_FILE)
            df.columns = [str(c).strip() for c in df.columns]
            rename_map = {
                "Выход металла (кг)": "Металл (кг)",
                "Счетчик": "Счетчик (м3)", 
                "Расход": "Расход (м3)",
                "Комментарии (Журнал событий)": "Комментарии"
            }
            df = df.rename(columns=rename_map)
            req = ["ID", "Дата", "Смена", "Мастер", "Металл (кг)", "Счетчик (м3)", "Расход (м3)", "Комментарии"]
            for c in req:
                if c not in df.columns:
                    df[c] = 0.0 if any(x in c for x in ["кг", "м3"]) else ""
            for c in ["Металл (кг)", "Счетчик (м3)", "Расход (м3)"]:
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.').str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0.0)
            df["Дата"] = pd.to_datetime(df["Дата"], errors='coerce')
            df["Комментарии"] = df["Комментарии"].fillna("").astype(str)
            df = df.sort_values(["Дата", "Смена"], ascending=[True, True])
            return df.dropna(subset=["Дата"])[req]
        except Exception as e:
            st.error(f"Ошибка БД: {e}")
    return pd.DataFrame(columns=["ID", "Дата", "Смена", "Мастер", "Металл (кг)", "Счетчик (м3)", "Расход (м3)", "Комментарии"])

def save_data(df):
    df.sort_values(["Дата", "Смена"], ascending=[True, True]).to_excel(DB_FILE, index=False)

if 'db' not in st.session_state:
    st.session_state.db = load_data()

st.title("🔥 Мониторинг выплавки и затрат v8.3")

# --- БОКОВАЯ ПАНЕЛЬ ---
st.sidebar.header("💰 Экономика")
price_l = st.sidebar.number_input("Цена ДТ (тг/литр)", min_value=0.0, value=320.0, step=1.0)
price_m3 = price_l * 1000

with st.sidebar.form("entry_form"):
    st.markdown("### 📝 Новая запись")
    in_date = st.date_input("Дата", datetime.now())
    in_shift = st.selectbox("Смена", ["День", "Ночь"])
    in_master = st.text_input("Мастер")
    in_metal = st.number_input("Металл (кг)", min_value=0.0)
    in_count = st.number_input("Счетчик (м³)", min_value=0.0, format="%.3f")
    in_comm = st.text_area("События")
    if st.form_submit_button("Сохранить"):
        clean_comm = re.sub(r'(чушка|пакет|пачек)?\s*кэз', 'остатки шихтовых', in_comm, flags=re.IGNORECASE)
        new_row = {"ID": int(datetime.now().timestamp()), "Дата": pd.to_datetime(in_date), "Смена": in_shift, "Мастер": in_master, "Металл (кг)": in_metal, "Счетчик (м3)": in_count, "Расход (м3)": 0.0, "Комментарии": clean_comm}
        st.session_state.db = pd.concat([st.session_state.db, pd.DataFrame([new_row])], ignore_index=True)
        st.session_state.db = st.session_state.db.sort_values(["Дата", "Смена"], ascending=[True, True]).reset_index(drop=True)
        for i in range(1, len(st.session_state.db)):
            d = st.session_state.db.at[i, "Счетчик (м3)"] - st.session_state.db.at[i-1, "Счетчик (м3)"]
            st.session_state.db.at[i, "Расход (м3)"] = round(max(0, d), 3) if d < 2.0 else 0.350
        save_data(st.session_state.db); st.rerun()

# --- АНАЛИТИКА ---
if not st.session_state.db.empty:
    df = st.session_state.db.copy()
    df["Затраты"] = df["Расход (м3)"] * price_m3
    df["тг_на_кг"] = df.apply(lambda x: x["Затраты"] / x["Металл (кг)"] if x["Металл (кг)"] > 0 else 0, axis=1)
    df["Метка"] = df.apply(lambda x: f"{x['Дата'].strftime('%d.%m')} {x['Смена'][0]}", axis=1)
    
    color_map = {'День': '#3498DB', 'Ночь': '#2C3E50'}
    df["Цвет"] = df["Смена"].map(color_map)

    # 1. График: Производство и Расход топлива
    st.subheader("📊 Производство и Расход топлива")
    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    fig1.add_trace(go.Bar(x=df["Метка"], y=df["Металл (кг)"], marker_color=df["Цвет"], text=df["Металл (кг)"].apply(lambda x: f"{int(x)} кг"), textposition='outside', name="Металл (кг)"), secondary_y=False)
    fig1.add_trace(go.Scatter(x=df["Метка"], y=df["Расход (м3)"], line=dict(color='#E67E22', width=4), mode='lines+markers+text', text=df["Расход (м3)"].apply(lambda x: f"{x:.3f}"), name="Расход ДТ (м³)"), secondary_y=True)
    fig1.update_layout(height=500, legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"), yaxis_range=[0, df["Металл (кг)"].max()*1.3])
    st.plotly_chart(fig1, use_container_width=True)

    # 2. График: Эффективность плавки и Выплавка (v8.3 ОБНОВЛЕННЫЙ)
    st.subheader("💰 Эффективность плавки и Выплавка")
    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Столбики: Эффективность (тг/кг)
    fig2.add_trace(go.Bar(
        x=df["Метка"], 
        y=df["тг_на_кг"], 
        name="Эффективность (тг/кг)", 
        marker_color=df["Цвет"], 
        text=df["тг_на_кг"].apply(lambda x: f"{x:.1f} тг/кг"), # Добавлено /кг
        textposition='outside', 
        textfont=dict(size=14, color='black'),
        cliponaxis=False
    ), secondary_y=False)
    
    # Линия: Количество металла (кг) - СПЛОШНАЯ ЗЕЛЕНАЯ
    fig2.add_trace(go.Scatter(
        x=df["Метка"], 
        y=df["Металл (кг)"], 
        name="Количество металла (кг)", 
        line=dict(color='#2ECC71', width=4), # Сплошная зеленая линия
        mode='lines+markers+text',
        text=df["Металл (кг)"].apply(lambda x: f"{int(x)} кг"),
        textposition='top center',
        textfont=dict(size=12, color='#27AD60') # Зеленые подписи
    ), secondary_y=True)

    fig2.update_layout(
        height=550, 
        margin=dict(t=60),
        legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center", font=dict(size=13)),
        hovermode="x unified"
    )
    
    fig2.update_yaxes(title_text="Себестоимость (тг/кг)", secondary_y=False, range=[0, df["тг_на_кг"].max()*1.4])
    fig2.update_yaxes(title_text="Металл (кг)", secondary_y=True, range=[0, df["Металл (кг)"].max()*1.3])
    st.plotly_chart(fig2, use_container_width=True)

    # --- АНАЛИТИЧЕСКИЕ СПОЙЛЕРЫ ---
    st.markdown("---")
    with st.expander("🏆 Карточки: Лучшая и худшая смена периода"):
        df_work = df[df["Металл (кг)"] > 100].copy()
        if not df_work.empty:
            best_idx = df_work["тг_на_кг"].idxmin()
            worst_idx = df_work["тг_на_кг"].idxmax()
            c1, c2 = st.columns(2)
            with c1: st.success(f"🏆 **ЛУЧШАЯ ЭФФЕКТИВНОСТЬ**\n\n{df_work.loc[best_idx, 'Дата'].date()} | {df_work.loc[best_idx, 'Смена']}\n\n# {df_work.loc[best_idx, 'тг_на_кг']:.1f} тг/кг\n\nМастер: {df_work.loc[best_idx, 'Мастер']}")
            with c2: st.error(f"⚠️ **ХУДШАЯ ЭФФЕКТИВНОСТЬ**\n\n{df_work.loc[worst_idx, 'Дата'].date()} | {df_work.loc[worst_idx, 'Смена']}\n\n# {df_work.loc[worst_idx, 'тг_на_кг']:.1f} тг/кг\n\nМастер: {df_work.loc[worst_idx, 'Мастер']}")

    with st.expander("📊 График-рейтинг: Смены по возрастанию себестоимости"):
        df_rank = df[df["Металл (кг)"] > 0].sort_values("тг_на_кг").copy()
        if not df_rank.empty:
            fig_rank = go.Figure(go.Bar(x=df_rank["Метка"], y=df_rank["тг_на_кг"], marker_color=df_rank["Цвет"], text=df_rank["тг_на_кг"].apply(lambda x: f"{x:.1f}"), textposition='outside'))
            fig_rank.update_layout(height=450, title="Рейтинг смен (слева - дешевле 1 кг)", xaxis_title="Смены", yaxis_title="тг/кг")
            st.plotly_chart(fig_rank, use_container_width=True)

else:
    st.info("Данных нет. Используйте форму в боковой панели.")
