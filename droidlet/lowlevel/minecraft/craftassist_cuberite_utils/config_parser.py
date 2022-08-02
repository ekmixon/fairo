"""
Copyright (c) Facebook, Inc. and its affiliates.

This .ini file config parser accepts multiple keys with the same name, unlike
Python's configparser.
"""
import contextlib


@contextlib.contextmanager
def inplace_edit(path):
    with open(path, "r") as f:
        config = read_config(f.readlines())
    yield config
    with open(path, "w") as f:
        write_config(f, config)


def read_config(lines):
    """Read the config into a dictionary"""
    d = {}
    current_section = None
    for line in lines:
        line = line.strip()
        if len(line) == 0 or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            d[current_section] = {}
        else:
            if "=" not in line:
                raise ValueError(f"No = in line: {line}")
            key, val = line.split("=", maxsplit=1)
            if key in d[current_section]:
                old_val = d[current_section][key]
                if type(old_val) == list:
                    old_val.append(val)
                else:
                    d[current_section][key] = [old_val, val]
            else:
                d[current_section][key] = val
    return d


def write_config(f, config):
    """Write out config into file f"""
    for section, data in config.items():
        f.write(f"[{section}]\n")
        for key, val in data.items():
            if type(val) == list:
                for v in val:
                    f.write(f"{key}={v}\n")
            else:
                f.write(f"{key}={val}\n")
        f.write("\n")
