import streamlit as st
import pandas as pd
import requests
import time
from nba_api.stats.endpoints import playergamelog, leaguegamefinder, teamdashboardbygeneralsplits
from nba_api.stats.static import players, teams
from nba_api.live.nba.endpoints import scoreboard

# --- OLDAL BEÁLLÍTÁSA ---
st.set_page_config(page_title="NBA Pro Analizátor", layout="wide")

# --- API KULCS KEZELÉSE ---
API_KEY = st.secrets.get("API_KEY", "")

# --- SEGÉDFÜGGVÉNYEK ---

def get_today_matchups():
    """Lekéri a mai meccseket a menetrendből."""
    try:
        sb = scoreboard.ScoreBoard()
        games = sb.get_dict()['scoreboard']['games']
        matchups = []
        for g in games:
            matchups.append({
                'home': g['homeTeam']['teamName'],
                'away': g['awayTeam']['teamName'],
                'home_id': g['homeTeam']['teamId'],
                'away_id': g['awayTeam']['teamId']
            })
        return matchups
    except Exception as e:
        return []

def get_last_10_player_stat(player_name, prop_type):
    """Játékos statisztikák (pont, lepattanó, gólpassz)."""
    p = players.find_players_by_full_name(player_name)
    if not p: return None
    p_id = p[0]['id']
    try:
        log = playergamelog.PlayerGameLog(player_id=p_id).get_data_frames()[0].head(10)
        col = 'PTS' if 'points' in prop_type else 'REB' if 'rebounds' in prop_type else 'AST'
        return log[col].tolist()
    except:
        return None

def get_team_advanced_stats(team_id, is_home):
    """Csapat statisztikák (Home/Away split és átlagos pontszámok)."""
    try:
        # Győzelmi arány és split adatok
        dash = teamdashboardbygeneralsplits.TeamDashboardByGeneralSplits(team_id=team_id)
        splits = dash.get_data_frames()[1] # Home/Away táblázat
        
        # Kiválasztjuk a hazai vagy idegenbeli sort
        row = splits[splits['GROUP_VALUE'] == ('Home' if is_home else 'Road')]
        win_rate = row['W_PCT'].values[0] * 100 if not row.empty else 0
        
        # Utolsó 10 meccs átlagpontszámai a hendikephez/totalhoz
        finder = leaguegamefinder.LeagueGameFinder(team_id_nullable=team_id)
        recent_games = finder.get_data_frames()[0].head(10)
        avg_score = recent_games['PTS'].mean()
        avg_diff = recent_games['PLUS_MINUS'].mean()
        
        return {
            "win_rate": f"{round(win_rate, 1)}%",
            "avg_pts": round(avg_score, 1),
            "avg_diff": round(avg_diff, 1)
        }
    except:
        return {"win_rate": "N/A", "avg_pts": 0, "avg_diff": 0}

# --- FŐ PROGRAM (UI) ---

st.title("🏀 Pro NBA Fogadási Tanácsadó")
st.markdown("Statisztikák az utolsó 10 meccs alapján: Játékosok, Csapatok, Home/Away split.")

tab1, tab2 = st.tabs(["🔥 Játékos Propok", "🏠 Csapat Elemzés (O/U & Hendikep)"])

with tab1:
    st.header("Játékos Statisztika vs Cél")
    col1, col2 = st.columns(2)
    p_name = col1.text_input("Játékos neve:", "Luka Doncic")
    p_target = col2.number_input("Határ (pl. 28.5):", value=25.5)
    
    if st.button("Játékos elemzése"):
        stats = get_last_10_player_stat(p_name, "points")
        if stats:
            hits = sum(1 for s in stats if s > p_target)
            st.metric("Esély (Last 10)", f"{hits*10}%")
            st.bar_chart(stats)
            st.write(f"Pontok: {stats}")
        else:
            st.error("Nincs adat.")

with tab2:
    st.header("Mai Meccsek Elemzése")
    if st.button("Csapat statisztikák betöltése"):
        matchups = get_today_matchups()
        if not matchups:
            st.warning("Ma nincsenek meccsek.")
        else:
            results = []
            with st.spinner('Adatok lekérése...'):
                for m in matchups:
                    home = get_team_advanced_stats(m['home_id'], is_home=True)
                    away = get_team_advanced_stats(m['away_id'], is_home=False)
                    
                    results.append({
                        "Meccs": f"{m['away']} @ {m['home']}",
                        "Hazai Win Rate (Otthon)": home['win_rate'],
                        "Vendég Win Rate (Idegenben)": away['win_rate'],
                        "Várható Pont (H/V)": f"{home['avg_pts']} / {away['avg_pts']}",
                        "Összesített Várható": round(home['avg_pts'] + away['avg_pts'], 1),
                        "Hazai Diff": home['avg_diff']
                    })
                    time.sleep(0.7) # API limit védelem
                
            st.table(pd.DataFrame(results))
            st.download_button("Adatok letöltése CSV-ben", pd.DataFrame(results).to_csv(), "nba_today.csv")
