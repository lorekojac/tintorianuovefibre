import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, time
from streamlit.components.v1 import html
import matplotlib.pyplot as plt

st.set_page_config(layout="wide", page_title="Tintoria nuovefibre")

# ---------------- CONFIG ----------------
FASI = [
    "Bruciapelo","Sbozzima","Lavaggio",
    "Candeggio Vaporizzo","Mercerizzo",
    "Sodatrice","Candeggio Stoccaggio","Ramosa"
    "Smeriglio","Artex","spazzola"
]

UTENTI = {
    "Op1": {"password":"op1","ruolo":"operatore"},
    "Admin1": {"password":"admin1","ruolo":"admin"}
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
CREATE TABLE IF NOT EXISTS cicli(
articolo TEXT PRIMARY KEY,
fasi TEXT
)
""")

conn.commit()

# default macchine
for f in FASI:
    c.execute("INSERT OR IGNORE INTO macchine VALUES (?,?,?)",(f,20,10))

conn.commit()

# ---------------- TEMPO ----------------
def aggiungi_tempo(start, durata_min):
    return start + timedelta(minutes=durata_min)

# ---------------- CICLI ----------------
def get_ciclo(art):
    r = c.execute("SELECT fasi FROM cicli WHERE articolo=?", (art,)).fetchone()
    if r and r[0]:
        return r[0].split("|")
    return FASI

# ---------------- LOAD ----------------
def load():
    df = pd.read_sql("SELECT * FROM lotti", conn)
    if df.empty:
        return df

    mac = pd.read_sql("SELECT * FROM macchine", conn)

    records=[]

    for _,r in df.iterrows():
        start = pd.to_datetime(r["data"])
        ciclo = get_ciclo(r["articolo"])

        for i in range(r["fase"], len(ciclo)):
            fase = ciclo[i]

            m = mac[mac["nome"]==fase]
            vel = float(m["velocita"].values[0])
            setup = int(m["setup"].values[0])

            durata = (r["metri"]/vel) + setup
            end = aggiungi_tempo(start, durata)

            records.append({
                "id":r["id"],
                "lotto":r["lotto"],
                "articolo":r["articolo"],
                "cliente":r["cliente"],
                "fase":fase,
                "start":start,
                "end":end,
                "durata":round(durata,1)
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
            st.session_state.ruolo=UTENTI[u]["ruolo"]
            st.rerun()
        else:
            st.error("Errore")

    st.stop()

df = load()

# ---------------- MENU ----------------
if st.session_state.ruolo=="operatore":
    menu = "Produzione"
else:
    menu = st.sidebar.selectbox("Menu",[
        "Produzione","Calendario","Cicli","Inserimento","Setup","Dashboard"
    ])

# ---------------- PRODUZIONE ----------------
if menu=="Produzione":
    st.title("Produzione")

    if df.empty:
        st.info("Nessun lavoro")
    else:
        # selezione macchina
        macchina = st.selectbox("Seleziona macchina", sorted(df["fase"].unique()))

        # filtro per macchina
        df_macchina = df[df["fase"] == macchina].sort_values(by="start")

        st.subheader(f"Lavori per: {macchina}")

        for i, r in df_macchina.iterrows():
            col1, col2, col3, col4 = st.columns([2,2,2,1])

            col1.write(f"**{r['lotto']}**")
            col2.write(r["cliente"])
            col3.write(f"{r['start'].strftime('%d/%m %H:%M')} → {r['end'].strftime('%H:%M')}")
            col4.write(f"{r['durata']} min")

            if st.button(f"Fatto_{r['id']}_{i}"):
                c.execute("UPDATE lotti SET fase=fase+1 WHERE id=?", (r["id"],))
                conn.commit()
                st.rerun()

# ---------------- CALENDARIO ----------------
elif menu=="Calendario":
    st.title("Calendario produzione")

    if not df.empty:
        items=[]
        for _,r in df.iterrows():
            items.append({
                "content":f"{r['lotto']} - {r['fase']}",
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

# ---------------- CICLI ----------------
elif menu=="Cicli":
    st.title("Cicli articoli")

    art = st.text_input("Articolo")

    # recupera ciclo attuale
    ciclo_attuale = get_ciclo(art) if art else []

    st.subheader("Ciclo attuale")

    if "ciclo_temp" not in st.session_state:
        st.session_state.ciclo_temp = ciclo_attuale.copy()

    # reset quando cambia articolo
    if art and ciclo_attuale != st.session_state.ciclo_temp:
        st.session_state.ciclo_temp = ciclo_attuale.copy()

    # mostra ciclo corrente
    for i, fase in enumerate(st.session_state.ciclo_temp):
        col1, col2 = st.columns([4,1])
        col1.write(f"{i+1}. {fase}")
        if col2.button(f"❌_{i}"):
            st.session_state.ciclo_temp.pop(i)
            st.rerun()

    st.divider()

    st.subheader("Aggiungi fase")

    nuova_fase = st.selectbox("Macchina", FASI)

    if st.button("➕ Aggiungi"):
        st.session_state.ciclo_temp.append(nuova_fase)
        st.rerun()

    st.divider()

    if st.button("💾 Salva ciclo"):
        if art and st.session_state.ciclo_temp:
            c.execute(
                "INSERT OR REPLACE INTO cicli VALUES (?,?)",
                (art, "|".join(st.session_state.ciclo_temp))
            )
            conn.commit()
            st.success("Ciclo salvato")
# ---------------- INSERIMENTO ----------------
elif menu=="Inserimento":
    st.title("Nuovo lotto")

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

# ---------------- SETUP ----------------
elif menu=="Setup":
    st.title("Setup macchine")

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

# ---------------- DASHBOARD ----------------
elif menu=="Dashboard":
    st.title("Carico macchine")

    if not df.empty:
        df["giorno"] = df["start"].dt.date

        grouped = df.groupby(["giorno","fase"]).agg({"durata":"sum"}).reset_index()

        for macchina in grouped["fase"].unique():
            sub = grouped[grouped["fase"]==macchina]

            st.subheader(macchina)

            fig, ax = plt.subplots()
            ax.bar(sub["giorno"], sub["durata"])
            ax.set_ylabel("minuti lavorazione")

            st.pyplot(fig)
