"""Bracket view-model builders + pick reconciliation.

`build_user_bracket` and `build_group_bracket` produce the structured data the
bracket templates iterate over. `reconcile_user_picks` cascades orphan picks
when a user changes an earlier-round pick that invalidates downstream picks.
"""

from .models import (
    GroupMembership,
    Match,
    Prediction,
    Round,
    is_tournament_locked,
    tournament_lock_time,
)

TOTAL_MATCHES = 32

ROUND_DISPLAY_ORDER = [
    Round.R32,
    Round.R16,
    Round.QF,
    Round.SF,
    Round.THIRD,
    Round.FINAL,
]


def _slot_sort_key(slot: str) -> int:
    """Sort key for slots like 'R32-1', 'R16-3'. Returns the numeric suffix so
    'R32-2' sorts before 'R32-10'. THIRD/FINAL have no suffix → 0."""
    parts = slot.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    return 0


def _fetch_matches():
    return list(
        Match.objects.select_related("home_team", "away_team", "winner").order_by(
            "slot"
        )
    )


def _sources_by_match_id(matches):
    out = {}
    for m in matches:
        if m.feeds_into_id:
            out.setdefault(m.feeds_into_id, []).append(m)
    return out


def _user_pick_map(user, group):
    qs = Prediction.objects.filter(user=user, group=group).select_related(
        "picked_winner"
    )
    return {p.match_id: p.picked_winner for p in qs}


def _sf_loser(sf_match, pick_map, derived_so_far):
    """Team in `sf_match` the user did NOT pick. None if no pick or no teams."""
    sf_home, sf_away = derived_so_far.get(sf_match.id, (None, None))
    pick = pick_map.get(sf_match.id)
    if pick is None:
        return None
    if pick == sf_home:
        return sf_away
    if pick == sf_away:
        return sf_home
    return None


def _derived_teams(match, pick_map, sources_by_match, derived_so_far, matches_by_slot):
    """Return (home, away) for `match`: actual if Match has them set, otherwise
    derived from user's source-match picks. THIRD is special — derives from
    losers of SF-1 / SF-2."""
    home = match.home_team
    away = match.away_team
    if home and away:
        return home, away

    if match.slot == "THIRD":
        sf1 = matches_by_slot.get("SF-1")
        sf2 = matches_by_slot.get("SF-2")
        derived_home = _sf_loser(sf1, pick_map, derived_so_far) if sf1 else None
        derived_away = _sf_loser(sf2, pick_map, derived_so_far) if sf2 else None
        return (home or derived_home, away or derived_away)

    sources = sources_by_match.get(match.id, [])
    home_src = next((s for s in sources if s.feeds_as == "home"), None)
    away_src = next((s for s in sources if s.feeds_as == "away"), None)
    derived_home = pick_map.get(home_src.id) if home_src else None
    derived_away = pick_map.get(away_src.id) if away_src else None
    return (home or derived_home, away or derived_away)


def _scoring_state(match, pick):
    if match.winner_id is None:
        return "neutral"
    if pick is not None and pick == match.winner:
        return "correct"
    return "incorrect"


def build_user_bracket(user, group):
    matches = _fetch_matches()
    matches_by_slot = {m.slot: m for m in matches}
    sources_by_match = _sources_by_match_id(matches)
    pick_map = _user_pick_map(user, group)

    membership = GroupMembership.objects.filter(group=group, user=user).first()
    submitted = membership.bracket_submitted if membership else False
    submitted_at = membership.bracket_submitted_at if membership else None
    locked = is_tournament_locked()
    editable_phase = (not locked) and (not submitted)

    derived_teams = {}
    rounds_data = []
    for round_key in ROUND_DISPLAY_ORDER:
        round_matches = sorted(
            [m for m in matches if m.round == round_key],
            key=lambda m: _slot_sort_key(m.slot),
        )
        matches_out = []
        for m in round_matches:
            home, away = _derived_teams(
                m, pick_map, sources_by_match, derived_teams, matches_by_slot
            )
            derived_teams[m.id] = (home, away)
            pick = pick_map.get(m.id)
            has_teams = bool(home and away)
            matches_out.append(
                {
                    "match": m,
                    "home": home,
                    "away": away,
                    "pick": pick,
                    "has_teams": has_teams,
                    "pickable": has_teams and editable_phase,
                    "scoring": _scoring_state(m, pick),
                }
            )
        rounds_data.append(
            {
                "round": round_key,
                "label": Round(round_key).label,
                "matches": matches_out,
            }
        )

    return {
        "rounds": rounds_data,
        "lock_time": tournament_lock_time(),
        "is_locked": locked,
        "submitted": submitted,
        "submitted_at": submitted_at,
        "pick_count": len(pick_map),
        "complete": len(pick_map) >= TOTAL_MATCHES,
        "editable_phase": editable_phase,
    }


def reconcile_user_picks(user, group):
    """Delete any Prediction whose picked_winner is no longer in its match's
    derived teams. Walks in dependency order so deletions cascade naturally
    (clearing a R32 pick invalidates the dependent R16 pick, which on the next
    round's pass invalidates the dependent QF pick, etc.). R32 picks are never
    auto-cleared because R32 teams are admin-set, not derived from user picks."""
    matches = _fetch_matches()
    matches_by_slot = {m.slot: m for m in matches}
    sources_by_match = _sources_by_match_id(matches)
    derived_teams = {}

    for round_key in ROUND_DISPLAY_ORDER:
        pick_map = _user_pick_map(user, group)
        round_matches = [m for m in matches if m.round == round_key]
        for m in round_matches:
            home, away = _derived_teams(
                m, pick_map, sources_by_match, derived_teams, matches_by_slot
            )
            derived_teams[m.id] = (home, away)
            if round_key == Round.R32:
                continue
            pick = pick_map.get(m.id)
            if pick is None:
                continue
            if home is None or away is None or (pick != home and pick != away):
                Prediction.objects.filter(user=user, group=group, match=m).delete()


def build_group_bracket(group):
    """Aggregated view: for each match, list every member's pick. Picks are
    hidden pre-lock (returns rounds with empty picks lists)."""
    matches = _fetch_matches()
    locked = is_tournament_locked()
    picks_by_match = {}
    if locked:
        predictions = Prediction.objects.filter(group=group).select_related(
            "user", "picked_winner"
        )
        for p in predictions:
            picks_by_match.setdefault(p.match_id, []).append(
                {"user": p.user, "team": p.picked_winner}
            )

    rounds_data = []
    for round_key in ROUND_DISPLAY_ORDER:
        round_matches = sorted(
            [m for m in matches if m.round == round_key],
            key=lambda m: _slot_sort_key(m.slot),
        )
        matches_out = []
        for m in round_matches:
            matches_out.append(
                {
                    "match": m,
                    "home": m.home_team,
                    "away": m.away_team,
                    "winner": m.winner,
                    "picks": picks_by_match.get(m.id, []),
                }
            )
        rounds_data.append(
            {
                "round": round_key,
                "label": Round(round_key).label,
                "matches": matches_out,
            }
        )

    return {
        "rounds": rounds_data,
        "is_locked": locked,
    }
