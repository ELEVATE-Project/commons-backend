def load_env_to_dict(value: str | None) -> dict:
    if value is None:
        return {}
    env_dict = {}
    env_lines = value.split("\n")
    for line in env_lines:
        line = line.strip()
        # Ignore empty lines and comments
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            env_dict[key.strip()] = value.strip().strip('"').strip("'")
    return env_dict
