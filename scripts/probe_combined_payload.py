#!/usr/bin/env python3
"""Live probe: does GO DAIKIN apply a COMBINED Set_OnOff+Set_Mode+Set_Fan update?

Usage:
    GODAIKIN_USER=... GODAIKIN_PASS=... \\
        .venv/bin/python scripts/probe_combined_payload.py [AC_NAME_OR_UNIQUE_ID] \\
        [--wait SECONDS] [--yes] [--reader {airconds,shadow}]

With no AC argument, lists the ACs and exits. Credentials come only from the
environment. The probe changes the real unit's state and restores it at the end.

NOTE: Output includes AC names and unique IDs (which contain the device MAC) --
redact before sharing.

Reported-state reader: the default "airconds" (get_airconds) is the same path the
integration's coordinator polls, so it shows what Home Assistant would see. Both
readers expose the cloud shadow's Set_OnOff/Set_Mode/Set_Fan; "shadow" additionally
sends an empty desired update then fetches the shadow (type 1), which may be fresher.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.godaikin.api import ApiClient  # noqa: E402
from custom_components.godaikin.auth import AuthClient  # noqa: E402
from custom_components.godaikin.types import (  # noqa: E402
    Aircond,
    AircondMode,
    FanSpeed,
)

MAX_REREADS = 3


def mode_name(v: int) -> str:
    return AircondMode(v).name if v in AircondMode._value2member_map_ else f"?{v}"


def fan_name(v: int) -> str:
    return FanSpeed(v).name if v in FanSpeed._value2member_map_ else f"?{v}"


def fmt(onoff: int, mode: int, fan: int) -> str:
    return f"{'on' if onoff else 'off'}/{mode_name(mode)}/{fan_name(fan)}"


class Probe:
    def __init__(self, api, ac: Aircond, wait: float, reader: str = "airconds"):
        self.api = api
        self.uid = ac.unique_id
        self.ac = ac
        self.wait = wait
        self.reader = reader
        self.results: list[tuple[str, str, str, bool, int]] = []

    async def read(self) -> tuple[int, int, int]:
        if self.reader == "shadow":
            s = await self.api.get_shadow_state(self.ac)
        else:
            acs = await self.api.get_airconds()
            self.ac = next(a for a in acs if a.unique_id == self.uid)
            s = self.ac.shadowState
        return s.Set_OnOff, s.Set_Mode, s.Set_Fan

    async def raw(self, **state):
        print(f"    desired payload -> {state}")
        await self.api._set_desired_state(self.uid, **state)

    async def check(self, step: str, expected: tuple[int, int, int]):
        await asyncio.sleep(self.wait)
        reported = (0, 0, 0)
        ok = False
        reads = 0
        for reads in range(1, MAX_REREADS + 2):
            reported = await self.read()
            ok = reported == expected
            if ok:
                break
            if reads <= MAX_REREADS:
                await asyncio.sleep(self.wait)
        print(
            f"    reported {fmt(*reported)} (expected {fmt(*expected)}) "
            f"-> {'PASS' if ok else 'FAIL'} [reads={reads}]"
        )
        self.results.append((step, fmt(*expected), fmt(*reported), ok, reads))

    async def run(self, target_fan: FanSpeed):
        C, F, L = AircondMode.COOL, AircondMode.FAN_ONLY, FanSpeed.LOW
        exp_cool = (1, int(C), int(target_fan))
        exp_mold = (1, int(F), int(L))

        print("\n[0] Setup: COOL + target fan")
        print(
            f"    desired payload -> Set_OnOff=1,Set_Mode={int(C)} then Set_Fan={int(target_fan)}"
        )
        await self.api.set_mode(self.uid, C)
        await self.api.set_fan_mode(self.uid, target_fan)
        await self.check("0 setup", exp_cool)

        await self.mold("1 mold-proof sim", exp_mold)

        print("\n[A] ONE request: Set_OnOff=0, Set_Mode=COOL, Set_Fan=target")
        print("    >>> Watch the unit: note whether it blows COLD air before stopping.")
        await self.raw(Set_OnOff=0, Set_Mode=int(C), Set_Fan=int(target_fan))
        await self.check("A off+mode+fan", (0, int(C), int(target_fan)))

        print("\n[A2] ONE request: Set_OnOff=1 only (was mode/fan stored while off?)")
        await self.raw(Set_OnOff=1)
        await self.check("A2 plain power-on", exp_cool)

        await self.mold("2 mold-proof sim", exp_mold)

        print("\n[B] ONE request: Set_OnOff=1, Set_Mode=COOL, Set_Fan=target")
        await self.raw(Set_OnOff=1, Set_Mode=int(C), Set_Fan=int(target_fan))
        await self.check("B on+mode+fan", exp_cool)

    async def mold(self, step: str, expected):
        print(f"\n[{step}] FAN_ONLY + LOW")
        print(
            f"    desired payload -> Set_OnOff=1,Set_Mode={int(AircondMode.FAN_ONLY)} "
            f"then Set_Fan={int(FanSpeed.LOW)}"
        )
        await self.api.set_mode(self.uid, AircondMode.FAN_ONLY)
        await self.api.set_fan_mode(self.uid, FanSpeed.LOW)
        await self.check(step, expected)

    def summary(self) -> str:
        print("\n=== Summary ===")
        print(f"{'step':<20}{'expected':<22}{'reported':<22}{'result':<7}reads")
        for step, e, r, ok, n in self.results:
            print(f"{step:<20}{e:<22}{r:<22}{'PASS' if ok else 'FAIL':<7}{n}")
        by = {s.split()[0]: ok for s, _, _, ok, _ in self.results}
        off_ok = by.get("A", False) and by.get("A2", False)
        on_ok = by.get("B", False)
        if off_ok and on_ok:
            msg = "Combined payload safe for both OFF-restore and ON-restore"
        else:
            parts = []
            if not off_ok:
                parts.append("OFF-restore (steps A/A2) FAILED")
            if not on_ok:
                parts.append("ON-restore (step B) FAILED")
            msg = "; ".join(parts)
        print(f"\nConclusion: {msg}")
        return msg


def describe(ac: Aircond) -> str:
    s = ac.shadowState
    return (
        f"{ac.ACName!r} id={ac.unique_id} "
        f"state={fmt(s.Set_OnOff, s.Set_Mode, s.Set_Fan)}"
    )


async def restore(api, uid, original: tuple[int, int, int]):
    onoff, mode, fan = original
    try:
        # Mode/fan first while on, then power, so the final state matches original.
        state = {"Set_OnOff": 1, "Set_Mode": mode, "Set_Fan": fan}
        print(f"\n[cleanup] restoring original {fmt(*original)}")
        print(f"    desired payload -> {state}")
        await api._set_desired_state(uid, **state)
        if not onoff:
            print("    desired payload -> {'Set_OnOff': 0}")
            await api._set_desired_state(uid, Set_OnOff=0)
        print(f"[cleanup] restored: {fmt(*original)}")
    except BaseException as e:  # noqa: BLE001
        print(
            f"[cleanup] FAILED to restore ({type(e).__name__}); "
            f"original was {fmt(*original)} - restore manually"
        )


async def amain(args, api=None, input_fn=input) -> int:
    own_api = api is None
    if own_api:
        user, pw = os.environ.get("GODAIKIN_USER"), os.environ.get("GODAIKIN_PASS")
        if not user or not pw:
            print(
                "Missing credentials: set GODAIKIN_USER and GODAIKIN_PASS "
                "environment variables.",
                file=sys.stderr,
            )
            return 2
        api = ApiClient(AuthClient(user, pw))
    print(
        "NOTE: Output includes AC names and unique IDs (which contain the device "
        "MAC) -- redact before sharing."
    )
    try:
        airconds = await api.get_airconds()
        if not args.ac:
            for a in airconds:
                print(describe(a))
            return 0
        key = args.ac.lower()
        match = [a for a in airconds if a.ACName.lower() == key or a.unique_id == key]
        if len(match) != 1:
            print(f"AC {args.ac!r} matched {len(match)} units; available:")
            for a in airconds:
                print("  " + describe(a))
            return 2
        ac = match[0]
        s = ac.shadowState
        original = (s.Set_OnOff, s.Set_Mode, s.Set_Fan)
        target = (
            FanSpeed.MEDIUM
            if (s.Set_Mode, s.Set_Fan) == (AircondMode.COOL, FanSpeed.HIGH)
            else FanSpeed.HIGH
        )
        print(f"Selected: {describe(ac)}")
        print(
            "Plan: 0 setup COOL+target -> 1 FAN_ONLY+LOW -> A one-shot OFF+COOL+target "
            "-> A2 plain ON -> 2 FAN_ONLY+LOW -> B one-shot ON+COOL+target -> restore "
            f"{fmt(*original)}. Target fan={fan_name(int(target))}, wait={args.wait}s."
        )
        if (
            not args.yes
            and input_fn("Type 'yes' to send commands to the real unit: ").strip()
            != "yes"
        ):
            print("Aborted; nothing sent.")
            return 1
        probe = Probe(api, ac, args.wait, args.reader)
        try:
            await probe.run(target)
        finally:
            await restore(api, ac.unique_id, original)
        msg = probe.summary()
        return 0 if msg.startswith("Combined payload safe") else 3
    finally:
        if own_api:
            await api.session.close()


def parse(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("ac", nargs="?", help="ACName (case-insensitive) or unique_id")
    p.add_argument("--wait", type=float, default=8.0, help="seconds between steps")
    p.add_argument("--yes", action="store_true", help="skip confirmation")
    p.add_argument("--reader", choices=["airconds", "shadow"], default="airconds")
    return p.parse_args(argv)


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(amain(parse())))
    except KeyboardInterrupt:
        sys.exit(130)
