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



def get_next_game_date():

    """Kiszámolja a következő meccsnap dátumát (magyar idő szerint holnap)."""

    tz = pytz.timezone('Europe/Budapest')

    now = datetime.now(tz)

    # Ha hajnal van, még a mai meccsek érdekesek, ha nappal, akkor a holnapiak

    next_day = now + timedelta(days=1)

    return next_day.strftime('%Y-%m-%d')



def get_matchups(date_str):

    """Lekéri a meccseket egy adott napra."""

    try:

        sb = scoreboardv2.ScoreboardV2(game_date=date_str)

        df = sb.get_data_frames()[0]

        matchups = []

        for i in range(0, len(df), 2):

            away_row = df.iloc[i]

            home_row = df.iloc[i+1]

            matchups.append({

                'home_name': home_row['TEAM_NAME'],

                'home_id': home_row['TEAM_ID'],

                'away_name': away_row['TEAM_NAME'],

                'away_id': away_row['TEAM_ID']

            })

        return matchups

    except:

        return []



def get_live_odds():

    """Lekéri az aktuális fogadási kínálatot az Odds API-tól."""

    url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/events'

    try:

        events_res = requests.get(url, params={'apiKey': API_KEY}).json()
        st.write(events_res)
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
