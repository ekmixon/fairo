"""
Copyright (c) Facebook, Inc. and its affiliates.
"""

import math

from base_log_reader import BaseLogReader


def to_discrete(pos):
    return tuple(math.floor(p) for p in pos)


class PrintLogReader(BaseLogReader):
    def on_player_spawned(self, tick, buf_start, eid, name, pos, look):
        print(f"[{tick}] Player {(eid, name)} spawned at {to_discrete(pos)}")

    def on_player_destroyed(self, tick, buf_start, eid):
        print(f"[{tick}] Player {eid} destroyed")

    def on_player_moving(self, tick, buf_start, eid, oldpos, newpos):
        oldpos = to_discrete(oldpos)
        newpos = to_discrete(newpos)
        if oldpos == newpos:
            return
        dx, dy, dz = tuple(n - o for n, o in zip(newpos, oldpos))
        assert all(
            p in (-1, 0, 1) for p in (dx, dy, dz)
        ), f"Bad (dx, dy, dz) == {(dx, dy, dz)}"

        if dx == -1:
            print(f"[{tick}] Player {eid} STEP_NEG_X")
        elif dx == 1:
            print(f"[{tick}] Player {eid} STEP_POS_X")
        if dy == -1:
            print(f"[{tick}] Player {eid} STEP_NEG_Y")
        elif dy == 1:
            print(f"[{tick}] Player {eid} STEP_POS_Y")
        if dz == -1:
            print(f"[{tick}] Player {eid} STEP_NEG_Z")
        elif dz == 1:
            print(f"[{tick}] Player {eid} STEP_POS_Z")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("logdir", help="Cuberite workdir; should contain settings.ini")
    args = parser.parse_args()

    PrintLogReader(args.logdir).start()
