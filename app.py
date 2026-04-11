import requests
import pandas as pd
from nba_api.stats.endpoints import playergamelog
from nba_api.stats.static import players
import time

# --- BEÁLLÍTÁSOK ---
API_KEY = 'IDE_ÍRD_AZ_API_KULCSOD'  # Regisztrálj: the-odds-api.com
REGION = 'eu' # Európai irodák
MARKETS = 'player_points,player_rebounds,player_assists' # Pont, Lepattanó, Gólpassz

def get_live_odds():
    """Lekéri az aktuális fogadási kínálatot az Odds API-tól."""
    url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/events'
    # Először lekérjük a meccseket
    events_res = requests.get(url, params={'apiKey': API_KEY}).json()
    
    all_props = []
    
    # Minden meccshez lekérjük a konkrét játékos fogadásokat
    # Az ingyenes verzióban meccsenként kell lekérni a propokat
    for event in events_res[:3]: # Limitáljuk az első 3 meccsre a gyorsaság és az API limit miatt
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
                        if 'Over' in outcome['name']: # Csak a "Felett" fogadásokat nézzük az egyszerűség kedvéért
                            all_props.append({
                                'player': outcome['description'],
                                'type': market['key'], # pl. player_points
                                'line': outcome['point'],
                                'odds': outcome['price']
                            })
    return all_props

def get_last_10_stat(player_name, prop_type):
    """Lekéri a specifikus statisztikát az NBA-től."""
    full_player = players.find_players_by_full_name(player_name)
    if not full_player: return None
    
    p_id = full_player[0]['id']
    try:
        log = playergamelog.PlayerGameLog(player_id=p_id).get_data_frames()[0].head(10)
        
        # Melyik oszlopot nézzük?
        col = 'PTS' if 'points' in prop_type else 'REB' if 'rebounds' in prop_type else 'AST'
        stats = log[col].tolist()
        return stats
    except:
        return None

def main():
    print("🚀 Élő oddsok betöltése és elemzése...")
    props = get_live_odds()
    
    if not props:
        print("❌ Nem találtam aktív fogadási kínálatot.")
        return

    print(f"✅ {len(props)} fogadási lehetőség található. Statisztikák ellenőrzése...\n")
    print(f"{'JÁTÉKOS':<20} | {'TÍPUS':<10} | {'HATÁR':<6} | {'ESÉLY (10/x)':<12} | {'ODDS':<6} | {'VALUE'}")
    print("-" * 85)

    seen_players = set() # Hogy ne kérdezzük le ugyanazt a játékost többször

    for p in props:
        # Csak a legfontosabbakat nézzük, hogy ne fussunk bele API limitbe
        if p['player'] in seen_players: continue
        
        stats = get_last_10_stat(p['player'], p['type'])
        if stats:
            hits = sum(1 for s in stats if s > p['line'])
            prob = (hits / 10)
            ev = prob * p['odds']
            
            status = "🔥 MEGÉRI" if ev > 1.1 else "❌ NEM"
            
            print(f"{p['player']:<20} | {p['type'].replace('player_',''):<10} | {p['line']:<6} | {hits*10:>3}% (10/{hits}) | {p['odds']:<6} | {status}")
            
            seen_players.add(p['player'])
            time.sleep(0.6) # NBA API biztonsági szünet

if __name__ == "__main__":
    main()
    
