import requests
import pandas as pd
from nba_api.stats.endpoints import playergamelog
from nba_api.stats.static import players
import time
import streamlit as st

from nba_api.stats.endpoints import teamdashboardbyteamperformance, leaguegamefinder
from nba_api.stats.static import teams

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

def get_team_advanced_stats(team_name, is_home):
    """
    Lekéri a csapat specifikus statisztikáit: 
    Győzelmi arány (otthon/idegenben) és átlagos pontok.
    """
    nba_team = teams.find_teams_by_full_name(team_name)[0]
    team_id = nba_team['id']
    
    # Utolsó 10 meccs lekérése a csapattól
    game_finder = leaguegamefinder.LeagueGameFinder(team_id_nullable=team_id)
    games = game_finder.get_data_frames()[0]
    
    # Csak az aktuális szezon és az utolsó 10 meccs
    recent_games = games.head(10).copy()
    
    # Számítások
    avg_score = recent_games['PTS'].mean()
    avg_opp_score = (recent_games['PTS'] - recent_games['PLUS_MINUS']).mean()
    total_avg_points = avg_score + avg_opp_score
    
    # Home/Away győzelmi arány
    # A MATCHUP oszlopban 'vs.' = Otthon, '@' = Idegenben
    if is_home:
        split_games = games[games['MATCHUP'].str.contains('vs.')].head(10)
    else:
        split_games = games[games['MATCHUP'].str.contains('@')].head(10)
        
    win_rate = (split_games['WL'] == 'W').mean() * 100
    
    return {
        "win_rate_split": f"{round(win_rate, 1)}%",
        "avg_team_score": round(avg_score, 1),
        "total_avg_pts": round(total_avg_points, 1),
        "avg_diff": round(recent_games['PLUS_MINUS'].mean(), 1)
    }

# --- UI Bővítés a Streamlit részhez ---
st.divider()
st.header("🏠 vs ✈️ Csapat Analitika (Home/Away Split)")

if st.button("Csapat statisztikák betöltése"):
    matchups = get_today_matchups() # A korábbi függvényed
    team_results = []
    
    for m in matchups:
        # Hazai csapat elemzése (Home)
        home_stats = get_team_advanced_stats(m['home'], is_home=True)
        # Vendég csapat elemzése (Away)
        away_stats = get_team_advanced_stats(m['away'], is_home=False)
        
        team_results.append({
            "Meccs": f"{m['away']} @ {m['home']}",
            "Hazai Győzelem (Otthon)": home_stats['win_rate_split'],
            "Vendég Győzelem (Idegenben)": away_stats['win_rate_split'],
            "Várható Összes Pont": round((home_stats['total_avg_pts'] + away_stats['total_avg_pts'])/2, 1),
            "Hazai Átlag Differencia": home_stats['avg_diff']
        })
        time.sleep(0.6)

    st.table(pd.DataFrame(team_results))

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
