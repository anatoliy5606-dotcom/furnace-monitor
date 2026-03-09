import pandas as pd
import streamlit as st
from datetime import datetime
import os
import plotly.graph_objects as go

st.set_page_config(page_title="Учет роторной печи v4.2", layout="wide")

DB_FILE = "furnace_data.xlsx"

# --- ФУНКЦИИ РАБОТЫ С ДАННЫМИ ---
def load_data():
    if os.path.exists(DB_FILE):
        try:
            df = pd.read_excel(DB_FILE)
            # Автоматическое приведение заголовков к стандарту
            rename_map = {
                "Мастер смены": "Мастер",
                "Расход топлива": "Расход (м3)",
                "Показание счетчика": "Счетчик (м3)",
                "Вес слитого (кг)": "Выход металла (кг)",
                "Счетчик топлива (м3)": "Счетчик (м3)"
            }
            df = df.rename(columns=rename_map)
            
            # Проверка и создание недостающих колонок
            required = ["ID", "Дата", "Смена", "№ смены", "Мастер", "Выход металла (кг)", "Счетчик (м3)", "Расход (м3)"]
            for col in required:
                if col not in df.columns:
                    df[col] = 0 if "кг" in col or "м3" in col else ""
            
            df["Дата"] = pd.to_datetime(df["Дата"])
            return df
        except Exception as e:
            st.error(f"Ошибка чтения базы данных: {e}")
            return pd.DataFrame(columns=["ID", "Дата", "Смена", "№ смены", "Мастер", "Выход металла (кг)", "Счетчик (м3)", "Расход (м3)"])
    return pd.DataFrame(columns=["ID", "Дата", "Смена", "№ смены", "Мастер", "Выход металла (кг)", "Счетчик (м3)", "Расход (м3)"])

def save_data(df):
    df = df.sort_values(["Дата", "№ смены"])
    df.to_excel(DB_FILE, index=False)

# Инициализация состояния
if 'db' not in st.session_state:
    st.session_state.db = load_data()

if 'edit_index' not in st.session_state:
    st.session_state.edit_index = None

st.title("🔥 Учет эффективности плавки роторной печи")

# --- БОКОВАЯ ПАНЕЛЬ ---
st.sidebar.header("📝 Ввод данных смены")

masters_list = []
if not st.session_state.db.empty:
    masters_list = sorted(st.session_state.db["Мастер"].astype(str).unique().tolist())

if st.session_state.edit_index is not None:
    row = st.session_state.db.loc[st.session_state.edit_index]
    st.sidebar.warning(f"Редактирование ID: {row['ID']}")
    d_date, d_shift, d_num = pd.to_datetime(row["Дата"]), row["Смена"], int(row["№ смены"])
    d_master, d_metal, d_count = str(row["Мастер"]), float(row["Выход металла (кг)"]), float(row["Счетчик (м3)"])
    btn_label = "Обновить запись"
else:
    d_date, d_shift, d_num = datetime.now(), "День", 1
    d_master, d_metal, d_count = "", 0.0, 0.0
    btn_label = "Добавить в базу"

with st.sidebar.form("entry_form"):
    in_date = st.date_input("Дата", d_date)
    in_shift = st.selectbox("Тип смены", ["День", "Ночь"], index=0 if d_shift=="День" else 1)
    in_num = st.selectbox("№ смены", [1, 2, 3, 4], index=d_num-1 if d_num <= 4 else 0)
    in_m_sel = st.selectbox("Выбрать мастера", [""] + masters_list)
    in_m_new = st.text_input("Или вписать нового")
    in_metal = st.number_input("Выход металла (кг)", min_value=0.0, value=d_metal)
    in_count = st.number_input("Счетчик (м³)", min_value=0.0, value=d_count, format="%.3f")
    submit = st.form_submit_button(btn_label)

