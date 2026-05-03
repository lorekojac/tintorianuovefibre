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
    "Sodatrice","Candeggio Stoccaggio",
    "Ramosa","Leone","spazzola","smeriglio"
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
                "cliente":r["cliente"],
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
        "Produzione","Gantt","Excel","Inserimento","Cicli","Setup"
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

        st.warning("Dopo aver spostato i blocchi premi sotto")

        if st.button("📥 Applica modifiche"):
            nuovo = df.sort_values(by="start")
            for _,r in nuovo.iterrows():
                c.execute("UPDATE lotti SET data=? WHERE id=?",
                          (str(r["start"].date()), r["id"]))
            conn.commit()
            st.success("Produzione aggiornata")
            st.rerun()

# ---------------- EXCEL ----------------
elif menu=="Excel":
    st.title("Export Excel per macchina")

    if df.empty:
        st.info("Nessun dato")
    else:
        macchina = st.selectbox("Macchina", sorted(df["fase"].unique()))
        dfm = df[df["fase"]==macchina].sort_values(by="start")

        st.dataframe(dfm)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            dfm.to_excel(writer, index=False, sheet_name=macchina)

        st.download_button(
            label="📥 Scarica Excel",
            data=output.getvalue(),
            file_name=f"{macchina}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

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

        if not lotto: errori.append("Lotto obbligatorio")
        if not articolo: errori.append("Articolo obbligatorio")
        if metri <= 0: errori.append("Metri > 0")
        if lotto_esiste(lotto): errori.append("Lotto già esistente")
        if not get_ciclo(articolo): errori.append("Articolo senza ciclo")

        if errori:
            for e in errori: st.error(e)
        else:
            c.execute("""
                INSERT INTO lotti (lotto, articolo, cliente, metri, data, fase)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (lotto, articolo, cliente, metri, str(data), 0))
            conn.commit()
            st.success("Inserito")
            st.rerun()

# ---------------- CICLI ----------------
elif menu=="Cicli":
elif menu=="Cicli":
    st.title("Editor cicli PRO")

    articoli = pd.read_sql("SELECT articolo FROM cicli", conn)["articolo"].tolist()
    art = st.text_input("Articolo")

    # stato persistente
    if "ciclo_temp" not in st.session_state:
        st.session_state.ciclo_temp = []
        st.session_state.art_corrente = None

    if art != st.session_state.art_corrente:
        st.session_state.art_corrente = art

        if art in articoli:
            st.session_state.ciclo_temp = get_ciclo(art)
        else:
            st.session_state.ciclo_temp = []

    # ---------------- TABELLA ----------------
    st.subheader("Ciclo lavorazione")

    if st.session_state.ciclo_temp:
        df_ciclo = pd.DataFrame({
            "Step": range(1, len(st.session_state.ciclo_temp)+1),
            "Macchina": st.session_state.ciclo_temp
        })
        st.dataframe(df_ciclo, use_container_width=True)
    else:
        st.info("Ciclo vuoto")

    st.divider()

    # ---------------- DRAG ----------------
    st.subheader("Riordina (drag & drop)")
    if st.session_state.ciclo_temp:
        st.session_state.ciclo_temp = sort_items(st.session_state.ciclo_temp)

    st.divider()

    # ---------------- INSERIMENTO POSIZIONE ----------------
    st.subheader("Inserisci fase in posizione")

    col1, col2 = st.columns(2)

    nuova = col1.selectbox("Macchina", FASI)
    pos = col2.number_input(
        "Posizione",
        min_value=1,
        max_value=len(st.session_state.ciclo_temp)+1,
        value=len(st.session_state.ciclo_temp)+1
    )

    if st.button("➕ Inserisci fase"):
        st.session_state.ciclo_temp.insert(int(pos)-1, nuova)
        st.rerun()

    # ---------------- MODIFICA ----------------
    st.subheader("Modifica fase")

    if st.session_state.ciclo_temp:
        idx = st.number_input(
            "Seleziona step",
            min_value=1,
            max_value=len(st.session_state.ciclo_temp),
            value=1
        )

        nuova_val = st.selectbox("Nuova macchina", FASI, key="edit")

        if st.button("✏️ Modifica"):
            st.session_state.ciclo_temp[int(idx)-1] = nuova_val
            st.rerun()

    # ---------------- RIMOZIONE ----------------
    st.subheader("Rimuovi fase")

    if st.session_state.ciclo_temp:
        idx_del = st.number_input(
            "Step da eliminare",
            min_value=1,
            max_value=len(st.session_state.ciclo_temp),
            value=1,
            key="delete"
        )

        if st.button("❌ Elimina"):
            st.session_state.ciclo_temp.pop(int(idx_del)-1)
            st.rerun()

    st.divider()

    # ---------------- COPIA ----------------
    st.subheader("Copia ciclo")

    copia = st.selectbox("Da articolo", [""] + articoli)

    if st.button("📥 Copia ciclo"):
        if copia:
            st.session_state.ciclo_temp = get_ciclo(copia)
            st.success(f"Copiato da {copia}")
            st.rerun()

    # ---------------- DUPLICA ----------------
    st.subheader("Duplica fase")

    if st.session_state.ciclo_temp:
        idx_dup = st.number_input(
            "Step da duplicare",
            min_value=1,
            max_value=len(st.session_state.ciclo_temp),
            value=1,
            key="dup"
        )

        if st.button("📑 Duplica"):
            fase = st.session_state.ciclo_temp[int(idx_dup)-1]
            st.session_state.ciclo_temp.insert(int(idx_dup), fase)
            st.rerun()

    st.divider()

    # ---------------- RESET ----------------
    if st.button("🧹 Reset ciclo"):
        st.session_state.ciclo_temp = []
        st.rerun()

    # ---------------- SALVA ----------------
    if st.button("💾 Salva ciclo"):
        if art:
            c.execute(
                "INSERT OR REPLACE INTO cicli VALUES (?,?)",
                (art, "|".join(st.session_state.ciclo_temp))
            )
            conn.commit()
            st.success("Ciclo salvato correttamente")

# ---------------- SETUP ----------------
elif menu=="Setup":
    st.title("Orario lavoro")

    start = st.text_input("Inizio giornata", "08:00")

    if st.button("Salva"):
        c.execute("UPDATE orari SET inizio=? WHERE id=1",(start,))
        conn.commit()
        st.success("Salvato")
