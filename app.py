import streamlit as st
import pandas as pd

# Ez a rész felel a webes megjelenésért
st.set_page_config(page_title="NBA Stat & Odds Analizátor", layout="wide")

st.title("🏀 NBA Játékos Statisztika vs Vegas Odds")
st.write("Ez az app összehasonlítja az utolsó 10 meccset az aktuális szorzókkal.")

# BEMENETI ADATOK A WEBOLDALON
col1, col2, col3 = st.columns(3)
with col1:
    player = st.text_input("Játékos neve", "Luka Doncic")
with col2:
    line = st.number_input("Vegas Határ (pl. 28.5)", value=25.5)
with col3:
    odds = st.number_input("Szorzó (Odds)", value=1.85)

if st.button("Elemzés indítása"):
    # Itt hívnánk meg az API-t, most szimuláljuk az adatokat a példa kedvéért
    last_10_games = [30, 22, 35, 28, 19, 40, 25, 31, 27, 33] 
    
    hits = sum(1 for x in last_10_games if x > line)
    prob = (hits / 10) * 100
    ev = (prob/100) * odds

    # Megjelenítés kártyákon
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Valószínűség (Last 10)", f"{prob}%")
    c2.metric("Várható Érték (EV)", round(ev, 2))
    c3.metric("Státusz", "🔥 AJÁNLOTT" if ev > 1.05 else "❌ KERÜLD")

    # Grafikon az utolsó 10 meccsről
    st.subheader(f"{player} utolsó 10 meccse")
    st.bar_chart(last_10_games)
    st.info(f"A játékos {hits} alkalommal teljesítette a határt ({line}) az utolsó 10 meccsen.")