if submit:
    final_master = in_m_new if in_m_new else in_m_sel
    entry = {
        "ID": st.session_state.db.loc[st.session_state.edit_index]["ID"] if st.session_state.edit_index is not None else int(datetime.now().timestamp()),
        "Дата": pd.to_datetime(in_date), "Смена": in_shift, "№ смены": in_num,
        "Мастер": final_master, "Выход металла (кг)": in_metal,
        "Счетчик (м3)": in_count, "Расход (м3)": 0.0
    }

    if st.session_state.edit_index is not None:
        st.session_state.db.loc[st.session_state.edit_index] = entry
        st.session_state.edit_index = None
    else:
        st.session_state.db = pd.concat([st.session_state.db, pd.DataFrame([entry])], ignore_index=True)
    
    # ПЕРЕСЧЕТ РАСХОДА ТОПЛИВА ПО ВСЕЙ ЦЕПОЧКЕ
    st.session_state.db = st.session_state.db.sort_values(["Дата", "№ смены"]).reset_index(drop=True)
    for i in range(len(st.session_state.db)):
        if i > 0:
            prev_c = st.session_state.db.iloc[i-1]["Счетчик (м3)"]
            curr_c = st.session_state.db.iloc[i]["Счетчик (м3)"]
            st.session_state.db.at[i, "Расход (м3)"] = round(curr_c - prev_c, 3) if curr_c >= prev_c else 0.0
        else:
            st.session_state.db.at[i, "Расход (м3)"] = 0.0

    save_data(st.session_state.db)
    st.rerun()

# --- АНАЛИТИКА ---
if not st.session_state.db.empty:
    df_a = st.session_state.db.copy()
    
    # Эффективность (%)
    df_a["КПД"] = df_a.apply(lambda x: x["Выход металла (кг)"] / x["Расход (м3)"] if x["Расход (м3)"] > 0 else 0, axis=1)
    max_kpd = df_a["КПД"].max()
    df_a["Эффективность (%)"] = df_a["КПД"].apply(lambda x: round((x / max_kpd * 100), 1) if max_kpd > 0 else 0)

    # Подготовка данных для графика
    chart_df = df_a.sort_values(["Дата", "№ смены"]).copy()
    chart_df["Метка"] = chart_df.apply(lambda x: f"{x['Дата'].strftime('%d.%m')} №{x['№ смены']} ({x['Смена'][0]})", axis=1)

    st.subheader("📊 Посменная динамика ресурсов (Лог. шкала)")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=chart_df["Метка"], y=chart_df["Выход металла (кг)"], name="Металл (кг)", marker_color='#2E86C1', text=chart_df["Выход металла (кг)"], textposition='auto'))
    fig.add_trace(go.Bar(x=chart_df["Метка"], y=chart_df["Расход (м3)"], name="Топливо (м3)", marker_color='#E67E22', text=chart_df["Расход (м3)"], textposition='auto'))
    fig.update_layout(yaxis=dict(type="log", title="Лог. масштаб"), barmode='group', height=500, legend=dict(x=0.5, y=1.1, orientation="h", xanchor="center"))
    st.plotly_chart(fig, use_container_width=True)

    t1, t2 = st.tabs(["📋 Сводная таблица", "⚙️ Журнал управления"])
    
    with t1:
        view_df = df_a.drop(columns=["ID", "КПД"]).copy()
        view_df["Дата"] = view_df["Дата"].dt.date
        st.dataframe(view_df.sort_values(["Дата", "№ смены"], ascending=False), use_container_width=True)

    with t2:
        st.subheader("Редактирование записей")
        for idx, row in st.session_state.db.iterrows():
            c1, c2, c3, c4 = st.columns([1, 4, 1, 1])
            
            # БЕЗОПАСНЫЙ ВЫВОД ID (исправление TypeError)
            try:
                display_id = int(row['ID']) % 1000
            except:
                display_id = "!!!"
                
            c1.write(f"#{display_id}")
            c2.write(f"**{row['Дата'].date()}** | Смена №{row['№ смены']} | {row['Мастер']}")
            
            if c3.button("📝", key=f"edit_btn_{idx}"):
                st.session_state.edit_index = idx
                st.rerun()
            if c4.button("🗑️", key=f"del_btn_{idx}"): 
                st.session_state.db = st.session_state.db.drop(idx).reset_index(drop=True)
                save_data(st.session_state.db)
                st.rerun()
else:
    st.info("База данных пуста. Внесите данные первой смены слева.")
