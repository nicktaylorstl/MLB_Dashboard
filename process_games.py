import os
import json
import glob

INPUT_DIR = "D:/Baseball_Data/game_jsons/2026/"
OUTPUT_DIR = "D:/Baseball_Web/data/"
INDEX_FILE = os.path.join(OUTPUT_DIR, "games_index.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)
games_index = []

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

    pitches = []
    for play in live_data.get("plays", {}).get("allPlays", []):
        pitcher = play.get("matchup", {}).get("pitcher", {})
        batter = play.get("matchup", {}).get("batter", {})
        inning = play.get("about", {}).get("inning")
        half = play.get("about", {}).get("halfInning")
        at_bat_index = play.get("about", {}).get("atBatIndex", 0)
        pa_result = play.get("result", {}).get("event", "")
        pitch_in_pa = 0

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
                "playId": event.get("playId", ""),
                "inning": inning,
                "halfInning": half,
                "atBatIndex": at_bat_index,
                "pitchInPa": pitch_in_pa,
                "paResult": pa_result,
            }
            if hit_data:
                pitch["launchSpeed"] = hit_data.get("launchSpeed")
                pitch["launchAngle"] = hit_data.get("launchAngle")
                pitch["trajectory"] = hit_data.get("trajectory")

            pitches.append(pitch)

    out = {
        "gamePk": game_pk,
        "date": date,
        "awayTeam": away_team,
        "homeTeam": home_team,
        "awayAbbr": away_abbr,
        "homeAbbr": home_abbr,
        "venue": venue,
        "pitches": pitches,
    }

    out_file = os.path.join(OUTPUT_DIR, f"{game_pk}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out, f)

    games_index.append({
        "gamePk": game_pk,
        "date": date,
        "away": away_team,
        "home": home_team,
        "awayAbbr": away_abbr,
        "homeAbbr": home_abbr,
        "file": f"{game_pk}.json",
    })
    print(f"Processed: {date} {away_abbr} @ {home_abbr} ({len(pitches)} pitches)")

games_index.sort(key=lambda x: (x["date"], x["gamePk"]))
with open(INDEX_FILE, "w", encoding="utf-8") as f:
    json.dump(games_index, f)

print(f"\nDone. {len(games_index)} games written to {OUTPUT_DIR}")
