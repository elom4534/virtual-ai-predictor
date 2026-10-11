import urllib.request
import json
import urllib.parse
import re
from typing import Dict, Optional

# Pre-cached CDN URLs for instant loading (0 ms latency)
PRECACHED_BADGES: Dict[str, str] = {
    "real madrid": "https://r2.thesportsdb.com/images/media/team/badge/vwvwrw1473502969.png",
    "barcelona": "https://r2.thesportsdb.com/images/media/team/badge/k4zo0k1641767927.png",
    "barcelone": "https://r2.thesportsdb.com/images/media/team/badge/k4zo0k1641767927.png",
    "fc barcelona": "https://r2.thesportsdb.com/images/media/team/badge/k4zo0k1641767927.png",
    "manchester city": "https://r2.thesportsdb.com/images/media/team/badge/vwpvry1467462651.png",
    "manchester united": "https://r2.thesportsdb.com/images/media/team/badge/xzqdr11517660252.png",
    "bayern munich": "https://r2.thesportsdb.com/images/media/team/badge/01ogkh1716960412.png",
    "bayern": "https://r2.thesportsdb.com/images/media/team/badge/01ogkh1716960412.png",
    "paris saint-germain": "https://r2.thesportsdb.com/images/media/team/badge/has8b01763050866.png",
    "paris sg": "https://r2.thesportsdb.com/images/media/team/badge/has8b01763050866.png",
    "psg": "https://r2.thesportsdb.com/images/media/team/badge/has8b01763050866.png",
    "chelsea": "https://r2.thesportsdb.com/images/media/team/badge/pbf4ul1782638263.png",
    "arsenal": "https://r2.thesportsdb.com/images/media/team/badge/uyhbfe1612467038.png",
    "liverpool": "https://r2.thesportsdb.com/images/media/team/badge/kfaher1737969724.png",
    "juventus": "https://r2.thesportsdb.com/images/media/team/badge/uxf0gr1742983727.png",
    "piemonte calcio": "https://r2.thesportsdb.com/images/media/team/badge/uxf0gr1742983727.png",
    "inter": "https://r2.thesportsdb.com/images/media/team/badge/plo1hz1784764806.png",
    "inter milan": "https://r2.thesportsdb.com/images/media/team/badge/plo1hz1784764806.png",
    "milano": "https://r2.thesportsdb.com/images/media/team/badge/plo1hz1784764806.png",
    "ac milan": "https://r2.thesportsdb.com/images/media/team/badge/1429k11586523992.png",
    "borussia dortmund": "https://r2.thesportsdb.com/images/media/team/badge/tqo8ge1716960353.png",
    "dortmund": "https://r2.thesportsdb.com/images/media/team/badge/tqo8ge1716960353.png",
    "atletico madrid": "https://r2.thesportsdb.com/images/media/team/badge/0ulh3q1719984315.png",
    "club atlético de madrid": "https://r2.thesportsdb.com/images/media/team/badge/0ulh3q1719984315.png",
    "tottenham": "https://r2.thesportsdb.com/images/media/team/badge/dfhe3i1621593847.png",
    "tottenham hotspur": "https://r2.thesportsdb.com/images/media/team/badge/dfhe3i1621593847.png",
    "newcastle": "https://r2.thesportsdb.com/images/media/team/badge/029efr1621594119.png",
    "newcastle united": "https://r2.thesportsdb.com/images/media/team/badge/029efr1621594119.png",
    "aston villa": "https://r2.thesportsdb.com/images/media/team/badge/e71b2k1621594246.png",
    "galatasaray": "https://r2.thesportsdb.com/images/media/team/badge/io7jk21767941298.png",
    "fenerbahçe": "https://r2.thesportsdb.com/images/media/team/badge/twxxvs1448199691.png",
    "fenerbahce": "https://r2.thesportsdb.com/images/media/team/badge/twxxvs1448199691.png",
    "psv eindhoven": "https://r2.thesportsdb.com/images/media/team/badge/xfsz6i1721297428.png",
    "psv": "https://r2.thesportsdb.com/images/media/team/badge/xfsz6i1721297428.png",
    "ajax": "https://r2.thesportsdb.com/images/media/team/badge/8m1z391621595111.png",
    "lyon": "https://r2.thesportsdb.com/images/media/team/badge/blk9771656932845.png",
    "olympique lyonnais": "https://r2.thesportsdb.com/images/media/team/badge/blk9771656932845.png",
    "marseille": "https://r2.thesportsdb.com/images/media/team/badge/qvvptv1420584442.png",
    "olympique de marseille": "https://r2.thesportsdb.com/images/media/team/badge/qvvptv1420584442.png",
    "bayer 04": "https://r2.thesportsdb.com/images/media/team/badge/vrtuyp1420583765.png",
    "bayer leverkusen": "https://r2.thesportsdb.com/images/media/team/badge/vrtuyp1420583765.png",
    "napoli": "https://r2.thesportsdb.com/images/media/team/badge/wwyqxv1420584288.png",
    "roma": "https://r2.thesportsdb.com/images/media/team/badge/206y441621594895.png",
    "as roma": "https://r2.thesportsdb.com/images/media/team/badge/206y441621594895.png",
    "lazio": "https://r2.thesportsdb.com/images/media/team/badge/2u2d1e1621594966.png",
    "leeds": "https://r2.thesportsdb.com/images/media/team/badge/vwtvuq1420584411.png",
    "leeds united": "https://r2.thesportsdb.com/images/media/team/badge/vwtvuq1420584411.png",
    "nottingham forest": "https://r2.thesportsdb.com/images/media/team/badge/139366.png",
    "real betis": "https://r2.thesportsdb.com/images/media/team/badge/xvtupy1420584347.png",
    "sevilla": "https://r2.thesportsdb.com/images/media/team/badge/vxvtqs1420584311.png",
    "valencia": "https://r2.thesportsdb.com/images/media/team/badge/uyrqvv1420584255.png",
    "porto": "https://r2.thesportsdb.com/images/media/team/badge/vwysrx1420584478.png",
    "benfica": "https://r2.thesportsdb.com/images/media/team/badge/142998.png",
    "sporting cp": "https://r2.thesportsdb.com/images/media/team/badge/4v8a211621595188.png",
    "france": "https://r2.thesportsdb.com/images/media/team/badge/134444.png",
    "brazil": "https://r2.thesportsdb.com/images/media/team/badge/134443.png",
    "bresil": "https://r2.thesportsdb.com/images/media/team/badge/134443.png",
    "argentina": "https://r2.thesportsdb.com/images/media/team/badge/134442.png",
    "argentine": "https://r2.thesportsdb.com/images/media/team/badge/134442.png",
    "england": "https://r2.thesportsdb.com/images/media/team/badge/134441.png",
    "angleterre": "https://r2.thesportsdb.com/images/media/team/badge/134441.png",
    "germany": "https://r2.thesportsdb.com/images/media/team/badge/134440.png",
    "allemagne": "https://r2.thesportsdb.com/images/media/team/badge/134440.png",
    "spain": "https://r2.thesportsdb.com/images/media/team/badge/134439.png",
    "espagne": "https://r2.thesportsdb.com/images/media/team/badge/134439.png",
}

