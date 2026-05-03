import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

st.set_page_config(page_title="Tintoria nuovefibre", layout="wide")

# ------------------------
# CONFIG
# ------------------------
FASI = [
    "Bruciapelo",
    "Sbozzima",
    "Lavaggio",
    "Candeggio Vaporizzo",
    "Mercerizzo",
    "Sodatrice",
    "Candeggio Stoccaggio"
]

CAPACITA = {
    "Bruciapelo": (5,5),
    "Sbozzima": (5,5),
    "Lavaggio": (5,5),
    "Candeggio Vaporizzo": (5,5),
    "Mercerizzo": (5,5),
    "Sodatrice": (5,5),
    "Candeggio Stoccaggio": (5,5),
}

UTENTI = {
    "op1": {"password": "op1", "ruolo": "operatore"},
    "admin1": {"password": "admin1", "ruolo": "admin"},
}

DB_FILE = "lotti.csv"

# ------------------------
# DB
# ------------------------
def load_data():
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE)
    else:
        return pd.DataFrame(columns=[
            "Lotto","Articolo","DataInizio","IndiceFase","Priorità"
        ])

def save_data(df):
    df.to_csv(DB_FILE, index=False)

df = load_data()

# ------------------------
# LOGIN
# ------------------------
if "logged" not in st.session_state:
    st.session_state.logged = False

if not st.session_state.logged:
    st.title("Login Tintoria nuovefibre")

    user = st.text_input("Utente")
    pwd = st.text_input("Password", type="password")

    if st.button("Login"):
        if user in UTENTI and UTENTI[user]["password"] == pwd:
            st.session_state.logged = True
            st.session_state.user = user
            st.session_state.ruolo = UTENTI[user]["ruolo"]
            st.rerun()
        else:
            st.error("Credenziali errate")

    st.stop()

# ------------------------
# HEADER
# ------------------------
st.sidebar.write(f"👤 {st.session_state.user}")
menu = st.sidebar.selectbox("Menu", ["Produzione","Macchine","Inserimento"])

# ------------------------
# CALCOLI
# ------------------------
def calcola(df):
    if df.empty:
        return df

    df = df.copy()

    df["Fase"] = df["IndiceFase"].apply(
        lambda x: FASI[x] if x < len(FASI) else "Finito"
    )

    df["Data Fase"] = df.apply(
        lambda r: pd.to_datetime(r["DataInizio"]) + timedelta(days=int(r["IndiceFase"])),
        axis=1
    )

    # priorità ordinata
    ordine_priorita = {"Urgente":0,"Alta":1,"Normale":2}
    df["Ord"] = df["Priorità"].map(ordine_priorita)

    df = df.sort_values(by=["Data Fase","Ord"])

    # assegna turni
    df["Turno"] = ""
    df["Over"] = ""

    for (data, macchina), group in df.groupby(["Data Fase","Fase"]):
        if macchina == "Finito":
            continue

        cap1, cap2 = CAPACITA.get(macchina,(5,5))

        for i, idx in enumerate(group.index):
            if i < cap1:
                df.at[idx,"Turno"] = "1"
            elif i < cap1 + cap2:
                df.at[idx,"Turno"] = "2"
            else:
                df.at[idx,"Turno"] = "OVER"

    return df

df_calc = calcola(df)

# ------------------------
# INSERIMENTO
# ------------------------
if menu == "Inserimento" and st.session_state.ruolo == "admin":
    st.subheader("➕ Nuovo Lotto")

    lotto = st.text_input("Lotto")
    articolo = st.text_input("Articolo")
    data = st.date_input("Data Inizio", datetime.today())
    priorita = st.selectbox("Priorità", ["Normale","Alta","Urgente"])

    if st.button("Inserisci"):
        new = pd.DataFrame([{
            "Lotto": lotto,
            "Articolo": articolo,
            "DataInizio": data,
            "IndiceFase": 0,
            "Priorità": priorita
        }])

        df = pd.concat([df, new], ignore_index=True)
        save_data(df)
        st.success("Inserito!")
        st.rerun()

# ------------------------
# PRODUZIONE
# ------------------------
elif menu == "Produzione":
    st.subheader("📅 Produzione")

    giorni = st.slider("Giorni futuri", 0, 10, 2)

    oggi = datetime.today()
    limite = oggi + timedelta(days=giorni)

    df_view = df_calc[
        (df_calc["Data Fase"] >= pd.to_datetime(oggi)) &
        (df_calc["Data Fase"] <= pd.to_datetime(limite))
    ]

    for i, r in df_view.iterrows():
        col1,col2,col3,col4,col5 = st.columns([2,2,2,1,1])

        col1.write(f"**{r['Lotto']}**")
        col2.write(r["Fase"])
        col3.write(r["Data Fase"].date())
        col4.write(f"T{r['Turno']}")
        col5.write(r["Priorità"])

        if r["Fase"] != "Finito":
            if st.button(f"Fatto {i}"):
                df.at[i,"IndiceFase"] += 1
                save_data(df)
                st.rerun()

        if st.button(f"Urg {i}"):
            df.at[i,"Priorità"] = "Urgente"
            save_data(df)
            st.rerun()

# ------------------------
# MACCHINE
# ------------------------
elif menu == "Macchine":
    st.subheader("⚙️ Vista Macchine")

    macchina = st.selectbox("Macchina", FASI)

    df_m = df_calc[df_calc["Fase"] == macchina]

    st.dataframe(df_m[[
        "Lotto","Data Fase","Turno","Priorità"
    ]])