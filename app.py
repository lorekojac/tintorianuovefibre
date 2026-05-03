import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, time
from streamlit.components.v1 import html

st.set_page_config(layout="wide", page_title="Tintoria nuovefibre PRO")

# ---------------- CONFIG ----------------
FASI = [
    "Bruciapelo","Sbozzima","Lavaggio",
    "Candeggio Vaporizzo","Mercerizzo",
    "Sodatrice","Candeggio Stoccaggio","Ramosa","Leone"
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
id INTEGER PRIMARY KEY,
lotto TEXT,
articolo TEXT,
cliente TEXT,
metri REAL,
data TEXT,
fase INT,
priorita TEXT
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
CREATE TABLE IF NOT EXISTS turni(
nome TEXT PRIMARY KEY,
start TEXT,
end TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS pause(
nome TEXT PRIMARY KEY,
start TEXT,
end TEXT
)
""")

conn.commit()

# default macchine
for f in FASI:
    c.execute("INSERT OR IGNORE INTO macchine VALUES (?,?,?)",(f,20,10))

# default turni
c.execute("INSERT OR IGNORE INTO turni VALUES ('T1','06:00','14:00')")
c.execute("INSERT OR IGNORE INTO turni VALUES ('T2','14:00','22:00')")

# pausa
c.execute("INSERT OR IGNORE INTO pause VALUES ('Pranzo','12:00','13:00')")

conn.commit()

# ---------------- UTILS TEMPO ----------------
def in_pausa(dt):
    pause = pd.read_sql("SELECT * FROM pause", conn)
    for _,p in pause.iterrows():
        s = datetime.combine(dt.date(), datetime.strptime(p["start"],"%H:%M").time())
        e = datetime.combine(dt.date(), datetime.strptime(p["end"],"%H:%M").time())
        if s <= dt < e:
            return True, e
    return False, dt

def prossimo_turno(dt):
    turni = pd.read_sql("SELECT * FROM turni", conn)
    for _,t in turni.iterrows():
        s = datetime.combine(dt.date(), datetime.strptime(t["start"],"%H:%M").time())
        e = datetime.combine(dt.date(), datetime.strptime(t["end"],"%H:%M").time())
        if s <= dt < e:
            return dt
    # vai al giorno dopo primo turno
    t0 = turni.iloc[0]
    return datetime.combine(dt.date()+timedelta(days=1), datetime.strptime(t0["start"],"%H:%M").time())

def aggiungi_tempo(start, durata_min):
    corrente = start
    minuti = durata_min

    while minuti > 0:
        corrente = prossimo_turno(corrente)

        pausa, fine_pausa = in_pausa(corrente)
        if pausa:
            corrente = fine_pausa
            continue

        corrente += timedelta(minutes=1)
        minuti -= 1

    return corrente

# ---------------- LOAD ----------------
def load():
    df = pd.read_sql("SELECT * FROM lotti", conn)
    if df.empty:
        return df

    mac = pd.read_sql("SELECT * FROM macchine", conn)

    records=[]

    for _,r in df.iterrows():
        start = pd.to_datetime(r["data"])

        for i in range(r["fase"], len(FASI)):
            fase = FASI[i]

            m = mac[mac["nome"]==fase]
            vel = float(m["velocita"].values[0])
            setup = int(m["setup"].values[0])

            durata = (r["metri"]/vel) + setup

            end = aggiungi_tempo(start, durata)

            records.append({
                "id":r["id"],
                "lotto":r["lotto"],
                "cliente":r["cliente"],
                "fase":fase,
                "start":start,
                "end":end,
                "durata":round(durata,1),
                "priorita":r["priorita"]
            })

            start = end

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
            st.session_state.user=u
            st.rerun()
        else:
            st.error("Errore")

    st.stop()

df = load()

menu = st.sidebar.selectbox("Menu",[
    "Produzione","Gantt","Inserimento","Setup"
])

# ---------------- INSERIMENTO ----------------
if menu=="Inserimento":
    st.title("Nuovo Lotto")

    lotto=st.text_input("Lotto")
    art=st.text_input("Articolo")
    cliente=st.text_input("Cliente")
    metri=st.number_input("Metri", value=1000)
    data=st.date_input("Data", datetime.today())

    if st.button("Salva"):
        c.execute("INSERT INTO lotti VALUES(NULL,?,?,?,?,?,?,?)",
                  (lotto,art,cliente,metri,str(data),0,"Normale"))
        conn.commit()
        st.success("Inserito")
        st.rerun()

# ---------------- PRODUZIONE ----------------
elif menu=="Produzione":
    st.title("Produzione")

    for i,r in df.iterrows():
        col1,col2,col3,col4=st.columns(4)

        col1.write(f"**{r['lotto']}**")
        col2.write(r["fase"])
        col3.write(f"{r['start']} → {r['end']}")
        col4.write(f"{r['durata']} min")

        if st.button(f"Fatto {i}"):
            c.execute("UPDATE lotti SET fase=fase+1 WHERE id=?", (r["id"],))
            conn.commit()
            st.rerun()

# ---------------- GANTT ----------------
elif menu=="Gantt":
    st.title("Gantt")

    items=[]
    for _,r in df.iterrows():
        items.append({
            "content":r["lotto"],
            "start":str(r["start"]),
            "end":str(r["end"])
        })

    html(f"""
    <div id="timeline"></div>
    <script src="https://unpkg.com/vis-timeline/standalone/umd/vis-timeline-graph2d.min.js"></script>
    <link href="https://unpkg.com/vis-timeline/styles/vis-timeline-graph2d.min.css" rel="stylesheet" />

    <script>
    var container = document.getElementById('timeline');
    var items = new vis.DataSet({items});
    var timeline = new vis.Timeline(container, items, {{stack:true}});
    </script>
    """, height=500)

# ---------------- SETUP ----------------
elif menu=="Setup":
    st.title("Setup Macchine")

    mac = pd.read_sql("SELECT * FROM macchine", conn)

    for i,r in mac.iterrows():
        col1,col2,col3=st.columns(3)
        col1.write(r["nome"])
        vel=col2.number_input("m/min", value=float(r["velocita"]), key=f"v{i}")
        setup=col3.number_input("setup min", value=int(r["setup"]), key=f"s{i}")

        if st.button(f"Salva {r['nome']}"):
            c.execute("UPDATE macchine SET velocita=?,setup=? WHERE nome=?",
                      (vel,setup,r["nome"]))
            conn.commit()
            st.success("Salvato")
