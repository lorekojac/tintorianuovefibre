import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from streamlit.components.v1 import html
from streamlit_sortables import sort_items

st.set_page_config(layout="wide", page_title="Tintoria nuovefibre")

# ---------------- CONFIG ----------------
FASI = [
    "Bruciapelo","Sbozzima","Lavaggio",
    "Candeggio Vaporizzo","Mercerizzo",
    "Sodatrice","Candeggio Stoccaggio","Ramosa"
]

UTENTI = {
    "op1": {"password":"op1","ruolo":"operatore"},
    "admin1": {"password":"admin1","ruolo":"admin"}
}

DB="tintoria.db"

# ---------------- DB ----------------
conn = sqlite3.connect(DB, check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS lotti(
id INTEGER PRIMARY KEY AUTOINCREMENT,
lotto TEXT UNIQUE,
articolo TEXT,
cliente TEXT,
metri REAL,
data TEXT,
fase INT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS macchine(
nome TEXT PRIMARY KEY,
velocita REAL,
setup INT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS cicli(
articolo TEXT PRIMARY KEY,
fasi TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS orari(
id INTEGER PRIMARY KEY,
inizio TEXT
)
""")

conn.commit()

# default
for f in FASI:
    c.execute("INSERT OR IGNORE INTO macchine VALUES (?,?,?)",(f,20,10))
c.execute("INSERT OR IGNORE INTO orari VALUES (1,'08:00')")
conn.commit()

# ---------------- FUNZIONI ----------------
def get_orario():
    df = pd.read_sql("SELECT * FROM orari", conn)
    return df.iloc[0]["inizio"]

def get_ciclo(art):
    r = c.execute("SELECT fasi FROM cicli WHERE articolo=?", (art,)).fetchone()
    return r[0].split("|") if r and r[0] else []

def lotto_esiste(lotto):
    r = c.execute("SELECT id FROM lotti WHERE lotto=?", (lotto,)).fetchone()
    return r is not None

def load():
    df = pd.read_sql("SELECT * FROM lotti", conn)
    if df.empty:
        return df

    mac = pd.read_sql("SELECT * FROM macchine", conn)
    start_day = get_orario()

    records=[]
    for _,r in df.iterrows():
        base_date = pd.to_datetime(r["data"])
        ciclo = get_ciclo(r["articolo"])

        for i in range(r["fase"], len(ciclo)):
            fase = ciclo[i]

            vel = mac[mac["nome"]==fase]["velocita"].values[0]
            setup = mac[mac["nome"]==fase]["setup"].values[0]

            durata = (r["metri"]/vel) + setup
            giorno = base_date + timedelta(days=i)

            start = datetime.combine(
                giorno.date(),
                datetime.strptime(start_day,"%H:%M").time()
            )
            end = start + timedelta(minutes=durata)

            records.append({
                "id":r["id"],
                "lotto":r["lotto"],
                "fase":fase,
                "start":start,
                "end":end,
                "durata":round(durata,1)
            })

    return pd.DataFrame(records)

# ---------------- LOGIN ----------------
if "login" not in st.session_state:
    st.session_state.login=False

if not st.session_state.login:
    st.title("Login")

    u=st.text_input("Utente")
    p=st.text_input("Password", type="password")

    if st.button("Login"):
        if u in UTENTI and UTENTI[u]["password"]==p:
            st.session_state.login=True
            st.session_state.ruolo=UTENTI[u]["ruolo"]
            st.rerun()
        else:
            st.error("Credenziali errate")

    st.stop()

df = load()

# ---------------- MENU ----------------
if st.session_state.ruolo=="operatore":
    menu="Produzione"
else:
    menu=st.sidebar.selectbox("Menu",[
        "Produzione","Inserimento","Cicli","Setup"
    ])

# ---------------- PRODUZIONE ----------------
if menu=="Produzione":
    st.title("Produzione")

    if df.empty:
        st.info("Nessun lavoro")
    else:
        macchina = st.selectbox("Macchina", sorted(df["fase"].unique()))
        dfm = df[df["fase"]==macchina].sort_values(by="start")

        for i,r in dfm.iterrows():
            col1,col2,col3=st.columns(3)

            col1.write(r["lotto"])
            col2.write(r["start"].strftime("%d/%m %H:%M"))
            col3.write(f"{r['durata']} min")

            if st.button(f"Fatto_{r['id']}_{i}"):
                c.execute("UPDATE lotti SET fase=fase+1 WHERE id=?", (r["id"],))
                conn.commit()
                st.rerun()

# ---------------- INSERIMENTO ----------------
elif menu=="Inserimento":
    st.title("Nuovo lotto")

    lotto = st.text_input("Lotto")
    articolo = st.text_input("Articolo")
    cliente = st.text_input("Cliente")
    metri = st.number_input("Metri", min_value=1.0, value=1000.0)
    data = st.date_input("Data")

    if st.button("Salva"):
        errori = []

        # controlli
        if not lotto:
            errori.append("Lotto obbligatorio")
        if not articolo:
            errori.append("Articolo obbligatorio")
        if metri <= 0:
            errori.append("Metri devono essere > 0")

        if lotto_esiste(lotto):
            errori.append("Lotto già esistente")

        ciclo = get_ciclo(articolo)
        if not ciclo:
            errori.append("Questo articolo non ha un ciclo definito")

        # output errori
        if errori:
            for e in errori:
                st.error(e)
        else:
            c.execute("""
                INSERT INTO lotti (lotto, articolo, cliente, metri, data, fase)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (lotto.strip(), articolo.strip(), cliente.strip(), metri, str(data), 0))

            conn.commit()
            st.success("Lotto inserito correttamente")
            st.rerun()

# ---------------- CICLI ----------------
elif menu=="Cicli":
    st.title("Editor cicli")

    art = st.text_input("Articolo")

    if "ciclo" not in st.session_state:
        st.session_state.ciclo = []

    if art:
        st.session_state.ciclo = get_ciclo(art)

    st.write(st.session_state.ciclo)

    nuova = st.selectbox("Fase", FASI)

    if st.button("Aggiungi"):
        st.session_state.ciclo.append(nuova)
        st.rerun()

    if st.button("Salva"):
        c.execute("INSERT OR REPLACE INTO cicli VALUES (?,?)",
                  (art, "|".join(st.session_state.ciclo)))
        conn.commit()
        st.success("Ciclo salvato")

# ---------------- SETUP ----------------
elif menu=="Setup":
    st.title("Orario lavoro")

    start = st.text_input("Inizio giornata", "08:00")

    if st.button("Salva"):
        c.execute("UPDATE orari SET inizio=? WHERE id=1",(start,))
        conn.commit()
        st.success("Salvato")
