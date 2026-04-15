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



if analysis_mode == "📊 Következő Nap: Csapat & Totál":
    st.header("Szezonális Elemzés az Odds API alapján")
    
    if st.button("Következő meccsnap keresése és elemzése"):
        next_date, events = get_next_matchday_from_odds()
        
        if not next_date:
            st.warning("Nem található aktív meccs az Odds API kínálatában.")
        else:
            st.success(f"Talált meccsnap: **{next_date}**")
            
            team_results = []
            # Végigmegyünk az Odds API-tól kapott eseményeken
            # Csak azokat nézzük, amik ugyanazon a napon vannak
            target_date_iso = datetime.strptime(next_date, '%m/%d/%Y').strftime('%Y-%m-%d')
            
            for event in events:
                if event['commence_time'].startswith(target_date_iso):
                    home_team_name = event['home_team']
                    away_team_name = event['away_team']
                    
                    with st.spinner(f"Elemzés: {away_team_name} @ {home_team_name}..."):
                        # Megkeressük az ID-kat a csapatnevek alapján
                        all_teams = teams.get_teams()
                        h_id = next((t['id'] for t in all_teams if t['full_name'] == home_team_name), None)
                        a_id = next((t['id'] for t in all_teams if t['full_name'] == away_team_name), None)
                        
                        if h_id and a_id:
                            # Statisztikák lekérése a már megírt stabil függvénnyel
                            h_stats = get_season_team_stats(h_id, True)
                            time.sleep(1.2) # API korlát védelem
                            a_stats = get_season_team_stats(a_id, False)
                            time.sleep(1.2)
                            
                            projected_total = h_stats['avg_pts'] + a_stats['avg_pts']
                            
                            team_results.append({
                                "Meccs": f"{away_team_name} @ {home_team_name}",
                                "Kezdés (UTC)": event['commence_time'].split('T')[1][:5],
                                "Hazai Win%": h_stats['win_rate'],
                                "Hazai Dobott": h_stats['avg_pts'],
                                "Vendég Win%": a_stats['win_rate'],
                                "Vendég Dobott": a_stats['avg_pts'],
                                "Várható Összesített": round(projected_total, 1)
                            })
            
            if team_results:
                df_res = pd.DataFrame(team_results)
                st.dataframe(df_res, use_container_width=True)
                
                # CSV letöltés
                csv = df_res.to_csv(index=False).encode('utf-8')
                st.download_button("Adatok mentése (CSV)", csv, f"nba_odds_analysis_{next_date}.csv", "text/csv")
            else:
                st.error("Nem sikerült párosítani a csapatokat az NBA adatbázissal.")



else:

    next_date = get_next_game_date()

    st.header(f"Szezonális Elemzés: {next_date}")

    if st.button(f"{next_date} meccseinek elemzése"):

        matchups = get_matchups(next_date)

        if not matchups:

            st.info(f"Nincs meccs a menetrendben erre a napra: {next_date}")

        else:

            team_results = []

            for m in matchups:

                with st.spinner(f"Adatok: {m['away_name']} @ {m['home_name']}..."):

                    h_stats = get_season_team_stats(m['home_id'], True)

                    a_stats = get_season_team_stats(m['away_id'], False)

                    

                    projected_total = h_stats['avg_pts'] + a_stats['avg_pts']

                    

                    team_results.append({

                        "Meccs": f"{m['away_name']} @ {m['home_name']}",

                        "Hazai Win% (Otthon)": h_stats['win_rate'],

                        "Hazai Dobott (Avg)": h_stats['avg_pts'],

                        "Hazai Kapott (Avg)": h_stats['opp_pts'],

                        "Meccsszám (H)": h_stats['gp'],

                        "Vendég Win% (Idegen)": a_stats['win_rate'],

                        "Vendég Dobott (Avg)": a_stats['avg_pts'],

                        "Vendég Kapott (Avg)": a_stats['opp_pts'],

                        "Meccsszám (V)": a_stats['gp'],

                        "Várható Összesített": round(projected_total, 1)

                    })

                time.sleep(0.7)

            

            df_res = pd.DataFrame(team_results)

            st.table(df_res)

            st.download_button("Adatok mentése (CSV)", df_res.to_csv(index=False), f"nba_{next_date}.csv")



st.markdown("---")

st.caption("A csapat statisztikák a teljes szezon lejátszott meccseinek átlagát mutatják Home/Road bontásban.")