_DYNAMIC_CACHE: Dict[str, str] = {}

def clean_team_name(name: str) -> str:
    """Removes Gamer handles, 'Cyber', and special markers to extract club name."""
    if not name:
        return ""
    # Strip player nicknames in parentheses: e.g. "Real Madrid (Nazario)" -> "Real Madrid"
    cleaned = re.sub(r"\(.*?\)", "", name)
    cleaned = cleaned.replace("Cyber", "").replace("eSports", "").replace("Esports", "").strip()
    return cleaned.lower()

def get_team_logo(team_name: str) -> Optional[str]:
    """
    Resolves official team logo URL:
    1. Fast lookup in PRECACHED_BADGES
    2. Dynamic lookup in memory cache
    3. TheSportsDB free API query (with fallback)
    """
    if not team_name:
        return None

    cleaned = clean_team_name(team_name)

    # 1. Exact match in precached dictionary
    if cleaned in PRECACHED_BADGES:
        return PRECACHED_BADGES[cleaned]

    # 2. Substring matching
    for key, url in PRECACHED_BADGES.items():
        if key in cleaned or cleaned in key:
            return url

    # 3. Dynamic cache
    if cleaned in _DYNAMIC_CACHE:
        return _DYNAMIC_CACHE[cleaned]

    # 4. Fallback search via TheSportsDB free API
    try:
        query_url = f"https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t={urllib.parse.quote(cleaned)}"
        req = urllib.request.Request(query_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            teams = data.get("teams")
            if teams and teams[0].get("strBadge"):
                badge = teams[0]["strBadge"]
                _DYNAMIC_CACHE[cleaned] = badge
                return badge
    except Exception:
        pass

    return None
