import urllib.request
import json
import urllib.parse
import re
from typing import Dict, Optional

# Pre-cached CDN URLs for instant loading (0 ms latency)
PRECACHED_BADGES: Dict[str, str] = {
    # Spain / La Liga
    "real madrid": "https://r2.thesportsdb.com/images/media/team/badge/vwvwrw1473502969.png",
    "barcelona": "https://r2.thesportsdb.com/images/media/team/badge/k4zo0k1641767927.png",
    "barcelone": "https://r2.thesportsdb.com/images/media/team/badge/k4zo0k1641767927.png",
    "fc barcelona": "https://r2.thesportsdb.com/images/media/team/badge/k4zo0k1641767927.png",
    "atletico madrid": "https://r2.thesportsdb.com/images/media/team/badge/0ulh3q1719984315.png",
    "club atlético de madrid": "https://r2.thesportsdb.com/images/media/team/badge/0ulh3q1719984315.png",
    "sevilla": "https://r2.thesportsdb.com/images/media/team/badge/vxvtqs1420584311.png",
    "real sociedad": "https://r2.thesportsdb.com/images/media/team/badge/qvvswq1420584328.png",
    "real betis": "https://r2.thesportsdb.com/images/media/team/badge/xvtupy1420584347.png",
    "athletic bilbao": "https://r2.thesportsdb.com/images/media/team/badge/upprxp1420584364.png",
    "valencia": "https://r2.thesportsdb.com/images/media/team/badge/uyrqvv1420584255.png",
    "villarreal": "https://r2.thesportsdb.com/images/media/team/badge/0l2l331621594738.png",
    "girona": "https://r2.thesportsdb.com/images/media/team/badge/5k1n0z1656932598.png",
    "celta vigo": "https://r2.thesportsdb.com/images/media/team/badge/2839211621594812.png",

    # England / Premier League & Championship
    "manchester city": "https://r2.thesportsdb.com/images/media/team/badge/vwpvry1467462651.png",
    "manchester united": "https://r2.thesportsdb.com/images/media/team/badge/xzqdr11517660252.png",
    "arsenal": "https://r2.thesportsdb.com/images/media/team/badge/uyhbfe1612467038.png",
    "liverpool": "https://r2.thesportsdb.com/images/media/team/badge/kfaher1737969724.png",
    "chelsea": "https://r2.thesportsdb.com/images/media/team/badge/pbf4ul1782638263.png",
    "tottenham": "https://r2.thesportsdb.com/images/media/team/badge/dfhe3i1621593847.png",
    "tottenham hotspur": "https://r2.thesportsdb.com/images/media/team/badge/dfhe3i1621593847.png",
    "newcastle": "https://r2.thesportsdb.com/images/media/team/badge/029efr1621594119.png",
    "newcastle united": "https://r2.thesportsdb.com/images/media/team/badge/029efr1621594119.png",
    "aston villa": "https://r2.thesportsdb.com/images/media/team/badge/e71b2k1621594246.png",
    "west ham": "https://r2.thesportsdb.com/images/media/team/badge/rqvrur1420584428.png",
    "brighton": "https://r2.thesportsdb.com/images/media/team/badge/e4a1k51621594314.png",
    "leeds": "https://r2.thesportsdb.com/images/media/team/badge/vwtvuq1420584411.png",
    "leeds united": "https://r2.thesportsdb.com/images/media/team/badge/vwtvuq1420584411.png",
    "leicester": "https://r2.thesportsdb.com/images/media/team/badge/133626.png",
    "southampton": "https://r2.thesportsdb.com/images/media/team/badge/133623.png",
    "ipswich": "https://r2.thesportsdb.com/images/media/team/badge/133647.png",
    "west brom": "https://r2.thesportsdb.com/images/media/team/badge/133644.png",
    "norwich": "https://r2.thesportsdb.com/images/media/team/badge/133632.png",
    "nottingham forest": "https://r2.thesportsdb.com/images/media/team/badge/139366.png",

    # Germany / Bundesliga (Complete List)
    "bayern munich": "https://r2.thesportsdb.com/images/media/team/badge/01ogkh1716960412.png",
    "bayern": "https://r2.thesportsdb.com/images/media/team/badge/01ogkh1716960412.png",
    "borussia dortmund": "https://r2.thesportsdb.com/images/media/team/badge/tqo8ge1716960353.png",
    "dortmund": "https://r2.thesportsdb.com/images/media/team/badge/tqo8ge1716960353.png",
    "bayer leverkusen": "https://r2.thesportsdb.com/images/media/team/badge/vrtuyp1420583765.png",
    "bayer 04": "https://r2.thesportsdb.com/images/media/team/badge/vrtuyp1420583765.png",
    "leverkusen": "https://r2.thesportsdb.com/images/media/team/badge/vrtuyp1420583765.png",
    "rb leipzig": "https://r2.thesportsdb.com/images/media/team/badge/e4w9c71621595574.png",
    "leipzig": "https://r2.thesportsdb.com/images/media/team/badge/e4w9c71621595574.png",
    "vfb stuttgart": "https://r2.thesportsdb.com/images/media/team/badge/u827291621595821.png",
    "stuttgart": "https://r2.thesportsdb.com/images/media/team/badge/u827291621595821.png",
    "eintracht frankfurt": "https://r2.thesportsdb.com/images/media/team/badge/6kug1k1621595640.png",
    "frankfurt": "https://r2.thesportsdb.com/images/media/team/badge/6kug1k1621595640.png",
    "vfl wolfsburg": "https://r2.thesportsdb.com/images/media/team/badge/vwpwtv1420583794.png",
    "wolfsburg": "https://r2.thesportsdb.com/images/media/team/badge/vwpwtv1420583794.png",
    "werder bremen": "https://r2.thesportsdb.com/images/media/team/badge/m06jcb1621595701.png",
    "werder": "https://r2.thesportsdb.com/images/media/team/badge/m06jcb1621595701.png",
    "borussia monchengladbach": "https://r2.thesportsdb.com/images/media/team/badge/03t61m1621595763.png",
    "monchengladbach": "https://r2.thesportsdb.com/images/media/team/badge/03t61m1621595763.png",
    "mönchengladbach": "https://r2.thesportsdb.com/images/media/team/badge/03t61m1621595763.png",
    "sc freiburg": "https://r2.thesportsdb.com/images/media/team/badge/8a1lfc1621595880.png",
    "freiburg": "https://r2.thesportsdb.com/images/media/team/badge/8a1lfc1621595880.png",
    "1. fc union berlin": "https://r2.thesportsdb.com/images/media/team/badge/8q97f51621596000.png",
    "union berlin": "https://r2.thesportsdb.com/images/media/team/badge/8q97f51621596000.png",
    "1. fc koln": "https://r2.thesportsdb.com/images/media/team/badge/2s7nfb1621596060.png",
    "koln": "https://r2.thesportsdb.com/images/media/team/badge/2s7nfb1621596060.png",
    "cologne": "https://r2.thesportsdb.com/images/media/team/badge/2s7nfb1621596060.png",
    "tsg hoffenheim": "https://r2.thesportsdb.com/images/media/team/badge/1k3i471621595941.png",
    "hoffenheim": "https://r2.thesportsdb.com/images/media/team/badge/1k3i471621595941.png",
    "fc augsburg": "https://r2.thesportsdb.com/images/media/team/badge/9d2j2b1621596180.png",
    "augsburg": "https://r2.thesportsdb.com/images/media/team/badge/9d2j2b1621596180.png",
    "fsv mainz 05": "https://r2.thesportsdb.com/images/media/team/badge/0p891b1621596120.png",
    "mainz": "https://r2.thesportsdb.com/images/media/team/badge/0p891b1621596120.png",
    "schalke 04": "https://r2.thesportsdb.com/images/media/team/badge/tvqvxu1420583852.png",
    "schalke": "https://r2.thesportsdb.com/images/media/team/badge/tvqvxu1420583852.png",

    # Italy / Serie A
    "inter milan": "https://r2.thesportsdb.com/images/media/team/badge/plo1hz1784764806.png",
    "inter": "https://r2.thesportsdb.com/images/media/team/badge/plo1hz1784764806.png",
    "juventus": "https://r2.thesportsdb.com/images/media/team/badge/uxf0gr1742983727.png",
    "ac milan": "https://r2.thesportsdb.com/images/media/team/badge/1429k11586523992.png",
    "milan": "https://r2.thesportsdb.com/images/media/team/badge/1429k11586523992.png",
    "napoli": "https://r2.thesportsdb.com/images/media/team/badge/wwyqxv1420584288.png",
    "roma": "https://r2.thesportsdb.com/images/media/team/badge/206y441621594895.png",
    "as roma": "https://r2.thesportsdb.com/images/media/team/badge/206y441621594895.png",
    "lazio": "https://r2.thesportsdb.com/images/media/team/badge/2u2d1e1621594966.png",
    "atalanta": "https://r2.thesportsdb.com/images/media/team/badge/y1c8281621595026.png",
    "fiorentina": "https://r2.thesportsdb.com/images/media/team/badge/142959.png",

    # France / Other Europe
    "paris saint-germain": "https://r2.thesportsdb.com/images/media/team/badge/has8b01763050866.png",
    "paris sg": "https://r2.thesportsdb.com/images/media/team/badge/has8b01763050866.png",
    "psg": "https://r2.thesportsdb.com/images/media/team/badge/has8b01763050866.png",
    "marseille": "https://r2.thesportsdb.com/images/media/team/badge/qvvptv1420584442.png",
    "lyon": "https://r2.thesportsdb.com/images/media/team/badge/blk9771656932845.png",
    "porto": "https://r2.thesportsdb.com/images/media/team/badge/vwysrx1420584478.png",
    "benfica": "https://r2.thesportsdb.com/images/media/team/badge/142998.png",
    "sporting cp": "https://r2.thesportsdb.com/images/media/team/badge/4v8a211621595188.png",
    "ajax": "https://r2.thesportsdb.com/images/media/team/badge/8m1z391621595111.png",
    "psv": "https://r2.thesportsdb.com/images/media/team/badge/xfsz6i1721297428.png",
    "galatasaray": "https://r2.thesportsdb.com/images/media/team/badge/io7jk21767941298.png",
    "fenerbahce": "https://r2.thesportsdb.com/images/media/team/badge/twxxvs1448199691.png",

    # National Teams (World Cup)
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
    "portugal": "https://r2.thesportsdb.com/images/media/team/badge/134438.png",
    "italy": "https://r2.thesportsdb.com/images/media/team/badge/134437.png",
    "italie": "https://r2.thesportsdb.com/images/media/team/badge/134437.png",
    "netherlands": "https://r2.thesportsdb.com/images/media/team/badge/134436.png",
    "pays-bas": "https://r2.thesportsdb.com/images/media/team/badge/134436.png",
    "belgium": "https://r2.thesportsdb.com/images/media/team/badge/134435.png",
    "belgique": "https://r2.thesportsdb.com/images/media/team/badge/134435.png",
}

_DYNAMIC_CACHE: Dict[str, str] = {}

def clean_team_name(name: str) -> str:
    """Removes Gamer handles, 'Cyber', and special markers to extract club name."""
    if not name:
        return ""
    cleaned = re.sub(r"\(.*?\)", "", name)
    cleaned = cleaned.replace("Cyber", "").replace("eSports", "").replace("Esports", "").replace("FC", "").replace("1.", "").strip()
    return cleaned.lower()

def get_team_logo(team_name: str) -> Optional[str]:
    """Resolves official team logo URL with instantaneous precached dictionary lookup."""
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

    return None
