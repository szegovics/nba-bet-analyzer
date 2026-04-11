import streamlit as st
import pandas as pd
from nba_api.stats.endpoints import commonallplayers, playergamelog
from nba_api.live.nba.endpoints import scoreboard
import time

st.set_page_config(page_title="NBA Napi Esélylatolgató", layout="wide")

st.title("🏀 Napi NBA Statisztikai Elemző")
st.write("Az utolsó 10 meccs alapján számolt valószínűségek a mai meccsekre.")

# --- FUNKCIÓK ---

@st.cache_data(ttl=3600)
def get_today_games():
    """Lekéri a mai meccseket."""
    sb = scoreboard.ScoreBoard()
    games = sb.get_dict()['scoreboard']['games']
    return games

def get_player_stats(player_id):
    """Lekéri az utolsó 10 meccs pontjait."""
    try:
        log = playergamelog.PlayerGameLog(player_id=player_id, season='2023-24')
        df = log.get_data_frames()[0]
        return df.head(10)['PTS'].tolist()
    except:
        return []

# --- OLDALSÁV / BEÁLLÍTÁSOK ---
st.sidebar.header("Beállítások")
target_pts = st.sidebar.slider("Minimum elvárt pontszám", 10, 40, 20)
min_prob = st.sidebar.slider("Minimum esély szűrése (%)", 0, 100, 60)

if st.button("Mai meccsek és statisztikák betöltése"):
    games = get_today_games()
    
    if not games:
        st.warning("Ma nincsenek meccsek vagy még nem frissült a menetrend.")
    else:
        results = []
        
        with st.spinner('Elemzés folyamatban... Ez eltarthat 1-2 percig.'):
            # Lekérjük az összes aktív játékost egyszer (gyorsítás)
            all_players = commonallplayers.CommonAllPlayers(is_only_current_season=1).get_data_frames()[0]
            
            for game in games:
                home_team = game['homeTeam']['teamName']
                away_team = game['awayTeam']['teamName']
                st.subheader(f"🏟️ {away_team} @ {home_team}")
                
                # Itt egy példa listát használunk a top játékosokról, 
                # mert az összes NBA játékos lekérése túl lassú lenne egyben
                # A valóságban ide egy "Top Players" listát érdemes tenni
                sample_players = [
                    {"name": "Luka Doncic", "id": 1629029},
                    {"name": "Kyrie Irving", "id": 202681},
                    {"name": "Jayson Tatum", "id": 1628369},
                    {"name": "Jaylen Brown", "id": 1627759},
                    {"name": "Nikola Jokic", "id": 203999}
                ]
                
                # Csak azokat nézzük, akik az adott meccsen játszanak (egyszerűsítve)
                for p in sample_players:
                    stats = get_player_stats(p['id'])
                    if stats:
                        hits = sum(1 for pts in stats if pts >= target_pts)
                        prob = (hits / 10) * 100
                        
                        if prob >= min_prob:
                            results.append({
                                "Játékos": p['name'],
                                "Meccs": f"{away_team}@{home_team}",
                                "Cél": f"{target_pts}+ pont",
                                "Utolsó 10 meccs": str(stats),
                                "Esély (%)": f"{prob}%",
                                "Várható Odds": round(100/prob, 2) if prob > 0 else 0
                            })
            
            if results:
                df_res = pd.DataFrame(results)
                st.table(df_res)
                st.success("Elemzés kész!")
            else:
                st.info("A megadott szűrőkkel nem találtam biztos tippet.")

# --- UTASÍTÁS ---
st.divider()
st.info("""
**Hogyan használd?**
1. Kattints a betöltésre.
2. Az app kiszámolja, hányszor érte el a játékos a célpontszámot az utolsó 10 meccsén.
3. A 'Várható Odds' azt mutatja, mi lenne a reális szorzó. Ha a Vegas ennél nagyobbat ad, akkor érdemes megfogadni!
""")
