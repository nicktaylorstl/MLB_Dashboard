import os
import json
import time
import requests
import statsapi
import pandas as pd
from datetime import date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

YEAR = date.today().year
INDEX_FILE = os.path.join(DATA_DIR, "games_index.json")
PLAYERS_FILE = os.path.join(DATA_DIR, "players_index.json")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def process_game_json(game):
    game_data = game.get("gameData", {})
    live_data = game.get("liveData", {})

    game_pk = game.get("gamePk")
    game_date = game_data.get("datetime", {}).get("officialDate", "")
    away_team = game_data.get("teams", {}).get("away", {}).get("name", "")
    home_team = game_data.get("teams", {}).get("home", {}).get("name", "")
    away_abbr = game_data.get("teams", {}).get("away", {}).get("abbreviation", "")
    home_abbr = game_data.get("teams", {}).get("home", {}).get("abbreviation", "")
    venue = game_data.get("venue", {}).get("name", "")

    player_lookup = {}
    for pinfo in game_data.get("players", {}).values():
        pid = pinfo.get("id")
        name = pinfo.get("fullName", "")
        if pid and name:
            player_lookup[str(pid)] = name

    pitches = []
    fielding_events = []

    for play in live_data.get("plays", {}).get("allPlays", []):
        pitcher = play.get("matchup", {}).get("pitcher", {})
        batter = play.get("matchup", {}).get("batter", {})
        bat_side = play.get("matchup", {}).get("batSide", {}).get("code", "")
        pitch_hand_code = play.get("matchup", {}).get("pitchHand", {}).get("code", "")
        inning = play.get("about", {}).get("inning")
        half = play.get("about", {}).get("halfInning")
        at_bat_index = play.get("about", {}).get("atBatIndex", 0)
        pa_result = play.get("result", {}).get("event", "")
        pitch_in_pa = 0
        balls_in_pa = 0
        strikes_in_pa = 0

        for event in play.get("playEvents", []):
            if not event.get("isPitch"):
                continue
            pitch_in_pa += 1

            pitch_data = event.get("pitchData", {})
            coords = pitch_data.get("coordinates", {})
            details = event.get("details", {})
            hit_data = event.get("hitData", {})

            px = coords.get("pX")
            pz = coords.get("pZ")
            if px is None or pz is None:
                continue

            if details.get("isInPlay"):
                outcome = "inplay"
            elif details.get("isStrike"):
                outcome = "strike"
            elif details.get("isBall"):
                outcome = "ball"
            else:
                continue

            pitch = {
                "pitcher": pitcher.get("fullName", ""),
                "pitcherId": pitcher.get("id"),
                "batter": batter.get("fullName", ""),
                "batterId": batter.get("id"),
                "pitchType": details.get("type", {}).get("description", "Unknown"),
                "call": details.get("description", ""),
                "outcome": outcome,
                "pX": round(px, 4),
                "pZ": round(pz, 4),
                "szTop": round(pitch_data.get("strikeZoneTop", 3.5), 3),
                "szBottom": round(pitch_data.get("strikeZoneBottom", 1.5), 3),
                "startSpeed": pitch_data.get("startSpeed"),
                "spinRate": pitch_data.get("breaks", {}).get("spinRate"),
                "iVB": pitch_data.get("breaks", {}).get("breakVerticalInduced"),
                "HB": pitch_data.get("breaks", {}).get("breakHorizontal"),
                "playId": event.get("playId", ""),
                "inning": inning,
                "halfInning": half,
                "atBatIndex": at_bat_index,
                "pitchInPa": pitch_in_pa,
                "paResult": pa_result,
                "batSide": bat_side,
                "pitchHand": pitch_hand_code,
                "homeAbbr": home_abbr,
                "awayAbbr": away_abbr,
                "countBalls": balls_in_pa,
                "countStrikes": strikes_in_pa,
            }
            if hit_data:
                pitch["launchSpeed"] = hit_data.get("launchSpeed")
                pitch["launchAngle"] = hit_data.get("launchAngle")
                pitch["trajectory"] = hit_data.get("trajectory")
                pitch["totalDistance"] = hit_data.get("totalDistance")
                hit_coords = hit_data.get("coordinates", {})
                pitch["hitX"] = hit_coords.get("coordX")
                pitch["hitY"] = hit_coords.get("coordY")

            pitches.append(pitch)

            if outcome == "ball":
                balls_in_pa += 1
            elif outcome == "strike":
                desc = details.get("description", "")
                if not ("Foul" in desc and strikes_in_pa >= 2):
                    strikes_in_pa = min(strikes_in_pa + 1, 2)

        hit_info = {}
        inplay_play_id = ""
        for event in play.get("playEvents", []):
            if event.get("isPitch") and event.get("details", {}).get("isInPlay"):
                hd = event.get("hitData", {})
                hc = hd.get("coordinates", {})
                if hc.get("coordX") is not None:
                    hit_info = {
                        "hitX": hc["coordX"],
                        "hitY": hc["coordY"],
                        "launchSpeed": hd.get("launchSpeed"),
                        "launchAngle": hd.get("launchAngle"),
                        "trajectory": hd.get("trajectory"),
                        "totalDistance": hd.get("totalDistance"),
                    }
                inplay_play_id = event.get("playId", "")

        for event in play.get("runners", []):
            for credit_entry in event.get("credits", []):
                player_id = credit_entry.get("player", {}).get("id")
                fname = player_lookup.get(str(player_id), "")
                if not fname:
                    continue
                credit = credit_entry.get("credit", "")
                if credit not in ("f_putout", "f_assist", "f_fielding_error"):
                    continue
                pos = credit_entry.get("position", {})
                fe = {
                    "fielder": fname,
                    "fielderId": player_id,
                    "position": pos.get("name", ""),
                    "positionAbbr": pos.get("abbreviation", ""),
                    "credit": credit,
                    "batter": batter.get("fullName", ""),
                    "batterId": batter.get("id"),
                    "batSide": bat_side,
                    "inning": inning,
                    "halfInning": half,
                    "atBatIndex": at_bat_index,
                    "paResult": pa_result,
                    "playId": inplay_play_id,
                    "homeAbbr": home_abbr,
                    "awayAbbr": away_abbr,
                }
                fe.update(hit_info)
                fielding_events.append(fe)

    return {
        "gamePk": game_pk,
        "date": game_date,
        "awayTeam": away_team,
        "homeTeam": home_team,
        "awayAbbr": away_abbr,
        "homeAbbr": home_abbr,
        "venue": venue,
        "pitches": pitches,
        "fielding": fielding_events,
    }


