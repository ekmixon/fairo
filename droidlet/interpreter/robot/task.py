"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
# put a counter and a max_count so can't get stuck?
class Task(object):
    def __init__(self, featurizer=None):
        self.interrupted = False
        self.featurizer = featurizer
        self.finished = False
        self.name = None
        self.block_memory = None
        self.undone = False
        # FIXME: remove these
        self.memid = None
        self.children = []

    def featurize(self):
        return self.featurizer(self) if self.featurizer is not None else "empty"

    def step(self):
        return

    def interrupt(self):
        self.interrupted = True

    def check_finished(self):
        if self.finished and self.block_memory is not None:
            self.block_memory.end_time = self.end_time
        return self.finished

    def __repr__(self):
        return str(type(self))
