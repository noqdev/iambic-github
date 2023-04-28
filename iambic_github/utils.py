from __future__ import annotations

import asyncio


async def aio_call_with_identifier(
        identifier: str, fn, return_exception: bool = False, *args, **kwargs
) -> dict[str, any]:
    if return_exception:
        try:
            res = await fn(*args, **kwargs)
        except Exception as err:
            res = err
    else:
        res = await fn(*args, **kwargs)

    return {identifier: res}


def get_dict_value(key_space: str, dictionary: dict, default_val=None):
    """
    Get the value of a key from a dictionary. Use a dot notation key to access the value of a nested dict

    Args:
        key_space (str): The key space of the key.
        dictionary (dict): The dictionary to retrieve the value from.
        default_val (any): The default value to return if the key is not found. Defaults to None.
    Returns:
        any: The value of the key.
    """
    if "." in key_space:
        split_key = key_space.split(".")
        key_space = split_key.pop(-1)
        for key in split_key:
            dictionary = dictionary.get(key, {})

    return dictionary.get(key_space, default_val)


async def handle_github_fn(fn, *args, **kwargs):
    try:
        res = await fn(*args, **kwargs)
    except asyncio.exceptions.TimeoutError:
        raise asyncio.exceptions.TimeoutError
    return res
