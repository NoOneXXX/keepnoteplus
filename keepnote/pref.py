"""

    KeepNote
    Preference data structure

"""


from keepnote import orderdict


def get_pref(pref, *args, **kargs):
    """
    Get config value from preferences

    default -- set a default value if it does not exist
    define  -- create a new dict if the key does not exist
    type    -- ensure return value has this type, otherwise return/set default
    """

    if len(args) == 0:
        return pref

    try:
        d = pref
        if "default" in kargs or "define" in kargs:
            # set default values when needed
            # define keyword causes default value to be a OrderDict()
            # all keys are expected to be present

            for arg in args[:-1]:
                if arg not in d:
                    d[arg] = orderdict.OrderDict()
                    d = d[arg]
                else:
                    c = d[arg]
                    # ensure child value c is a dict
                    if not isinstance(c, dict):
                        c = d[arg] = orderdict.OrderDict()
                    d = c
            if kargs.get("define", False):
                if args[-1] not in d:
                    d[args[-1]] = orderdict.OrderDict()
                d = d[args[-1]]
            else:
                d = d.setdefault(args[-1], kargs["default"])
        else:
            # no default or define specified
            # all keys are expected to be present
            for arg in args:
                d = d[arg]

        # check type
        if "type" in kargs and "default" in kargs:
            if not isinstance(d, kargs["type"]):
                args2 = args + (kargs["default"],)
                return set_pref(pref, *args2)
        return d

    except KeyError:
        raise Exception("unknown config value '%s'" % ".".join(args))


def set_pref(pref, *args):
    """Set config value in preferences"""
    if len(args) == 0:
        return
    elif len(args) == 1:
        pref.clear()
        pref.update(args[0])
        return args[0]
    else:
        keys = args[:-1]
        val = args[-1]
        get_pref(pref, *keys[:-1])[keys[-1]] = val
        return val


class Pref (object):
    """A general preference object"""

    def __init__(self, data=None):
        if data is None:
            self._data = orderdict.OrderDict()
        else:
            self._data = data

    def get(self, *args, **kargs):
        """
        Get config value from preferences

        default -- set a default value if it does not exist
        define  -- create a new dict if the key does not exist
        type    -- ensure return value has this type,
                   otherwise return/set default
        """
        return get_pref(self._data, *args, **kargs)

    def set(self, *args):
        """Set config value in preferences"""
        return set_pref(self._data, *args)

    def clear(self, *args):
        """Clear the config value"""
        kargs = {"define": True}
        get_pref(self._data, *args, **kargs).clear()
