"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
from droidlet.interpreter import AttributeInterpreter
from droidlet.memory.craftassist.mc_attributes import VoxelCounter


class MCAttributeInterpreter(AttributeInterpreter):
    def __call__(self, interpreter, speaker, d_attribute, get_all=False):
        if (
            type(d_attribute) is str
            or type(d_attribute) is not dict
            or not (bd := d_attribute.get("num_blocks"))
        ):
            return super().__call__(interpreter, speaker, d_attribute, get_all=get_all)
        block_data = [{"obj_text": v} for k, v in bd.get("block_filters", {}).items()]
        return VoxelCounter(block_data)
