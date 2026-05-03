import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from streamlit.components.v1 import html
from streamlit_sortables import sort_items
import io

st.set_page_config(layout="wide", page_title="Tintoria nuovefibre")

# ---------------- CONFIG ----------------
FASI = [
    "Bruciapelo","Sbozzima","Lavaggio",
    "Candeggio Vaporizzo","Mercerizzo",
    "Sodatrice","Candeggio Stoccaggio","Ramosa",
    "Leone","Smeriglio","Spazzola"
]

UTENTI = {
    "op1": {"password":"op1","ruolo":"operatore"},
    "admin1": {"password":"admin1","ruolo":"admin"}
}

# ---------------- DB ----------------
conn = sqlite3.connect("tintoria.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS lotti(
id INTEGER PRIMARY KEY AUTOINCREMENT,
lotto TEXT UNIQUE,
articolo TEXT,
cliente TEXT,
metri REAL,
data TEXT,
fase INT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS macchine(
nome TEXT PRIMARY KEY,
velocita REAL,
setup INT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS cicli(
articolo TEXT PRIMARY KEY,
fasi TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS orari(
id INTEGER PRIMARY KEY,
inizio TEXT
)""")

conn.commit()

# default init
for f in FASI:
    c.execute("INSERT OR IGNORE INTO macchine VALUES (?,?,?)",(f,20,10))
c.execute("INSERT OR IGNORE INTO orari VALUES (1,'08:00')")
conn.commit()

# ---------------- FUNZIONI ----------------
def get_orario():
    return pd.read_sql("SELECT * FROM orari", conn).iloc[0]["inizio"]

def get_ciclo(art):
    r = c.execute("SELECT fasi FROM cicli WHERE articolo=?", (art,)).fetchone()
    return r[0].split("|") if r and r[0] else []

def lotto_esiste(lotto):
    return c.execute("SELECT id FROM lotti WHERE lotto=?", (lotto,)).fetchone() is not None

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

            vel = mac.loc[mac["nome"]==fase, "velocita"].values[0]
            setup = mac.loc[mac["nome"]==fase, "setup"].values[0]

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
    st.session_state.login = False

if not st.session_state.login:
    st.title("Login")

    user = st.text_input("Utente")
    pwd = st.text_input("Password", type="password")

    if st.button("Login"):
        if user in UTENTI and UTENTI[user]["password"] == pwd:
            st.session_state.login = True
            st.session_state.ruolo = UTENTI[user]["ruolo"]
            st.rerun()
        else:
            st.error("Credenziali errate")

    st.stop()

df = load()

# ---------------- MENU ----------------
if st.session_state.ruolo == "operatore":
    menu = "Produzione"
else:
    menu = st.sidebar.selectbox("Menu",
        ["Produzione","Gantt","Excel","Inserimento","Cicli","Setup"]
    )

# ---------------- PRODUZIONE ----------------
if menu == "Produzione":
    st.title("Produzione")

    if df.empty:
        st.info("Nessun lavoro")
    else:
        macchina = st.selectbox("Macchina", sorted(df["fase"].unique()))
        dfm = df[df["fase"]==macchina].sort_values(by="start")

        for _,r in dfm.iterrows():
            col1,col2,col3 = st.columns(3)
            col1.write(r["lotto"])
            col2.write(r["start"].strftime("%d/%m %H:%M"))
            col3.write(f"{r['durata']} min")

            if st.button(f"Fatto_{r['id']}"):
                c.execute("UPDATE lotti SET fase=fase+1 WHERE id=?", (r["id"],))
                conn.commit()
                st.rerun()

# ---------------- GANTT ----------------
elif menu == "Gantt":
    st.title("Gantt")

    items = []
    for _,r in df.iterrows():
        items.append({
            "id":r["id"],
            "content":f"{r['lotto']} - {r['fase']}",
            "start":str(r["start"]),
            "end":str(r["end"])
        })

    html(f"""
    <div id="timeline"></div>
    <script src="https://unpkg.com/vis-timeline/standalone/umd/vis-timeline-graph2d.min.js"></script>
    <link href="https://unpkg.com/vis-timeline/styles/vis-timeline-graph2d.min.css" rel="stylesheet"/>
    <script>
    var container = document.getElementById('timeline');
    var items = new vis.DataSet({items});
    new vis.Timeline(container, items, {{editable:true, stack:true}});
    </script>
    """, height=500)

    if st.button("Applica modifiche"):
        df_sorted = df.sort_values(by="start")
        for _,r in df_sorted.iterrows():
            c.execute("UPDATE lotti SET data=? WHERE id=?",
                      (str(r["start"].date()), r["id"]))
        conn.commit()
        st.success("Aggiornato")
        st.rerun()

# ---------------- EXCEL ----------------
elif menu == "Excel":
    st.title("Export Excel")

    macchina = st.selectbox("Macchina", sorted(df["fase"].unique()))

    dfm = df[df["fase"]==macchina].sort_values(by="start")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        dfm.to_excel(writer, index=False)

    st.download_button("Scarica Excel", output.getvalue(),
                       file_name=f"{macchina}.xlsx")

# ---------------- INSERIMENTO ----------------
elif menu == "Inserimento":
    st.title("Nuovo lotto")

    lotto = st.text_input("Lotto")
    articolo = st.text_input("Articolo")
    cliente = st.text_input("Cliente")
    metri = st.number_input("Metri", min_value=1.0)
    data = st.date_input("Data")

    if st.button("Salva"):
        errori = []

        if not lotto: errori.append("Lotto obbligatorio")
        if not articolo: errori.append("Articolo obbligatorio")
        if metri <= 0: errori.append("Metri > 0")
        if lotto_esiste(lotto): errori.append("Lotto duplicato")
        if not get_ciclo(articolo): errori.append("Articolo senza ciclo")

        if errori:
            for e in errori:
                st.error(e)
        else:
            c.execute("""
            INSERT INTO lotti (lotto, articolo, cliente, metri, data, fase)
            VALUES (?, ?, ?, ?, ?, ?)
            """,(lotto,articolo,cliente,metri,str(data),0))
            conn.commit()
            st.success("Inserito")
            st.rerun()

# ---------------- CICLI ----------------
elif menu == "Cicli":
    st.title("Cicli PRO")

    art = st.text_input("Articolo")

    if "ciclo" not in st.session_state:
        st.session_state.ciclo = []

    if art:
        st.session_state.ciclo = get_ciclo(art)

    st.dataframe(pd.DataFrame({
        "Step":range(1,len(st.session_state.ciclo)+1),
        "Fase":st.session_state.ciclo
    }))

    if st.session_state.ciclo:
        st.session_state.ciclo = sort_items(st.session_state.ciclo)

    nuova = st.selectbox("Fase", FASI)
    if st.button("Aggiungi fase"):
        st.session_state.ciclo.append(nuova)
        st.rerun()

    if st.button("Salva ciclo"):
        c.execute("INSERT OR REPLACE INTO cicli VALUES (?,?)",
                  (art,"|".join(st.session_state.ciclo)))
        conn.commit()
        st.success("Salvato")

# ---------------- SETUP ----------------
elif menu == "Setup":
    st.title("Orario lavoro")

    start = st.text_input("Inizio giornata","08:00")

    if st.button("Salva"):
        c.execute("UPDATE orari SET inizio=? WHERE id=1",(start,))
        conn.commit()
        st.success("Salvato")
