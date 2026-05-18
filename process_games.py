import os
import json
import glob

INPUT_DIR = "D:/Baseball_Data/game_jsons/2026/"
OUTPUT_DIR = "D:/Baseball_Data/Baseball_Web/data/"
INDEX_FILE = os.path.join(OUTPUT_DIR, "games_index.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)
games_index = []
player_games = {"pitchers": {}, "batters": {}, "fielders": {}}

for filepath in sorted(glob.glob(os.path.join(INPUT_DIR, "*.json"))):
    filename = os.path.basename(filepath)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            game = json.loads(f.readline())
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        continue

    game_data = game.get("gameData", {})
    live_data = game.get("liveData", {})

    game_pk = game.get("gamePk")
    date = game_data.get("datetime", {}).get("officialDate", "")
    away_team = game_data.get("teams", {}).get("away", {}).get("name", "")
    home_team = game_data.get("teams", {}).get("home", {}).get("name", "")
    away_abbr = game_data.get("teams", {}).get("away", {}).get("abbreviation", "")
    home_abbr = game_data.get("teams", {}).get("home", {}).get("abbreviation", "")
    venue = game_data.get("venue", {}).get("name", "")

    # Build player name lookup from game roster
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

        # Extract hit location from the in-play pitch event (if any)
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

        # Extract fielding credits from runners array
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

    seen_p, seen_b, seen_f = set(), set(), set()
    for pitch in pitches:
        pname = pitch["pitcher"]
        bname = pitch["batter"]
        half = pitch.get("halfInning", "top")
        if pname not in seen_p:
            seen_p.add(pname)
            pteam = home_abbr if half == "top" else away_abbr
            entry = player_games["pitchers"].setdefault(pname, {"team": pteam, "games": []})
            entry["games"].append(f"{game_pk}.json")
            entry["team"] = pteam
        if bname not in seen_b:
            seen_b.add(bname)
            bteam = away_abbr if half == "top" else home_abbr
            entry = player_games["batters"].setdefault(bname, {"team": bteam, "games": []})
            entry["games"].append(f"{game_pk}.json")
            entry["team"] = bteam

    for fe in fielding_events:
        fname = fe["fielder"]
        if fname not in seen_f:
            seen_f.add(fname)
            fteam = home_abbr if fe.get("halfInning") == "top" else away_abbr
            entry = player_games["fielders"].setdefault(fname, {"team": fteam, "games": []})
            entry["games"].append(f"{game_pk}.json")
            entry["team"] = fteam

    out = {
        "gamePk": game_pk,
        "date": date,
        "awayTeam": away_team,
        "homeTeam": home_team,
        "awayAbbr": away_abbr,
        "homeAbbr": home_abbr,
        "venue": venue,
        "pitches": pitches,
        "fielding": fielding_events,
    }

    out_file = os.path.join(OUTPUT_DIR, f"{game_pk}.json")
    for _attempt in range(5):
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(out, f)
            break
        except OSError:
            import time; time.sleep(0.3)

    if pitches:
        games_index.append({
            "gamePk": game_pk,
            "date": date,
            "away": away_team,
            "home": home_team,
            "awayAbbr": away_abbr,
            "homeAbbr": home_abbr,
            "file": f"{game_pk}.json",
        })
    print(f"Processed: {date} {away_abbr} @ {home_abbr} ({len(pitches)} pitches, {len(fielding_events)} fielding)")

games_index.sort(key=lambda x: (x["date"], x["gamePk"]))
with open(INDEX_FILE, "w", encoding="utf-8") as f:
    json.dump(games_index, f)

players_index_file = os.path.join(OUTPUT_DIR, "players_index.json")
with open(players_index_file, "w", encoding="utf-8") as f:
    json.dump(player_games, f)
print(f"Players index: {len(player_games['pitchers'])} pitchers, {len(player_games['batters'])} batters, {len(player_games['fielders'])} fielders")

print(f"\nDone. {len(games_index)} games written to {OUTPUT_DIR}")
