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
id INTEGER PRIMARY KEY,
lotto TEXT,
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

def save_ciclo(art, ciclo):
    c.execute("INSERT OR REPLACE INTO cicli VALUES (?,?)",(art,"|".join(ciclo)))
    conn.commit()

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
        if not ciclo:
            continue

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
                "articolo":r["articolo"],
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
        "Produzione","Gantt","Cicli","Inserimento","Setup"
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

# ---------------- GANTT ----------------
elif menu=="Gantt":
    st.title("Gantt interattivo")

    if df.empty:
        st.info("Nessun dato")
    else:
        items=[]
        for _,r in df.iterrows():
            items.append({
                "id":r["id"],
                "content":f"{r['lotto']} - {r['fase']}",
                "start":str(r["start"]),
                "end":str(r["end"])
            })

        st.markdown("👉 Trascina i blocchi per cambiare ordine temporale")

        html(f"""
        <div id="timeline"></div>
        <script src="https://unpkg.com/vis-timeline/standalone/umd/vis-timeline-graph2d.min.js"></script>
        <link href="https://unpkg.com/vis-timeline/styles/vis-timeline-graph2d.min.css" rel="stylesheet" />
        <script>
        var container = document.getElementById('timeline');
        var items = new vis.DataSet({items});
        var timeline = new vis.Timeline(container, items, {{
            editable:true,
            stack:true
        }});
        </script>
        """, height=500)

        st.warning("Premi sotto per applicare la nuova pianificazione")

        if st.button("📥 Applica modifiche"):
            nuovo = df.sort_values(by="start")

            for _,r in nuovo.iterrows():
                nuova_data = r["start"].date()
                c.execute("UPDATE lotti SET data=? WHERE id=?",
                          (str(nuova_data), r["id"]))

            conn.commit()
            st.success("Pianificazione aggiornata")
            st.rerun()

# ---------------- CICLI ----------------
elif menu=="Cicli":
    st.title("Editor cicli avanzato")

    articoli = pd.read_sql("SELECT articolo FROM cicli", conn)["articolo"].tolist()
    art = st.text_input("Articolo")

    if "ciclo_temp" not in st.session_state:
        st.session_state.ciclo_temp=[]
        st.session_state.art=None

    if art != st.session_state.art:
        st.session_state.art = art
        st.session_state.ciclo_temp = get_ciclo(art) if art in articoli else []

    st.subheader("Ciclo")
    st.dataframe(pd.DataFrame({
        "Ordine":range(1,len(st.session_state.ciclo_temp)+1),
        "Fase":st.session_state.ciclo_temp
    }))

    st.subheader("Riordina")
    if st.session_state.ciclo_temp:
        st.session_state.ciclo_temp = sort_items(st.session_state.ciclo_temp)

    st.subheader("Inserisci fase")
    nuova=st.selectbox("Fase", FASI)
    pos=st.number_input("Posizione",1,len(st.session_state.ciclo_temp)+1,
                        len(st.session_state.ciclo_temp)+1)

    if st.button("➕ Inserisci"):
        st.session_state.ciclo_temp.insert(int(pos)-1, nuova)
        st.rerun()

    st.subheader("Rimuovi fase")
    if st.session_state.ciclo_temp:
        idx=st.number_input("Indice",1,len(st.session_state.ciclo_temp),1)
        if st.button("❌ Rimuovi"):
            st.session_state.ciclo_temp.pop(int(idx)-1)
            st.rerun()

    st.subheader("Copia ciclo")
    copia=st.selectbox("Da articolo",[""]+articoli)
    if st.button("📥 Copia"):
        if copia:
            st.session_state.ciclo_temp=get_ciclo(copia)
            st.rerun()

    if st.button("💾 Salva"):
        save_ciclo(art, st.session_state.ciclo_temp)
        st.success("Salvato")

# ---------------- INSERIMENTO ----------------
elif menu=="Inserimento":
    st.title("Nuovo lotto")

    lotto=st.text_input("Lotto")
    art=st.text_input("Articolo")
    cliente=st.text_input("Cliente")
    metri=st.number_input("Metri",value=1000)
    data=st.date_input("Data")

    if st.button("Salva"):
        c.execute("INSERT INTO lotti VALUES(NULL,?,?,?,?,?,0)",
                  (lotto,art,cliente,metri,str(data)))
        conn.commit()
        st.success("Inserito")

# ---------------- SETUP ----------------
elif menu=="Setup":
    st.title("Orario lavoro")

    start=st.text_input("Inizio giornata","08:00")

    if st.button("Salva"):
        c.execute("UPDATE orari SET inizio=? WHERE id=1",(start,))
        conn.commit()
        st.success("Salvato")
