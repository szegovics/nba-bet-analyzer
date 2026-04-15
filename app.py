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
    """Lekéri a következő meccsnap dátumát az Odds API eseményeiből."""
    url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/events'
    try:
        res = requests.get(url, params={'apiKey': API_KEY}).json()
        if res and isinstance(res, list) and len(res) > 0:
            # Az első elérhető meccs kezdési ideje (pl: 2024-04-16T23:30:00Z)
            first_game_time = res[0]['commence_time']
            # Átalakítjuk az NBA API által kedvelt MM/DD/YYYY formátumra
            dt_obj = datetime.strptime(first_game_time.split('T')[0], '%Y-%m-%d')
            return dt_obj.strftime('%m/%d/%Y'), res
        return None, []
    except Exception as e:
        st.error(f"Hiba az események lekérésekor: {e}")
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

    if st.button("Következő meccsnap elemzése (Odds API alapú)"):
    # 1. Lekérjük a meccseket az Odds API-ról
    next_date, events = get_next_matchday_from_odds()
    
    if not next_date or not events:
        st.warning("Nem találtam meccseket az Odds API-ban.")
    else:
        st.info(f"Elemzés indítása a következő napra: {next_date}")
        team_results = []
        
        for event in events:
            # Csak a következő játéknap meccseit nézzük (kiszűrjük a távolabbiakat)
            target_iso = datetime.strptime(next_date, '%m/%d/%Y').strftime('%Y-%m-%d')
            if not event['commence_time'].startswith(target_iso):
                continue
                
            h_name = event['home_team']
            a_name = event['away_team']
            
            with st.spinner(f"Adatok lekérése: {a_name} @ {h_name}..."):
                # Csapat ID-k kikeresése a nevekből
                all_nba_teams = teams.get_teams()
                # Fontos: Az Odds API nevei (pl. 'Boston Celtics') egyeznek az NBA API full_name mezőjével
                h_id = next((t['id'] for t in all_nba_teams if t['full_name'] == h_name), None)
                a_id = next((t['id'] for t in all_nba_teams if t['full_name'] == a_name), None)
                
                if h_id and a_id:
                    # Itt hívjuk a statisztikai függvényt, amit korábban írtunk
                    h_stats = get_season_team_stats(h_id, True)
                    time.sleep(1.5) # Szünet az API blokkolás ellen
                    a_stats = get_season_team_stats(a_id, False)
                    time.sleep(1.5)
                    
                    projected_total = h_stats['avg_pts'] + a_stats['avg_pts']
                    
                    team_results.append({
                        "Meccs": f"{a_name} @ {h_name}",
                        "Hazai forma": h_stats['win_rate'],
                        "Hazai átlag": h_stats['avg_pts'],
                        "Vendég forma": a_stats['win_rate'],
                        "Vendég átlag": a_stats['avg_pts'],
                        "Várható Pontszám": round(projected_total, 1)
                    })
                else:
                    st.error(f"Nem találtam ID-t a csapathoz: {h_name} vagy {a_name}")

        if team_results:
            st.table(pd.DataFrame(team_results))
