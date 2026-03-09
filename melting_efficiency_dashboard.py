import pandas as pd
import streamlit as st
from datetime import datetime
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Учет роторной печи v4.4", layout="wide")

DB_FILE = "furnace_data.xlsx"

# --- ФУНКЦИИ РАБОТЫ С ДАННЫМИ ---
def load_data():
    if os.path.exists(DB_FILE):
        try:
            df = pd.read_excel(DB_FILE)
            rename_map = {
                "Мастер смены": "Мастер",
                "Расход топлива": "Расход (м3)",
                "Показание счетчика": "Счетчик (м3)",
                "Вес слитого (кг)": "Выход металла (кг)",
                "Счетчик топлива (м3)": "Счетчик (м3)"
            }
            df = df.rename(columns=rename_map)
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

if 'db' not in st.session_state:
    st.session_state.db = load_data()

if 'edit_index' not in st.session_state:
    st.session_state.edit_index = None

st.title("🔥 Мониторинг эффективности плавки")

# --- БОКОВАЯ ПАНЕЛЬ ---
st.sidebar.header("📝 Ввод данных")
masters_list = sorted(st.session_state.db["Мастер"].astype(str).unique().tolist()) if not st.session_state.db.empty else []

if st.session_state.edit_index is not None:
    row = st.session_state.db.loc[st.session_state.edit_index]
    st.sidebar.warning(f"Правка записи ID: {row['ID']}")
    d_date, d_shift, d_num = pd.to_datetime(row["Дата"]), row["Смена"], int(row["№ смены"])
    d_master, d_metal, d_count = str(row["Мастер"]), float(row["Выход металла (кг)"]), float(row["Счетчик (м3)"])
    btn_label = "Обновить"
else:
    d_date, d_shift, d_num = datetime.now(), "День", 1
    d_master, d_metal, d_count = "", 0.0, 0.0
    btn_label = "Добавить"

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

# --- ВИЗУАЛИЗАЦИЯ ---
if not st.session_state.db.empty:
    chart_df = st.session_state.db.sort_values(["Дата", "№ смены"]).copy()
    chart_df["Метка"] = chart_df.apply(lambda x: f"{x['Дата'].strftime('%d.%m')} №{x['№ смены']}", axis=1)

    st.subheader("📊 Посменная динамика: Металл и Топливо")
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Металл (Левая ось)
    fig.add_trace(
        go.Bar(x=chart_df["Метка"], y=chart_df["Выход металла (кг)"], 
               name="Металл (кг)", marker_color='#2E86C1', 
               text=chart_df["Выход металла (кг)"], textposition='auto',
               offsetgroup=1), # Группа 1
        secondary_y=False,
    )

    # Топливо (Правая ось)
    fig.add_trace(
        go.Bar(x=chart_df["Метка"], y=chart_df["Расход (м3)"], 
               name="Топливо (м3)", marker_color='#E67E22',
               text=chart_df["Расход (м3)"], textposition='auto',
               offsetgroup=2), # Группа 2
        secondary_y=True,
    )

    fig.update_layout(
        legend=dict(x=0.5, y=1.1, orientation="h", xanchor="center"),
        height=600,
        hovermode="x unified",
        # barmode='group' здесь не сработает напрямую с разными осями, 
        # поэтому мы используем offsetgroup для разделения столбиков
    )

    # Ограничение оси металла от 1000 кг
    fig.update_yaxes(title_text="<b>Металл (кг)</b>", secondary_y=False, 
                     range=[1000, max(chart_df["Выход металла (кг)"])*1.1])
    fig.update_yaxes(title_text="<b>Топливо (м3)</b>", secondary_y=True, 
                     range=[0, max(chart_df["Расход (м3)"])*1.2])

    st.plotly_chart(fig, use_container_width=True)

    # Таблица и Журнал
    t1, t2 = st.tabs(["📋 Таблица", "⚙️ Журнал"])
    with t1:
        df_view = st.session_state.db.copy()
        df_view["КПД"] = df_view.apply(lambda x: x["Выход металла (кг)"] / x["Расход (м3)"] if x["Расход (м3)"] > 0 else 0, axis=1)
        max_k = df_view["КПД"].max()
        df_view["Эффективность (%)"] = df_view["КПД"].apply(lambda x: round((x / max_k * 100), 1) if max_k > 0 else 0)
        df_view["Дата"] = df_view["Дата"].dt.date
        st.dataframe(df_view.drop(columns=["ID", "КПД"]).sort_values(["Дата", "№ смены"], ascending=False), use_container_width=True)
    with t2:
        for idx, row in st.session_state.db.iterrows():
            c1, c2, c3, c4 = st.columns([1, 4, 1, 1])
            try: display_id = int(row['ID']) % 1000
            except: display_id = "!!!"
            c1.write(f"#{display_id}")
            c2.write(f"**{row['Дата'].date()}** | Смена №{row['№ смены']} | {row['Мастер']}")
            if c3.button("📝", key=f"e_{idx}"): st.session_state.edit_index = idx; st.rerun()
            if c4.button("🗑️", key=f"d_{idx}"): 
                st.session_state.db = st.session_state.db.drop(idx).reset_index(drop=True)
                save_data(st.session_state.db); st.rerun()
