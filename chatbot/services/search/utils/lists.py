def unique(values):
    return list(dict.fromkeys(value for value in values or [] if value))
