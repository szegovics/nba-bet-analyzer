import requests
import pandas as pd
from nba_api.stats.endpoints import playergamelog
from nba_api.stats.static import players
import time
import streamlit as st

# --- OLDAL BEÁLLÍTÁSA ---
st.set_page_config(page_title="NBA Prop Analizátor", layout="wide")

# --- API KULCS KEZELÉSE ---
if "API_KEY" in st.secrets:
    API_KEY = st.secrets["API_KEY"]
else:
    st.error("Hiba: Az API_KEY nem található a Secrets beállítások között!")
    st.stop()

REGION = 'eu'
MARKETS = 'player_points,player_rebounds,player_assists'

# --- FUNKCIÓK ---

def get_live_odds():
    """Lekéri az aktuális fogadási kínálatot."""
    url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/events'
    try:
        events_res = requests.get(url, params={'apiKey': API_KEY}).json()
        if not isinstance(events_res, list):
            st.error("Hiba az Odds API lekérésekor. Ellenőrizd a kulcsod!")
            return []
            
        all_props = []
        # Csak az első 3 meccset nézzük a sebesség miatt
        for event in events_res[:3]:
            event_id = event['id']
            prop_url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event_id}/odds'
            res = requests.get(prop_url, params={
                'apiKey': API_KEY,
                'regions': REGION,
                'markets': MARKETS,
                'oddsFormat': 'decimal'
            }).json()
            
            if 'bookmakers' in res:
                for bm in res['bookmakers']:
                    for market in bm['markets']:
                        for outcome in market['outcomes']:
                            if 'Over' in outcome['name']:
                                all_props.append({
                                    'Játékos': outcome['description'],
                                    'Típus': market['key'].replace('player_', ''),
                                    'Határ': outcome['point'],
                                    'Odds': outcome['price']
                                })
        st.write(all_props)
        return all_props
    except Exception as e:
        st.error(f"Hiba történt: {e}")
        return []

def get_last_10_stat(player_name, prop_type):
    """Lekéri a statisztikát az NBA-től."""
    full_player = players.find_players_by_full_name(player_name)
    if not full_player: return None
    
    p_id = full_player[0]['id']
    try:
        log = playergamelog.PlayerGameLog(player_id=p_id).get_data_frames()[0].head(10)
        col = 'PTS' if 'points' in prop_type else 'REB' if 'rebounds' in prop_type else 'AST'
        return log[col].tolist()
    except:
        return None

# --- UI / MEGJELENÍTÉS ---

st.title("🏀 NBA Élő Prop Analizátor")
st.write("Az app lekéri a legfrissebb szorzókat és összeveti a játékosok utolsó 10 meccsével.")

if st.button("Elemzés indítása"):
    props = get_live_odds()
    
    if not props:
        st.warning("Jelenleg nincs elérhető fogadási kínálat.")
    else:
        st.info(f"Találtam {len(props)} lehetőséget. Statisztikák lekérése folyamatban...")
        
        results = []
        progress_bar = st.progress(0)
        seen_players = set()
        
        for i, p in enumerate(props):
            if p['Játékos'] in seen_players: continue
            
            stats = get_last_10_stat(p['Játékos'], p['Típus'])
            if stats:
                hits = sum(1 for s in stats if s > p['Határ'])
                prob = (hits / 10)
                ev = prob * p['Odds']
                
                results.append({
                    "Játékos": p['Játékos'],
                    "Típus": p['Típus'],
                    "Határ": p['Határ'],
                    "Utolsó 10": str(stats),
                    "Esély": f"{hits*10}%",
                    "Odds": p['Odds'],
                    "Érték (EV)": round(ev, 2),
                    "Döntés": "🔥 MEGÉRI" if ev > 1.1 else "❌ NEM"
                })
                seen_players.add(p['Játékos'])
                time.sleep(0.6) # NBA API limit miatt
            
            progress_bar.progress((i + 1) / len(props))
        
        if results:
            df = pd.DataFrame(results)
            # Táblázat színezése és megjelenítése
            st.table(df)
        else:
            st.error("Nem sikerült statisztikákat rendelni a játékosokhoz.")
