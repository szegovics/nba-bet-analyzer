import requests

import pandas as pd

from nba_api.stats.endpoints import playergamelog, leaguegamefinder, teamdashboardbygeneralsplits, scoreboardv2

from nba_api.stats.static import players, teams

import time

import streamlit as st

from datetime import datetime, timedelta

import pytz



# --- OLDAL BEÁLLÍTÁSA ---

st.set_page_config(page_title="NBA Pro Analizátor v2", layout="wide")



# --- API KULCS KEZELÉSE ---

if "API_KEY" in st.secrets:

    API_KEY = st.secrets["API_KEY"]

else:

    st.error("Hiba: Az API_KEY nem található a Secrets beállítások között!")

    st.stop()



REGION = 'eu' 

MARKETS = 'player_points,player_rebounds,player_assists'



# --- SEGÉDFÜGGVÉNYEK ---



def get_next_matchday_from_odds():
    """Lekéri a következő meccsnap dátumát és az aznapi meccseket."""
    url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/events'
    try:
        res = requests.get(url, params={'apiKey': API_KEY}).json()
        
        if not res or not isinstance(res, list) or len(res) == 0:
            return None, []
        st.write(res)
        # 1. Kinyerjük az első meccs dátumát (YYYY-MM-DD formátumban)
        first_game_date_str = res[0]['commence_time'].split('T')[0]
        
        # 2. Összegyűjtjük az összes meccset, ami ezen a napon van
        daily_matches = [
            event for event in res 
            if event['commence_time'].startswith(first_game_date_str)
        ]
        
        # 3. Formázzuk a dátumot az NBA API számára (MM/DD/YYYY)
        dt_obj = datetime.strptime(first_game_date_str, '%Y-%m-%d')
        #formatted_date = dt_obj.strftime('%m/%d/%Y')
        
        return  daily_matches
    except Exception as e:
        st.error(f"Hiba az Odds API lekérésekor: {e}")
        return None, []


def get_live_odds():

    """Lekéri az aktuális fogadási kínálatot az Odds API-tól."""

    url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/events'

    try:

        events_res = requests.get(url, params={'apiKey': API_KEY}).json()
        
        if not isinstance(events_res, list): return []

        

        all_props = []

        for event in events_res[:5]: 

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

    """Játékos statisztikák az utolsó 10 meccsről."""

    p = players.find_players_by_full_name(player_name)

    if not p: return None

    try:

        log = playergamelog.PlayerGameLog(player_id=p[0]['id']).get_data_frames()[0].head(10)

        col = 'PTS' if 'points' in prop_type else 'REB' if 'rebounds' in prop_type else 'AST'

        return log[col].tolist()

    except:

        return None



def get_season_team_stats(team_id, is_home):

    """Szezonátlagok: Dobott/Kapott pontok a LEJÁTSZOTT meccsek alapján."""

    try:

        dash = teamdashboardbygeneralsplits.TeamDashboardByGeneralSplits(team_id=team_id, per_mode_detailed='PerGame')

        splits = dash.get_data_frames()[1] 

        row = splits[splits['GROUP_VALUE'] == ('Home' if is_home else 'Road')]

        

        if not row.empty:

            pts_scored = row['PTS'].values[0]

            pts_allowed = pts_scored - row['PLUS_MINUS'].values[0]

            return {

                "win_rate": f"{round(row['W_PCT'].values[0] * 100, 1)}%",

                "avg_pts": round(pts_scored, 1),

                "opp_pts": round(pts_allowed, 1),

                "gp": int(row['GP'].values[0])

            }

        return {"win_rate": "0%", "avg_pts": 0, "opp_pts": 0, "gp": 0}

    except:

        return {"win_rate": "N/A", "avg_pts": 0, "opp_pts": 0, "gp": 0}



# --- UI MEGJELENÍTÉS ---



st.title("🏀 NBA Pro Betting Dashboard")

st.sidebar.header("Vezérlőpult")

analysis_mode = st.sidebar.radio("Válassz módot:", ["🔥 Élő Prop Elemző", "📊 Következő Nap: Csapat & Totál"])


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
    
    matches = get_next_matchday_from_odds()
    
    if (matches == []):
        st.warning("Nincs elérhető meccs az Odds API-ban.")
    else:
        st.info(f"Dátum: következő játéknap| Talált meccsek száma: **{len(matches)}**")
        
        results = []
        for event in matches:
            home = event['home_team']
            away = event['away_team']
            
            with st.spinner(f"Elemzés: {away} @ {home}..."):
                all_nba_teams = teams.get_teams()
                h_id = next((t['id'] for t in all_nba_teams if t['full_name'] == home), None)
                a_id = next((t['id'] for t in all_nba_teams if t['full_name'] == away), None)
                
                if h_id and a_id:
                    # Itt jönnek a korábban megírt statisztikai lekérések
                    h_stats = get_season_team_stats(h_id, True)
                    time.sleep(1.5) # Fontos a szünet!
                    a_stats = get_season_team_stats(a_id, False)
                    time.sleep(1.5)
                    
                    results.append({
                        "Meccs": f"{away} @ {home}",
                        "Hazai Win%": h_stats['win_rate'],
                        "Hazai Átlag": h_stats['avg_pts'],
                        "Vendég Win%": a_stats['win_rate'],
                        "Vendég Átlag": a_stats['avg_pts'],
                        "Várható Pontszám": round(h_stats['avg_pts'] + a_stats['avg_pts'], 1)
                    })
        
        if results:
            st.table(pd.DataFrame(results))
