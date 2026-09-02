"""The read-only default, the allow-list and self-protection."""

from keelson.interfaces.ErrorResponse_pb2 import ErrorResponse

from keelson_interface_docker.guard import ControlGuard

SELF_ID = "s" * 64


def test_default_is_read_only():
    assert ControlGuard().control_enabled is False


class TestReadOnly:
    guard = ControlGuard()

    def test_refuses_every_container(self):
        decision = self.guard.decide("anything", "id", "stop")
        assert not decision.allowed
        assert decision.code == ErrorResponse.Code.PERMISSION_DENIED

    def test_reason_names_the_flag_that_would_change_it(self):
        assert "--allow-control" in self.guard.decide("anything", verb="stop").reason

    def test_nothing_is_controllable(self):
        assert not self.guard.controllable("anything")


class TestAllowList:
    guard = ControlGuard(control_enabled=True, allow_globs=("keelson-*", "mcap"))

    def test_glob_match_is_allowed(self):
        assert self.guard.decide("keelson-router", verb="stop").allowed

    def test_exact_match_is_allowed(self):
        assert self.guard.decide("mcap", verb="stop").allowed

    def test_miss_is_refused_and_the_reason_lists_the_globs(self):
        decision = self.guard.decide("grafana", verb="stop")
        assert not decision.allowed
        assert "keelson-*" in decision.reason and "grafana" in decision.reason

    def test_star_means_everything(self):
        assert (
            ControlGuard(control_enabled=True, allow_globs=("*",)).decide("x", verb="stop").allowed
        )


class TestSelfProtection:
    guard = ControlGuard(
        control_enabled=True,
        # Note the glob WOULD match the responder's own name.
        allow_globs=("*",),
        self_identity=frozenset({"keelson-interface-docker", SELF_ID}),
    )

    def test_self_by_name_is_refused_even_though_the_glob_matches(self):
        decision = self.guard.decide("keelson-interface-docker", verb="stop")
        assert not decision.allowed
        assert "own container" in decision.reason

    def test_self_by_full_id_is_refused(self):
        assert not self.guard.decide("some-other-name", SELF_ID, "restart").allowed

    def test_self_by_short_id_is_refused(self):
        # Callers see the full id; --self-container-name may have resolved a short one.
        short = ControlGuard(
            control_enabled=True, allow_globs=("*",), self_identity=frozenset({SELF_ID[:12]})
        )
        assert not short.decide("other", SELF_ID, "stop").allowed

    def test_the_reason_names_the_verb_that_was_refused(self):
        assert "restart" in self.guard.decide("keelson-interface-docker", verb="restart").reason

    def test_a_different_container_is_still_allowed(self):
        assert self.guard.decide("grafana", "g" * 64, "stop").allowed

    def test_a_short_id_that_is_not_a_prefix_is_not_self(self):
        assert not self.guard.is_self("other", "b" * 64)


def test_controllable_agrees_with_decide_for_every_case():
    guard = ControlGuard(
        control_enabled=True, allow_globs=("keelson-*",), self_identity=frozenset({"keelson-self"})
    )
    for name, cid in [("keelson-router", "r"), ("grafana", "g"), ("keelson-self", "s")]:
        assert guard.controllable(name, cid) == guard.decide(name, cid).allowed
