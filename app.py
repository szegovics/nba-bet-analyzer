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
    """Csapat statisztikák: Home/Away győzelmi arány és átlagok."""
    try:
        # Home/Away Split
        dash = teamdashboardbygeneralsplits.TeamDashboardByGeneralSplits(team_id=team_id)
        splits = dash.get_data_frames()[1]
        row = splits[splits['GROUP_VALUE'] == ('Home' if is_home else 'Road')]
        win_rate = row['W_PCT'].values[0] * 100 if not row.empty else 0
        
        # Átlag pontok az utolsó 10 meccsen
        finder = leaguegamefinder.LeagueGameFinder(team_id_nullable=team_id)
        recent = finder.get_data_frames()[0].head(10)
        
        return {
            "win_rate": f"{round(win_rate, 1)}%",
            "avg_pts": round(recent['PTS'].mean(), 1),
            "avg_diff": round(recent['PLUS_MINUS'].mean(), 1)
        }
    except:
        return {"win_rate": "N/A", "avg_pts": 0, "avg_diff": 0}

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
    st.header("Mai Meccsek: Home/Away & Pontszámok")
    if st.button("Napi meccsek elemzése"):
        matchups = get_today_matchups()
        if not matchups:
            st.info("Nincs mai meccs a menetrendben.")
        else:
            team_results = []
            for m in matchups:
                with st.spinner(f"Elemzés: {m['away']} @ {m['home']}..."):
                    h_stats = get_team_stats(m['home_id'], True)
                    a_stats = get_team_stats(m['away_id'], False)
                    
                    team_results.append({
                        "Meccs": f"{m['away']} @ {m['home']}",
                        "Hazai Win% (Home)": h_stats['win_rate'],
                        "Vendég Win% (Away)": a_stats['win_rate'],
                        "Hazai Átlag PTS": h_stats['avg_pts'],
                        "Vendég Átlag PTS": a_stats['avg_pts'],
                        "Várható Összesített": round(h_stats['avg_pts'] + a_stats['avg_pts'], 1),
                        "Hazai Hendikep (Diff)": h_stats['avg_diff']
                    })
                time.sleep(0.7)
            st.table(pd.DataFrame(team_results))
            st.download_button("Adatok letöltése (CSV)", pd.DataFrame(team_results).to_csv(), "nba_day.csv")

st.markdown("---")
st.caption("Adatok forrása: NBA.com API & The Odds API. Az esélyek az utolsó 10 meccsre vonatkoznak.")
