import requests
import pandas as pd
from nba_api.stats.endpoints import playergamelog, leaguegamefinder, teamdashboardbygeneralsplits
from nba_api.stats.static import players, teams
from nba_api.live.nba.endpoints import scoreboard
import time
import streamlit as st

# --- OLDAL BEÁLLÍTÁSA ---
st.set_page_config(page_title="NBA Pro Analizátor", layout="wide")

# --- API KULCS KEZELÉSE ---
if "API_KEY" in st.secrets:
    API_KEY = st.secrets["API_KEY"]
else:
    st.error("Hiba: Az API_KEY nem található a Secrets beállítások között!")
    st.stop()

REGION = 'eu' # Vegas.hu stílusú európai szorzók
MARKETS = 'player_points,player_rebounds,player_assists'

# --- FUNKCIÓK ---

def get_today_matchups():
    """Lekéri a mai meccseket a menetrendből."""
    try:
        sb = scoreboard.ScoreBoard()
        games = sb.get_dict()['scoreboard']['games']
        matchups = []
        for g in games:
            matchups.append({
                'id': g['gameId'],
                'home': g['homeTeam']['teamName'],
                'away': g['awayTeam']['teamName'],
                'home_id': g['homeTeam']['teamId'],
                'away_id': g['awayTeam']['teamId']
            })
        return matchups
    except:
        return []

def get_live_odds():
    """Lekéri az aktuális fogadási kínálatot az Odds API-tól."""
    url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/events'
    try:
        events_res = requests.get(url, params={'apiKey': API_KEY}).json()
        if not isinstance(events_res, list): return []
        
        all_props = []
        for event in events_res[:5]: # Első 5 meccs
            event_id = event['id']
            prop_url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event_id}/odds'
            res = requests.get(prop_url, params={
                'apiKey': API_KEY, 'regions': REGION, 'markets': MARKETS, 'oddsFormat': 'decimal'
            }).json()
            
            if 'bookmakers' in res:
                for bm in res['bookmakers']:
                    for market in bm['markets']:
                        for outcome in market['outcomes']:
                            if 'Over' in outcome['name']:
                                all_props.append({
                                    'player': outcome['description'],
                                    'type': market['key'].replace('player_', ''),
                                    'line': outcome['point'],
                                    'odds': outcome['price']
                                })
        return all_props
    except:
        return []

def get_last_10_player_stat(player_name, prop_type):
    """Játékos statisztikák lekérése."""
    p = players.find_players_by_full_name(player_name)
    if not p: return None
    try:
        log = playergamelog.PlayerGameLog(player_id=p[0]['id']).get_data_frames()[0].head(10)
        col = 'PTS' if 'points' in prop_type else 'REB' if 'rebounds' in prop_type else 'AST'
        return log[col].tolist()
    except:
        return None

def get_team_stats(team_id, is_home):
    """Csapat statisztikák: Szezonbeli Home/Away győzelmi arány és dobott/kapott pontok."""
    try:
        # A TeamDashboardByGeneralSplits a teljes szezon adatait adja alapból
        dash = teamdashboardbygeneralsplits.TeamDashboardByGeneralSplits(team_id=team_id)
        splits = dash.get_data_frames()[1] # Home/Away táblázat
        
        # Kiválasztjuk a megfelelő sort (Home vagy Road)
        row = splits[splits['GROUP_VALUE'] == ('Home' if is_home else 'Road')]
        
        if not row.empty:
            win_rate = row['W_PCT'].values[0] * 100
            pts_scored = row['PTS'].values[0] # Átlag dobott pont abban a felállásban
            # A kapott pontot a PLUS_MINUS-ból számoljuk ki (PTS - PLUS_MINUS)
            pts_allowed = pts_scored - row['PLUS_MINUS'].values[0]
            
            return {
                "win_rate": f"{round(win_rate, 1)}%",
                "avg_pts": round(pts_scored, 1),
                "opp_pts": round(pts_allowed, 1)
            }
        else:
            return {"win_rate": "0%", "avg_pts": 0, "opp_pts": 0}
    except Exception as e:
        return {"win_rate": "N/A", "avg_pts": 0, "opp_pts": 0}

# --- UI MEGJELENÍTÉS ---

st.title("🏀 NBA Pro Betting Dashboard")
st.sidebar.header("Vezérlőpult")
analysis_mode = st.sidebar.radio("Válassz módot:", ["🔥 Élő Prop Elemző", "📊 Csapat & Totál Elemzés"])

if analysis_mode == "🔥 Élő Prop Elemző":
    st.header("Élő Játékos Fogadások (Over)")
    if st.button("Oddsok és Statok lekérése"):
        props = get_live_odds()
        if not props:
            st.warning("Nincs élő kínálat az Odds API-ban (próbáld este).")
        else:
            results = []
            progress = st.progress(0)
            seen = set()
            for i, p in enumerate(props):
                if p['player'] in seen: continue
                stats = get_last_10_player_stat(p['player'], p['type'])
                if stats:
                    hits = sum(1 for s in stats if s > p['line'])
                    ev = (hits/10) * p['odds']
                    results.append({
                        "Játékos": p['player'], "Típus": p['type'], "Határ": p['line'],
                        "Siker": f"{hits*10}%", "Odds": p['odds'], "EV": round(ev, 2),
                        "Döntés": "🔥 VALUE" if ev > 1.1 else "❌"
                    })
                seen.add(p['player'])
                progress.progress((i+1)/len(props))
                time.sleep(0.6)
            st.table(pd.DataFrame(results))

else:
    st.header("Szezonális Elemzés: Dobott/Kapott Pontok & Győzelmi Arány")
    if st.button("Napi meccsek elemzése"):
        matchups = get_today_matchups()
        if not matchups:
            st.info("Nincs mai meccs a menetrendben.")
        else:
            team_results = []
            for m in matchups:
                with st.spinner(f"Adatok lekérése: {m['away']} @ {m['home']}..."):
                    # Hazai csapat szezonbeli OTTHONI adatai
                    h_stats = get_team_stats(m['home_id'], True)
                    # Vendég csapat szezonbeli IDEGENBELI adatai
                    a_stats = get_team_stats(m['away_id'], False)
                    
                    # Összesített várható pontszám (Hazai dobott + Vendég dobott átlaga)
                    projected_total = h_stats['avg_pts'] + a_stats['avg_pts']
                    
                    team_results.append({
                        "Meccs": f"{m['away']} @ {m['home']}",
                        "Hazai Win% (Otthon)": h_stats['win_rate'],
                        "Hazai Dobott": h_stats['avg_pts'],
                        "Hazai Kapott": h_stats['opp_pts'],
                        "Vendég Win% (Idegen)": a_stats['win_rate'],
                        "Vendég Dobott": a_stats['avg_pts'],
                        "Vendég Kapott": a_stats['opp_pts'],
                        "Várható Összesített": round(projected_total, 1)
                    })
                time.sleep(0.7) # API védelem
            
            st.table(pd.DataFrame(team_results))
            st.caption("Megjegyzés: A pontok és győzelmi arányok a teljes szezon Home/Road bontására vonatkoznak.")