def main():
    games_index = load_json(INDEX_FILE, [])
    player_games = load_json(PLAYERS_FILE, {"pitchers": {}, "batters": {}, "fielders": {}})
    existing_pks = {g["gamePk"] for g in games_index}

    yesterday = date.today() - timedelta(days=1)
    print(f"Fetching {YEAR} schedule through {yesterday}...")
    schedule = statsapi.schedule(start_date=f"{YEAR}-02-01", end_date=str(yesterday))
    df = pd.json_normalize(schedule)
    all_game_ids = sorted(df[df["game_type"] == "R"]["game_id"].drop_duplicates().tolist())

    new_game_ids = [gid for gid in all_game_ids if gid not in existing_pks]
    print(f"{len(existing_pks)} games already processed, {len(new_game_ids)} new games to fetch")

    for count, game_pk in enumerate(new_game_ids, 1):
        url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            game = r.json()
        except Exception as e:
            print(f"[{count}/{len(new_game_ids)}] Failed {game_pk}: {e}")
            continue

        out = process_game_json(game)
        pitches = out["pitches"]
        fielding_events = out["fielding"]
        away_abbr = out["awayAbbr"]
        home_abbr = out["homeAbbr"]

        out_file = os.path.join(DATA_DIR, f"{game_pk}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(out, f)

        if pitches:
            games_index.append({
                "gamePk": game_pk,
                "date": out["date"],
                "away": out["awayTeam"],
                "home": out["homeTeam"],
                "awayAbbr": away_abbr,
                "homeAbbr": home_abbr,
                "file": f"{game_pk}.json",
            })

            seen_p, seen_b, seen_f = set(), set(), set()
            for pitch in pitches:
                pname = pitch["pitcher"]
                bname = pitch["batter"]
                half = pitch.get("halfInning", "top")
                if pname not in seen_p:
                    seen_p.add(pname)
                    pteam = home_abbr if half == "top" else away_abbr
                    entry = player_games["pitchers"].setdefault(pname, {"team": pteam, "games": []})
                    if f"{game_pk}.json" not in entry["games"]:
                        entry["games"].append(f"{game_pk}.json")
                    entry["team"] = pteam
                if bname not in seen_b:
                    seen_b.add(bname)
                    bteam = away_abbr if half == "top" else home_abbr
                    entry = player_games["batters"].setdefault(bname, {"team": bteam, "games": []})
                    if f"{game_pk}.json" not in entry["games"]:
                        entry["games"].append(f"{game_pk}.json")
                    entry["team"] = bteam

            seen_f = set()
            for fe in fielding_events:
                fname = fe["fielder"]
                if fname not in seen_f:
                    seen_f.add(fname)
                    fteam = home_abbr if fe.get("halfInning") == "top" else away_abbr
                    entry = player_games["fielders"].setdefault(fname, {"team": fteam, "games": []})
                    if f"{game_pk}.json" not in entry["games"]:
                        entry["games"].append(f"{game_pk}.json")
                    entry["team"] = fteam

        print(f"[{count}/{len(new_game_ids)}] {out['date']} {away_abbr} @ {home_abbr} ({len(pitches)} pitches)")
        time.sleep(0.1)

    games_index.sort(key=lambda x: (x["date"], x["gamePk"]))
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(games_index, f)
    with open(PLAYERS_FILE, "w", encoding="utf-8") as f:
        json.dump(player_games, f)

    print(f"\nDone. {len(games_index)} total games in index.")
    print(f"Players: {len(player_games['pitchers'])} pitchers, {len(player_games['batters'])} batters, {len(player_games['fielders'])} fielders")


if __name__ == "__main__":
    main()
