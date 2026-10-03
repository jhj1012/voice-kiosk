from kiosk.voice.hook import HookSwitch, SimulatedHook


def test_simulated_hook_reports_changes_only():
    hook = SimulatedHook()
    seen: list[bool] = []
    hook.subscribe(seen.append)
    hook.set(True)
    hook.set(True)
    hook.set(False)
    assert seen == [True, False]
    assert not hook.off_hook


def test_simulated_hook_is_a_hook_switch():
    switch: HookSwitch = SimulatedHook()
    assert switch.off_hook is False
