"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from typing import Optional, Union
from word2number.w2n import word_to_num
from droidlet.shared_data_structs import ErrorWithResponse
from droidlet.interpreter.condition_classes import (
    Condition,
    NeverCondition,
    AndCondition,
    OrCondition,
    TimeCondition,
)
from .comparator_helper import interpret_comparator


class ConditionInterpreter:
    def __init__(self):
        # extra layer of indirection to allow easier split into base_agent and specialized agent conditions...
        self.condition_types = {
            "NEVER": self.interpret_never,
            "AND": self.interpret_and,
            "OR": self.interpret_or,
            "TIME": self.interpret_time,
            "COMPARATOR": interpret_comparator,
        }

    def __call__(self, interpreter, speaker, d) -> Optional[Condition]:
        """subinterpreter for Conditions
        args:
        interpreter:  root interpreter.
        speaker (str): The name of the player/human/agent who uttered
            the chat resulting in this interpreter
        d: logical form from semantic parser
        """
        if not (ct := d.get("condition_type")):
            return None
        if not self.condition_types.get(ct):
            raise ErrorWithResponse("I don't understand that condition")
        # condition_type NEVER doesn't have a "condition" sibling
        if ct == "NEVER":
            return self.condition_types[ct](interpreter, speaker, d)
        if d.get("condition"):
            return self.condition_types[ct](interpreter, speaker, d["condition"])
        else:
            raise ErrorWithResponse(
                "I thought there was a condition but I don't understand it"
            )

    def interpret_never(self, interpreter, speaker, d) -> Optional[Condition]:
        return NeverCondition(interpreter.memory)

    def interpret_or(self, interpreter, speaker, d) -> Optional[Condition]:
        orlist = d["or_condition"]
        conds = []
        for c in orlist:
            if new_condition := self(interpreter, speaker, d):
                conds.append(new_condition)
        return OrCondition(interpreter.memory, conds)

    def interpret_and(self, interpreter, speaker, d) -> Optional[Condition]:
        orlist = d["and_condition"]
        conds = []
        for c in orlist:
            if new_condition := self(interpreter, speaker, d):
                conds.append(new_condition)
        return AndCondition(interpreter.memory, conds)

    def interpret_time(self, interpreter, speaker, d):
        if d.get("special_time_event"):
            return TimeCondition(interpreter.memory, d["special_time_event"])
        if not d.get("comparator"):
            raise ErrorWithResponse("I don't know how to interpret this time condition")
        dc = d["comparator"]
        dc["input_left"] = {"value_extractor": "NULL"}
        comparator = interpret_comparator(interpreter, speaker, dc)

        event = self(interpreter, speaker, d["event"]) if d.get("event") else None
        return TimeCondition(interpreter.memory, comparator, event=event)


# FIXME!!!!!
# this function needs to be torched
def get_repeat_num(d) -> Union[int, str]:
    if "repeat" in d:
        repeat_dict = d["repeat"]
        if repeat_dict["repeat_key"] == "FOR":
            try:
                return word_to_num(repeat_dict["repeat_count"])
            except:
                return 2  # TODO: dialogue instead of default?
        if repeat_dict["repeat_key"] == "ALL":
            return "ALL"
    return 1
