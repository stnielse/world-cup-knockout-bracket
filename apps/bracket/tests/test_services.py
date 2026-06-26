import pytest

from apps.bracket.models import Prediction, ScoringRule
from apps.bracket.services import (
    build_user_bracket,
    compute_group_standings,
    reconcile_user_picks,
)


@pytest.mark.django_db
class TestDerivedTeamsIsolation:
    """The user bracket display must derive R16+ teams purely from the user's
    own picks, ignoring canonical Match.home_team / away_team even after
    auto-advancement fills them in. This is the regression-critical invariant
    that protects users' picks from silent mutation."""

    def test_r32_uses_canonical_teams(self, bracket, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        b = build_user_bracket(owner, group)
        r32 = next(r for r in b["rounds"] if r["round"] == "R32")
        r32_1 = next(e for e in r32["matches"] if e["match"].slot == "R32-1")
        assert r32_1["home"].code == "USA"
        assert r32_1["away"].code == "MEX"

    def test_r16_derives_from_user_picks_ignoring_canonical(
        self, bracket, make_user, make_group
    ):
        """User picks MEX over USA in R32-1. Admin then sets R32-1.winner=USA
        (so R16-1.home_team auto-advances to USA). User's bracket should
        STILL show MEX in R16-1, NOT USA."""
        owner = make_user()
        group = make_group(owner=owner)
        r32_1 = bracket.match("R32-1")
        Prediction.objects.create(
            user=owner, group=group, match=r32_1, picked_winner=bracket.mex
        )
        # Admin sets canonical winner
        r32_1.winner = bracket.usa
        r32_1.save()

        b = build_user_bracket(owner, group)
        r16 = next(r for r in b["rounds"] if r["round"] == "R16")
        r16_1 = next(e for e in r16["matches"] if e["match"].slot == "R16-1")
        assert r16_1["home"].code == "MEX", "user pick should override canonical"

    def test_user_prediction_survives_winner_set(self, bracket, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        r32_1 = bracket.match("R32-1")
        r32_2 = bracket.match("R32-2")
        r16_1 = bracket.match("R16-1")
        Prediction.objects.create(
            user=owner, group=group, match=r32_1, picked_winner=bracket.mex
        )
        Prediction.objects.create(
            user=owner, group=group, match=r32_2, picked_winner=bracket.can
        )
        # User picks MEX vs CAN in R16-1 (their derived matchup)
        Prediction.objects.create(
            user=owner, group=group, match=r16_1, picked_winner=bracket.mex
        )
        # Admin sets canonical winners that differ from user picks
        r32_1.winner = bracket.usa
        r32_1.save()
        r32_2.winner = bracket.bra
        r32_2.save()
        # All three predictions should still exist — auto-advance never
        # touches Prediction rows
        assert Prediction.objects.filter(user=owner, group=group).count() == 3


@pytest.mark.django_db
class TestReconcileUserPicks:
    def test_changing_r32_pick_deletes_orphaned_r16_pick(
        self, bracket, make_user, make_group
    ):
        owner = make_user()
        group = make_group(owner=owner)
        r32_1 = bracket.match("R32-1")
        r32_2 = bracket.match("R32-2")
        r16_1 = bracket.match("R16-1")
        Prediction.objects.create(
            user=owner, group=group, match=r32_1, picked_winner=bracket.usa
        )
        Prediction.objects.create(
            user=owner, group=group, match=r32_2, picked_winner=bracket.can
        )
        Prediction.objects.create(
            user=owner, group=group, match=r16_1, picked_winner=bracket.usa
        )

        # User changes R32-1 pick to MEX. Derived R16-1 is now (MEX, CAN).
        # The existing R16-1 pick (USA) is orphaned.
        Prediction.objects.filter(user=owner, group=group, match=r32_1).update(
            picked_winner=bracket.mex
        )
        reconcile_user_picks(owner, group)

        assert not Prediction.objects.filter(
            user=owner, group=group, match=r16_1
        ).exists()

    def test_reconcile_never_deletes_r32_picks(self, bracket, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        r32_1 = bracket.match("R32-1")
        Prediction.objects.create(
            user=owner, group=group, match=r32_1, picked_winner=bracket.usa
        )
        reconcile_user_picks(owner, group)
        assert Prediction.objects.filter(user=owner, group=group, match=r32_1).exists()

    def test_reconcile_cascades_across_rounds(self, bracket, make_user, make_group):
        """Change R32-1 pick → R16-1 orphaned → QF-1 (built on R16-1) also
        orphaned in the same reconcile pass."""
        owner = make_user()
        group = make_group(owner=owner)
        r32_1 = bracket.match("R32-1")
        r32_2 = bracket.match("R32-2")
        r16_1 = bracket.match("R16-1")
        qf_1 = bracket.match("QF-1")
        # User picks chain: USA → USA → USA all the way up
        Prediction.objects.create(
            user=owner, group=group, match=r32_1, picked_winner=bracket.usa
        )
        Prediction.objects.create(
            user=owner, group=group, match=r32_2, picked_winner=bracket.can
        )
        Prediction.objects.create(
            user=owner, group=group, match=r16_1, picked_winner=bracket.usa
        )
        Prediction.objects.create(
            user=owner, group=group, match=qf_1, picked_winner=bracket.usa
        )

        # User changes R32-1 to MEX. R16-1 derived becomes (MEX, CAN).
        # R16-1 pick (USA) is orphaned → deleted. Then QF-1 has no R16-1
        # source pick anymore → QF-1 derived home becomes None → QF-1 pick
        # (USA) orphaned → deleted.
        Prediction.objects.filter(user=owner, group=group, match=r32_1).update(
            picked_winner=bracket.mex
        )
        reconcile_user_picks(owner, group)

        assert not Prediction.objects.filter(
            user=owner, group=group, match=r16_1
        ).exists()
        assert not Prediction.objects.filter(
            user=owner, group=group, match=qf_1
        ).exists()


@pytest.mark.django_db
class TestComputeGroupStandings:
    def _setup_three_user_scenario(
        self, bracket, make_user, make_group, make_membership
    ):
        owner = make_user(username="owner")
        member = make_user(username="member")
        bystander = make_user(username="bystander")
        group = make_group(owner=owner)
        make_membership(group=group, user=member)
        make_membership(group=group, user=bystander)

        r32_1 = bracket.match("R32-1")
        r32_2 = bracket.match("R32-2")

        # owner: USA correct + CAN incorrect (winner BRA). 1 pt.
        Prediction.objects.create(
            user=owner, group=group, match=r32_1, picked_winner=bracket.usa
        )
        Prediction.objects.create(
            user=owner, group=group, match=r32_2, picked_winner=bracket.can
        )
        # member: MEX incorrect + BRA correct. 1 pt.
        Prediction.objects.create(
            user=member, group=group, match=r32_1, picked_winner=bracket.mex
        )
        Prediction.objects.create(
            user=member, group=group, match=r32_2, picked_winner=bracket.bra
        )
        # bystander: no picks at all.

        r32_1.winner = bracket.usa
        r32_1.save()
        r32_2.winner = bracket.bra
        r32_2.save()

        return group, owner, member, bystander

    def test_correct_pick_scores_round_points(
        self, bracket, make_user, make_group, make_membership
    ):
        group, owner, member, bystander = self._setup_three_user_scenario(
            bracket, make_user, make_group, make_membership
        )
        standings = compute_group_standings(group)
        by_user = {s["user"].username: s for s in standings}
        # R32 = 1 point. Owner got R32-1 right (1pt). Member got R32-2 right (1pt).
        assert by_user["owner"]["total_points"] == 1
        assert by_user["member"]["total_points"] == 1
        assert by_user["bystander"]["total_points"] == 0

    def test_zero_pick_user_still_included(
        self, bracket, make_user, make_group, make_membership
    ):
        group, owner, member, bystander = self._setup_three_user_scenario(
            bracket, make_user, make_group, make_membership
        )
        standings = compute_group_standings(group)
        usernames = {s["user"].username for s in standings}
        assert "bystander" in usernames

    def test_sort_tiebreaker_is_username_asc(
        self, bracket, make_user, make_group, make_membership
    ):
        group, owner, member, bystander = self._setup_three_user_scenario(
            bracket, make_user, make_group, make_membership
        )
        standings = compute_group_standings(group)
        # owner and member both have 1pt; sorted by username asc → member before owner.
        # bystander has 0pt → last.
        assert [s["user"].username for s in standings] == [
            "member",
            "owner",
            "bystander",
        ]

    def test_admin_edited_scoring_rule_applied(
        self, bracket, make_user, make_group, make_membership
    ):
        group, owner, member, bystander = self._setup_three_user_scenario(
            bracket, make_user, make_group, make_membership
        )
        # Bump R32 from 1 to 7 — owner and member should each total 7.
        ScoringRule.objects.filter(round="R32").update(points=7)
        standings = compute_group_standings(group)
        by_user = {s["user"].username: s for s in standings}
        assert by_user["owner"]["total_points"] == 7
        assert by_user["member"]["total_points"] == 7

    def test_empty_group_returns_empty_list(self, bracket, make_user):
        from apps.bracket.models import Group

        owner = make_user()
        group = Group.objects.create(name="Lonely", owner=owner)
        # No membership for owner — empty group
        standings = compute_group_standings(group)
        assert standings == []


@pytest.mark.django_db
class TestBuildUserBracket:
    def test_returns_all_rounds(self, bracket, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        b = build_user_bracket(owner, group)
        round_codes = [r["round"] for r in b["rounds"]]
        assert round_codes == ["R32", "R16", "QF", "SF", "THIRD", "FINAL"]

    def test_reports_lock_state(self, bracket, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        b = build_user_bracket(owner, group)
        assert b["is_locked"] is False
        bracket.lock_now()
        b = build_user_bracket(owner, group)
        assert b["is_locked"] is True

    def test_complete_flag_requires_32_picks(self, bracket, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        b = build_user_bracket(owner, group)
        assert b["complete"] is False
        assert b["pick_count"] == 0
