from typing import List, Dict, Union


def credential_check(credentials: List[Dict[str, str]]) -> None:
    # Check if the input is a list
    if not isinstance(credentials, list):
        raise TypeError("Expected a list of dictionaries.")

    # Ensure each item in the list is a dictionary and has all necessary keys
    required_keys = ('username', 'password', 'host', 'db')
    for idx, credential in enumerate(credentials):
        if not isinstance(credential, dict):
            raise TypeError(f"Item at index {idx} is not a dictionary.")

        missing_keys = [key for key in required_keys if key not in credential]
        if missing_keys:
            raise ValueError(
                f"Item at index {idx} is missing required keys: {', '.join(missing_keys)}")

        # Optionally, you could add further checks for value types or validity here
        for key in required_keys:
            if not isinstance(credential[key], str) or not credential[key]:
                raise ValueError(
                    f"Item at index {idx} has invalid value for '{key}'.")
