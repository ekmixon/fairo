"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import Pyro4
import time
import os

Pyro4.config.SERIALIZER = "pickle"
Pyro4.config.SERIALIZERS_ACCEPTED.add("pickle")


class LoCoBotMover:
    def __init__(self, ip=None):
        # self.bot = Pyro4.Proxy("PYRONAME:remotelocobot@192.168.0.124")
        self.bot = (
            Pyro4.Proxy(f"PYRONAME:remotelocobot@{ip}")
            if ip
            else Pyro4.Proxy("PYRONAME:remotelocobot@192.168.1.48")
        )

    def get_rgb_depth(self):
        print("getting rgb")
        rgb = self.bot.get_rgb()

        depth = self.bot.get_depth()

        # pts = self.bot.dip_pix_to_3dpt()
        return rgb, depth  # , pts


if __name__ == "__main__":
    IP = os.getenv("LOCOBOT_IP") or "127.0.0.1"
    lc = LoCoBotMover(ip=IP)
    for _ in range(5):
        tm = time.time()
        r, d = lc.get_rgb_depth()
        print(time.time() - tm, "seconds")
    print("RGB Shape", r.shape)
    print("Depth Shape", d.shape)
