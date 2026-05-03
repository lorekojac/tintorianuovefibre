import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from streamlit.components.v1 import html
import matplotlib.pyplot as plt
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

# ---------------- FUNZIONI ----------------
def get_ciclo(art):
    r = c.execute("SELECT fasi FROM cicli WHERE articolo=?", (art,)).fetchone()
    if r and r[0]:
        return r[0].split("|")
    return []

def save_ciclo(art, ciclo_list):
    c.execute("INSERT OR REPLACE INTO cicli VALUES (?,?)",
              (art, "|".join(ciclo_list)))
    conn.commit()

def load():
    df = pd.read_sql("SELECT * FROM lotti", conn)
    if df.empty:
        return df

    mac = pd.read_sql("SELECT * FROM macchine", conn)
    records=[]

    for _,r in df.iterrows():
        start = pd.to_datetime(r["data"])
        ciclo = get_ciclo(r["articolo"])
        if not ciclo:
            continue

        for i in range(r["fase"], len(ciclo)):
            fase = ciclo[i]

            m = mac[mac["nome"]==fase]
            vel = float(m["velocita"].values[0])
            setup = int(m["setup"].values[0])

            durata = (r["metri"]/vel) + setup
            end = start + timedelta(minutes=durata)

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
        macchina = st.selectbox("Macchina", sorted(df["fase"].unique()))
        df_mac = df[df["fase"]==macchina].sort_values(by="start")

        for i,r in df_mac.iterrows():
            col1,col2,col3,col4=st.columns(4)
            col1.write(f"{r['lotto']} - {r['cliente']}")
            col2.write(r["fase"])
            col3.write(f"{r['start'].strftime('%d/%m %H:%M')} → {r['end'].strftime('%H:%M')}")
            col4.write(f"{r['durata']} min")

            if st.button(f"Fatto_{r['id']}_{i}"):
                c.execute("UPDATE lotti SET fase=fase+1 WHERE id=?", (r["id"],))
                conn.commit()
                st.rerun()

# ---------------- CALENDARIO ----------------
elif menu=="Calendario":
    st.title("Calendario produzione")

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

# ---------------- CICLI AVANZATO ----------------
elif menu=="Cicli":
    st.title("Editor cicli avanzato")

    articoli = pd.read_sql("SELECT articolo FROM cicli", conn)["articolo"].tolist()
    art = st.text_input("Articolo")

    # stato
    if "ciclo_temp" not in st.session_state:
        st.session_state.ciclo_temp=[]
        st.session_state.art_corr=None

    # cambio articolo
    if art != st.session_state.art_corr:
        st.session_state.art_corr = art
        if art in articoli:
            st.session_state.ciclo_temp = get_ciclo(art)
        else:
            st.session_state.ciclo_temp = []

    # -------- TABELLA --------
    st.subheader("Ciclo")
    if st.session_state.ciclo_temp:
        df_ciclo = pd.DataFrame({
            "Ordine": range(1,len(st.session_state.ciclo_temp)+1),
            "Fase": st.session_state.ciclo_temp
        })
        st.dataframe(df_ciclo, use_container_width=True)
    else:
        st.info("Ciclo vuoto")

    st.divider()

    # -------- DRAG --------
    st.subheader("Riordina (drag)")
    if st.session_state.ciclo_temp:
        st.session_state.ciclo_temp = sort_items(st.session_state.ciclo_temp)

    st.divider()

    # -------- AGGIUNTA POSIZIONE --------
    st.subheader("Inserisci fase")

    colA, colB = st.columns(2)
    nuova = colA.selectbox("Macchina", FASI)
    pos = colB.number_input("Posizione (1 = inizio)", min_value=1,
                           max_value=len(st.session_state.ciclo_temp)+1,
                           value=len(st.session_state.ciclo_temp)+1)

    if st.button("➕ Inserisci"):
        st.session_state.ciclo_temp.insert(int(pos)-1, nuova)
        st.rerun()

    # -------- MODIFICA --------
    st.subheader("Modifica fase")

    if st.session_state.ciclo_temp:
        idx = st.number_input("Indice fase", min_value=1,
                              max_value=len(st.session_state.ciclo_temp), value=1)
        nuova_val = st.selectbox("Nuova fase", FASI, key="editfase")

        if st.button("✏️ Modifica"):
            st.session_state.ciclo_temp[int(idx)-1] = nuova_val
            st.rerun()

    # -------- RIMOZIONE --------
    st.subheader("Rimuovi fase")
    if st.session_state.ciclo_temp:
        idx_del = st.number_input("Indice da eliminare",
                                 min_value=1,
                                 max_value=len(st.session_state.ciclo_temp), value=1,
                                 key="del")

        if st.button("❌ Elimina"):
            st.session_state.ciclo_temp.pop(int(idx_del)-1)
            st.rerun()

    st.divider()

    # -------- COPIA --------
    st.subheader("Copia ciclo")
    copia = st.selectbox("Da articolo", [""]+articoli)

    if st.button("📥 Copia"):
        if copia:
            st.session_state.ciclo_temp = get_ciclo(copia)
            st.rerun()

    st.divider()

    # -------- SALVA --------
    if st.button("💾 Salva ciclo"):
        if art:
            save_ciclo(art, st.session_state.ciclo_temp)
            st.success("Salvato")

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
            ax.set_ylabel("minuti")
            st.pyplot(fig)
